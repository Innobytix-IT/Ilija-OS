"""
agent_core.py – Provider-agnostischer Coding-Agent für Ilija (Ilija OS)
======================================================================
Ein Agenten-Loop mit DATEI-Werkzeugen (lesen/schreiben/ändern/suchen), der über
Ilijas bestehendes `provider.chat()`-Interface läuft und damit mit JEDEM
KI-Provider funktioniert (Gemini, Claude, OpenAI, Ollama …).

Kein natives Function-Calling nötig: der Agent nutzt ein striktes Text-Protokoll
(ein JSON-Block zwischen <<<TOOL … TOOL>>>), genau wie Ilijas SKILL:-Konvention –
so ist er inhärent provider-unabhängig.

SICHERHEIT (Checkpoint 1): Es gibt BEWUSST KEINE Shell-Ausführung. Alle Werkzeuge
sind reine Dateioperationen, hart auf einen Arbeitsordner (Workspace) eingegrenzt
(kein Ausbruch per ../). Die Ausführung beliebiger Befehle (run_shell) ist ein
separater Schritt, der ausdrücklich vom Nutzer freigeschaltet werden muss.

Die Permission-Modi (Plan / Manuell / Auto / acceptEdits / Bypass) entsprechen
dem Menü aus der Claude-App und steuern hier, ob Datei-Änderungen erlaubt sind.
"""

import os
import re
import json
import time
import uuid
import threading
import subprocess

from providers import select_provider

# ── Workspace (Sandbox) ───────────────────────────────────────────────────────
DEFAULT_WORKSPACE           = "/srv/ilija-ablage/Coding"
DEFAULT_WORKSPACE_COWORKING = "/srv/ilija-ablage/Coworking"
_MAX_STEPS        = 14
_MAX_READ_BYTES   = 60_000
_SHELL_TIMEOUT    = 60
_SHELL_MAX_OUT    = 12_000
# Datei-Flag: existiert = Shell-Ausführung eingeschaltet (bewusst vom Nutzer)
_SHELL_FLAG       = os.path.join("data", "agent", "shell_enabled")
# Immer verbotene Shell-Muster (außer im Bypass-Modus): destruktiv / gefährlich
_SHELL_DENY = [
    r"\brm\s+-rf?\s+(/|~|\$HOME|/\*)", r"\bmkfs\b", r"\bdd\s+if=", r"of=/dev/",
    r">\s*/dev/sd", r":\(\)\s*\{", r"\bshutdown\b", r"\breboot\b", r"\bhalt\b",
    r"\bpoweroff\b", r"\binit\s+[06]\b", r"\bchown\s+-R\b\s+/",
    r"\bchmod\s+-R\s+777\s+/", r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh",
    r"\bwget\b[^|]*\|\s*(sudo\s+)?(ba)?sh", r"\bsudo\b",
]

# ── Permission-Modi → Richtlinie ──────────────────────────────────────────────
# read = list_dir/read_file/search ; edit = write_file/edit_file ; shell = run_shell
_MODE_POLICY = {
    "plan":        {"read": True, "edit": False, "shell": False, "deny": True},
    "manuell":     {"read": True, "edit": "ask", "shell": "ask", "deny": True},
    "auto":        {"read": True, "edit": True,  "shell": True,  "deny": True},
    "acceptEdits": {"read": True, "edit": True,  "shell": False, "deny": True},
    "bypass":      {"read": True, "edit": True,  "shell": True,  "deny": False},
}
_MODE_LABEL = {
    "plan": "Plan (nur lesen, erstellt einen Plan)",
    "manuell": "Manuell (fragt vor Änderungen)",
    "auto": "Auto (führt Datei-Änderungen selbst aus)",
    "acceptEdits": "Bearbeitungen automatisch akzeptieren",
    "bypass": "Berechtigungen umgehen (alle Datei-Änderungen erlaubt)",
}
_READ_TOOLS = {"list_dir", "read_file", "search"}
_EDIT_TOOLS = {"write_file", "edit_file"}
_SHELL_TOOLS = {"run_shell"}


def shell_enabled() -> bool:
    """True, wenn der Nutzer die Shell-Ausführung bewusst eingeschaltet hat."""
    return os.path.exists(_SHELL_FLAG)


def set_shell_enabled(on: bool) -> bool:
    os.makedirs(os.path.dirname(_SHELL_FLAG) or ".", exist_ok=True)
    if on:
        with open(_SHELL_FLAG, "w") as f:
            f.write("on")
    else:
        try:
            os.remove(_SHELL_FLAG)
        except FileNotFoundError:
            pass
    return shell_enabled()


# ── Workspace-Helfer ──────────────────────────────────────────────────────────
_DATA_AGENT_DIR = os.path.join("data", "agent")
_WS_STORE       = os.path.join(_DATA_AGENT_DIR, "workspace.txt")          # Legacy
_WS_STORES      = {
    "coding":    os.path.join(_DATA_AGENT_DIR, "workspace_coding.txt"),
    "coworking": os.path.join(_DATA_AGENT_DIR, "workspace_coworking.txt"),
}
_WS_DEFAULTS = {
    "coding":    DEFAULT_WORKSPACE,
    "coworking": DEFAULT_WORKSPACE_COWORKING,
}
# Systemordner, die NICHT als Arbeitsordner erlaubt sind
_REFUSED_ROOTS = {"/", "/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc",
                  "/sys", "/lib", "/lib64", "/root", "/var", "/opt", "/run"}


def _read_stored_ws(mode: str = "coding") -> str | None:
    store = _WS_STORES.get(mode, _WS_STORES["coding"])
    try:
        with open(store, encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        pass
    # Migration: altes workspace.txt nur für coding lesen
    if mode == "coding":
        try:
            with open(_WS_STORE, encoding="utf-8") as f:
                return f.read().strip() or None
        except Exception:
            pass
    return None


def _workspace(mode: str = "coding") -> str:
    ws = (_read_stored_ws(mode)
          or (os.environ.get("ILIJA_CODING_WORKSPACE") if mode == "coding" else None)
          or _WS_DEFAULTS.get(mode, DEFAULT_WORKSPACE))
    ws = os.path.abspath(os.path.expanduser(ws))
    os.makedirs(ws, exist_ok=True)
    return ws


def set_workspace(path: str, mode: str = "coding") -> str:
    """Setzt den Arbeitsordner für den angegebenen Modus und merkt ihn dauerhaft."""
    if not path or not path.strip():
        raise ValueError("Kein Pfad angegeben.")
    p = os.path.abspath(os.path.expanduser(path.strip()))
    if p in _REFUSED_ROOTS:
        raise ValueError(f"Systemordner ist als Arbeitsordner nicht erlaubt: {p}")
    if os.path.exists(p) and not os.path.isdir(p):
        raise ValueError(f"Pfad ist eine Datei, kein Ordner: {p}")
    os.makedirs(p, exist_ok=True)
    store = _WS_STORES.get(mode, _WS_STORES["coding"])
    os.makedirs(os.path.dirname(store) or ".", exist_ok=True)
    with open(store, "w", encoding="utf-8") as f:
        f.write(p)
    return p


def _safe_path(rel: str) -> str:
    """Löst rel gegen den Workspace auf und verhindert Ausbruch (path traversal)."""
    ws = os.path.realpath(_workspace())
    full = os.path.realpath(os.path.join(ws, rel or "."))
    if full != ws and not full.startswith(ws + os.sep):
        raise ValueError(f"Pfad außerhalb des Arbeitsordners nicht erlaubt: {rel}")
    return full


# ── Werkzeuge (nur Dateien – KEINE Shell) ─────────────────────────────────────
def _t_list_dir(path="."):
    full = _safe_path(path)
    if not os.path.isdir(full):
        return f"(kein Verzeichnis: {path})"
    eintraege = []
    for name in sorted(os.listdir(full)):
        p = os.path.join(full, name)
        eintraege.append(f"{'[dir]' if os.path.isdir(p) else '     '} {name}")
    return "\n".join(eintraege) or "(leer)"


def _t_read_file(path):
    full = _safe_path(path)
    if not os.path.isfile(full):
        return f"(Datei nicht gefunden: {path})"
    with open(full, "rb") as f:
        data = f.read(_MAX_READ_BYTES + 1)
    txt = data[:_MAX_READ_BYTES].decode("utf-8", "replace")
    if len(data) > _MAX_READ_BYTES:
        txt += f"\n… (abgeschnitten bei {_MAX_READ_BYTES} Bytes)"
    lines = txt.split("\n")
    return "\n".join(f"{i+1:>4}  {l}" for i, l in enumerate(lines))


def _t_write_file(path, content=""):
    full = _safe_path(path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return f"✓ geschrieben: {path} ({len(content)} Zeichen)"


def _t_edit_file(path, old="", new=""):
    full = _safe_path(path)
    if not os.path.isfile(full):
        return f"(Datei nicht gefunden: {path})"
    src = open(full, encoding="utf-8").read()
    if old == "":
        return "(edit_file braucht 'old' – den exakt zu ersetzenden Text)"
    n = src.count(old)
    if n == 0:
        return "(Text 'old' nicht gefunden – exakt kopieren, inkl. Einrückung)"
    if n > 1:
        return f"(Text 'old' kommt {n}× vor – mehr Kontext angeben, muss eindeutig sein)"
    open(full, "w", encoding="utf-8").write(src.replace(old, new, 1))
    return f"✓ bearbeitet: {path}"


def _t_search(query, path="."):
    base = _safe_path(path)
    treffer = []
    for root, _dirs, files in os.walk(base):
        if os.sep + ".git" in root or os.sep + "node_modules" in root:
            continue
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                for i, line in enumerate(open(fp, encoding="utf-8", errors="ignore"), 1):
                    if query in line:
                        rel = os.path.relpath(fp, _workspace())
                        treffer.append(f"{rel}:{i}: {line.strip()[:160]}")
                        if len(treffer) >= 60:
                            return "\n".join(treffer) + "\n… (mehr Treffer)"
            except Exception:
                pass
    return "\n".join(treffer) or f"(keine Treffer für '{query}')"


def _t_run_shell(command="", deny=True):
    if not command or not command.strip():
        return "(kein Befehl)"
    if deny:
        for pat in _SHELL_DENY:
            if re.search(pat, command, re.IGNORECASE):
                return f"⛔ Blockiert (Sicherheits-Denyliste): {command}"
    try:
        r = subprocess.run(command, shell=True, cwd=_workspace(),
                           capture_output=True, text=True, timeout=_SHELL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"(Timeout nach {_SHELL_TIMEOUT}s)"
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
    if len(out) > _SHELL_MAX_OUT:
        out = out[:_SHELL_MAX_OUT] + "\n… (Ausgabe abgeschnitten)"
    return f"[exit {r.returncode}]\n{out.strip() or '(keine Ausgabe)'}"


_TOOLS = {
    "list_dir":   _t_list_dir,
    "read_file":  _t_read_file,
    "write_file": _t_write_file,
    "edit_file":  _t_edit_file,
    "search":     _t_search,
    "run_shell":  _t_run_shell,
}

_TOOL_SPEC = """VERFÜGBARE WERKZEUGE (rufe immer HÖCHSTENS EINS pro Antwort auf):
- list_dir(path=".")          Verzeichnis auflisten
- read_file(path)             Datei lesen (mit Zeilennummern)
- write_file(path, content)   Datei anlegen/überschreiben
- edit_file(path, old, new)   genau EIN Vorkommen von 'old' durch 'new' ersetzen
- search(query, path=".")     Text im Projekt suchen"""


# ── System-Prompt (Coding-Persona) ────────────────────────────────────────────
def _system_prompt(mode: str) -> str:
    pol = _MODE_POLICY.get(mode, _MODE_POLICY["plan"])
    edit_txt = {True: "JA", False: "NEIN", "ask": "nur nach Freigabe"}[pol["edit"]]
    sh_on = shell_enabled()
    if sh_on:
        tool_spec = _TOOL_SPEC + "\n- run_shell(command)        Shell-Befehl im Arbeitsordner ausführen"
        shell_txt = {True: "JA", False: "NEIN", "ask": "nur nach Freigabe"}[pol["shell"]]
    else:
        tool_spec = _TOOL_SPEC + "\n(Hinweis: Shell-Ausführung ist derzeit AUSGESCHALTET.)"
        shell_txt = "nicht verfügbar (ausgeschaltet)"
    plan_hinweis = ""
    if mode == "plan":
        plan_hinweis = ("\nDu bist im PLAN-Modus: Du darfst NUR lesen/suchen. Erkunde das "
                        "Projekt und liefere am Ende einen klaren, nummerierten Umsetzungsplan "
                        "– führe KEINE Änderungen aus.")
    return f"""Du bist Ilija Coding – ein Programmier-Agent, der direkt auf dem \
Computer des Nutzers (Ilija OS) in einem Arbeitsordner mit Dateien arbeitet.

Arbeitsordner: {_workspace()}
Aktueller Modus: {_MODE_LABEL.get(mode, mode)}
Berechtigungen:
  - Lesen/Suchen: JA
  - Dateien ändern (write_file/edit_file): {edit_txt}
  - Shell ausführen (run_shell): {shell_txt}{plan_hinweis}

{tool_spec}

WERKZEUG-PROTOKOLL (streng einhalten):
- Um ein Werkzeug zu benutzen, gib GENAU einen Block aus – sonst nichts danach:
<<<TOOL
{{"name": "<werkzeug>", "args": {{ ... }} }}
TOOL>>>
- Der Block muss EIN gültiges JSON-Objekt enthalten. Bei write_file kommt der
  komplette Dateiinhalt als JSON-String in "content" (korrekt escaped).
- Nach jedem Werkzeug bekommst du das Ergebnis und machst weiter.
- Wenn die Aufgabe erledigt ist (oder im Plan-Modus der Plan fertig ist), gib
  KEINEN TOOL-Block mehr aus, sondern eine kurze, klare Abschluss-Antwort auf Deutsch.
- Bei einer REINEN FRAGE, die keine Datei-Änderung braucht (z. B. „wo liegt die
  Datei?", „was hast du gemacht?"), antworte DIREKT ohne Werkzeug. Dateien liegen
  im Arbeitsordner oben.

Arbeite zielstrebig in kleinen Schritten. Erkläre kurz, was du tust."""


# ── Tool-Aufruf aus der Modell-Antwort parsen ─────────────────────────────────
_TOOL_RE = re.compile(r"<<<TOOL\s*(.+?)\s*TOOL>>>", re.DOTALL)


def _parse_tool(text: str):
    """Gibt (text_davor, tool_dict|None, fehler|None) zurück."""
    m = _TOOL_RE.search(text)
    if not m:
        return text.strip(), None, None
    davor = text[:m.start()].strip()
    roh = m.group(1).strip()
    roh = re.sub(r"^```[a-zA-Z]*\s*", "", roh)
    roh = re.sub(r"\s*```$", "", roh).strip()
    try:
        obj = json.loads(roh)
        if not isinstance(obj, dict) or "name" not in obj:
            return davor, None, "TOOL-Block ist kein Objekt mit 'name'."
        obj.setdefault("args", {})
        return davor, obj, None
    except Exception as e:
        return davor, None, f"TOOL-Block ist kein gültiges JSON: {e}"


def _permission(mode: str, tool: str):
    """→ (erlaubt: bool|'ask', grund: str)"""
    pol = _MODE_POLICY.get(mode, _MODE_POLICY["plan"])
    if tool in _READ_TOOLS:
        return True, ""
    if tool in _EDIT_TOOLS:
        v = pol["edit"]
        if v is True:
            return True, ""
        if v == "ask":
            return "ask", ""
        return False, ("Im Plan-Modus sind keine Änderungen erlaubt."
                       if mode == "plan" else
                       "In diesem Modus sind keine Datei-Änderungen erlaubt.")
    if tool in _SHELL_TOOLS:
        if not shell_enabled():
            return False, "Shell-Ausführung ist ausgeschaltet (in den Einstellungen aktivieren)."
        v = pol["shell"]
        if v is True:
            return True, ""
        if v == "ask":
            return "ask", ""
        return False, ("Shell ist in diesem Modus nicht erlaubt "
                       "(nutze Auto/Bypass, oder Manuell mit Freigabe).")
    return False, f"Unbekanntes Werkzeug: {tool}"


# ── Verlauf (PRO Sitzung/Fenster isoliert – kein Übersprechen) ────────────────
_HISTORIES = {}
_LOCK = threading.Lock()


def clear_history(sid: str = "default"):
    with _LOCK:
        _HISTORIES.pop(sid or "default", None)
        _COWORK_HISTORIES.pop(sid or "default", None)
    return "Verlauf gelöscht."


def workspace_info(mode: str = "coding"):
    return {"workspace": _workspace(mode)}


def save_upload(filename: str, data: bytes) -> str:
    """Speichert eine hochgeladene Datei sicher im Arbeitsordner (nur Basisname)."""
    safe = os.path.basename(filename or "").strip() or "datei"
    full = _safe_path(safe)
    with open(full, "wb") as f:
        f.write(data)
    return safe


# ── Agenten-Loop ──────────────────────────────────────────────────────────────
def run_coding(user_msg: str, mode: str = "plan", provider_mode: str = "auto",
               sid: str = "default") -> dict:
    """Führt eine Coding-Anfrage aus und gibt {steps, answer, provider, mode} zurück."""
    if mode not in _MODE_POLICY:
        mode = "plan"
    try:
        prov_name, provider = select_provider(provider_mode)
    except Exception as e:
        return {"steps": [], "answer": f"❌ Kein KI-Provider verfügbar: {e}",
                "provider": None, "mode": mode}

    system = _system_prompt(mode)
    steps  = []
    key    = sid or "default"

    with _LOCK:
        h = _HISTORIES.setdefault(key, [])
        h.append({"role": "user", "content": user_msg})
        messages = list(h)

    answer = ""
    for _ in range(_MAX_STEPS):
        try:
            resp = provider.chat(messages=messages, system=system,
                                 max_tokens=8192, temperature=0.2)
        except TypeError:
            resp = provider.chat(messages=messages, system=system)
        except Exception as e:
            answer = f"❌ Provider-Fehler: {e}"
            break

        davor, tool, err = _parse_tool(resp)

        if err:
            messages.append({"role": "assistant", "content": resp})
            messages.append({"role": "user",
                             "content": f"Fehler beim Parsen: {err} "
                                        f"Bitte sende exakt einen gültigen TOOL-Block "
                                        f"oder die finale Antwort."})
            continue

        if tool is None:
            answer = davor or resp.strip()
            break

        if davor:
            steps.append({"type": "text", "text": davor})

        name = tool.get("name", "")
        args = tool.get("args", {}) or {}
        erlaubt, grund = _permission(mode, name)

        if erlaubt is True:
            fn = _TOOLS.get(name)
            if not fn:
                result = f"(Unbekanntes Werkzeug: {name})"
            else:
                try:
                    if name == "run_shell":
                        result = fn(args.get("command", ""),
                                    deny=_MODE_POLICY[mode]["deny"])
                    else:
                        result = fn(**args)
                except Exception as e:
                    result = f"(Fehler bei {name}: {e})"
            steps.append({"type": "tool", "name": name, "args": args,
                          "result": result, "allowed": True})
        else:
            if erlaubt == "ask":
                result = ("⏸ Diese Änderung braucht deine Freigabe (Manuell-Modus). "
                          "Interaktive Freigabe folgt im nächsten Schritt; wähle vorerst "
                          "'Auto' oder 'Plan'.")
            else:
                result = f"⛔ Nicht erlaubt: {grund}"
            steps.append({"type": "tool", "name": name, "args": args,
                          "result": result, "allowed": False})

        messages.append({"role": "assistant", "content": resp})
        messages.append({"role": "user",
                         "content": f"WERKZEUG-ERGEBNIS ({name}):\n{result}\n\n"
                                    f"Mache weiter oder gib die finale Antwort."})
    else:
        answer = answer or "⚠️ Schrittlimit erreicht. Bitte präziser nachfragen."

    with _LOCK:
        _HISTORIES.setdefault(key, []).append({"role": "assistant", "content": answer})

    return {"steps": steps, "answer": answer, "provider": prov_name, "mode": mode}


# ══ Interaktive Läufe (Start / Poll / Freigabe) ═══════════════════════════════
# Erlaubt den "Manuell"-Modus: der Agent hält vor einer Änderung an, fragt im
# Fenster nach (Erlauben/Ablehnen) und macht dann weiter. Der Lauf läuft in einem
# Hintergrund-Thread; das Frontend fragt per Poll den Fortschritt ab.
_RUNS = {}
_RUNS_LOCK = threading.Lock()


def _add_step(st, step):
    with _RUNS_LOCK:
        st["steps"].append(step)


def start_run(user_msg: str, mode: str = "plan", provider_mode: str = "auto",
              sid: str = "default", kind: str = "coding", kernel=None) -> str:
    if kind == "coding" and mode not in _MODE_POLICY:
        mode = "plan"
    rid = uuid.uuid4().hex[:12]
    st = {"id": rid, "mode": mode, "provider_mode": provider_mode, "sid": sid or "default",
          "kind": kind, "status": "running", "steps": [], "answer": "", "provider": None,
          "pending": None, "decision": None,
          "event": threading.Event(), "created": time.time()}
    with _RUNS_LOCK:
        for k in [k for k, v in _RUNS.items() if time.time() - v["created"] > 1800]:
            _RUNS.pop(k, None)
        _RUNS[rid] = st
    if kind == "cowork":
        threading.Thread(target=_cowork_loop, args=(st, user_msg, kernel), daemon=True).start()
    else:
        threading.Thread(target=_run_loop, args=(st, user_msg), daemon=True).start()
    return rid


def poll_run(run_id: str) -> dict:
    with _RUNS_LOCK:
        st = _RUNS.get(run_id)
        if not st:
            return {"status": "unknown"}
        return {"status": st["status"], "steps": list(st["steps"]),
                "answer": st["answer"], "provider": st["provider"],
                "mode": st["mode"], "pending": st["pending"]}


def decide_run(run_id: str, allow: bool) -> bool:
    with _RUNS_LOCK:
        st = _RUNS.get(run_id)
        if not st or st["status"] != "pending":
            return False
        st["decision"] = bool(allow)
        st["status"] = "running"
        ev = st["event"]
    ev.set()
    return True


def _run_loop(st, user_msg):
    mode = st["mode"]
    try:
        prov_name, provider = select_provider(st["provider_mode"])
    except Exception as e:
        with _RUNS_LOCK:
            st["answer"] = f"❌ Kein KI-Provider verfügbar: {e}"; st["status"] = "error"
        return
    with _RUNS_LOCK:
        st["provider"] = prov_name
    system = _system_prompt(mode)
    key = st.get("sid") or "default"

    with _LOCK:
        h = _HISTORIES.setdefault(key, [])
        h.append({"role": "user", "content": user_msg})
        messages = list(h)

    answer = ""
    for _ in range(_MAX_STEPS):
        try:
            resp = provider.chat(messages=messages, system=system,
                                 max_tokens=8192, temperature=0.2)
        except TypeError:
            resp = provider.chat(messages=messages, system=system)
        except Exception as e:
            answer = f"❌ Provider-Fehler: {e}"; break

        davor, tool, err = _parse_tool(resp)
        if err:
            messages.append({"role": "assistant", "content": resp})
            messages.append({"role": "user", "content":
                             f"Fehler beim Parsen: {err} Bitte exakt einen gültigen "
                             f"TOOL-Block oder die finale Antwort."})
            continue
        if tool is None:
            answer = davor or resp.strip(); break
        if davor:
            _add_step(st, {"type": "text", "text": davor})

        name = tool.get("name", "")
        args = tool.get("args", {}) or {}
        erlaubt, grund = _permission(mode, name)

        # Interaktive Freigabe (Manuell-Modus)
        if erlaubt == "ask":
            with _RUNS_LOCK:
                st["pending"] = {"name": name, "args": args}
                st["status"] = "pending"
                st["event"].clear()
            got = st["event"].wait(timeout=1800)   # wartet auf decide_run()
            if not got:
                answer = "⚠️ Zeitüberschreitung bei der Freigabe – Lauf abgebrochen."
                break
            with _RUNS_LOCK:
                allow = bool(st.get("decision"))
                st["pending"] = None; st["decision"] = None
            if not allow:
                result = "⛔ Vom Nutzer abgelehnt."
                _add_step(st, {"type": "tool", "name": name, "args": args,
                               "result": result, "allowed": False})
                messages.append({"role": "assistant", "content": resp})
                messages.append({"role": "user", "content":
                                 f"WERKZEUG-ERGEBNIS ({name}):\n{result}\n\n"
                                 f"Mache weiter oder gib die finale Antwort."})
                continue
            erlaubt = True

        if erlaubt is True:
            fn = _TOOLS.get(name)
            if not fn:
                result = f"(Unbekanntes Werkzeug: {name})"
            else:
                try:
                    if name == "run_shell":
                        result = fn(args.get("command", ""),
                                    deny=_MODE_POLICY[mode]["deny"])
                    else:
                        result = fn(**args)
                except Exception as e:
                    result = f"(Fehler bei {name}: {e})"
            _add_step(st, {"type": "tool", "name": name, "args": args,
                           "result": result, "allowed": True})
        else:
            result = f"⛔ Nicht erlaubt: {grund}"
            _add_step(st, {"type": "tool", "name": name, "args": args,
                           "result": result, "allowed": False})

        messages.append({"role": "assistant", "content": resp})
        messages.append({"role": "user", "content":
                         f"WERKZEUG-ERGEBNIS ({name}):\n{result}\n\n"
                         f"Mache weiter oder gib die finale Antwort."})
    else:
        answer = answer or "⚠️ Schrittlimit erreicht. Bitte präziser nachfragen."

    with _LOCK:
        _HISTORIES.setdefault(key, []).append({"role": "assistant", "content": answer})
    with _RUNS_LOCK:
        st["answer"] = answer; st["status"] = "done"; st["pending"] = None


# ══ Cowork-Agent (mehrstufig, nutzt Ilijas Skills als Werkzeuge) ══════════════
# Persona: proaktiver digitaler Mitarbeiter. Werkzeuge = Ilijas vorhandene Skills
# (DMS, Kalender, Gedächtnis, Web-Suche …) über die bewährte SKILL:-Konvention,
# aber MEHRSTUFIG (Schleife), damit er Aufgaben eigenständig abarbeitet.
_COWORK_HISTORIES = {}


def _extract_skill_calls(text):
    """Findet SKILL:name(...)-Aufrufe robust mit BALANCIERTEN Klammern, damit
    Klammern im Inhalt (z. B. '(siehe Anlage)') den Aufruf nicht abschneiden."""
    calls = []
    pat = re.compile(r'SKILL:(\w+)\(')
    i = 0
    while True:
        m = pat.search(text, i)
        if not m:
            break
        j, depth = m.end(), 1
        while j < len(text) and depth > 0:
            if text[j] == '(':
                depth += 1
            elif text[j] == ')':
                depth -= 1
            j += 1
        calls.append((m.group(1), text[m.end():j - 1]))
        i = j
    return calls

_COWORK_PERSONA = (
    "Du bist Ilija Cowork – ein proaktiver, mitdenkender digitaler Mitarbeiter/Kollege "
    "des Nutzers. Du erledigst Aufgaben eigenständig in mehreren Schritten, nutzt deine "
    "Fähigkeiten (Skills) selbstständig und fasst am Ende knapp und kollegial zusammen.\n\n"
)


def _parse_skill_params(params_str):
    """key="wert" / key='wert' – toleriert die andere Quote sowie \\" und \\n."""
    kwargs = {}
    for m in re.finditer(r'(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"', params_str):
        kwargs[m.group(1)] = (m.group(2).replace('\\"', '"')
                              .replace('\\n', '\n').replace('\\t', '\t'))
    for m in re.finditer(r"(\w+)\s*=\s*'((?:[^'\\]|\\.)*)'", params_str):
        kwargs.setdefault(m.group(1), (m.group(2).replace("\\'", "'")
                          .replace('\\n', '\n').replace('\\t', '\t')))
    return kwargs


def _cowork_loop(st, user_msg, kernel):
    try:
        prov_name, provider = select_provider(st["provider_mode"])
    except Exception as e:
        with _RUNS_LOCK:
            st["answer"] = f"❌ Kein KI-Provider verfügbar: {e}"; st["status"] = "error"
        return
    with _RUNS_LOCK:
        st["provider"] = prov_name
    try:
        system = _COWORK_PERSONA + kernel.get_system_prompt()
    except Exception:
        system = _COWORK_PERSONA
    key = st.get("sid") or "default"

    with _LOCK:
        h = _COWORK_HISTORIES.setdefault(key, [])
        h.append({"role": "user", "content": user_msg})
        messages = list(h)

    answer = ""
    for _ in range(_MAX_STEPS):
        try:
            resp = provider.chat(messages=messages, system=system,
                                 max_tokens=4096, temperature=0.4)
        except TypeError:
            resp = provider.chat(messages=messages, system=system)
        except Exception as e:
            answer = f"❌ Provider-Fehler: {e}"; break

        matches = _extract_skill_calls(resp)
        if not matches:
            answer = resp.strip(); break

        vor = resp.split("SKILL:")[0].strip()
        if vor:
            _add_step(st, {"type": "text", "text": vor})

        ergebnisse = []
        for name, params in matches:
            kwargs = _parse_skill_params(params)
            # Telefon-Sonderfall wie im Kernel (Anrufer darf nicht alle Skills auslösen)
            if name == "skill_ausfuehren" and "kernel" not in kwargs:
                try:
                    from customer_kernel import CustomerKernel
                    kwargs["kernel"] = CustomerKernel(haupt_kernel=kernel)
                except Exception:
                    kwargs["kernel"] = kernel
            try:
                res = kernel.manager.execute(name, **kwargs)
            except Exception as e:
                res = f"(Fehler bei {name}: {e})"
            disp = {k: v for k, v in kwargs.items() if k != "kernel"}
            _add_step(st, {"type": "tool", "name": name, "args": disp,
                           "result": str(res), "allowed": True})
            ergebnisse.append(f"{name}: {res}")

        messages.append({"role": "assistant", "content": resp})
        messages.append({"role": "user", "content":
                         "SKILL-ERGEBNIS:\n" + "\n".join(ergebnisse) +
                         "\n\nMache weiter oder gib die finale Antwort."})
    else:
        answer = answer or "⚠️ Schrittlimit erreicht."

    with _LOCK:
        _COWORK_HISTORIES.setdefault(key, []).append({"role": "assistant", "content": answer})
    with _RUNS_LOCK:
        st["answer"] = answer; st["status"] = "done"; st["pending"] = None
