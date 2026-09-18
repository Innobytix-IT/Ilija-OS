"""
web_server.py – Web-Interface für Ilija Public Edition
Starten: python web_server.py
Browser: http://localhost:5000

Erweitert um n8n-ähnliches Workflow Studio.
"""

import os
import json
import threading
import sys
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from kernel import Kernel

load_dotenv()

# --- PyInstaller Fix für den Templates-Ordner ---
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask(__name__, template_folder=template_folder)
else:
    app = Flask(__name__)

CORS(app)

# ── Ilija OS: optionale Passwort-Sperre ──
try:
    from ilija_os_auth import install_auth as _ilija_install_auth
    _ilija_install_auth(app)
except Exception as _e:  # noqa: BLE001
    print('Ilija OS Auth nicht geladen:', _e)

# Globaler Kernel (Thread-safe via Lock)
kernel      = None
kernel_lock = threading.RLock()


def get_kernel() -> Kernel:
    global kernel
    # Double-checked locking: Thread-sichere Initialisierung ohne permanenten Lock-Overhead
    if kernel is None:
        with kernel_lock:
            if kernel is None:
                kernel = Kernel()
    return kernel

# ── DMS-Routen einbinden ──────────────────────────────────────
from dms_routes import register_dms_routes
register_dms_routes(app)

# ── Workflow-Routen einbinden ─────────────────────────────────
from workflow_routes import register_workflow_routes
register_workflow_routes(app, get_kernel, kernel_lock)

# ── Lokaler Kalender einbinden ────────────────────────────────
from local_calendar_routes import register_local_calendar_routes
register_local_calendar_routes(app)

from agent_routes import register_agent_routes
register_agent_routes(app)

from cloud_routes import register_cloud_routes
register_cloud_routes(app)

# ── Log-Bereinigung beim Start ────────────────────────────────
from log_cleanup import bereinige_logs
bereinige_logs()

# ── Kalender-Sync Pull-Scheduler ─────────────────────────────
def _kalender_pull_scheduler():
    """Prüft alle 15 Minuten ob ein konfigurierter Pull fällig ist."""
    import time as _time
    while True:
        _time.sleep(900)  # alle 15 Minuten prüfen
        try:
            from skills.kalender_sync_skill import _lade_config, soll_pull_jetzt, pull_extern_zu_lokal
            cfg = _lade_config()
            if soll_pull_jetzt(cfg.get("letzte_sync", ""), cfg.get("pull_intervall", "manuell")):
                ergebnis = pull_extern_zu_lokal()
                print(f"[KalenderSync] Auto-Pull: {ergebnis}")
        except Exception as e:
            print(f"[KalenderSync] Scheduler-Fehler: {e}")

threading.Thread(target=_kalender_pull_scheduler, daemon=True, name="kalender-sync").start()


# ── Haupt-Interface (Workflow Studio) ────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/cloud")
def cloud_page():
    return render_template("cloud.html")


@app.route("/chat")
def chat_page():
    return render_template("indexchat.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data  = request.get_json() or {}
    msg   = data.get("message", "").strip()
    if not msg:
        return jsonify({"error": "Leere Nachricht"}), 400
    # Nur Kernel-Referenz im Lock holen — k.chat() AUSSERHALB des Locks!
    # k.chat() dauert bis zu 60s und würde sonst alle parallelen Requests blockieren.
    with kernel_lock:
        k = get_kernel()
    response = k.chat(msg)
    return jsonify({"response": response, "provider": k.state.active_provider})


@app.route("/api/status")
def status():
    with kernel_lock:
        k = get_kernel()
        return jsonify(k.state.get_status_dict())


@app.route("/api/stats")
def stats_alias():
    with kernel_lock:
        k = get_kernel()
        d = k.state.get_status_dict()
    try:
        from skills.dms import dms_stats
        d["dms"] = dms_stats()
    except Exception:
        pass
    return jsonify(d)


@app.route("/api/reload", methods=["POST"])
def reload_skills():
    with kernel_lock:
        k   = get_kernel()
        msg = k.reload_skills()
    return jsonify({"message": msg})


@app.route("/api/clear", methods=["POST"])
def clear_history():
    with kernel_lock:
        k = get_kernel()
        k.state.clear_history()
    return jsonify({"message": "Chat-Verlauf gelöscht"})


@app.route("/api/switch", methods=["POST"])
def switch_provider():
    data = request.get_json() or {}
    mode = data.get("provider", "auto")
    with kernel_lock:
        k   = get_kernel()
        msg = k.switch_provider(mode)
    return jsonify({"message": msg, "provider": k.state.active_provider})


@app.route("/api/providers")
def providers():
    from providers import get_available_providers
    return jsonify(get_available_providers())


@app.route("/api/skills")
def skills():
    with kernel_lock:
        k = get_kernel()
        return jsonify(k.manager.list_skills())


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Keine Datei"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Kein Dateiname"}), 400

    upload_dir = os.path.join("data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    from werkzeug.utils import secure_filename
    filename  = secure_filename(file.filename)
    filepath  = os.path.join(upload_dir, filename)
    file.save(filepath)

    auto_dms = request.form.get("auto_dms", "false").lower() == "true"
    if auto_dms:
        import shutil
        dms_import = os.path.join("data", "dms", "import")
        os.makedirs(dms_import, exist_ok=True)
        shutil.copy(filepath, os.path.join(dms_import, filename))
        return jsonify({"message": f"{filename} in DMS-Import gespeichert", "filename": filename})

    return jsonify({"message": f"{filename} hochgeladen", "filename": filename, "path": filepath})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Gibt aktuelle Konfiguration zurück (API-Keys maskiert)."""
    try:
        with open("models_config.json", "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {"default_provider": "auto", "models": {}}

    def mask(key):
        if not key:
            return ""
        return key[:6] + "****" if len(key) > 6 else "****"

    with kernel_lock:
        active = kernel.state.active_provider if kernel else "—"

    ant_key = os.getenv("ANTHROPIC_API_KEY", "")
    oai_key = os.getenv("OPENAI_API_KEY", "")
    gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")

    ollama_models = []
    try:
        import ollama
        result = ollama.list()
        ollama_models = [m.get("model", m.get("name", "")) for m in result.get("models", [])]
        ollama_models = [m for m in ollama_models if m]
    except Exception:
        pass

    return jsonify({
        "active_provider":  active,
        "default_provider": cfg.get("default_provider", "auto"),
        "models":           cfg.get("models", {}),
        "keys": {
            "anthropic": mask(ant_key),
            "openai":    mask(oai_key),
            "gemini":    mask(gem_key),
        },
        "has_keys": {
            "anthropic": bool(ant_key),
            "openai":    bool(oai_key),
            "gemini":    bool(gem_key),
        },
        "ollama_models": ollama_models,
    })


@app.route("/api/settings", methods=["POST"])
def save_settings():
    """Speichert API-Keys und Modell-Konfiguration, setzt Kernel zurück."""
    global kernel
    data = request.get_json() or {}

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

    def set_env_key(lines, key, value):
        if not value or "****" in value:
            return lines
        new_line = f"{key}={value}\n"
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines[i] = new_line
                return lines
        lines.append(new_line)
        return lines

    keys   = data.get("keys", {})
    models = data.get("models", {})

    env_lines = set_env_key(env_lines, "ANTHROPIC_API_KEY", keys.get("anthropic", ""))
    env_lines = set_env_key(env_lines, "OPENAI_API_KEY",    keys.get("openai", ""))
    env_lines = set_env_key(env_lines, "GOOGLE_API_KEY",    keys.get("gemini", ""))

    # Modell-Einstellungen ebenfalls als Env-Vars speichern
    if models.get("claude"): env_lines = set_env_key(env_lines, "ANTHROPIC_MODEL", models["claude"])
    if models.get("openai"): env_lines = set_env_key(env_lines, "OPENAI_MODEL",    models["openai"])
    if models.get("gemini"): env_lines = set_env_key(env_lines, "GOOGLE_MODEL",    models["gemini"])
    if models.get("ollama"): env_lines = set_env_key(env_lines, "OLLAMA_MODEL",    models["ollama"])

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(env_lines)

    load_dotenv(env_path, override=True)

    # models_config.json aktualisieren
    try:
        with open("models_config.json", "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    provider = data.get("provider", "auto")
    cfg["default_provider"] = provider
    if models:
        cfg.setdefault("models", {}).update({k: v for k, v in models.items() if v})

    with open("models_config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # Kernel zurücksetzen → beim nächsten Request neu initialisiert
    with kernel_lock:
        kernel = None

    return jsonify({"message": "Einstellungen gespeichert. Provider wird neu initialisiert."})


@app.route("/api/ollama/models")
def get_ollama_models():
    """Listet verfügbare lokale Ollama-Modelle auf."""
    try:
        import ollama
        result = ollama.list()
        models = [m.get("model", m.get("name", "")) for m in result.get("models", [])]
        return jsonify([m for m in models if m])
    except Exception:
        return jsonify([])


@app.route("/whatsapp")
def whatsapp_page():
    return render_template("whatsapp.html")


# ── WhatsApp Bridge State (im RAM) ────────────────────────
import time as _time
_wa_state = {"status": "disconnected", "qr": "", "connected_since": None, "msg_count": 0}
_wa_lock  = threading.Lock()


@app.route("/api/whatsapp/status")
def whatsapp_status():
    with _wa_lock:
        return jsonify(dict(_wa_state))


@app.route("/api/whatsapp/connection-status", methods=["POST"])
def whatsapp_connection_status():
    """Empfängt Status-Updates von der Baileys-Bridge (qr / connected / disconnected)."""
    data = request.get_json(silent=True) or {}
    status = data.get("status", "disconnected")
    with _wa_lock:
        _wa_state["status"] = status
        if status == "qr":
            _wa_state["qr"] = data.get("qr", "")
            _wa_state["connected_since"] = None
        elif status == "connected":
            _wa_state["qr"] = ""
            _wa_state["connected_since"] = _wa_state["connected_since"] or _time.time()
        else:
            _wa_state["qr"] = ""
            _wa_state["connected_since"] = None
    return jsonify({"ok": True})


@app.route("/einstellungen")
def einstellungen_page():
    return render_template("einstellungen.html")


# ── Kalender-Einstellungen ────────────────────────────────────
_KALENDER_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kalender_einstellungen.json")
_KALENDER_DEFAULTS = {
    "persoenlicher_kalender": "outlook",
    "buchungskalender": "lokal",
    "sync_provider": "keiner",
    "sync_intervall": "3x_taeglich",
    "sync_auto_push": True,
}


def _lade_kalender_einstellungen() -> dict:
    if os.path.exists(_KALENDER_CONFIG_PATH):
        try:
            with open(_KALENDER_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {**_KALENDER_DEFAULTS, **cfg}
        except Exception:
            pass
    return dict(_KALENDER_DEFAULTS)


def _speichere_kalender_einstellungen(cfg: dict):
    os.makedirs(os.path.dirname(_KALENDER_CONFIG_PATH), exist_ok=True)
    with open(_KALENDER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


@app.route("/api/kalender-settings", methods=["GET"])
def get_kalender_settings():
    return jsonify(_lade_kalender_einstellungen())


@app.route("/api/kalender-settings", methods=["POST"])
def save_kalender_settings():
    global kernel
    data = request.get_json() or {}
    cfg  = _lade_kalender_einstellungen()

    allowed = {"persoenlicher_kalender", "buchungskalender", "sync_provider", "sync_intervall", "sync_auto_push"}
    for key in allowed:
        if key in data:
            cfg[key] = data[key]
    _speichere_kalender_einstellungen(cfg)

    # Kalender-Sync-Config ebenfalls aktualisieren (sync_provider / intervall / auto_push)
    try:
        from skills.kalender_sync_skill import _lade_config as _lade_sync, _speichere_config as _speichere_sync
        sync_cfg = _lade_sync()
        sync_cfg["provider"]       = cfg.get("sync_provider", "keiner")
        sync_cfg["pull_intervall"] = cfg.get("sync_intervall", "3x_taeglich")
        sync_cfg["auto_push"]      = cfg.get("sync_auto_push", True)
        _speichere_sync(sync_cfg)
    except Exception as e:
        print(f"[KalenderSettings] Sync-Config-Update Fehler: {e}")

    # Kernel zurücksetzen → System-Prompt wird beim nächsten Chat neu gebaut
    with kernel_lock:
        kernel = None

    return jsonify({"ok": True, "message": "Kalender-Einstellungen gespeichert."})


@app.route("/api/whatsapp", methods=["POST"])
def whatsapp_bridge():
    """Empfängt WhatsApp-Nachrichten vom Baileys-Bridge und gibt Ilijas Antwort zurück."""
    data = request.get_json(silent=True) or {}
    sender_jid = (data.get("from") or "").strip()
    name       = (data.get("name") or sender_jid or "Unbekannt").strip()
    text       = (data.get("text") or "").strip()

    if not text:
        return jsonify({"reply": ""}), 200

    try:
        from skills.whatsapp_bridge_skill import verarbeite_whatsapp_nachricht
        k = get_kernel()
        antwort = verarbeite_whatsapp_nachricht(sender_jid, name, text, k.provider)
        with _wa_lock:
            _wa_state["msg_count"] = _wa_state.get("msg_count", 0) + 1
        return jsonify({"reply": antwort}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "reply": ""}), 500


if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "127.0.0.1"

    print(f"\n{'='*56}")
    print(f"  Ilija Public Edition – Workflow Studio")
    print(f"  Lokal:    http://localhost:{port}")
    print(f"  Netzwerk: http://{ip}:{port}")
    print(f"  DMS:      http://localhost:{port}/dms")
    print(f"{'='*56}\n")

    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
