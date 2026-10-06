"""
OpenAI-kompatibler Proxy mit nativer Agenten-Tokenoptimierung und Streaming.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
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


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=False)