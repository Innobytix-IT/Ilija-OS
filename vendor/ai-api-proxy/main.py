"""
OpenAI-kompatibler Proxy mit nativer Agenten-Tokenoptimierung und Streaming.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import os

from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from google.genai import types as gt

from config import Settings, get_settings
from models import OpenAIChatRequest, OpenAIMessage
from providers.api import GeminiAPIProvider
from router import Router, RouterResponse


app = FastAPI(
    title="Gemini Proxy (Agent Ready)",
    description="OpenAI-kompatibler Proxy mit History-Pruning und Quota-Fallback",
    version="2.1.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def normalize_api_path(request: Request, call_next):
    """
    Toleriert alle gängigen OpenAI-Base-URL-Formate der Clients:

      http://host:port         + Client hängt /v1/chat/completions an → OK
      http://host:port/v1      + Client hängt /chat/completions an     → OK
      http://host:port         + Client hängt /chat/completions an     → fix (fehlendes /v1)
      http://host:port/v1      + Client hängt /v1/chat/completions an  → fix (doppeltes /v1)

    So kann der User die Launcher-URL in jeden Client eintragen, egal ob
    der Client den /v1-Präfix selbst dranhängt oder in der Base-URL erwartet.
    """
    path = request.url.path
    original = path

    # Doppeltes (oder mehrfaches) /v1-Präfix kollabieren
    while path.startswith("/v1/v1/"):
        path = path[3:]  # entfernt ein führendes /v1

    # /v1-Präfix hinzufügen wenn Client den OpenAI-Pfad ohne Präfix sendet
    if path == "/models" or path.startswith("/chat/completions"):
        path = "/v1" + path

    if path != original:
        request.scope["path"] = path

    return await call_next(request)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme  = HTTPBearer(auto_error=False)

_router: Router | None = None
_router_lock = asyncio.Lock()


def _build_router(settings: Settings) -> Router:
    api = None
    if settings.gemini_api_key:
        api = GeminiAPIProvider(settings.gemini_api_key, settings.exclude_terms())
        try:
            api.refresh_models()
            print(f"[api] {len(api.models)} Modelle geladen: " + ", ".join(m.name for m in api.models))
        except Exception as e:
            print(f"[api] models.list() fehlgeschlagen: {e}")
    return Router(api)


async def get_router() -> Router:
    global _router
    if _router is None:
        async with _router_lock:
            if _router is None:
                _router = _build_router(get_settings())
    return _router


def verify_api_key(
    api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    if settings.api_secret in ("", "change-me", "change-me-to-a-random-string"):
        return "open"
    provided = api_key or (bearer.credentials if bearer else None)
    if not provided or provided != settings.api_secret:
        raise HTTPException(401, "Ungültiger API-Secret Key")
    return provided


# ── Agent History & Token Pruning ────────────────────────────────────────

def _extract_content(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
        return " ".join(parts)
    return str(content)


def _prune_agent_messages(messages: list[OpenAIMessage], settings: Settings) -> list[OpenAIMessage]:
    """
    Head-and-Tail Pruning:
    Erhält Turn 1 (Hauptziel des Agenten) und die letzten N Runden unversehrt.
    Dazwischenliegende Tool-Ergebnisse / Scratchpads werden gekürzt.
    """
    if not settings.enable_agent_pruning:
        return messages

    chat = [m for m in messages if m.role != "system"]
    if len(chat) <= settings.prune_keep_recent + 2:
        return messages

    first_turn = chat[0]
    middle_turns = chat[1 : -settings.prune_keep_recent]
    recent_turns = chat[-settings.prune_keep_recent :]

    pruned_middle: list[OpenAIMessage] = []
    for m in middle_turns:
        text = _extract_content(m.content)
        if len(text) > settings.prune_max_middle_chars:
            text = (
                text[: settings.prune_max_middle_chars]
                + f"\n[... {len(text) - settings.prune_max_middle_chars} Zeichen Zwischenausgabe vom Proxy komprimiert ...]"
            )
        pruned_middle.append(OpenAIMessage(role=m.role, content=text, name=m.name))

    system_msgs = [m for m in messages if m.role == "system"]
    return system_msgs + [first_turn] + pruned_middle + recent_turns


def _build_gemini_payload(
    messages: list[OpenAIMessage],
    settings: Settings,
) -> tuple[list[gt.Content], str | None]:
    """
    Wandelt OpenAI-Messages in native Gemini Content-Objekte um.
    - Extrahiert System-Prompts.
    - Mergt aufeinanderfolgende Turns derselben Rolle.
    - Sichert leere Parts und die First-Turn-User-Regel ab.
    """
    pruned = _prune_agent_messages(messages, settings)

    system_parts = [
        _extract_content(m.content)
        for m in pruned
        if m.role == "system"
    ]
    system_instruction = "\n\n".join(filter(None, system_parts)) or None

    contents: list[gt.Content] = []
    current_role: str | None = None
    accumulated_texts: list[str] = []

    for m in pruned:
        if m.role == "system":
            continue

        gemini_role = "model" if m.role in ("assistant", "model") else "user"
        text = _extract_content(m.content).strip()

        if m.role in ("tool", "function"):
            text = f"[Tool-Output ({m.name or 'unknown'})]: {text or '(ohne Rückgabe)'}"
        elif not text:
            text = "[Ausführung eines Zwischenschritts]" if gemini_role == "model" else "[Weiter]"

        if gemini_role == current_role:
            accumulated_texts.append(text)
        else:
            if current_role and accumulated_texts:
                combined = "\n\n".join(filter(None, accumulated_texts))
                if combined:
                    contents.append(gt.Content(
                        role=current_role,
                        parts=[gt.Part.from_text(text=combined)]
                    ))
            current_role = gemini_role
            accumulated_texts = [text]

    if current_role and accumulated_texts:
        combined = "\n\n".join(filter(None, accumulated_texts))
        if combined:
            contents.append(gt.Content(
                role=current_role,
                parts=[gt.Part.from_text(text=combined)]
            ))

    # Gemini-Regel: Contents darf nicht leer sein
    if not contents:
        contents.append(gt.Content(role="user", parts=[gt.Part.from_text(text="Start")]))

    # Gemini-Regel: Die erste Nachricht MUSS die Rolle 'user' haben
    if contents[0].role != "user":
        contents.insert(0, gt.Content(role="user", parts=[gt.Part.from_text(text="Beginne die Aufgabe.")]))

    return contents, system_instruction


# ── Streaming Helper ─────────────────────────────────────────────────────

async def _sse_streamer(model: str, stream_iter: AsyncIterator[str]) -> AsyncIterator[str]:
    cid = f"chatcmpl-{int(time.time())}"
    async for chunk in stream_iter:
        data = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(data)}\n\n"

    final = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


# ── Endpunkte ────────────────────────────────────────────────────────────

@app.get("/health")
async def health(router: Router = Depends(get_router)):
    return {
        "status": "ok",
        "version": "2.1.1",
        "api_active": bool(router.api and router.api.models),
        "api_models": [m.name for m in (router.api.models if router.api else [])],
    }


@app.get("/v1/models")
async def list_models(
    router: Router = Depends(get_router),
    _: str = Depends(verify_api_key),
):
    data = [{"id": "auto", "object": "model", "owned_by": "proxy", "created": 0}]
    if router.api:
        for m in router.api.models:
            data.append({"id": m.name, "object": "model", "owned_by": "google", "created": 0})
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: OpenAIChatRequest,
    settings: Settings = Depends(get_settings),
    router: Router = Depends(get_router),
    _: str = Depends(verify_api_key),
):
    if not request.messages:
        raise HTTPException(400, "Keine Nachrichten vorhanden.")

    contents, system = _build_gemini_payload(request.messages, settings)
    preferred = request.model or settings.default_model

    if request.stream:
        try:
            used_model, gen = await router.generate_stream(
                contents, system, preferred, request.temperature, request.max_tokens
            )
            return StreamingResponse(_sse_streamer(used_model, gen), media_type="text/event-stream")
        except RuntimeError as e:
            raise HTTPException(502, str(e))

    try:
        res: RouterResponse = await router.generate(
            contents, system, preferred, request.temperature, request.max_tokens
        )
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": res.used_model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": res.text},
            "finish_reason": "stop",
        }],
        "usage": res.usage,
        "x_proxy_attempts": res.attempts,
    }


# ── Web-Config-UI ────────────────────────────────────────────────────────
# Browser-basierte Konfiguration – oeffnet sich als Popup aus Ilija OS.
# Ersetzt den fruehen Tkinter-Launcher; funktioniert lokal und remote.

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_SCRIPT_DIR, ".env")


def _read_env_file() -> dict:
    data: dict[str, str] = {}
    if not os.path.exists(_ENV_FILE):
        return data
    try:
        with open(_ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                data[k.strip()] = v.strip()
    except OSError:
        pass
    return data


def _write_env_file(updates: dict) -> bool:
    try:
        current = _read_env_file()
        current.update({k: str(v) for k, v in updates.items() if v is not None})
        tmp = _ENV_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for k, v in current.items():
                f.write(f"{k}={v}\n")
        os.replace(tmp, _ENV_FILE)
        return True
    except OSError:
        return False


class ConfigPayload(BaseModel):
    gemini_api_key: str | None = None
    port: int | None = None


@app.get("/api/config/status")
async def config_status():
    env = _read_env_file()
    has_key = bool(env.get("gemini_api_key"))
    router = await get_router()
    models = []
    if router.api:
        try:
            models = [m.name for m in router.api.models]
        except Exception:
            pass
    return {
        "configured":   has_key,
        "port":         int(env.get("port", 8642)),
        "api_active":   bool(router.api and router.api.models),
        "models_count": len(models),
        "models":       models[:5],  # Top 5 reichen fuer Anzeige
    }


@app.post("/api/config/save")
async def config_save(payload: ConfigPayload):
    global _router
    updates = {}
    if payload.gemini_api_key:
        updates["gemini_api_key"] = payload.gemini_api_key.strip()
    if payload.port:
        updates["port"] = str(int(payload.port))
    if not updates:
        raise HTTPException(400, "Keine Aenderungen uebergeben")
    if not _write_env_file(updates):
        raise HTTPException(500, "Konnte .env nicht schreiben")
    # Settings-Cache leeren damit die naechste Anfrage den neuen Key sieht
    get_settings.cache_clear()
    # Router neu bauen damit Model-Discovery sofort passiert
    async with _router_lock:
        _router = _build_router(get_settings())
    env = _read_env_file()
    router = await get_router()
    return {
        "ok":         True,
        "configured": bool(env.get("gemini_api_key")),
        "api_active": bool(router.api and router.api.models),
        "models":     [m.name for m in (router.api.models if router.api else [])][:5],
    }


@app.get("/", response_class=HTMLResponse)
async def config_page():
    return """<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gemini API-Proxy</title>
<style>
  :root { color-scheme: dark;
    --bg:#0f172a; --card:#1e293b; --fg:#e2e8f0; --muted:#94a3b8;
    --accent:#e6a22e; --accent-h:#d49826; --teal:#2dd4bf; --danger:#ef4444;
    --border:rgba(148,163,184,.2); --input:#0b1222; }
  body { font-family: system-ui,-apple-system,sans-serif; background: var(--bg); color: var(--fg);
    margin:0; display:flex; align-items:center; justify-content:center; min-height:100vh; padding:20px; }
  .card { max-width:460px; width:100%; background:var(--card); border:1px solid var(--border);
    border-radius:14px; padding:32px 28px; box-shadow:0 20px 60px rgba(0,0,0,.4); }
  h1 { margin:0 0 8px; font-size:1.3rem; font-weight:700; }
  .sub { color:var(--muted); font-size:.82rem; margin-bottom:24px; }
  label { display:block; font-size:.78rem; font-weight:600; margin:14px 0 6px; color:var(--fg); }
  input { width:100%; box-sizing:border-box; padding:10px 12px; border-radius:6px;
    border:1px solid var(--border); background:var(--input); color:var(--fg);
    font-family:ui-monospace,monospace; font-size:.88rem; }
  input:focus { outline:none; border-color:var(--accent); }
  .row { display:grid; grid-template-columns:1fr 100px; gap:10px; }
  .hint { font-size:.72rem; color:var(--muted); margin-top:4px; }
  .hint a { color:var(--teal); text-decoration:none; }
  .btn { display:inline-flex; align-items:center; justify-content:center; gap:6px;
    padding:10px 18px; border-radius:6px; border:none; cursor:pointer;
    font-size:.85rem; font-weight:600; transition:background .15s; }
  .btn-prim { background:var(--accent); color:#1a1a1a; }
  .btn-prim:hover { background:var(--accent-h); }
  .status { margin-top:20px; padding:12px 14px; border-radius:8px; font-size:.82rem;
    display:flex; align-items:center; gap:10px; }
  .status.ok { background:rgba(45,212,191,.1); color:var(--teal); border:1px solid rgba(45,212,191,.3); }
  .status.warn { background:rgba(230,162,46,.1); color:var(--accent); border:1px solid rgba(230,162,46,.3); }
  .dot { width:8px; height:8px; border-radius:50%; }
  .dot.ok { background:var(--teal); }
  .dot.warn { background:var(--accent); }
  .models { margin-top:14px; font-size:.72rem; color:var(--muted); line-height:1.6; }
  .models code { font-family:ui-monospace,monospace; background:var(--input); padding:1px 5px; border-radius:3px; }
  .endpoints { margin-top:18px; padding-top:16px; border-top:1px solid var(--border); }
  .endpoint { display:flex; align-items:center; gap:8px; margin:6px 0; font-size:.74rem; }
  .endpoint-label { color:var(--muted); min-width:48px; }
  .endpoint code { flex:1; padding:4px 8px; background:var(--input); border-radius:4px;
    font-family:ui-monospace,monospace; }
  .copy { font-size:.68rem; padding:3px 10px; cursor:pointer; }
  .toast { position:fixed; bottom:20px; right:20px; padding:10px 16px; background:var(--teal);
    color:#0f172a; border-radius:6px; font-size:.82rem; font-weight:600;
    opacity:0; transition:opacity .3s; pointer-events:none; }
  .toast.show { opacity:1; }
</style>
</head><body>
<div class="card">
  <h1>🚀 Gemini API-Proxy</h1>
  <div class="sub">OpenAI-kompatibler Proxy mit Modell-Rotation bei Rate-Limits</div>

  <label>Gemini API-Key</label>
  <input type="password" id="k" placeholder="AIzaSy…" autocomplete="off">
  <div class="hint">Hole dir einen kostenlosen Key auf <a href="https://aistudio.google.com/apikey" target="_blank">aistudio.google.com/apikey</a></div>

  <label>Port</label>
  <div class="row">
    <input type="number" id="p" value="8642" min="1024" max="65535">
    <button class="btn btn-prim" onclick="save()">Speichern</button>
  </div>

  <div id="status" class="status warn"><span class="dot warn"></span><span id="statusTxt">lädt…</span></div>
  <div id="models" class="models" style="display:none"></div>

  <div class="endpoints" id="endpoints" style="display:none">
    <div class="endpoint">
      <span class="endpoint-label">Base</span>
      <code id="urlBase">—</code>
      <button class="btn btn-prim copy" onclick="copy('urlBase')">Kopieren</button>
    </div>
    <div class="endpoint">
      <span class="endpoint-label">/v1</span>
      <code id="urlV1">—</code>
      <button class="btn btn-prim copy" onclick="copy('urlV1')">Kopieren</button>
    </div>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
async function load() {
  try {
    const r = await fetch('/api/config/status');
    const d = await r.json();
    const dot = document.querySelector('.dot');
    const txt = document.getElementById('statusTxt');
    const box = document.getElementById('status');
    if (d.api_active) {
      box.className = 'status ok'; dot.className = 'dot ok';
      txt.textContent = `✓ Aktiv – ${d.models_count} Modelle verfügbar`;
      document.getElementById('models').style.display = 'block';
      document.getElementById('models').innerHTML = 'Erkannte Modelle: ' +
        d.models.map(m => '<code>' + m + '</code>').join(' ');
    } else if (d.configured) {
      box.className = 'status warn'; dot.className = 'dot warn';
      txt.textContent = 'Konfiguriert, aber Model-Discovery fehlgeschlagen – Key prüfen';
    } else {
      box.className = 'status warn'; dot.className = 'dot warn';
      txt.textContent = 'Noch nicht konfiguriert – Key eintragen und speichern';
    }
    document.getElementById('p').value = d.port;
    // Endpunkte zeigen falls aktiv
    if (d.api_active) {
      document.getElementById('endpoints').style.display = 'block';
      const host = location.hostname;
      document.getElementById('urlBase').textContent = `http://${host}:${d.port}`;
      document.getElementById('urlV1').textContent = `http://${host}:${d.port}/v1`;
    }
  } catch(e) { toast('Fehler: ' + e.message); }
}

async function save() {
  const k = document.getElementById('k').value.trim();
  const p = parseInt(document.getElementById('p').value) || 8642;
  if (!k) { toast('Bitte API-Key eintragen'); return; }
  try {
    const r = await fetch('/api/config/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({gemini_api_key: k, port: p})
    });
    const d = await r.json();
    if (d.ok) {
      toast(d.api_active ? `✓ Gespeichert – ${d.models.length} Modelle` : 'Gespeichert');
      document.getElementById('k').value = '';
      load();
    } else {
      toast('Fehler beim Speichern');
    }
  } catch(e) { toast('Fehler: ' + e.message); }
}

function copy(id) {
  const t = document.getElementById(id).textContent;
  navigator.clipboard?.writeText(t).then(() => toast('In Zwischenablage'));
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

load();
</script>
</body></html>"""


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=False)