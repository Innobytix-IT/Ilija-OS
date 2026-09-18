"""
workflow_routes.py – n8n-Style Workflow-Backend für Ilija
=========================================================
Registriert neue API-Routen für Workflow-Verwaltung und Skill-Direktausführung.

Integration in web_server.py:
    from workflow_routes import register_workflow_routes
    register_workflow_routes(app, kernel, kernel_lock)
"""

import os
import json
import uuid
import inspect
import threading as _sched_threading
import time as _sched_time
from datetime import datetime
from flask import Blueprint, request, jsonify

WORKFLOWS_DIR  = os.path.join("data", "workflows")
MEMORY_DIR     = os.path.join("data", "memory")
SCHEDULES_DIR  = os.path.join("data", "schedules")

# ── Hintergrund-Scheduler ─────────────────────────────────────────────────────
_scheduler_started = False
_schedules_lock    = _sched_threading.Lock()   # Verhindert Race-Condition auf active.json
_whisper_model     = None                      # Gecachtes Whisper-Modell (einmalig laden)

def _schedule_should_fire(config: dict, now: datetime) -> bool:
    """Prüft ob ein Zeitplan jetzt feuern soll."""
    itype = config.get("interval_type", "interval")
    last  = config.get("_last_run", "")
    try:
        last_dt = datetime.fromisoformat(last) if last else None
    except Exception:
        last_dt = None

    if itype == "interval":
        minuten  = int(config.get("minuten",  0))
        sekunden = int(config.get("sekunden", 0))
        gesamt   = minuten * 60 + sekunden
        if gesamt < 5:
            gesamt = 5  # Minimum 5 Sekunden
        if last_dt is None:
            return True
        return (now - last_dt).total_seconds() >= gesamt

    elif itype == "taglich":
        zeit = config.get("zeit", "08:00")
        try:
            h, m = map(int, zeit.split(":"))
        except Exception:
            return False
        if now.hour != h or now.minute != m:
            return False
        if last_dt is None or last_dt.date() < now.date():
            return True

    elif itype == "woechentlich":
        wochentag = int(config.get("wochentag", 0))
        zeit      = config.get("zeit", "08:00")
        try:
            h, m = map(int, zeit.split(":"))
        except Exception:
            return False
        if now.weekday() != wochentag or now.hour != h or now.minute != m:
            return False
        if last_dt is None or (now - last_dt).total_seconds() >= 604700:
            return True

    return False


def _start_scheduler(port: int):
    """Startet den Hintergrund-Scheduler (einmalig)."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        while True:
            try:
                os.makedirs(SCHEDULES_DIR, exist_ok=True)
                sched_file = os.path.join(SCHEDULES_DIR, "active.json")
                with _schedules_lock:
                    if os.path.exists(sched_file):
                        with open(sched_file, "r", encoding="utf-8") as _sf:
                            active = json.load(_sf)
                    else:
                        active = {}
                updated = False
                now     = datetime.now()
                for wid, entry in active.items():
                    if not entry.get("active"):
                        continue
                    cfg = entry.get("config", {})
                    if _schedule_should_fire(cfg, now):
                        wf_path = os.path.join(WORKFLOWS_DIR, f"{wid}.json")
                        if os.path.exists(wf_path):
                            try:
                                import requests as _rq
                                with open(wf_path, "r", encoding="utf-8") as _wf:
                                    wf_data = json.load(_wf)
                                ts = now.strftime("%d.%m.%Y %H:%M")
                                _wf_name = wf_data.get("name", wid)
                                _payload = {
                                    "nodes":       wf_data.get("nodes", []),
                                    "connections": wf_data.get("connections", []),
                                }
                                # Fire-and-Forget: Workflow als eigener Thread starten
                                # → Scheduler wird nicht durch lange Workflows blockiert
                                def _fire(url, payload, name, _rq=_rq):
                                    try:
                                        r = _rq.post(url, json=payload, timeout=120)
                                        print(f"[Scheduler] '{name}' — HTTP {r.status_code}")
                                    except Exception as _fe:
                                        print(f"[Scheduler] Fehler '{name}': {_fe}")
                                _sched_threading.Thread(
                                    target=_fire,
                                    args=(f"http://localhost:{port}/api/workflow/execute",
                                          _payload, _wf_name),
                                    daemon=True,
                                ).start()
                                print(f"[Scheduler] '{_wf_name}' gestartet — {ts}")
                                active[wid]["config"]["_last_run"] = now.isoformat()
                                updated = True
                            except Exception as _se:
                                print(f"[Scheduler] Fehler bei '{wid}': {_se}")
                if updated:
                    with _schedules_lock:
                        with open(sched_file, "w", encoding="utf-8") as _sf:
                            json.dump(active, _sf, ensure_ascii=False, indent=2)
            except Exception as _ge:
                print(f"[Scheduler] Allgemeiner Fehler: {_ge}")
            _sched_time.sleep(5)  # Alle 5s prüfen → ermöglicht Sekunden-genaue Intervalle

    t = _sched_threading.Thread(target=_loop, daemon=True, name="IlijaScheduler")
    t.start()
    print("[Ilija] Hintergrund-Scheduler gestartet ✅")


# ── Memory-Hilfsfunktionen ────────────────────────────────────────────────────

def _mem_path(key: str) -> str:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in key)
    return os.path.join(MEMORY_DIR, f"{safe}.json")

def _mem_read(key: str, window_size: int = 10) -> list:
    path = _mem_path(key)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("window", [])[-window_size * 2:]
    except Exception:
        return []

def _mem_write(key: str, user_msg: str, assistant_msg: str, window_size: int = 10):
    path   = _mem_path(key)
    window = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                window = json.load(f).get("window", [])
        except Exception:
            pass
    now = datetime.now().isoformat()
    window += [
        {"role": "user",      "content": str(user_msg)[:600],      "time": now},
        {"role": "assistant", "content": str(assistant_msg)[:600],  "time": now},
    ]
    if len(window) > window_size * 2:
        window = window[-window_size * 2:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"key": key, "updated": now, "window": window,
                   "count": len(window) // 2}, f, ensure_ascii=False, indent=2)

def _mem_format(window: list) -> str:
    if not window:
        return ""
    lines = ["── Bisheriger Gesprächsverlauf ──────────────"]
    for msg in window:
        prefix  = "Nutzer" if msg["role"] == "user" else "Ilija"
        content = str(msg.get("content", ""))[:250]
        lines.append(f"{prefix}: {content}")
    lines.append("─────────────────────────────────────────────")
    return "\n".join(lines)

def _mem_summary_read(key: str) -> str:
    path = _mem_path(key + "_summary")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("summary", "")
    except Exception:
        return ""

def _mem_summary_write(key: str, summary: str):
    path = _mem_path(key + "_summary")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"key": key, "updated": datetime.now().isoformat(),
                   "summary": summary}, f, ensure_ascii=False, indent=2)

def _mem_stats(key: str) -> dict:
    path = _mem_path(key)
    if not os.path.exists(path):
        return {"count": 0, "updated": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"count": d.get("count", len(d.get("window", [])) // 2),
                "updated": d.get("updated")}
    except Exception:
        return {"count": 0, "updated": None}


def register_workflow_routes(app, get_kernel_func, kernel_lock):
    """Registriert alle Workflow-Routen an der Flask-App."""

    os.makedirs(WORKFLOWS_DIR, exist_ok=True)

    # ── Skill direkt ausführen (ohne KI-Vermittlung) ──────────────────
    @app.route("/api/skill/execute", methods=["POST"])
    def execute_skill_direct():
        """Führt einen Skill direkt aus (ohne Umweg über den KI-Kernel)."""
        data       = request.get_json() or {}
        skill_name = data.get("skill", "").strip()
        params     = data.get("params", {})

        if not skill_name:
            return jsonify({"error": "Kein Skill angegeben"}), 400

        with kernel_lock:
            k      = get_kernel_func()
            result = k.manager.execute(skill_name, **params)

        return jsonify({"result": result, "skill": skill_name})

    # ── Skill-Signatur abfragen ───────────────────────────────────────
    @app.route("/api/skill/signature/<skill_name>")
    def skill_signature(skill_name):
        """Gibt Parameter-Informationen eines Skills zurück."""
        with kernel_lock:
            k = get_kernel_func()
            if skill_name not in k.manager.skills:
                return jsonify({"error": "Skill nicht gefunden"}), 404

            func = k.manager.skills[skill_name]
            sig  = inspect.signature(func)
            doc  = k.manager.skill_docs.get(skill_name, "")

            params = []
            for pname, param in sig.parameters.items():
                p = {"name": pname, "required": param.default is inspect.Parameter.empty}
                if param.default is not inspect.Parameter.empty:
                    p["default"] = str(param.default)
                if param.annotation is not inspect.Parameter.empty:
                    p["type"] = str(param.annotation.__name__ if hasattr(param.annotation, '__name__') else param.annotation)
                params.append(p)

        return jsonify({"skill": skill_name, "params": params, "doc": doc})

    # ── Workflow speichern ────────────────────────────────────────────
    @app.route("/api/workflows", methods=["POST"])
    def save_workflow():
        data = request.get_json() or {}
        wid  = data.get("id") or f"wf_{uuid.uuid4().hex[:8]}"
        name = data.get("name", "Neuer Workflow")

        workflow = {
            "id":          wid,
            "name":        name,
            "nodes":       data.get("nodes", []),
            "connections": data.get("connections", []),
            "updated":     datetime.now().isoformat(),
            "created":     data.get("created", datetime.now().isoformat()),
        }

        filepath = os.path.join(WORKFLOWS_DIR, f"{wid}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(workflow, f, ensure_ascii=False, indent=2)

        return jsonify({"message": f"Workflow '{name}' gespeichert", "id": wid})

    # ── Alle Workflows auflisten ──────────────────────────────────────
    @app.route("/api/workflows", methods=["GET"])
    def list_workflows():
        workflows = []
        for fname in sorted(os.listdir(WORKFLOWS_DIR)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(WORKFLOWS_DIR, fname), "r", encoding="utf-8") as f:
                    wf = json.load(f)
                workflows.append({
                    "id":      wf.get("id"),
                    "name":    wf.get("name"),
                    "updated": wf.get("updated"),
                    "nodes":   len(wf.get("nodes", [])),
                })
            except Exception:
                pass
        return jsonify(workflows)

    # ── Einzelnen Workflow laden ──────────────────────────────────────
    @app.route("/api/workflows/<wid>", methods=["GET"])
    def load_workflow(wid):
        filepath = os.path.join(WORKFLOWS_DIR, f"{wid}.json")
        if not os.path.exists(filepath):
            return jsonify({"error": "Workflow nicht gefunden"}), 404
        with open(filepath, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))

    # ── Workflow löschen ──────────────────────────────────────────────
    @app.route("/api/workflows/<wid>", methods=["DELETE"])
    def delete_workflow(wid):
        filepath = os.path.join(WORKFLOWS_DIR, f"{wid}.json")
        if not os.path.exists(filepath):
            return jsonify({"error": "Workflow nicht gefunden"}), 404
        os.remove(filepath)
        return jsonify({"message": "Workflow gelöscht"})

    # ── Workflow ausführen ────────────────────────────────────────────
    @app.route("/api/workflow/execute", methods=["POST"])
    def execute_workflow():
        """
        Führt einen kompletten Workflow aus.
        
        Ablauf:
        1. Trigger-Node finden
        2. Graph topologisch sortieren
        3. Jeden Node in Reihenfolge ausführen
        4. Ausgaben als Eingaben an verbundene Nodes weitergeben
        """
        data        = request.get_json() or {}
        nodes       = {n["id"]: n for n in data.get("nodes", [])}
        connections = data.get("connections", [])

        if not nodes:
            return jsonify({"error": "Keine Nodes vorhanden"}), 400

        # Adjazenzliste und In-Degree aufbauen
        adj      = {nid: [] for nid in nodes}  # nid → [successor_nid]
        in_deg   = {nid: 0  for nid in nodes}
        conn_map = {}  # (to_nid) → [(from_nid, conn)]

        for conn in connections:
            frm = conn["from"]
            to  = conn["to"]
            if frm in adj and to in in_deg:
                adj[frm].append(to)
                in_deg[to] += 1
                conn_map.setdefault(to, []).append(frm)

        # Topologische Sortierung (Kahn)
        queue = [nid for nid, deg in in_deg.items() if deg == 0]
        order = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for successor in adj[nid]:
                in_deg[successor] -= 1
                if in_deg[successor] == 0:
                    queue.append(successor)

        if len(order) != len(nodes):
            return jsonify({"error": "Workflow enthält Zyklen (nicht erlaubt)"}), 400

        # Ausführung
        results            = {}   # nid → output string
        statuses           = {}   # nid → "success" | "error" | "skipped"
        memory_write_queue = []   # memory nodes to write back after execution
        loop_processed     = set()  # nodes already executed inside a loop
        workflow_stopped   = None   # Wenn gesetzt: Workflow früh beendet (Grund als String)

        with kernel_lock:
            k = get_kernel_func()

            for nid in order:
                if workflow_stopped:
                    statuses[nid] = "skipped"
                    continue

                if nid in loop_processed:
                    continue   # wurde bereits innerhalb einer Schleife ausgeführt

                node    = nodes[nid]
                ntype   = node.get("type", "note")
                config  = node.get("config", {})

                # Eingabe-Kontext aus Vorgängern zusammenbauen
                prev_outputs = []
                for prev_id in conn_map.get(nid, []):
                    if prev_id in results:
                        prev_outputs.append(results[prev_id])
                context = "\n".join(prev_outputs) if prev_outputs else ""

                try:
                    if ntype == "trigger":
                        output = config.get("startMessage", "Workflow gestartet ✅")

                    elif ntype == "chat":
                        message = config.get("message", "").strip()
                        # Template: {{input}} durch Vorgänger-Output ersetzen
                        if "{{input}}" in message and context:
                            message = message.replace("{{input}}", context)
                        elif not message and context:
                            message = context
                        if not message:
                            message = "Hallo Ilija!"
                        output = k.chat(message)

                    elif ntype == "chatfilter":
                        # ── Chat-Filter: universeller Wächter zwischen Lese- und Chat-Nodes ──
                        # Modus "intelligent": KI entscheidet ob echte Nachricht vorhanden.
                        # Modus "einfach": schneller String-Check auf "📭" und leer.
                        modus     = config.get("modus", "intelligent")
                        bei_leer  = config.get("bei_leer", "stoppen")

                        # ── Einfacher Vor-Check (immer) ─────────────────────────────────────
                        leere_signale = ("📭",)
                        offensichtlich_leer = (
                            not context.strip()
                            or any(context.strip().startswith(s) for s in leere_signale)
                        )

                        if offensichtlich_leer:
                            hat_echte_nachricht = False
                        elif modus == "intelligent":
                            # ── KI-Klassifikation ─────────────────────────────────────────
                            _filter_prompt = (
                                "Du bist ein strikter Nachrichtenfilter. "
                                "Deine einzige Aufgabe: Entscheide ob der folgende Text "
                                "eine echte Benutzer-Nachricht enthält die beantwortet werden soll.\n\n"
                                "Antworte NUR mit einem einzigen Wort: JA oder NEIN.\n\n"
                                "JA = Text enthält mindestens eine echte Nachricht eines Users.\n"
                                "NEIN = Text ist leer, eine Fehlermeldung, ein System-Signal "
                                "(z.B. '📭', 'keine Nachrichten', 'Fehler', technische Info).\n\n"
                                f"Text:\n{context.strip()[:500]}"
                            )
                            try:
                                _antwort = k.chat(_filter_prompt).strip().upper()
                                hat_echte_nachricht = _antwort.startswith("JA")
                            except Exception:
                                # Fallback auf einfachen Check wenn KI nicht erreichbar
                                hat_echte_nachricht = not offensichtlich_leer
                        else:
                            # Modus "einfach": alles was nicht leer/📭 ist gilt als echt
                            hat_echte_nachricht = True

                        if not hat_echte_nachricht:
                            if bei_leer == "weiter":
                                output = ""
                            else:
                                workflow_stopped = (
                                    context.strip()
                                    or "📭 Kein Input — Workflow gestoppt."
                                )
                                output = ""
                                statuses[nid] = "skipped"
                                results[nid]  = output
                                continue
                        else:
                            # Echte Nachricht → unverändert durchleiten
                            output = context

                    elif ntype == "skill":
                        skill_name = config.get("skill", "")
                        params     = dict(config.get("params", {}))
                        # Template-Variablen in Params ersetzen
                        for pkey, pval in params.items():
                            if isinstance(pval, str) and "{{input}}" in pval and context:
                                params[pkey] = pval.replace("{{input}}", context)
                        if not skill_name:
                            output = "⚠️ Kein Skill ausgewählt"
                        else:
                            output = k.manager.execute(skill_name, **params)

                    elif ntype == "note":
                        output = config.get("text", "")

                    elif ntype == "set":
                        output = config.get("value", "")
                        if "{{input}}" in output and context:
                            output = output.replace("{{input}}", context)

                    elif ntype == "memory_window":
                        key  = config.get("memory_key", "default")
                        size = max(1, int(config.get("window_size", 10)))
                        window = _mem_read(key, size)
                        output = _mem_format(window) if window else "── Gedächtnis noch leer ──"
                        memory_write_queue.append({
                            "nid": nid, "key": key, "size": size, "type": "window"
                        })

                    elif ntype == "memory_summary":
                        key     = config.get("memory_key", "default")
                        summary = _mem_summary_read(key)
                        output  = (f"── Zusammenfassung bisheriger Gespräche ──\n{summary}"
                                   if summary else "── Noch keine Zusammenfassung vorhanden ──")
                        memory_write_queue.append({
                            "nid": nid, "key": key, "type": "summary"
                        })

                    elif ntype == "telegram":
                        operation = config.get("operation", "send")
                        token     = config.get("token", "").strip()
                        chat_id   = config.get("chat_id", "").strip()

                        # Gespeicherte Telegram-Konfiguration als Fallback
                        if not token or not chat_id:
                            tg_cfg_path = os.path.join("data", "telegram", "telegram_config.json")
                            if os.path.exists(tg_cfg_path):
                                try:
                                    with open(tg_cfg_path, "r", encoding="utf-8") as _f:
                                        tg_cfg = json.load(_f)
                                    token   = token   or tg_cfg.get("token", "")
                                    chat_id = chat_id or tg_cfg.get("chat_id", "")
                                except Exception:
                                    pass

                        if not token:
                            output = "❌ Kein Token. Im Node eingeben oder telegram_konfigurieren() ausführen."
                        elif operation == "send":
                            text = config.get("text", "{{input}}").strip() or "{{input}}"
                            if "{{input}}" in text and context:
                                text = text.replace("{{input}}", context)
                            elif not text and context:
                                text = context
                            if not text:
                                output = "⚠️ Kein Text zum Senden."
                            elif not chat_id:
                                output = "❌ Keine Chat-ID angegeben."
                            else:
                                try:
                                    import urllib.request as _ureq
                                    import json as _json
                                    _payload = _json.dumps({
                                        "chat_id": chat_id,
                                        "text": text[:4096]
                                    }).encode("utf-8")
                                    _tg_req = _ureq.Request(
                                        f"https://api.telegram.org/bot{token}/sendMessage",
                                        data=_payload,
                                        headers={"Content-Type": "application/json"},
                                        method="POST"
                                    )
                                    with _ureq.urlopen(_tg_req, timeout=15) as _resp:
                                        _result = _json.loads(_resp.read())
                                    if _result.get("ok"):
                                        output = f"✅ Telegram-Nachricht gesendet an {chat_id}."
                                    else:
                                        output = f"❌ Telegram-Fehler: {_result.get('description', 'Unbekannt')}"
                                except Exception as e:
                                    output = f"❌ Sendefehler: {e}"

                        elif operation == "read":
                            anzahl = max(1, int(config.get("anzahl", 5)))
                            # Offset-Datei: merkt sich den letzten verarbeiteten update_id
                            _tg_offset_dir  = os.path.join("data", "telegram")
                            _tg_offset_file = os.path.join(_tg_offset_dir, "last_update_id.json")
                            os.makedirs(_tg_offset_dir, exist_ok=True)
                            _last_uid = 0
                            if os.path.exists(_tg_offset_file):
                                try:
                                    with open(_tg_offset_file, "r") as _of:
                                        _last_uid = json.load(_of).get("last_update_id", 0)
                                except Exception:
                                    pass
                            try:
                                import urllib.request as _ureq
                                import urllib.parse as _uparse
                                import json as _json
                                _params = _uparse.urlencode({
                                    "limit": anzahl,
                                    "offset": _last_uid + 1,
                                })
                                _tg_url = f"https://api.telegram.org/bot{token}/getUpdates?{_params}"
                                with _ureq.urlopen(_tg_url, timeout=15) as _resp:
                                    _data = _json.loads(_resp.read())
                                updates = _data.get("result", [])
                                if not updates:
                                    output = "📭 Keine neuen Telegram-Nachrichten."
                                else:
                                    # ── Hilfsfunktion: Audio transkribieren ──────────────
                                    def _tg_transkribieren(audio_bytes: bytes) -> str:
                                        """Transkribiert Audio: erst Gemini, dann lokaler Whisper."""
                                        import base64 as _b64
                                        # Option 1: Gemini (GOOGLE_API_KEY bereits konfiguriert)
                                        _gkey  = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
                                        _gmod  = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
                                        if _gkey:
                                            try:
                                                _gp = _json.dumps({
                                                    "contents": [{
                                                        "parts": [
                                                            {"inline_data": {
                                                                "mime_type": "audio/ogg",
                                                                "data": _b64.b64encode(audio_bytes).decode()
                                                            }},
                                                            {"text": "Transkribiere diese Sprachnachricht. "
                                                                     "Gib NUR den gesprochenen Text zurück, "
                                                                     "keine Erklärungen."}
                                                        ]
                                                    }]
                                                }).encode("utf-8")
                                                _gurl = (
                                                    f"https://generativelanguage.googleapis.com/v1beta"
                                                    f"/models/{_gmod}:generateContent"
                                                )
                                                _greq = _ureq.Request(
                                                    _gurl, data=_gp,
                                                    headers={"Content-Type": "application/json",
                                                             "X-goog-api-key": _gkey},
                                                    method="POST"
                                                )
                                                with _ureq.urlopen(_greq, timeout=30) as _gr:
                                                    _gd = _json.loads(_gr.read())
                                                _gtxt = "".join(
                                                    p.get("text", "")
                                                    for p in _gd["candidates"][0]["content"]["parts"]
                                                ).strip()
                                                if _gtxt:
                                                    return f"🎤 {_gtxt}"
                                            except Exception:
                                                pass
                                        # Option 2: lokaler Whisper (pip install openai-whisper)
                                        try:
                                            import whisper as _w
                                            import tempfile as _tmp
                                            global _whisper_model
                                            if _whisper_model is None:
                                                _whisper_model = _w.load_model("base")
                                            with _tmp.NamedTemporaryFile(suffix=".ogg", delete=False) as _tf:
                                                _tf.write(audio_bytes)
                                                _tf_path = _tf.name
                                            _wres = _whisper_model.transcribe(_tf_path, language="de")
                                            os.unlink(_tf_path)
                                            _wtxt = _wres.get("text", "").strip()
                                            if _wtxt:
                                                return f"🎤 {_wtxt}"
                                        except ImportError:
                                            pass
                                        except Exception:
                                            pass
                                        return "🎤 [Sprachnachricht — kein Transkriptions-Service verfügbar]"

                                    zeilen  = []
                                    max_uid = _last_uid
                                    for upd in updates:
                                        uid = upd.get("update_id", 0)
                                        if uid > max_uid:
                                            max_uid = uid
                                        msg = upd.get("message", {})
                                        if not msg:
                                            continue
                                        name = msg.get("from", {}).get("first_name", "?")
                                        ts   = datetime.fromtimestamp(
                                            msg.get("date", 0)
                                        ).strftime("%d.%m. %H:%M")

                                        # ── Text-Nachricht ────────────────────────────────
                                        if msg.get("text"):
                                            text_in = msg["text"]

                                        # ── Sprachnachricht / Audio ───────────────────────
                                        elif msg.get("voice") or msg.get("audio"):
                                            _vobj   = msg.get("voice") or msg.get("audio")
                                            _fid    = _vobj.get("file_id", "")
                                            try:
                                                # Datei-URL holen
                                                _furl = (
                                                    f"https://api.telegram.org/bot{token}"
                                                    f"/getFile?file_id={_uparse.quote(_fid)}"
                                                )
                                                with _ureq.urlopen(_furl, timeout=15) as _fr:
                                                    _fp = _json.loads(_fr.read()).get(
                                                        "result", {}
                                                    ).get("file_path", "")
                                                if _fp:
                                                    _dlurl = (
                                                        f"https://api.telegram.org/file"
                                                        f"/bot{token}/{_fp}"
                                                    )
                                                    with _ureq.urlopen(_dlurl, timeout=30) as _ar:
                                                        _abytes = _ar.read()
                                                    text_in = _tg_transkribieren(_abytes)
                                                else:
                                                    text_in = "🎤 [Sprachnachricht — Datei nicht abrufbar]"
                                            except Exception as _ve:
                                                text_in = f"🎤 [Sprachnachricht — Fehler: {_ve}]"

                                        # ── Sonstige Medien (Foto, Sticker usw.) ──────────
                                        else:
                                            mtyp = (
                                                "Foto"    if msg.get("photo")     else
                                                "Sticker" if msg.get("sticker")   else
                                                "Video"   if msg.get("video")     else
                                                "Datei"   if msg.get("document")  else
                                                "Medium"
                                            )
                                            caption = msg.get("caption", "")
                                            text_in = (
                                                f"[{mtyp} empfangen"
                                                + (f": {caption}" if caption else "")
                                                + "]"
                                            )

                                        zeilen.append(f"[{ts}] {name}: {text_in}")

                                    # Offset speichern
                                    with open(_tg_offset_file, "w") as _of:
                                        _json.dump({"last_update_id": max_uid}, _of)
                                    if zeilen:
                                        output = "\n".join(zeilen)
                                    else:
                                        # Updates vorhanden, aber keine verarbeitbaren Nachrichten
                                        output = "📭 Keine verarbeitbaren Nachrichten."
                            except Exception as e:
                                output = f"❌ Lesefehler: {e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "email":
                        import imaplib
                        import smtplib
                        import email as _elib
                        from email.mime.text      import MIMEText
                        from email.mime.multipart import MIMEMultipart
                        from email.header         import decode_header as _dh

                        def _hdr(val):
                            if not val: return ""
                            parts = _dh(val)
                            out = []
                            for b, enc in parts:
                                if isinstance(b, bytes):
                                    out.append(b.decode(enc or "utf-8", errors="replace"))
                                else:
                                    out.append(str(b))
                            return " ".join(out)

                        _EMAIL_PRESETS = {
                            "gmail":   ("imap.gmail.com",        993, "smtp.gmail.com",        587),
                            "outlook": ("outlook.office365.com", 993, "smtp.office365.com",    587),
                            "gmx":     ("imap.gmx.net",          993, "mail.gmx.net",          587),
                            "webde":   ("imap.web.de",           993, "smtp.web.de",           587),
                            "yahoo":   ("imap.mail.yahoo.com",   993, "smtp.mail.yahoo.com",   587),
                        }

                        operation  = config.get("operation", "read")
                        provider   = config.get("provider", "").strip().lower()
                        email_addr = config.get("email_adresse", "").strip()
                        password   = config.get("passwort", "").strip()
                        imap_host  = ""
                        imap_port  = 993
                        smtp_host  = ""
                        smtp_port  = 587

                        # Gespeicherte E-Mail-Konfiguration als Fallback
                        _ecfg_path = os.path.join("data", "email", "email_config.json")
                        if os.path.exists(_ecfg_path):
                            try:
                                with open(_ecfg_path, "r", encoding="utf-8") as _f:
                                    _ec = json.load(_f)
                                email_addr = email_addr or _ec.get("email_adresse", "")
                                password   = password   or _ec.get("passwort", "")
                                provider   = provider   or _ec.get("provider", "gmail")
                                imap_host  = _ec.get("imap_host", "")
                                imap_port  = _ec.get("imap_port", 993)
                                smtp_host  = _ec.get("smtp_host", "")
                                smtp_port  = _ec.get("smtp_port", 587)
                            except Exception:
                                pass

                        # Provider-Preset anwenden wenn Hosts noch fehlen
                        if provider in _EMAIL_PRESETS and not imap_host:
                            imap_host, imap_port, smtp_host, smtp_port = _EMAIL_PRESETS[provider]

                        if not email_addr or not password:
                            output = "❌ Keine Zugangsdaten. Im Node eintragen oder email_konfigurieren() ausführen."

                        elif operation == "read":
                            ordner       = config.get("ordner", "INBOX").strip() or "INBOX"
                            anzahl       = max(1, int(config.get("anzahl", 5)))
                            nur_ungelesen = config.get("nur_ungelesen", "nein").lower() == "ja"
                            try:
                                imap = imaplib.IMAP4_SSL(imap_host, imap_port)
                                imap.login(email_addr, password)
                                imap.select(ordner)
                                kriterium = "UNSEEN" if nur_ungelesen else "ALL"
                                _, ids_raw = imap.search(None, kriterium)
                                ids = ids_raw[0].split() if ids_raw[0] else []
                                ids = ids[-anzahl:][::-1]
                                zeilen = []
                                for mid in ids:
                                    _, daten = imap.fetch(mid, "(RFC822)")
                                    if not daten: continue
                                    msg    = _elib.message_from_bytes(daten[0][1])
                                    absend = _hdr(msg.get("From", "?"))
                                    subj   = _hdr(msg.get("Subject", "(kein Betreff)"))
                                    datum  = msg.get("Date", "")[:25]
                                    msg_id = msg.get("Message-ID", "")
                                    body   = ""
                                    if msg.is_multipart():
                                        for part in msg.walk():
                                            if part.get_content_type() == "text/plain":
                                                cs = part.get_content_charset() or "utf-8"
                                                try: body = part.get_payload(decode=True).decode(cs, errors="replace")
                                                except: body = "[nicht lesbar]"
                                                break
                                    else:
                                        cs = msg.get_content_charset() or "utf-8"
                                        try: body = msg.get_payload(decode=True).decode(cs, errors="replace")
                                        except: body = "[nicht lesbar]"
                                    body_k = body.strip()[:250].replace("\n"," ")
                                    if len(body.strip()) > 250: body_k += "…"
                                    zeilen.append(
                                        f"── E-Mail ──────────────────────\n"
                                        f"Von:     {absend}\n"
                                        f"Betreff: {subj}\n"
                                        f"Datum:   {datum}\n"
                                        f"ID:      {msg_id}\n"
                                        f"Text:    {body_k}"
                                    )
                                imap.logout()
                                output = (f"📬 {len(zeilen)} E-Mail(s):\n\n" + "\n\n".join(zeilen)
                                          if zeilen else "📭 Keine E-Mails gefunden.")
                            except imaplib.IMAP4.error as e:
                                output = f"❌ Login fehlgeschlagen: {e}"
                            except Exception as e:
                                output = f"❌ Fehler beim Lesen: {e}"

                        elif operation == "send":
                            an      = config.get("an", "").strip()
                            betreff = config.get("betreff", "").strip()
                            text    = config.get("text", "{{input}}").strip() or "{{input}}"
                            if "{{input}}" in text and context:
                                text = text.replace("{{input}}", context)
                            elif not text and context:
                                text = context
                            if not an:
                                output = "❌ Kein Empfänger (Feld 'An') angegeben."
                            elif not betreff:
                                output = "❌ Kein Betreff angegeben."
                            elif not text:
                                output = "❌ Kein Text angegeben."
                            else:
                                try:
                                    msg = MIMEMultipart()
                                    msg["From"]    = email_addr
                                    msg["To"]      = an
                                    msg["Subject"] = betreff
                                    msg.attach(MIMEText(text, "plain", "utf-8"))
                                    with smtplib.SMTP(smtp_host, smtp_port) as srv:
                                        srv.ehlo(); srv.starttls()
                                        srv.login(email_addr, password)
                                        srv.sendmail(email_addr, an, msg.as_string())
                                    output = f"✅ E-Mail gesendet an {an} · Betreff: {betreff}"
                                except smtplib.SMTPAuthenticationError:
                                    output = "❌ Authentifizierung fehlgeschlagen. App-Passwort prüfen."
                                except Exception as e:
                                    output = f"❌ Sendefehler: {e}"

                        elif operation == "reply":
                            an        = config.get("an", "").strip()
                            betreff   = config.get("betreff", "").strip()
                            antwort   = config.get("antwort_text", "{{input}}").strip() or "{{input}}"
                            if "{{input}}" in antwort and context:
                                antwort = antwort.replace("{{input}}", context)
                            elif not antwort and context:
                                antwort = context
                            if not an:
                                output = "❌ Kein Empfänger angegeben."
                            else:
                                reply_subj = betreff if betreff.startswith("Re:") else f"Re: {betreff}"
                                try:
                                    msg = MIMEMultipart()
                                    msg["From"]    = email_addr
                                    msg["To"]      = an
                                    msg["Subject"] = reply_subj
                                    msg.attach(MIMEText(antwort, "plain", "utf-8"))
                                    with smtplib.SMTP(smtp_host, smtp_port) as srv:
                                        srv.ehlo(); srv.starttls()
                                        srv.login(email_addr, password)
                                        srv.sendmail(email_addr, an, msg.as_string())
                                    output = f"✅ Antwort gesendet an {an} · {reply_subj}"
                                except smtplib.SMTPAuthenticationError:
                                    output = "❌ Authentifizierung fehlgeschlagen."
                                except Exception as e:
                                    output = f"❌ Fehler beim Antworten: {e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "google_kalender":
                        import datetime as _dt

                        operation      = config.get("operation", "slots_lesen")
                        creds_pfad     = config.get("credentials_pfad",
                                                    os.path.join("data", "google_kalender",
                                                                 "credentials.json")).strip()
                        _TOKEN_PATH    = os.path.join("data", "google_kalender", "token.json")
                        _GK_SCOPES     = ["https://www.googleapis.com/auth/calendar"]

                        # Datum: nur wenn explizit "{{input}}" → aus vorherigem Node
                        # Leer = heute (nicht den Input-Text als Datum parsen!)
                        datum_raw = config.get("datum", "").strip()
                        if datum_raw == "{{input}}":
                            datum_raw = context.strip().split("\n")[0].strip() if context else ""
                        if not datum_raw:
                            datum_raw = _dt.datetime.today().strftime("%d.%m.%Y")
                        try:
                            datum_dt = _dt.datetime.strptime(datum_raw, "%d.%m.%Y")
                        except Exception:
                            output = f"❌ Ungültiges Datum: '{datum_raw}' (Format: TT.MM.JJJJ)"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── OAuth2-Bibliotheken laden ────────────────────────────────
                        try:
                            from google.oauth2.credentials          import Credentials as _GCreds
                            from google_auth_oauthlib.flow          import InstalledAppFlow as _Flow
                            from google.auth.transport.requests     import Request as _GRequest
                            from googleapiclient.discovery          import build as _gbuild
                        except ImportError:
                            output = ("❌ Google-Bibliotheken fehlen.\n"
                                      "Bitte ausführen:\n"
                                      "pip install google-auth google-auth-oauthlib "
                                      "google-auth-httplib2 google-api-python-client")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── credentials.json vorhanden? ──────────────────────────────
                        if not os.path.exists(creds_pfad):
                            output = (f"❌ credentials.json nicht gefunden: {creds_pfad}\n"
                                      "Bitte credentials.json in den Ordner "
                                      "data/google_kalender/ legen.\n"
                                      "(Einmalig herunterladen von Google Cloud Console "
                                      "→ APIs & Dienste → Anmeldedaten → OAuth-Client)")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Token laden oder erstmalig autorisieren ──────────────────
                        _gcreds = None
                        if os.path.exists(_TOKEN_PATH):
                            try:
                                _gcreds = _GCreds.from_authorized_user_file(
                                    _TOKEN_PATH, _GK_SCOPES)
                            except Exception:
                                _gcreds = None

                        if not _gcreds or not _gcreds.valid:
                            if _gcreds and _gcreds.expired and _gcreds.refresh_token:
                                try:
                                    _gcreds.refresh(_GRequest())
                                except Exception:
                                    _gcreds = None

                            if not _gcreds or not _gcreds.valid:
                                # Beim ersten Mal: Browser öffnet sich, User klickt "Allow"
                                _flow   = _Flow.from_client_secrets_file(
                                    creds_pfad, _GK_SCOPES)
                                _gcreds = _flow.run_local_server(port=0, open_browser=True)

                            # Token für nächste Ausführung speichern
                            os.makedirs(os.path.dirname(_TOKEN_PATH), exist_ok=True)
                            with open(_TOKEN_PATH, "w", encoding="utf-8") as _tf:
                                _tf.write(_gcreds.to_json())

                        # ── Google Calendar API-Service ──────────────────────────────
                        try:
                            _svc = _gbuild("calendar", "v3", credentials=_gcreds,
                                           cache_discovery=False)
                        except Exception as _se:
                            output = f"❌ Fehler beim Aufbau des API-Services: {_se}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # Hilfsfunktion: datetime → RFC3339 (lokal als UTC-naive übergeben)
                        def _rfc(dt_naive):
                            return dt_naive.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

                        # ── Operations ───────────────────────────────────────────────
                        if operation == "slots_lesen":
                            dauer_min  = int(config.get("dauer_minuten", 60))
                            arbeit_von = int(config.get("arbeit_von", 8))
                            arbeit_bis = int(config.get("arbeit_bis", 18))

                            tag_start_rfc = _rfc(datum_dt.replace(hour=0,  minute=0,  second=0))
                            tag_ende_rfc  = _rfc(datum_dt.replace(hour=23, minute=59, second=59))

                            try:
                                _ev_result = _svc.events().list(
                                    calendarId="primary",
                                    timeMin=tag_start_rfc,
                                    timeMax=tag_ende_rfc,
                                    singleEvents=True,
                                    orderBy="startTime",
                                ).execute()
                                ev_items = _ev_result.get("items", [])
                            except Exception as _e:
                                output = f"❌ Fehler beim Lesen der Termine: {_e}"
                                results[nid]  = str(output)
                                statuses[nid] = "error"
                                continue

                            def _parse_gev_dt(ev_time_dict):
                                """Google event start/end dict → naive datetime"""
                                if "dateTime" in ev_time_dict:
                                    _s = ev_time_dict["dateTime"][:19]
                                    return _dt.datetime.fromisoformat(_s)
                                if "date" in ev_time_dict:
                                    _d = ev_time_dict["date"]
                                    return _dt.datetime.fromisoformat(_d)
                                return None

                            belegte = []
                            for _ev in ev_items:
                                _vs = _parse_gev_dt(_ev.get("start", {}))
                                _ve = _parse_gev_dt(_ev.get("end",   {}))
                                if _vs and _ve:
                                    belegte.append((_vs, _ve))
                            belegte.sort()

                            arbeit_start = datum_dt.replace(hour=arbeit_von, minute=0, second=0)
                            arbeit_end   = datum_dt.replace(hour=arbeit_bis, minute=0, second=0)
                            dauer        = _dt.timedelta(minutes=dauer_min)
                            freie_slots  = []
                            zeiger       = arbeit_start
                            for (ev_von, ev_bis) in belegte:
                                if zeiger + dauer <= ev_von:
                                    freie_slots.append((zeiger, ev_von))
                                if ev_bis > zeiger:
                                    zeiger = ev_bis
                            if zeiger + dauer <= arbeit_end:
                                freie_slots.append((zeiger, arbeit_end))

                            if not freie_slots:
                                output = f"Keine freien Slots am {datum_raw} (Mindestdauer: {dauer_min} Min.)."
                            else:
                                zeilen = [f"FREIE ZEITFENSTER AM {datum_raw} (mind. {dauer_min} Min.):\n"]
                                for i, (von, bis) in enumerate(freie_slots, 1):
                                    diff = int((bis - von).total_seconds() // 60)
                                    zeilen.append(
                                        f"{i}. {von.strftime('%H:%M')} – "
                                        f"{bis.strftime('%H:%M')} ({diff} Min. frei)")
                                output = "\n".join(zeilen)

                        elif operation == "termin_eintragen":
                            titel        = config.get("titel", "").strip() or context.strip() or "Neuer Termin"
                            uhrzeit_von  = config.get("uhrzeit_von", "09:00").strip()
                            uhrzeit_bis  = config.get("uhrzeit_bis", "10:00").strip()
                            beschreibung = config.get("beschreibung", "").strip()
                            zeitzone     = config.get("zeitzone", "Europe/Berlin").strip() or "Europe/Berlin"
                            try:
                                h_von, m_von = map(int, uhrzeit_von.split(":"))
                                h_bis, m_bis = map(int, uhrzeit_bis.split(":"))
                                _ev_body = {
                                    "summary": titel,
                                    "start": {
                                        "dateTime": datum_dt.replace(
                                            hour=h_von, minute=m_von, second=0).isoformat(),
                                        "timeZone": zeitzone,
                                    },
                                    "end": {
                                        "dateTime": datum_dt.replace(
                                            hour=h_bis, minute=m_bis, second=0).isoformat(),
                                        "timeZone": zeitzone,
                                    },
                                }
                                if beschreibung:
                                    _ev_body["description"] = beschreibung
                                _created = _svc.events().insert(
                                    calendarId="primary", body=_ev_body).execute()
                                output = (f"✅ Termin eingetragen!\n"
                                          f"📅 {titel}\n"
                                          f"🕐 {datum_raw}, {uhrzeit_von} – {uhrzeit_bis} Uhr\n"
                                          f"🔗 {_created.get('htmlLink', '')}")
                            except Exception as _e:
                                output = f"❌ Fehler beim Eintragen: {_e}"

                        elif operation == "termin_loeschen":
                            titel_suche = config.get("titel", "").strip() or context.strip()
                            if not titel_suche:
                                output = "❌ Kein Titel angegeben."
                            else:
                                tag_start_rfc = _rfc(datum_dt.replace(hour=0,  minute=0,  second=0))
                                tag_ende_rfc  = _rfc(datum_dt.replace(hour=23, minute=59, second=59))
                                try:
                                    _ev_result = _svc.events().list(
                                        calendarId="primary",
                                        timeMin=tag_start_rfc,
                                        timeMax=tag_ende_rfc,
                                        singleEvents=True,
                                    ).execute()
                                    geloescht = False
                                    for _ev in _ev_result.get("items", []):
                                        _summary = _ev.get("summary", "")
                                        if titel_suche.lower() in _summary.lower():
                                            _svc.events().delete(
                                                calendarId="primary",
                                                eventId=_ev["id"]
                                            ).execute()
                                            output    = f"✅ Termin '{_summary}' am {datum_raw} gelöscht."
                                            geloescht = True
                                            break
                                    if not geloescht:
                                        output = f"❌ Kein Termin mit '{titel_suche}' am {datum_raw} gefunden."
                                except Exception as _e:
                                    output = f"❌ Fehler beim Löschen: {_e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "gmail":
                        import base64 as _b64
                        import email  as _eml

                        operation      = config.get("operation", "read")
                        creds_pfad     = config.get("credentials_pfad",
                                                    os.path.join("data", "google_kalender",
                                                                 "credentials.json")).strip()
                        _GM_TOKEN_PATH = os.path.join("data", "gmail", "token.json")
                        _GM_SCOPES     = [
                            "https://www.googleapis.com/auth/gmail.modify",
                            "https://www.googleapis.com/auth/gmail.send",
                        ]

                        # ── OAuth2-Bibliotheken laden ────────────────────────────────
                        try:
                            from google.oauth2.credentials          import Credentials as _GCreds2
                            from google_auth_oauthlib.flow          import InstalledAppFlow as _Flow2
                            from google.auth.transport.requests     import Request as _GRequest2
                            from googleapiclient.discovery          import build as _gbuild2
                        except ImportError:
                            output = ("❌ Google-Bibliotheken fehlen.\n"
                                      "pip install google-auth google-auth-oauthlib "
                                      "google-auth-httplib2 google-api-python-client")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        if not os.path.exists(creds_pfad):
                            output = (f"❌ credentials.json nicht gefunden: {creds_pfad}\n"
                                      "Dieselbe Datei wie beim Google Kalender Node verwenden.")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Token laden oder erstmalig autorisieren ──────────────────
                        _gmcreds = None
                        if os.path.exists(_GM_TOKEN_PATH):
                            try:
                                _gmcreds = _GCreds2.from_authorized_user_file(
                                    _GM_TOKEN_PATH, _GM_SCOPES)
                            except Exception:
                                _gmcreds = None

                        if not _gmcreds or not _gmcreds.valid:
                            if _gmcreds and _gmcreds.expired and _gmcreds.refresh_token:
                                try:
                                    _gmcreds.refresh(_GRequest2())
                                except Exception:
                                    _gmcreds = None

                            if not _gmcreds or not _gmcreds.valid:
                                _flow2   = _Flow2.from_client_secrets_file(
                                    creds_pfad, _GM_SCOPES)
                                _gmcreds = _flow2.run_local_server(port=0, open_browser=True)

                            os.makedirs(os.path.dirname(_GM_TOKEN_PATH), exist_ok=True)
                            with open(_GM_TOKEN_PATH, "w", encoding="utf-8") as _tf2:
                                _tf2.write(_gmcreds.to_json())

                        try:
                            _gmsvc = _gbuild2("gmail", "v1", credentials=_gmcreds,
                                              cache_discovery=False)
                        except Exception as _se:
                            output = f"❌ Fehler beim Aufbau des Gmail-Services: {_se}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Hilfsfunktion: Body aus MIME-Payload extrahieren ─────────
                        def _gm_body(payload):
                            mime = payload.get("mimeType", "")
                            if mime == "text/plain":
                                data = payload.get("body", {}).get("data", "")
                                if data:
                                    return _b64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                            if mime.startswith("multipart/"):
                                for part in payload.get("parts", []):
                                    result = _gm_body(part)
                                    if result:
                                        return result
                            return ""

                        def _gm_header(headers, name):
                            return next((h["value"] for h in headers
                                         if h["name"].lower() == name.lower()), "")

                        # ── Operations ───────────────────────────────────────────────
                        if operation == "read":
                            anzahl        = max(1, int(config.get("anzahl", 5)))
                            label         = config.get("label", "INBOX").strip() or "INBOX"
                            nur_ungelesen = config.get("nur_ungelesen", "nein").lower() == "ja"

                            _q = "is:unread" if nur_ungelesen else ""
                            try:
                                _lst = _gmsvc.users().messages().list(
                                    userId="me",
                                    labelIds=[label],
                                    q=_q,
                                    maxResults=anzahl,
                                ).execute()
                                _msgs = _lst.get("messages", [])
                                if not _msgs:
                                    output = "📭 Keine E-Mails gefunden."
                                else:
                                    zeilen = []
                                    for _m in _msgs:
                                        _md = _gmsvc.users().messages().get(
                                            userId="me", id=_m["id"], format="full"
                                        ).execute()
                                        _hdrs = _md.get("payload", {}).get("headers", [])
                                        _subj = _gm_header(_hdrs, "Subject") or "(kein Betreff)"
                                        _von  = _gm_header(_hdrs, "From") or "?"
                                        _dat  = _gm_header(_hdrs, "Date")[:25]
                                        _body = _gm_body(_md.get("payload", {})).strip()[:250]
                                        if len(_body) == 250:
                                            _body += "…"
                                        zeilen.append(
                                            f"── E-Mail ──────────────────────\n"
                                            f"Von:     {_von}\n"
                                            f"Betreff: {_subj}\n"
                                            f"Datum:   {_dat}\n"
                                            f"Text:    {_body or '[kein Text]'}"
                                        )
                                    output = f"📬 {len(zeilen)} E-Mail(s):\n\n" + "\n\n".join(zeilen)
                            except Exception as _e:
                                output = f"❌ Fehler beim Lesen: {_e}"

                        elif operation == "send":
                            an      = config.get("an", "").strip()
                            betreff = config.get("betreff", "").strip()
                            text    = config.get("text", "{{input}}").strip() or "{{input}}"
                            if "{{input}}" in text and context:
                                text = text.replace("{{input}}", context)
                            elif not text and context:
                                text = context
                            if not an:
                                output = "❌ Kein Empfänger (Feld 'An') angegeben."
                            elif not betreff:
                                output = "❌ Kein Betreff angegeben."
                            elif not text:
                                output = "❌ Kein Text angegeben."
                            else:
                                try:
                                    from email.mime.text      import MIMEText as _MT
                                    from email.mime.multipart import MIMEMultipart as _MM
                                    _msg = _MM()
                                    _msg["To"]      = an
                                    _msg["Subject"] = betreff
                                    _msg.attach(_MT(text, "plain", "utf-8"))
                                    _raw = _b64.urlsafe_b64encode(
                                        _msg.as_bytes()).decode("utf-8")
                                    _gmsvc.users().messages().send(
                                        userId="me", body={"raw": _raw}).execute()
                                    output = f"✅ E-Mail gesendet an {an} · Betreff: {betreff}"
                                except Exception as _e:
                                    output = f"❌ Sendefehler: {_e}"

                        elif operation == "search":
                            query  = config.get("query", "").strip()
                            if "{{input}}" in query and context:
                                query = query.replace("{{input}}", context.strip())
                            anzahl = max(1, int(config.get("anzahl", 5)))
                            if not query:
                                output = "❌ Kein Suchbegriff angegeben."
                            else:
                                try:
                                    _lst = _gmsvc.users().messages().list(
                                        userId="me", q=query, maxResults=anzahl
                                    ).execute()
                                    _msgs = _lst.get("messages", [])
                                    if not _msgs:
                                        output = f"📭 Keine E-Mails für '{query}' gefunden."
                                    else:
                                        zeilen = []
                                        for _m in _msgs:
                                            _md = _gmsvc.users().messages().get(
                                                userId="me", id=_m["id"], format="full"
                                            ).execute()
                                            _hdrs = _md.get("payload", {}).get("headers", [])
                                            _subj = _gm_header(_hdrs, "Subject") or "(kein Betreff)"
                                            _von  = _gm_header(_hdrs, "From") or "?"
                                            _dat  = _gm_header(_hdrs, "Date")[:25]
                                            _body = _gm_body(_md.get("payload", {})).strip()[:200]
                                            if len(_body) == 200:
                                                _body += "…"
                                            zeilen.append(
                                                f"── Treffer ──────────────────────\n"
                                                f"Von:     {_von}\n"
                                                f"Betreff: {_subj}\n"
                                                f"Datum:   {_dat}\n"
                                                f"Text:    {_body or '[kein Text]'}"
                                            )
                                        output = (f"🔍 {len(zeilen)} Treffer für '{query}':"
                                                  f"\n\n" + "\n\n".join(zeilen))
                                except Exception as _e:
                                    output = f"❌ Suchfehler: {_e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "google_docs":
                        import re as _re
                        import datetime as _dt2

                        operation      = config.get("operation", "lesen")
                        creds_pfad     = config.get("credentials_pfad",
                                                    os.path.join("data", "google_kalender",
                                                                 "credentials.json")).strip()
                        _GD_TOKEN_PATH = os.path.join("data", "google_docs", "token.json")
                        _GD_SCOPES     = [
                            "https://www.googleapis.com/auth/documents",
                            "https://www.googleapis.com/auth/drive.file",
                        ]

                        # ── OAuth2 laden ─────────────────────────────────────────────
                        try:
                            from google.oauth2.credentials      import Credentials as _GCreds3
                            from google_auth_oauthlib.flow      import InstalledAppFlow as _Flow3
                            from google.auth.transport.requests import Request as _GRequest3
                            from googleapiclient.discovery      import build as _gbuild3
                        except ImportError:
                            output = ("❌ Google-Bibliotheken fehlen.\n"
                                      "pip install google-auth google-auth-oauthlib "
                                      "google-auth-httplib2 google-api-python-client")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        if not os.path.exists(creds_pfad):
                            output = (f"❌ credentials.json nicht gefunden: {creds_pfad}\n"
                                      "Dieselbe Datei wie bei Google Kalender & Gmail verwenden.")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Token ────────────────────────────────────────────────────
                        _gdcreds = None
                        if os.path.exists(_GD_TOKEN_PATH):
                            try:
                                _gdcreds = _GCreds3.from_authorized_user_file(
                                    _GD_TOKEN_PATH, _GD_SCOPES)
                            except Exception:
                                _gdcreds = None

                        if not _gdcreds or not _gdcreds.valid:
                            if _gdcreds and _gdcreds.expired and _gdcreds.refresh_token:
                                try:
                                    _gdcreds.refresh(_GRequest3())
                                except Exception:
                                    _gdcreds = None
                            if not _gdcreds or not _gdcreds.valid:
                                _flow3   = _Flow3.from_client_secrets_file(
                                    creds_pfad, _GD_SCOPES)
                                _gdcreds = _flow3.run_local_server(port=0, open_browser=True)
                            os.makedirs(os.path.dirname(_GD_TOKEN_PATH), exist_ok=True)
                            with open(_GD_TOKEN_PATH, "w", encoding="utf-8") as _tf3:
                                _tf3.write(_gdcreds.to_json())

                        try:
                            _gdsvc = _gbuild3("docs", "v1", credentials=_gdcreds,
                                              cache_discovery=False)
                        except Exception as _se:
                            output = f"❌ Fehler beim Aufbau des Docs-Services: {_se}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Hilfsfunktion: Doc-ID aus URL oder direkt ─────────────────
                        def _doc_id(url_or_id):
                            m = _re.search(r'/document/d/([a-zA-Z0-9_-]+)', url_or_id)
                            return m.group(1) if m else url_or_id.strip()

                        # ── Hilfsfunktion: Text aus Docs-Body extrahieren ─────────────
                        def _doc_text(body_content):
                            lines = []
                            for elem in body_content:
                                if "paragraph" in elem:
                                    line = ""
                                    for pe in elem["paragraph"].get("elements", []):
                                        if "textRun" in pe:
                                            line += pe["textRun"].get("content", "")
                                    lines.append(line)
                            return "".join(lines)

                        # ── Operations ───────────────────────────────────────────────
                        if operation == "lesen":
                            url_raw    = config.get("dokument_url", "").strip()
                            if "{{input}}" in url_raw and context:
                                url_raw = url_raw.replace("{{input}}", context.strip())
                            max_zeichen = int(config.get("max_zeichen", 5000))
                            if not url_raw:
                                output = "❌ Keine Dokument-URL angegeben."
                            else:
                                try:
                                    _did  = _doc_id(url_raw)
                                    _doc  = _gdsvc.documents().get(documentId=_did).execute()
                                    _titel = _doc.get("title", "Unbekannt")
                                    _text  = _doc_text(
                                        _doc.get("body", {}).get("content", []))
                                    _text  = _text.strip()
                                    _trunc = ""
                                    if len(_text) > max_zeichen:
                                        _text  = _text[:max_zeichen]
                                        _trunc = f"\n\n[… gekürzt auf {max_zeichen} Zeichen]"
                                    output = (f"📄 Dokument: {_titel}\n"
                                              f"{'─'*40}\n"
                                              f"{_text}{_trunc}")
                                except Exception as _e:
                                    output = f"❌ Fehler beim Lesen: {_e}"

                        elif operation == "anhaengen":
                            url_raw    = config.get("dokument_url", "").strip()
                            text_neu   = config.get("text", "{{input}}").strip() or "{{input}}"
                            trennlinie = config.get("trennlinie", "ja").lower() == "ja"
                            if "{{input}}" in text_neu and context:
                                text_neu = text_neu.replace("{{input}}", context)
                            elif not text_neu and context:
                                text_neu = context
                            if not url_raw:
                                output = "❌ Keine Dokument-URL angegeben."
                            elif not text_neu:
                                output = "❌ Kein Text zum Anhängen."
                            else:
                                try:
                                    _did = _doc_id(url_raw)
                                    _doc = _gdsvc.documents().get(documentId=_did).execute()
                                    _titel = _doc.get("title", "Dokument")
                                    # End-Index ermitteln
                                    _body_content = _doc.get("body", {}).get("content", [])
                                    _end_idx = _body_content[-1]["endIndex"] - 1 if _body_content else 1
                                    # Text zusammenbauen
                                    if trennlinie:
                                        _ts   = _dt2.datetime.now().strftime("%d.%m.%Y %H:%M")
                                        _eintrag = f"\n\n── {_ts} ──────────────────────\n{text_neu}"
                                    else:
                                        _eintrag = f"\n{text_neu}"
                                    _requests = [{
                                        "insertText": {
                                            "location": {"index": _end_idx},
                                            "text": _eintrag,
                                        }
                                    }]
                                    _gdsvc.documents().batchUpdate(
                                        documentId=_did,
                                        body={"requests": _requests}
                                    ).execute()
                                    output = (f"✅ Text angehängt in: {_titel}\n"
                                              f"📝 {len(text_neu)} Zeichen geschrieben.")
                                except Exception as _e:
                                    output = f"❌ Fehler beim Anhängen: {_e}"

                        elif operation == "erstellen":
                            titel_neu = config.get("titel", "").strip() or "{{input}}"
                            inhalt    = config.get("inhalt", "{{input}}").strip()
                            if "{{input}}" in titel_neu and context:
                                titel_neu = titel_neu.replace("{{input}}", context.strip().split("\n")[0])
                            elif titel_neu == "{{input}}" and not context:
                                titel_neu = f"Dokument vom {_dt2.datetime.now().strftime('%d.%m.%Y')}"
                            if "{{input}}" in inhalt and context:
                                inhalt = inhalt.replace("{{input}}", context)
                            try:
                                _new_doc = _gdsvc.documents().create(
                                    body={"title": titel_neu}).execute()
                                _did     = _new_doc["documentId"]
                                _link    = f"https://docs.google.com/document/d/{_did}/edit"
                                if inhalt and inhalt != "{{input}}":
                                    _gdsvc.documents().batchUpdate(
                                        documentId=_did,
                                        body={"requests": [{
                                            "insertText": {
                                                "location": {"index": 1},
                                                "text": inhalt,
                                            }
                                        }]}
                                    ).execute()
                                output = (f"✅ Dokument erstellt: {titel_neu}\n"
                                          f"🔗 {_link}")
                            except Exception as _e:
                                output = f"❌ Fehler beim Erstellen: {_e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "google_sheets":
                        import re as _re2
                        import datetime as _dt3

                        operation      = config.get("operation", "bereich_lesen")
                        creds_pfad     = config.get("credentials_pfad",
                                                    os.path.join("data", "google_kalender",
                                                                 "credentials.json")).strip()
                        tabellen_url   = config.get("tabellen_url", "").strip()
                        tabellenblatt  = config.get("tabellenblatt", "").strip() or "Tabelle1"
                        _GS_TOKEN_PATH = os.path.join("data", "google_sheets", "token.json")
                        _GS_SCOPES     = ["https://www.googleapis.com/auth/spreadsheets"]

                        # ── OAuth2 laden ─────────────────────────────────────────────
                        try:
                            from google.oauth2.credentials      import Credentials as _GCreds4
                            from google_auth_oauthlib.flow      import InstalledAppFlow as _Flow4
                            from google.auth.transport.requests import Request as _GRequest4
                            from googleapiclient.discovery      import build as _gbuild4
                        except ImportError:
                            output = ("❌ Google-Bibliotheken fehlen.\n"
                                      "pip install google-auth google-auth-oauthlib "
                                      "google-auth-httplib2 google-api-python-client")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        if not os.path.exists(creds_pfad):
                            output = (f"❌ credentials.json nicht gefunden: {creds_pfad}\n"
                                      "Dieselbe Datei wie bei allen Google Nodes verwenden.")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        if not tabellen_url:
                            output = "❌ Keine Tabellen-URL angegeben."
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Token ────────────────────────────────────────────────────
                        _gscreds = None
                        if os.path.exists(_GS_TOKEN_PATH):
                            try:
                                _gscreds = _GCreds4.from_authorized_user_file(
                                    _GS_TOKEN_PATH, _GS_SCOPES)
                            except Exception:
                                _gscreds = None

                        if not _gscreds or not _gscreds.valid:
                            if _gscreds and _gscreds.expired and _gscreds.refresh_token:
                                try:
                                    _gscreds.refresh(_GRequest4())
                                except Exception:
                                    _gscreds = None
                            if not _gscreds or not _gscreds.valid:
                                _flow4   = _Flow4.from_client_secrets_file(
                                    creds_pfad, _GS_SCOPES)
                                _gscreds = _flow4.run_local_server(port=0, open_browser=True)
                            os.makedirs(os.path.dirname(_GS_TOKEN_PATH), exist_ok=True)
                            with open(_GS_TOKEN_PATH, "w", encoding="utf-8") as _tf4:
                                _tf4.write(_gscreds.to_json())

                        try:
                            _gssvc = _gbuild4("sheets", "v4", credentials=_gscreds,
                                              cache_discovery=False)
                        except Exception as _se:
                            output = f"❌ Fehler beim Aufbau des Sheets-Services: {_se}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Hilfsfunktion: Spreadsheet-ID aus URL ─────────────────────
                        def _sheet_id(url_or_id):
                            m = _re2.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
                            return m.group(1) if m else url_or_id.strip()

                        _sid = _sheet_id(tabellen_url)

                        # ── Operations ───────────────────────────────────────────────
                        if operation == "bereich_lesen":
                            bereich       = config.get("bereich", "A1:Z100").strip() or "A1:Z100"
                            ausgabe_fmt   = config.get("ausgabe_format", "text")
                            _range_name   = f"{tabellenblatt}!{bereich}"
                            try:
                                _res = _gssvc.spreadsheets().values().get(
                                    spreadsheetId=_sid,
                                    range=_range_name,
                                ).execute()
                                _rows = _res.get("values", [])
                                if not _rows:
                                    output = f"📭 Keine Daten in '{_range_name}'."
                                elif ausgabe_fmt == "csv":
                                    _lines = [",".join(
                                        f'"{c}"' if "," in c else c
                                        for c in row) for row in _rows]
                                    output = "\n".join(_lines)
                                else:
                                    # Erste Zeile als Header behandeln
                                    _header = _rows[0] if _rows else []
                                    _zeilen = []
                                    for i, row in enumerate(_rows):
                                        if i == 0:
                                            continue  # Header überspringen
                                        if _header:
                                            _zeilen.append(" | ".join(
                                                f"{_header[j] if j < len(_header) else j+1}: {v}"
                                                for j, v in enumerate(row)
                                            ))
                                        else:
                                            _zeilen.append(" | ".join(row))
                                    _hdr_str = " | ".join(_header) if _header else ""
                                    output = (f"📊 {tabellenblatt} · {bereich} "
                                              f"({len(_rows)-1} Zeilen):\n"
                                              f"{'─'*40}\n"
                                              + (f"Spalten: {_hdr_str}\n{'─'*40}\n" if _header else "")
                                              + "\n".join(_zeilen[:50])
                                              + (f"\n[…+{len(_zeilen)-50} weitere]"
                                                 if len(_zeilen) > 50 else ""))
                            except Exception as _e:
                                output = f"❌ Fehler beim Lesen: {_e}"

                        elif operation == "zeile_anhaengen":
                            werte_raw = config.get("werte", "{{input}}").strip() or "{{input}}"
                            _now      = _dt3.datetime.now()
                            # Template-Variablen ersetzen
                            if "{{input}}" in werte_raw and context:
                                werte_raw = werte_raw.replace("{{input}}", context.strip())
                            werte_raw = werte_raw.replace(
                                "{{datum}}", _now.strftime("%d.%m.%Y"))
                            werte_raw = werte_raw.replace(
                                "{{uhrzeit}}", _now.strftime("%H:%M"))
                            # CSV-Parsing: kommagetrennte Werte → Liste
                            import csv as _csv
                            import io  as _io
                            try:
                                _reader = _csv.reader(_io.StringIO(werte_raw))
                                _values = next(_reader, [werte_raw])
                                _values = [v.strip() for v in _values]
                            except Exception:
                                _values = [werte_raw]
                            try:
                                _gssvc.spreadsheets().values().append(
                                    spreadsheetId=_sid,
                                    range=f"{tabellenblatt}!A1",
                                    valueInputOption="USER_ENTERED",
                                    insertDataOption="INSERT_ROWS",
                                    body={"values": [_values]},
                                ).execute()
                                output = (f"✅ Zeile angehängt in '{tabellenblatt}':\n"
                                          f"📝 {' | '.join(_values)}")
                            except Exception as _e:
                                output = f"❌ Fehler beim Anhängen: {_e}"

                        elif operation == "zelle_schreiben":
                            zelle = config.get("zelle", "A1").strip() or "A1"
                            wert  = config.get("wert", "{{input}}").strip()
                            if "{{input}}" in wert and context:
                                wert = wert.replace("{{input}}", context.strip())
                            try:
                                _gssvc.spreadsheets().values().update(
                                    spreadsheetId=_sid,
                                    range=f"{tabellenblatt}!{zelle}",
                                    valueInputOption="USER_ENTERED",
                                    body={"values": [[wert]]},
                                ).execute()
                                output = f"✅ Zelle {zelle} in '{tabellenblatt}' = {wert}"
                            except Exception as _e:
                                output = f"❌ Fehler beim Schreiben: {_e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "google_drive":
                        import re as _re3

                        operation      = config.get("operation", "docs_lesen")
                        creds_pfad     = config.get("credentials_pfad",
                                                    os.path.join("data", "google_kalender",
                                                                 "credentials.json")).strip()
                        _GDR_TOKEN_PATH = os.path.join("data", "google_drive", "token.json")
                        _GDR_SCOPES     = [
                            "https://www.googleapis.com/auth/drive.readonly",
                            "https://www.googleapis.com/auth/drive.file",
                            "https://www.googleapis.com/auth/documents.readonly",
                        ]

                        # ── OAuth2 laden ─────────────────────────────────────────────
                        try:
                            from google.oauth2.credentials      import Credentials as _GCreds5
                            from google_auth_oauthlib.flow      import InstalledAppFlow as _Flow5
                            from google.auth.transport.requests import Request as _GRequest5
                            from googleapiclient.discovery      import build as _gbuild5
                        except ImportError:
                            output = ("❌ Google-Bibliotheken fehlen.\n"
                                      "pip install google-auth google-auth-oauthlib "
                                      "google-auth-httplib2 google-api-python-client")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        if not os.path.exists(creds_pfad):
                            output = (f"❌ credentials.json nicht gefunden: {creds_pfad}")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Token ────────────────────────────────────────────────────
                        _gdrcreds = None
                        if os.path.exists(_GDR_TOKEN_PATH):
                            try:
                                _gdrcreds = _GCreds5.from_authorized_user_file(
                                    _GDR_TOKEN_PATH, _GDR_SCOPES)
                            except Exception:
                                _gdrcreds = None

                        if not _gdrcreds or not _gdrcreds.valid:
                            if _gdrcreds and _gdrcreds.expired and _gdrcreds.refresh_token:
                                try:
                                    _gdrcreds.refresh(_GRequest5())
                                except Exception:
                                    _gdrcreds = None
                            if not _gdrcreds or not _gdrcreds.valid:
                                _flow5    = _Flow5.from_client_secrets_file(
                                    creds_pfad, _GDR_SCOPES)
                                _gdrcreds = _flow5.run_local_server(port=0, open_browser=True)
                            os.makedirs(os.path.dirname(_GDR_TOKEN_PATH), exist_ok=True)
                            with open(_GDR_TOKEN_PATH, "w", encoding="utf-8") as _tf5:
                                _tf5.write(_gdrcreds.to_json())

                        try:
                            _gdrsvc  = _gbuild5("drive", "v3", credentials=_gdrcreds,
                                                cache_discovery=False)
                            _docssvc = _gbuild5("docs",  "v1", credentials=_gdrcreds,
                                                cache_discovery=False)
                        except Exception as _se:
                            output = f"❌ Fehler beim Aufbau des Drive-Services: {_se}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Hilfsfunktion: Docs-Text extrahieren ──────────────────────
                        def _extract_doc_text(body_content):
                            lines = []
                            for elem in body_content:
                                if "paragraph" in elem:
                                    line = ""
                                    for pe in elem["paragraph"].get("elements", []):
                                        if "textRun" in pe:
                                            line += pe["textRun"].get("content", "")
                                    lines.append(line)
                            return "".join(lines)

                        # ── Operations ───────────────────────────────────────────────
                        if operation == "docs_lesen":
                            anzahl           = max(1, int(config.get("anzahl", 10)))
                            max_z_pro_doc    = int(config.get("max_zeichen_pro_doc", 2000))
                            suche            = config.get("suche", "").strip()

                            _q = "mimeType='application/vnd.google-apps.document' and trashed=false"
                            if suche:
                                _q += f" and name contains '{suche}'"

                            try:
                                _lst = _gdrsvc.files().list(
                                    q=_q,
                                    pageSize=anzahl,
                                    orderBy="modifiedTime desc",
                                    fields="files(id,name,modifiedTime)",
                                ).execute()
                                _files = _lst.get("files", [])
                            except Exception as _e:
                                output = f"❌ Fehler beim Auflisten: {_e}"
                                results[nid]  = str(output)
                                statuses[nid] = "error"
                                continue

                            if not _files:
                                output = "📭 Keine Google Docs gefunden."
                            else:
                                teile = [f"GOOGLE DRIVE – {len(_files)} DOKUMENT(E):\n{'═'*50}\n"]
                                for _f in _files:
                                    _fname = _f.get("name", "Unbekannt")
                                    _fmod  = _f.get("modifiedTime", "")[:10]
                                    try:
                                        _doc   = _docssvc.documents().get(
                                            documentId=_f["id"]).execute()
                                        _text  = _extract_doc_text(
                                            _doc.get("body", {}).get("content", [])
                                        ).strip()
                                        _trunc = ""
                                        if len(_text) > max_z_pro_doc:
                                            _text  = _text[:max_z_pro_doc]
                                            _trunc = " […gekürzt]"
                                        teile.append(
                                            f"📄 {_fname}  ({_fmod}){_trunc}\n"
                                            f"{'─'*40}\n{_text}\n"
                                        )
                                    except Exception:
                                        teile.append(f"📄 {_fname}  ({_fmod})\n[Inhalt nicht lesbar]\n")
                                output = "\n".join(teile)

                        elif operation == "dateien_auflisten":
                            anzahl    = max(1, int(config.get("anzahl", 20)))
                            dateityp  = config.get("dateityp", "docs")
                            suche     = config.get("suche", "").strip()

                            _mime_map = {
                                "docs":   "mimeType='application/vnd.google-apps.document'",
                                "sheets": "mimeType='application/vnd.google-apps.spreadsheet'",
                                "alle":   "mimeType!='application/vnd.google-apps.folder'",
                            }
                            _q = _mime_map.get(dateityp, _mime_map["docs"]) + " and trashed=false"
                            if suche:
                                _q += f" and name contains '{suche}'"

                            try:
                                _lst = _gdrsvc.files().list(
                                    q=_q,
                                    pageSize=anzahl,
                                    orderBy="modifiedTime desc",
                                    fields="files(id,name,mimeType,modifiedTime,size)",
                                ).execute()
                                _files = _lst.get("files", [])
                            except Exception as _e:
                                output = f"❌ Fehler beim Auflisten: {_e}"
                                results[nid]  = str(output)
                                statuses[nid] = "error"
                                continue

                            if not _files:
                                output = "📭 Keine Dateien gefunden."
                            else:
                                _typ_icons = {
                                    "application/vnd.google-apps.document":     "📄",
                                    "application/vnd.google-apps.spreadsheet":  "📊",
                                    "application/vnd.google-apps.presentation": "🎨",
                                    "application/pdf":                          "📕",
                                }
                                zeilen = [f"📁 {len(_files)} Datei(en) in Google Drive:\n"]
                                for _f in _files:
                                    _icon = _typ_icons.get(_f.get("mimeType",""), "📎")
                                    _mod  = _f.get("modifiedTime","")[:10]
                                    zeilen.append(
                                        f"{_icon} {_f['name']}  · zuletzt: {_mod}  · ID: {_f['id']}")
                                output = "\n".join(zeilen)

                        elif operation == "hochladen":
                            lokaler_pfad = config.get("lokaler_pfad", "").strip()
                            if "{{input}}" in lokaler_pfad and context:
                                lokaler_pfad = lokaler_pfad.replace("{{input}}", context.strip())
                            ordner_id    = config.get("ordner_id", "").strip()

                            if not lokaler_pfad:
                                output = "❌ Kein lokaler Dateipfad angegeben."
                            elif not os.path.exists(lokaler_pfad):
                                output = f"❌ Datei nicht gefunden: {lokaler_pfad}"
                            else:
                                try:
                                    from googleapiclient.http import MediaFileUpload as _MFU
                                    import mimetypes as _mt
                                    _fname    = os.path.basename(lokaler_pfad)
                                    _mime, _  = _mt.guess_type(lokaler_pfad)
                                    _mime     = _mime or "application/octet-stream"
                                    _meta     = {"name": _fname}
                                    if ordner_id:
                                        _meta["parents"] = [ordner_id]
                                    _media    = _MFU(lokaler_pfad, mimetype=_mime, resumable=True)
                                    _uploaded = _gdrsvc.files().create(
                                        body=_meta, media_body=_media, fields="id,name,webViewLink"
                                    ).execute()
                                    output = (f"✅ Datei hochgeladen: {_fname}\n"
                                              f"🔗 {_uploaded.get('webViewLink','')}\n"
                                              f"🆔 ID: {_uploaded.get('id','')}")
                                except Exception as _e:
                                    output = f"❌ Upload-Fehler: {_e}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {operation}"

                    elif ntype == "google_forms":
                        import re as _re4
                        import datetime as _dt4

                        operation      = config.get("operation", "neue_antworten")
                        formular_raw   = config.get("formular_id", "").strip()
                        creds_pfad     = config.get("credentials_pfad",
                                                    os.path.join("data", "google_kalender",
                                                                 "credentials.json")).strip()
                        _GF_TOKEN_PATH = os.path.join("data", "google_forms", "token.json")
                        _GF_SCOPES     = [
                            "https://www.googleapis.com/auth/forms.responses.readonly",
                            "https://www.googleapis.com/auth/forms.body.readonly",
                        ]

                        # ── Formular-ID aus URL extrahieren ──────────────────────────
                        _fm = _re4.search(r'/forms/d/([a-zA-Z0-9_-]+)', formular_raw)
                        formular_id = _fm.group(1) if _fm else formular_raw

                        if not formular_id:
                            output = "❌ Keine Formular-URL oder ID angegeben."
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── OAuth2 laden ─────────────────────────────────────────────
                        try:
                            from google.oauth2.credentials      import Credentials as _GCreds6
                            from google_auth_oauthlib.flow      import InstalledAppFlow as _Flow6
                            from google.auth.transport.requests import Request as _GRequest6
                            from googleapiclient.discovery      import build as _gbuild6
                        except ImportError:
                            output = ("❌ Google-Bibliotheken fehlen.\n"
                                      "pip install google-auth google-auth-oauthlib "
                                      "google-auth-httplib2 google-api-python-client")
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        if not os.path.exists(creds_pfad):
                            output = f"❌ credentials.json nicht gefunden: {creds_pfad}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Token ────────────────────────────────────────────────────
                        _gfcreds = None
                        if os.path.exists(_GF_TOKEN_PATH):
                            try:
                                _gfcreds = _GCreds6.from_authorized_user_file(
                                    _GF_TOKEN_PATH, _GF_SCOPES)
                            except Exception:
                                _gfcreds = None

                        if not _gfcreds or not _gfcreds.valid:
                            if _gfcreds and _gfcreds.expired and _gfcreds.refresh_token:
                                try:
                                    _gfcreds.refresh(_GRequest6())
                                except Exception:
                                    _gfcreds = None
                            if not _gfcreds or not _gfcreds.valid:
                                _flow6   = _Flow6.from_client_secrets_file(
                                    creds_pfad, _GF_SCOPES)
                                _gfcreds = _flow6.run_local_server(port=0, open_browser=True)
                            os.makedirs(os.path.dirname(_GF_TOKEN_PATH), exist_ok=True)
                            with open(_GF_TOKEN_PATH, "w", encoding="utf-8") as _tf6:
                                _tf6.write(_gfcreds.to_json())

                        try:
                            _gfsvc = _gbuild6("forms", "v1", credentials=_gfcreds,
                                              cache_discovery=False)
                        except Exception as _se:
                            output = f"❌ Fehler beim Aufbau des Forms-Services: {_se}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Formular-Struktur laden (Fragen-Titel) ───────────────────
                        try:
                            _form_meta = _gfsvc.forms().get(formId=formular_id).execute()
                            _form_titel = _form_meta.get("info", {}).get("title", "Formular")
                            # Fragen-Map: questionId → Titel
                            _fragen = {}
                            for _item in _form_meta.get("items", []):
                                _qid = _item.get("questionItem", {}).get(
                                    "question", {}).get("questionId")
                                _lbl = _item.get("title", f"Frage {_qid}")
                                if _qid:
                                    _fragen[_qid] = _lbl
                        except Exception as _e:
                            output = f"❌ Formular nicht lesbar: {_e}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # ── Letzten Abruf-Zeitstempel laden/speichern ────────────────
                        _ts_path = os.path.join("data", "google_forms",
                                                f"last_{formular_id[:20]}.json")

                        def _load_last_ts():
                            if os.path.exists(_ts_path):
                                try:
                                    with open(_ts_path, "r") as _f:
                                        return json.load(_f).get("last_check", "")
                                except Exception:
                                    pass
                            return ""

                        def _save_last_ts(ts):
                            os.makedirs(os.path.dirname(_ts_path), exist_ok=True)
                            with open(_ts_path, "w") as _f:
                                json.dump({"last_check": ts,
                                           "updated": _dt4.datetime.now().isoformat()}, _f)

                        # ── Hilfsfunktion: Antwort formatieren ───────────────────────
                        def _fmt_antwort(resp, fragen_map):
                            _ts   = resp.get("lastSubmittedTime", "")[:16].replace("T", " ")
                            zeile = [f"📋 Einsendung vom {_ts}"]
                            for _qid, _ans in resp.get("answers", {}).items():
                                _frage = fragen_map.get(_qid, _qid)
                                _werte = _ans.get("textAnswers", {}).get("answers", [])
                                _wert  = ", ".join(a.get("value", "") for a in _werte)
                                zeile.append(f"  • {_frage}: {_wert}")
                            return "\n".join(zeile)

                        # ── Operations ───────────────────────────────────────────────
                        _filter_ts = ""
                        if operation == "neue_antworten":
                            _filter_ts = _load_last_ts()

                        try:
                            _params = {"formId": formular_id}
                            if operation == "alle_antworten":
                                _params["pageSize"] = max(1, int(config.get("anzahl", 50)))
                            _resp_list = _gfsvc.forms().responses().list(**_params).execute()
                            _responses = _resp_list.get("responses", [])
                        except Exception as _e:
                            output = f"❌ Fehler beim Abrufen der Antworten: {_e}"
                            results[nid]  = str(output)
                            statuses[nid] = "error"
                            continue

                        # Neue filtern (nach Zeitstempel)
                        if _filter_ts and operation == "neue_antworten":
                            _responses = [
                                r for r in _responses
                                if r.get("lastSubmittedTime", "") > _filter_ts
                            ]

                        # Letzten Zeitstempel aktualisieren
                        if _responses:
                            _newest_ts = max(
                                r.get("lastSubmittedTime", "") for r in _responses)
                            _save_last_ts(_newest_ts)

                        if not _responses:
                            if operation == "neue_antworten":
                                output = f"📭 Keine neuen Antworten in '{_form_titel}'."
                            else:
                                output = f"📭 Noch keine Antworten in '{_form_titel}'."
                        else:
                            _teile = [
                                f"📋 FORMULAR: {_form_titel}\n"
                                f"{len(_responses)} Antwort(en):\n{'═'*50}\n"
                            ]
                            for _r in _responses:
                                _teile.append(_fmt_antwort(_r, _fragen))
                                _teile.append("─" * 40)
                            output = "\n".join(_teile)

                    # ── condition ────────────────────────────────────────────
                    elif ntype == "condition":
                        cond_raw = config.get("condition", "").strip()
                        if "{{input}}" in cond_raw and context:
                            cond_raw = cond_raw.replace("{{input}}", context)
                        # Evaluiere einfache Bedingungen
                        passed = False
                        c = cond_raw.lower()
                        if "==" in cond_raw:
                            l, r2 = cond_raw.split("==", 1)
                            passed = l.strip() == r2.strip().strip("'\"")
                        elif "!=" in cond_raw:
                            l, r2 = cond_raw.split("!=", 1)
                            passed = l.strip() != r2.strip().strip("'\"")
                        elif "enthält" in c or "contains" in c:
                            parts = cond_raw.replace("enthält", "contains").split("contains", 1)
                            passed = parts[1].strip().strip("'\"").lower() in parts[0].strip().lower()
                        elif ">" in cond_raw:
                            l, r2 = cond_raw.split(">", 1)
                            try: passed = float(l.strip()) > float(r2.strip())
                            except: passed = l.strip() > r2.strip()
                        elif "<" in cond_raw:
                            l, r2 = cond_raw.split("<", 1)
                            try: passed = float(l.strip()) < float(r2.strip())
                            except: passed = l.strip() < r2.strip()
                        elif cond_raw:
                            passed = bool(cond_raw) and cond_raw.lower() not in ("false","0","nein","no")
                        label = "✅ Bedingung erfüllt" if passed else "❌ Bedingung nicht erfüllt"
                        output = f"{label}\n{context}" if context else label

                    # ── http ─────────────────────────────────────────────────
                    elif ntype == "http":
                        import requests as _req
                        method  = config.get("method", "GET").upper()
                        url     = config.get("url", "").strip()
                        body    = config.get("body", "").strip()
                        headers_raw = config.get("headers", "").strip()
                        if "{{input}}" in url and context:
                            url = url.replace("{{input}}", context)
                        if "{{input}}" in body and context:
                            body = body.replace("{{input}}", context)
                        if not url:
                            output = "⚠️ Keine URL angegeben."
                        else:
                            hdrs = {}
                            for line in headers_raw.split("\n"):
                                if ":" in line:
                                    hk, hv = line.split(":", 1)
                                    hdrs[hk.strip()] = hv.strip()
                            try:
                                if method in ("POST", "PUT", "PATCH"):
                                    resp = _req.request(method, url, headers=hdrs,
                                                        data=body.encode("utf-8"), timeout=30)
                                else:
                                    resp = _req.request(method, url, headers=hdrs, timeout=30)
                                output = resp.text[:3000]
                            except Exception as e:
                                output = f"❌ HTTP-Fehler: {e}"

                    # ── error_handler ────────────────────────────────────────
                    elif ntype == "error_handler":
                        msg_tpl = config.get("message", "{{input}}")
                        if "{{input}}" in msg_tpl and context:
                            msg_tpl = msg_tpl.replace("{{input}}", context)
                        elif not msg_tpl and context:
                            msg_tpl = context
                        aktion = config.get("aktion", "weitergeben")
                        if aktion == "stoppen":
                            output = f"🛑 Workflow gestoppt wegen Fehler:\n{msg_tpl}"
                            results[nid]  = output
                            statuses[nid] = "error"
                            break  # Ausführung abbrechen
                        elif aktion == "ignorieren":
                            output = context  # Fehler ignorieren, Original-Kontext weitergeben
                        else:
                            output = f"🚨 Fehler abgefangen:\n{msg_tpl}"

                    # ── schedule_trigger ─────────────────────────────────────
                    elif ntype == "schedule_trigger":
                        itype = config.get("interval_type", "interval")
                        if itype == "interval":
                            min_ = int(config.get("minuten", 0))
                            sec_ = int(config.get("sekunden", 30))
                            tot_ = min_ * 60 + sec_
                            desc = f"alle {min_}m {sec_}s ({tot_}s)" if min_ > 0 else f"alle {sec_}s"
                        elif itype == "taglich":
                            desc = f"täglich um {config.get('zeit', '08:00')}"
                        elif itype == "woechentlich":
                            tage = ["Mo","Di","Mi","Do","Fr","Sa","So"]
                            tag  = tage[int(config.get("wochentag", 0))]
                            desc = f"wöchentlich {tag} um {config.get('zeit', '08:00')}"
                        else:
                            desc = "Zeitplan"
                        output = (f"⏰ Zeitplan-Trigger ausgelöst ({desc})\n"
                                  f"Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

                    # ── webhook ──────────────────────────────────────────────
                    elif ntype == "webhook":
                        wh_data = config.get("_webhook_data", "")
                        if not wh_data and context:
                            wh_data = context
                        wh_id = config.get("webhook_id", "—")
                        output = (f"🔗 Webhook empfangen (ID: {wh_id})\n"
                                  f"{wh_data}" if wh_data else
                                  f"🔗 Webhook bereit (ID: {wh_id})")

                    # ── loop ─────────────────────────────────────────────────
                    elif ntype == "loop":
                        items_src = config.get("items", "{{input}}")
                        if "{{input}}" in items_src and context:
                            items_src = items_src.replace("{{input}}", context)
                        elif not items_src.strip() and context:
                            items_src = context
                        # JSON-Array oder Zeilenweise oder Komma-getrennt
                        try:
                            parsed = json.loads(items_src)
                            items_list = parsed if isinstance(parsed, list) else [parsed]
                        except Exception:
                            items_list = [x.strip() for x in items_src.split("\n") if x.strip()]
                            if len(items_list) == 1 and "," in items_list[0]:
                                items_list = [x.strip() for x in items_list[0].split(",") if x.strip()]
                        items_list = items_list[:int(config.get("max_items", 50))]

                        successors_loop = adj.get(nid, [])
                        if not items_list:
                            output = "⚠️ Keine Elemente zum Iterieren."
                        elif not successors_loop:
                            output = (f"🔁 {len(items_list)} Element(e) (keine verbundenen Nodes):\n"
                                      + "\n".join(f"• {i}" for i in items_list[:20]))
                        else:
                            # Alle erreichbaren Nachfolger bestimmen
                            reachable_loop = set()
                            _q = list(successors_loop)
                            while _q:
                                _n = _q.pop(0)
                                if _n not in reachable_loop:
                                    reachable_loop.add(_n)
                                    _q.extend(adj.get(_n, []))
                            loop_processed.update(reachable_loop)
                            sub_order_loop = [x for x in order if x in reachable_loop]

                            all_iter = []
                            for _item in items_list:
                                _item_str  = json.dumps(_item) if not isinstance(_item, str) else _item
                                _sub_ctx   = {nid: _item_str}

                                for _snid in sub_order_loop:
                                    _sn   = nodes[_snid]
                                    _snt  = _sn.get("type", "note")
                                    _scfg = _sn.get("config", {})
                                    _sprevs = [_sub_ctx[p] for p in conn_map.get(_snid, []) if p in _sub_ctx]
                                    _sctx = "\n".join(_sprevs) if _sprevs else _item_str
                                    try:
                                        if _snt == "chat":
                                            _sm = _scfg.get("message", "{{input}}").strip() or "{{input}}"
                                            if "{{input}}" in _sm: _sm = _sm.replace("{{input}}", _sctx)
                                            _sr = k.chat(_sm)
                                        elif _snt == "skill":
                                            _ssn = _scfg.get("skill", "")
                                            _ssp = dict(_scfg.get("params", {}))
                                            for _pk, _pv in _ssp.items():
                                                if isinstance(_pv, str) and "{{input}}" in _pv:
                                                    _ssp[_pk] = _pv.replace("{{input}}", _sctx)
                                            _sr = k.manager.execute(_ssn, **_ssp) if _ssn else "⚠️ Kein Skill"
                                        elif _snt == "set":
                                            _sv = _scfg.get("value", "")
                                            _sr = _sv.replace("{{input}}", _sctx) if "{{input}}" in _sv else _sv
                                        elif _snt == "http":
                                            import requests as _req
                                            _surl = _scfg.get("url", "")
                                            if "{{input}}" in _surl: _surl = _surl.replace("{{input}}", _sctx)
                                            _sbdy = _scfg.get("body", "")
                                            if "{{input}}" in _sbdy: _sbdy = _sbdy.replace("{{input}}", _sctx)
                                            _sm2  = _scfg.get("method", "GET").upper()
                                            _sr   = _req.request(_sm2, _surl, data=_sbdy.encode(),
                                                                  timeout=30).text[:2000]
                                        else:
                                            _sr = _sctx
                                        _sub_ctx[_snid] = str(_sr)
                                    except Exception as _le:
                                        _sub_ctx[_snid] = f"❌ {_le}"

                                _final = _sub_ctx.get(sub_order_loop[-1], _item_str)
                                all_iter.append(f"[{len(all_iter)+1}] {_final}")
                                # UI: letzte Iteration sichtbar machen
                                for _snid in sub_order_loop:
                                    results[_snid]  = _sub_ctx.get(_snid, "")
                                    statuses[_snid] = "success"

                            output = (f"🔁 Loop — {len(items_list)} Iteration(en):\n"
                                      + "\n".join(all_iter))

                    # ── code ─────────────────────────────────────────────────
                    elif ntype == "code":
                        import sys
                        from io import StringIO
                        code_str = config.get("code", "").strip()
                        if not code_str:
                            output = "⚠️ Kein Code eingegeben."
                        else:
                            if "{{input}}" in code_str and context:
                                code_str = code_str.replace("{{input}}", repr(context))
                            _buf = StringIO()
                            _old = sys.stdout
                            sys.stdout = _buf
                            # Sicheres Builtins-Whitelist — kein os, open, exec, eval, import
                            _safe_builtins = {
                                "print": print, "str": str, "int": int, "float": float,
                                "bool": bool, "list": list, "dict": dict, "tuple": tuple,
                                "set": set, "len": len, "range": range, "enumerate": enumerate,
                                "zip": zip, "map": map, "filter": filter, "sorted": sorted,
                                "reversed": reversed, "sum": sum, "min": min, "max": max,
                                "abs": abs, "round": round, "type": type, "isinstance": isinstance,
                                "repr": repr, "format": format, "hasattr": hasattr,
                                "getattr": getattr, "setattr": setattr,
                            }
                            _locals = {"input": context, "context": context,
                                       "output": None, "result": None,
                                       "json": json, "datetime": datetime}
                            try:
                                exec(code_str, {"__builtins__": _safe_builtins}, _locals)
                                sys.stdout = _old
                                _printed  = _buf.getvalue()
                                _returned = _locals.get("output") or _locals.get("result")
                                if _returned is not None:
                                    output = str(_returned)
                                elif _printed:
                                    output = _printed.strip()
                                else:
                                    output = "✅ Code ausgeführt (kein Output)"
                            except Exception as _ce:
                                sys.stdout = _old
                                output = f"❌ Code-Fehler: {_ce}"

                    # ── wait ─────────────────────────────────────────────────
                    elif ntype == "wait":
                        sek = max(0, min(int(config.get("sekunden", 5)), 300))
                        _sched_time.sleep(sek)
                        output = f"⏱️ {sek} Sekunde(n) gewartet. Weiter: {datetime.now().strftime('%H:%M:%S')}"

                    # ── switch ────────────────────────────────────────────────
                    elif ntype == "switch":
                        wert = config.get("wert", "{{input}}")
                        if "{{input}}" in wert and context:
                            wert = wert.replace("{{input}}", context)
                        elif wert == "{{input}}":
                            wert = context
                        matched_case = None
                        matched_out  = None
                        for _ci in range(1, 6):
                            _cond = config.get(f"case{_ci}_bedingung", "").strip()
                            _cout = config.get(f"case{_ci}_ausgabe", "{{input}}").strip()
                            if not _cond:
                                continue
                            _hit = False
                            if "==" in _cond:
                                _cl, _cr = _cond.split("==", 1)
                                _hit = wert.strip() == _cr.strip().strip("'\"")
                            elif "!=" in _cond:
                                _cl, _cr = _cond.split("!=", 1)
                                _hit = wert.strip() != _cr.strip().strip("'\"")
                            elif ">" in _cond:
                                try:
                                    _cl, _cr = _cond.split(">", 1)
                                    _hit = float(wert) > float(_cr.strip())
                                except Exception: pass
                            elif "<" in _cond:
                                try:
                                    _cl, _cr = _cond.split("<", 1)
                                    _hit = float(wert) < float(_cr.strip())
                                except Exception: pass
                            else:
                                _hit = _cond.lower() in wert.lower()
                            if _hit:
                                matched_case = _ci
                                matched_out  = _cout
                                break
                        if matched_case:
                            _final_out = matched_out.replace("{{input}}", wert) if "{{input}}" in matched_out else matched_out
                            output = f"🔀 Case {matched_case} ✅\n{_final_out}"
                        else:
                            _def = config.get("default_ausgabe", "{{input}}")
                            output = f"🔀 Default:\n{_def.replace('{{input}}', wert) if '{{input}}' in _def else _def}"

                    # ── sub_workflow ──────────────────────────────────────────
                    elif ntype == "sub_workflow":
                        sub_id = config.get("workflow_id", "").strip()
                        if not sub_id:
                            output = "⚠️ Kein Sub-Workflow ausgewählt."
                        else:
                            _swpath = os.path.join(WORKFLOWS_DIR, f"{sub_id}.json")
                            if not os.path.exists(_swpath):
                                output = f"❌ Sub-Workflow '{sub_id}' nicht gefunden."
                            else:
                                try:
                                    with open(_swpath, "r", encoding="utf-8") as _swf:
                                        _swdata = json.load(_swf)
                                    # Kontext in Trigger-Node injizieren
                                    for _swn in _swdata.get("nodes", []):
                                        if _swn.get("type") in ("trigger", "schedule_trigger", "webhook"):
                                            _swn.setdefault("config", {})["startMessage"] = context
                                            break
                                    import requests as _req
                                    _port2 = int(os.getenv("PORT", 5000))
                                    _rr = _req.post(
                                        f"http://localhost:{_port2}/api/workflow/execute",
                                        json={"nodes": _swdata.get("nodes", []),
                                              "connections": _swdata.get("connections", [])},
                                        timeout=120,
                                    )
                                    if _rr.ok:
                                        _swr = _rr.json().get("results", {})
                                        _last = [v for v in _swr.values() if v and not v.startswith("❌")]
                                        output = (f"▶ Sub-Workflow '{_swdata.get('name', sub_id)}':\n"
                                                  + (_last[-1] if _last else context))
                                    else:
                                        output = f"❌ Sub-Workflow HTTP-Fehler: {_rr.status_code}"
                                except Exception as _swe:
                                    output = f"❌ Sub-Workflow Fehler: {_swe}"

                    # ── rss ──────────────────────────────────────────────────
                    elif ntype == "rss":
                        import requests as _req
                        from xml.etree import ElementTree as _ET
                        feed_url = config.get("url", "").strip()
                        if "{{input}}" in feed_url and context:
                            feed_url = feed_url.replace("{{input}}", context)
                        elif not feed_url and context:
                            feed_url = context.strip()
                        anzahl_rss = max(1, min(int(config.get("anzahl", 5)), 30))
                        if not feed_url:
                            output = "⚠️ Keine RSS-URL angegeben."
                        else:
                            try:
                                _rresp = _req.get(feed_url, timeout=15,
                                                  headers={"User-Agent": "Mozilla/5.0"})
                                _rresp.raise_for_status()
                                _root = _ET.fromstring(_rresp.content)
                                _ns   = {"atom": "http://www.w3.org/2005/Atom"}
                                _chan = _root.find("channel")
                                _feed_items = []
                                if _chan is not None:
                                    _ftitle = _chan.findtext("title", feed_url)
                                    for _ri in _chan.findall("item")[:anzahl_rss]:
                                        _t = _ri.findtext("title", "").strip()
                                        _l = _ri.findtext("link", "").strip()
                                        _d = _ri.findtext("pubDate", "")[:16]
                                        _de = _ri.findtext("description", "").strip()
                                        # HTML-Tags entfernen
                                        import re as _re_rss
                                        _de = _re_rss.sub(r"<[^>]+>", "", _de)[:200]
                                        _feed_items.append(f"📰 {_t}\n   🕐 {_d}  🔗 {_l}\n   {_de}")
                                else:
                                    _ftitle = feed_url
                                    for _ae in _root.findall("atom:entry", _ns)[:anzahl_rss]:
                                        _t  = _ae.findtext("atom:title", "", _ns).strip()
                                        _le = _ae.find("atom:link", _ns)
                                        _l  = _le.get("href", "") if _le is not None else ""
                                        _d  = _ae.findtext("atom:updated", "", _ns)[:16]
                                        _feed_items.append(f"📰 {_t}\n   🕐 {_d}  🔗 {_l}")
                                if _feed_items:
                                    output = (f"📡 {_ftitle} — {len(_feed_items)} Einträge\n"
                                              f"{'─'*50}\n" + "\n\n".join(_feed_items))
                                else:
                                    output = f"📭 Keine Einträge in: {feed_url}"
                            except Exception as _re_err:
                                output = f"❌ RSS-Fehler: {_re_err}"

                    # ── whatsapp ─────────────────────────────────────────────
                    elif ntype == "whatsapp":
                        import requests as _req
                        _wa_token    = config.get("token", "").strip()
                        _wa_phone_id = config.get("phone_id", "").strip()
                        _wa_to       = config.get("to", "").strip()
                        _wa_op       = config.get("operation", "send")

                        # Gespeicherte WA-Config als Fallback
                        _wa_cfg_path = os.path.join("data", "whatsapp", "whatsapp_config.json")
                        if os.path.exists(_wa_cfg_path):
                            try:
                                with open(_wa_cfg_path, "r", encoding="utf-8") as _waf:
                                    _wac = json.load(_waf)
                                _wa_token    = _wa_token    or _wac.get("token", "")
                                _wa_phone_id = _wa_phone_id or _wac.get("phone_id", "")
                            except Exception:
                                pass

                        if not _wa_token or not _wa_phone_id:
                            output = ("❌ WhatsApp: Token und Phone-ID fehlen.\n"
                                      "Erstelle eine App unter developers.facebook.com → "
                                      "WhatsApp Business API und trage Token + Phone-ID ein.")
                        elif _wa_op == "send":
                            _wa_text = config.get("text", "{{input}}").strip() or "{{input}}"
                            if "{{input}}" in _wa_text and context:
                                _wa_text = _wa_text.replace("{{input}}", context)
                            if not _wa_to:
                                output = "❌ Keine Empfänger-Nummer (Format: 49171234567)"
                            elif not _wa_text:
                                output = "⚠️ Kein Text zum Senden."
                            else:
                                try:
                                    _war = _req.post(
                                        f"https://graph.facebook.com/v18.0/{_wa_phone_id}/messages",
                                        headers={"Authorization": f"Bearer {_wa_token}",
                                                 "Content-Type": "application/json"},
                                        json={"messaging_product": "whatsapp", "to": _wa_to,
                                              "type": "text", "text": {"body": _wa_text[:4096]}},
                                        timeout=15,
                                    )
                                    if _war.ok:
                                        _mid = _war.json().get("messages", [{}])[0].get("id", "")
                                        output = f"✅ WhatsApp gesendet an {_wa_to} (ID: {_mid})"
                                    else:
                                        _werr = _war.json().get("error", {}).get("message", str(_war.status_code))
                                        output = f"❌ WhatsApp API: {_werr}"
                                except Exception as _wae:
                                    output = f"❌ WhatsApp Fehler: {_wae}"
                        else:
                            output = f"⚠️ Unbekannte Operation: {_wa_op}"

                    else:
                        output = f"[Unbekannter Node-Typ: {ntype}]"

                    results[nid]  = str(output)
                    statuses[nid] = "success"

                except Exception as e:
                    results[nid]  = f"❌ Fehler: {e}"
                    statuses[nid] = "error"

            # ── Memory Write-Back ─────────────────────────────────────────
            # Für jeden Memory-Node: finde den nächsten Chat-Node und schreibe zurück
            for mem in memory_write_queue:
                mem_nid = mem["nid"]
                # Chat-Node suchen, der direkt von diesem Memory-Node gespeist wird
                for chat_nid in order:
                    if nodes[chat_nid].get("type") != "chat":
                        continue
                    if mem_nid not in conn_map.get(chat_nid, []):
                        continue
                    if chat_nid not in results or statuses.get(chat_nid) == "error":
                        continue

                    # Rekonstruiere was an den Chat geschickt wurde
                    chat_cfg  = nodes[chat_nid].get("config", {})
                    chat_msg  = chat_cfg.get("message", "").strip()
                    prev_outs = [results[p] for p in conn_map.get(chat_nid, []) if p in results]
                    ctx       = "\n".join(prev_outs)

                    if "{{input}}" in chat_msg and ctx:
                        user_content = chat_msg.replace("{{input}}", ctx)
                    elif not chat_msg and ctx:
                        user_content = ctx
                    else:
                        user_content = chat_msg or ctx or "…"

                    assistant_content = results[chat_nid]

                    try:
                        if mem["type"] == "window":
                            _mem_write(mem["key"], user_content, assistant_content, mem.get("size", 10))

                        elif mem["type"] == "summary":
                            old_sum = _mem_summary_read(mem["key"])
                            prompt  = (
                                "Erstelle eine prägnante Zusammenfassung (max. 150 Wörter) "
                                "der bisherigen Gesprächsinhalte.\n\n"
                                + (f"Bisherige Zusammenfassung:\n{old_sum}\n\n" if old_sum else "")
                                + f"Neue Interaktion:\n"
                                  f"Nutzer: {user_content[:300]}\n"
                                  f"Ilija: {assistant_content[:300]}\n\n"
                                  f"Neue Zusammenfassung (nur der reine Text, keine Einleitung):"
                            )
                            new_sum = k.chat(prompt)
                            _mem_summary_write(mem["key"], new_sum)
                    except Exception:
                        pass
                    # Kein break — alle passenden Chat-Nodes werden beschrieben

        return jsonify({
            "results":    results,
            "statuses":   statuses,
            "order":      order,
        })

    # ── Webhook-Receiver ─────────────────────────────────────────────
    @app.route("/api/webhook/<webhook_id>", methods=["GET", "POST"])
    def receive_webhook(webhook_id):
        """Empfängt externe HTTP-Anfragen und startet den zugehörigen Workflow."""
        if request.is_json:
            wh_body = request.get_json() or {}
        elif request.form:
            wh_body = dict(request.form)
        else:
            wh_body = {"body": request.get_data(as_text=True)}
        wh_json = json.dumps(wh_body, ensure_ascii=False)

        target_wf = None
        os.makedirs(WORKFLOWS_DIR, exist_ok=True)
        for fname in sorted(os.listdir(WORKFLOWS_DIR)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(WORKFLOWS_DIR, fname), "r", encoding="utf-8") as _f:
                    wf = json.load(_f)
                for _n in wf.get("nodes", []):
                    if _n.get("type") == "webhook" and \
                       _n.get("config", {}).get("webhook_id") == webhook_id:
                        _n.setdefault("config", {})["_webhook_data"] = wh_json
                        target_wf = wf
                        break
            except Exception:
                pass
            if target_wf:
                break

        if not target_wf:
            return jsonify({"error": f"Kein Workflow mit Webhook-ID '{webhook_id}'"}), 404

        import requests as _req
        _port = int(os.getenv("PORT", 5000))
        try:
            _r = _req.post(
                f"http://localhost:{_port}/api/workflow/execute",
                json={"nodes": target_wf["nodes"],
                      "connections": target_wf.get("connections", [])},
                timeout=120,
            )
            if _r.ok:
                _res = _r.json().get("results", {})
                _last = list(_res.values())[-1] if _res else "Workflow ausgeführt"
                return jsonify({"status": "success",
                                "workflow": target_wf.get("name"),
                                "result": _last})
            return jsonify({"status": "error", "code": _r.status_code}), 500
        except Exception as _we:
            return jsonify({"status": "error", "error": str(_we)}), 500

    # ── Zeitplan verwalten ────────────────────────────────────────────
    @app.route("/api/schedules", methods=["GET"])
    def list_schedules_route():
        os.makedirs(SCHEDULES_DIR, exist_ok=True)
        sf = os.path.join(SCHEDULES_DIR, "active.json")
        with _schedules_lock:
            if os.path.exists(sf):
                with open(sf, "r", encoding="utf-8") as _f:
                    return jsonify(json.load(_f))
        return jsonify({})

    @app.route("/api/schedules/<wid>", methods=["POST"])
    def set_schedule_route(wid):
        data    = request.get_json() or {}
        active  = data.get("active", True)
        cfg     = data.get("config", {})
        os.makedirs(SCHEDULES_DIR, exist_ok=True)
        sf      = os.path.join(SCHEDULES_DIR, "active.json")
        with _schedules_lock:
            scheds = {}
            if os.path.exists(sf):
                with open(sf, "r", encoding="utf-8") as _f:
                    scheds = json.load(_f)
            if active:
                scheds[wid] = {"active": True, "config": cfg,
                               "enabled_at": datetime.now().isoformat()}
                msg = f"Zeitplan für '{wid}' aktiviert"
            else:
                if wid in scheds:
                    scheds[wid]["active"] = False
                msg = f"Zeitplan für '{wid}' deaktiviert"
            with open(sf, "w", encoding="utf-8") as _f:
                json.dump(scheds, _f, ensure_ascii=False, indent=2)
        return jsonify({"message": msg, "active": active})

    @app.route("/api/schedules/<wid>", methods=["DELETE"])
    def delete_schedule_route(wid):
        sf = os.path.join(SCHEDULES_DIR, "active.json")
        with _schedules_lock:
            if os.path.exists(sf):
                with open(sf, "r", encoding="utf-8") as _f:
                    scheds = json.load(_f)
                scheds.pop(wid, None)
                with open(sf, "w", encoding="utf-8") as _f:
                    json.dump(scheds, _f, ensure_ascii=False, indent=2)
        return jsonify({"message": f"Zeitplan '{wid}' entfernt"})

    # ── WhatsApp-Config speichern ─────────────────────────────────────
    @app.route("/api/whatsapp/config", methods=["POST"])
    def save_whatsapp_config():
        data = request.get_json() or {}
        os.makedirs(os.path.join("data", "whatsapp"), exist_ok=True)
        path = os.path.join("data", "whatsapp", "whatsapp_config.json")
        with open(path, "w", encoding="utf-8") as _f:
            json.dump({"token": data.get("token", ""),
                       "phone_id": data.get("phone_id", ""),
                       "updated": datetime.now().isoformat()}, _f, ensure_ascii=False, indent=2)
        return jsonify({"message": "WhatsApp-Config gespeichert"})

    # ── Hintergrund-Scheduler starten ────────────────────────────────
    _port_main = int(os.getenv("PORT", 5000))
    _start_scheduler(_port_main)

    print("[Ilija] Workflow-Routen registriert ✅")
