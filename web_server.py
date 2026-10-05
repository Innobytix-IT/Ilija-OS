"""
web_server.py – Web-Interface für Ilija Public Edition
Starten: python web_server.py
Browser: http://localhost:5000
Version: 2.1.0

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

# ── AHPT-Routen einbinden ─────────────────────────────────────
try:
    from ahpt_routes import register_ahpt_routes
    register_ahpt_routes(app)
except Exception as _e:
    print(f'AHPT-Routen nicht geladen: {_e}')

# ── Fristen & Vorlagen einbinden ──────────────────────────────
from fristen_routes import register_fristen_routes
register_fristen_routes(app, get_kernel, kernel_lock)

# ── Chat-Sessions einbinden ───────────────────────────────────
from session_routes import register_session_routes
register_session_routes(app, get_kernel, kernel_lock)

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
        "ollama_models":    ollama_models,
        "skills_enabled":   cfg.get("skills_enabled", True),
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
    if models.get("ollama"):   env_lines = set_env_key(env_lines, "OLLAMA_MODEL",   models["ollama"])
    if models.get("whisper"):  env_lines = set_env_key(env_lines, "WHISPER_MODEL",  models["whisper"])

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
    if "skills_enabled" in data:
        cfg["skills_enabled"] = bool(data["skills_enabled"])
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

_WA_AUTO_REPLY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "whatsapp", "auto_reply.json")

def _load_auto_reply() -> bool:
    try:
        with open(_WA_AUTO_REPLY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("enabled", True)
    except Exception:
        return True

def _save_auto_reply(enabled: bool):
    os.makedirs(os.path.dirname(_WA_AUTO_REPLY_PATH), exist_ok=True)
    with open(_WA_AUTO_REPLY_PATH, "w", encoding="utf-8") as f:
        json.dump({"enabled": enabled}, f)

_wa_state = {"status": "disconnected", "qr": "", "connected_since": None, "msg_count": 0, "auto_reply": _load_auto_reply()}
_wa_lock  = threading.Lock()

def _wa_bridge_kick():
    """Nach Ilija-Neustart die Bridge kurz neustarten damit sie ihren Status neu meldet."""
    import subprocess as _sp, time as _t
    _t.sleep(3)
    try:
        r = _sp.run(["systemctl", "is-active", "whatsapp-bridge.service"],
                    capture_output=True, text=True, timeout=5)
        if r.stdout.strip() == "active":
            _sp.run(["sudo", "systemctl", "restart", "whatsapp-bridge.service"],
                    capture_output=True, timeout=10)
    except Exception:
        pass

threading.Thread(target=_wa_bridge_kick, daemon=True).start()


@app.route("/api/whatsapp/status")
def whatsapp_status():
    with _wa_lock:
        return jsonify(dict(_wa_state))

@app.route("/api/whatsapp/auto-reply", methods=["POST"])
def toggle_auto_reply():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))
    _save_auto_reply(enabled)
    with _wa_lock:
        _wa_state["auto_reply"] = enabled
    state = "aktiviert" if enabled else "pausiert"
    return jsonify({"ok": True, "enabled": enabled, "message": f"Autonomer Dialog {state}."})


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


@app.route("/api/whatsapp/bridge", methods=["POST"])
def whatsapp_bridge_control():
    """Startet oder stoppt den whatsapp-bridge.service via systemctl."""
    import subprocess as _sp
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "start")
    if action not in ("start", "stop", "restart"):
        return jsonify({"ok": False, "error": "Ungültige Aktion"}), 400
    try:
        result = _sp.run(
            ["sudo", "systemctl", action, "whatsapp-bridge.service"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return jsonify({"ok": True, "action": action})
        return jsonify({"ok": False, "error": result.stderr.strip() or "Unbekannter Fehler"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/whatsapp/bridge-status")
def whatsapp_bridge_service_status():
    """Prüft ob whatsapp-bridge.service läuft."""
    import subprocess as _sp
    try:
        r = _sp.run(["systemctl", "is-active", "whatsapp-bridge.service"],
                    capture_output=True, text=True, timeout=5)
        running = r.stdout.strip() == "active"
        return jsonify({"ok": True, "running": running})
    except Exception as e:
        return jsonify({"ok": False, "running": False, "error": str(e)})


# ── Telegram Bot (Eingehende Nachrichten) ─────────────────────────────────

_TG_STATE      = {"running": False, "connected_since": None, "msg_count": 0}
_tg_state_lock = threading.Lock()
_TG_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "telegram", "telegram_config.json")

def _tg_autostart():
    """Startet den Telegram-Bot automatisch wenn Token + Chat-ID konfiguriert sind."""
    import time as _t
    _t.sleep(4)
    try:
        if not os.path.exists(_TG_CONFIG_PATH):
            return
        with open(_TG_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if not cfg.get("token") or not cfg.get("chat_id") or cfg["chat_id"] == "DEINE_CHAT_ID":
            return
        from skills.telegram_skill import telegram_starten as _tg_start, _bot_running
        if not _bot_running:
            _tg_start()
            with _tg_state_lock:
                _TG_STATE["running"]         = True
                _TG_STATE["connected_since"] = _t.time()
    except Exception as e:
        print(f"[Telegram] Autostart fehlgeschlagen: {e}")

threading.Thread(target=_tg_autostart, daemon=True).start()


@app.route("/telegram")
def telegram_page():
    return render_template("telegram.html")


@app.route("/api/telegram/status")
def telegram_bot_status():
    try:
        from skills.telegram_skill import _bot_running, _cfg_laden
        cfg = _cfg_laden()
        with _tg_state_lock:
            since = _TG_STATE.get("connected_since")
            count = _TG_STATE.get("msg_count", 0)
        return jsonify({
            "ok":      True,
            "running": _bot_running,
            "configured": bool(cfg.get("token") and cfg.get("chat_id") and cfg.get("chat_id") != "DEINE_CHAT_ID"),
            "connected_since": since,
            "msg_count": count,
        })
    except Exception as e:
        return jsonify({"ok": False, "running": False, "error": str(e)})


@app.route("/api/telegram/control", methods=["POST"])
def telegram_bot_control():
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "start")
    try:
        if action == "start":
            from skills.telegram_skill import telegram_starten as _tg_s
            result = _tg_s()
            with _tg_state_lock:
                _TG_STATE["running"]         = True
                _TG_STATE["connected_since"] = _time.time()
            return jsonify({"ok": True, "message": result})
        elif action == "stop":
            from skills.telegram_skill import telegram_stoppen as _tg_stop
            result = _tg_stop()
            with _tg_state_lock:
                _TG_STATE["running"]         = False
                _TG_STATE["connected_since"] = None
            return jsonify({"ok": True, "message": result})
        else:
            return jsonify({"ok": False, "error": "Unbekannte Aktion"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/telegram/msg-count", methods=["POST"])
def telegram_msg_count():
    """Wird intern nach jeder verarbeiteten Nachricht aufgerufen."""
    with _tg_state_lock:
        _TG_STATE["msg_count"] = _TG_STATE.get("msg_count", 0) + 1
    return jsonify({"ok": True})


@app.route("/einstellungen")
def einstellungen_page():
    return render_template("einstellungen.html")


def _lan_ip():
    """Ermittelt die LAN-IP dieses Servers (nicht loopback). Fuer den noVNC-
    Link damit andere Geraete im Netzwerk ihn auch anklicken koennen –
    nicht nur der Host auf dem Ilija selbst laeuft."""
    import socket as _sock
    try:
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        try:
            # UDP-"connect" ohne tatsaechlichen Traffic ermittelt das Interface
            # das in Richtung dieses Ziels raus-routen wuerde
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


@app.route("/api/novnc-info")
def novnc_info():
    import socket as _sock
    import getpass, os as _os, subprocess as _sp
    # 1) noVNC-Server erreichbar?
    available = False
    try:
        with _sock.create_connection(("127.0.0.1", 6080), timeout=0.5):
            available = True
    except OSError:
        pass
    # 2) Laeuft ueberhaupt ein grafischer Desktop auf dieser Maschine?
    #    Pruefung in dieser Reihenfolge:
    #    a) Env-Variablen (greifen wenn Ilija selbst in einer Desktop-Session laeuft)
    #    b) X11-Socket in /tmp/.X11-unix (greift wenn Ilija als Service laeuft, aber ein X-Server aktiv ist)
    #    c) Session-Manager-Prozess (ultimativer Fallback)
    has_desktop = bool(_os.environ.get("DISPLAY") or _os.environ.get("WAYLAND_DISPLAY"))
    if not has_desktop:
        try:
            x11_dir = "/tmp/.X11-unix"
            if _os.path.isdir(x11_dir) and _os.listdir(x11_dir):
                has_desktop = True
        except OSError:
            pass
    if not has_desktop:
        try:
            r = _sp.run(
                ["pgrep", "-f",
                 "lxqt-session|gnome-session|xfce4-session|plasmashell|cinnamon-session|mate-session|lxsession|budgie-wm"],
                capture_output=True, timeout=1
            )
            has_desktop = r.returncode == 0
        except Exception:
            pass
    # Fuer den noVNC-Link den gleichen Host benutzen, ueber den der User
    # Ilija gerade aufruft. Wichtig fuer Setups mit Port-Forwarding (z.B.
    # VirtualBox NAT): dort funktioniert *localhost:6080* aus Sicht des
    # Nutzers, waehrend _lan_ip() die VM-interne IP (10.0.2.15) zurueckgeben
    # wuerde – von aussen nicht erreichbar. Fuer echten LAN-Zugriff ruft
    # der User Ilija ohnehin schon mit der LAN-IP auf; dann steht die
    # richtige IP im request.host.
    client_host = request.host.split(":")[0]
    host = client_host or "localhost"
    user = getpass.getuser()
    return jsonify({
        "available": available,
        "has_desktop": has_desktop,
        "url": f"http://{host}:6080/vnc.html",
        "ssh": f"ssh {user}@{host}",
        "host": host,
        "user": user,
    })


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


# ── Auto-Update Einstellungen ────────────────────────────────
_UPDATE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "update_settings.json")
_UPDATE_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ilija-update.sh"))
# Script als Repo-Besitzer ausführen, damit git/apt-Rechte stimmen.
# Wenn Flask bereits als Repo-Besitzer läuft (Normalfall bei install.sh), kein sudo-u nötig.
try:
    _UPDATE_SCRIPT_USER = __import__("pwd").getpwuid(
        os.stat(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".git")).st_uid
    ).pw_name
    _CURRENT_SERVICE_USER = __import__("pwd").getpwuid(os.getuid()).pw_name
    if _UPDATE_SCRIPT_USER == _CURRENT_SERVICE_USER:
        _UPDATE_SCRIPT_USER = None  # gleicher User → direkt ausführen, kein sudo-u
except Exception:
    _UPDATE_SCRIPT_USER = None

def _load_update_settings():
    try:
        with open(_UPDATE_CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"auto_update_enabled": True, "update_time": "03:00"}

def _save_update_settings(cfg):
    os.makedirs(os.path.dirname(_UPDATE_CONFIG_PATH), exist_ok=True)
    with open(_UPDATE_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def _rewrite_crontab(enabled, time_str):
    import subprocess as _sp
    try:
        result = _sp.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [l for l in result.stdout.splitlines() if "ilija-update.sh" not in l]
        if enabled and time_str:
            h, m = time_str.split(":")
            lines.append(f"{m} {h} * * * {_UPDATE_SCRIPT} >> ~/ilija-update.log 2>&1")
        new_crontab = "\n".join(lines) + "\n"
        _sp.run(["crontab", "-"], input=new_crontab, text=True, check=True)
        return True
    except Exception:
        return False

@app.route("/api/update-settings", methods=["GET"])
def get_update_settings():
    return jsonify(_load_update_settings())

@app.route("/api/update-settings", methods=["POST"])
def save_update_settings_route():
    data = request.get_json() or {}
    cfg = _load_update_settings()
    if "auto_update_enabled" in data:
        cfg["auto_update_enabled"] = bool(data["auto_update_enabled"])
    if "update_time" in data:
        cfg["update_time"] = str(data["update_time"])
    _save_update_settings(cfg)
    _rewrite_crontab(cfg["auto_update_enabled"], cfg["update_time"])
    return jsonify({"ok": True, "message": "Update-Einstellungen gespeichert."})

_UPDATE_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "update_run.log")
_update_running = False
_update_lock = __import__("threading").Lock()

@app.route("/api/update-now", methods=["POST"])
def update_now():
    import subprocess as _sp, threading as _th
    global _update_running
    with _update_lock:
        if _update_running:
            return jsonify({"ok": False, "message": "Update läuft bereits."})
        if not os.path.isfile(_UPDATE_SCRIPT):
            return jsonify({"ok": False, "message": "Update-Skript nicht gefunden."})
        _update_running = True
    def _run():
        global _update_running
        try:
            os.makedirs(os.path.dirname(_UPDATE_LOG_PATH), exist_ok=True)
            with open(_UPDATE_LOG_PATH, "w", buffering=1) as log:
                log.write("=== Ilija OS Update gestartet ===\n\n")
                run_as = _UPDATE_SCRIPT_USER if _UPDATE_SCRIPT_USER else None
                cmd = (["sudo", "-u", run_as, "/bin/bash", _UPDATE_SCRIPT]
                       if run_as else ["/bin/bash", _UPDATE_SCRIPT])
                proc = _sp.Popen(cmd, stdout=log, stderr=log, text=True)
                proc.wait()
                log.write(f"\n=== Fertig (Exit-Code: {proc.returncode}) ===\n")
        except Exception as e:
            with open(_UPDATE_LOG_PATH, "a") as log:
                log.write(f"\nFehler: {e}\n")
        finally:
            _update_running = False
    _th.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/update-log", methods=["GET"])
def update_log():
    global _update_running
    try:
        with open(_UPDATE_LOG_PATH, "r") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    return jsonify({"running": _update_running, "log": content})


# ── Setup-Status (Wizard / Settings Erkennung) ───────────────
@app.route("/api/setup-status")
def setup_status():
    """Gibt zurück ob Ilija bereits eingerichtet ist (für Wizard vs. Settings-Modus)."""
    env = {}
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    has_ki   = bool(env.get("ANTHROPIC_API_KEY") or env.get("GOOGLE_API_KEY") or env.get("GEMINI_API_KEY") or env.get("OPENAI_API_KEY"))
    has_email  = os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "email", "email_config.json"))
    has_phone  = os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone_config.json"))
    return jsonify({"setup_complete": has_ki, "has_ki": has_ki, "has_email": has_email, "has_phone": has_phone})


# ── E-Mail-Einstellungen ──────────────────────────────────────
_EMAIL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "email", "email_config.json")
_EMAIL_PROVIDERS = {
    "gmail":   {"imap_host": "imap.gmail.com",            "imap_port": 993, "smtp_host": "smtp.gmail.com",         "smtp_port": 587},
    "outlook": {"imap_host": "outlook.office365.com",     "imap_port": 993, "smtp_host": "smtp.office365.com",     "smtp_port": 587},
    "gmx":     {"imap_host": "imap.gmx.net",              "imap_port": 993, "smtp_host": "mail.gmx.net",           "smtp_port": 587},
    "webde":   {"imap_host": "imap.web.de",               "imap_port": 993, "smtp_host": "smtp.web.de",            "smtp_port": 587},
    "yahoo":   {"imap_host": "imap.mail.yahoo.com",       "imap_port": 993, "smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587},
    "ionos":   {"imap_host": "imap.ionos.de",             "imap_port": 993, "smtp_host": "smtp.ionos.de",          "smtp_port": 587},
    "eigener": {"imap_host": "",                           "imap_port": 993, "smtp_host": "",                       "smtp_port": 587},
}

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    """Gibt ungelesene Notifications zurück und markiert sie als gelesen."""
    import threading as _thr
    _nq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "notifications.json")
    _nl = _thr.Lock()
    try:
        if not os.path.exists(_nq):
            return jsonify([])
        with open(_nq, encoding="utf-8") as f:
            queue = json.load(f)
        ungelesen = [n for n in queue if not n.get("gelesen")]
        for n in queue:
            n["gelesen"] = True
        with open(_nq, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
        return jsonify(ungelesen)
    except Exception as e:
        return jsonify([])

@app.route("/api/notifications/<nid>", methods=["DELETE"])
def delete_notification(nid):
    _nq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "notifications.json")
    try:
        if not os.path.exists(_nq):
            return jsonify({"ok": True})
        with open(_nq, encoding="utf-8") as f:
            queue = json.load(f)
        queue = [n for n in queue if n.get("id") != nid]
        with open(_nq, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/email-settings", methods=["GET"])
def get_email_settings():
    cfg = {}
    if os.path.exists(_EMAIL_CONFIG_PATH):
        try:
            with open(_EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    if cfg.get("passwort"):
        cfg["passwort"] = "****"
    return jsonify({"config": cfg, "providers": list(_EMAIL_PROVIDERS.keys())})

@app.route("/api/email-settings", methods=["POST"])
def save_email_settings():
    data = request.get_json() or {}
    cfg = {}
    if os.path.exists(_EMAIL_CONFIG_PATH):
        try:
            with open(_EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    provider = data.get("provider", cfg.get("provider", "outlook"))
    passwort  = data.get("passwort", "")
    if "****" in passwort:
        passwort = cfg.get("passwort", "")
    provider_cfg = _EMAIL_PROVIDERS.get(provider, {})
    new_cfg = {
        "provider":      provider,
        "email_adresse": data.get("email_adresse", cfg.get("email_adresse", "")),
        "passwort":      passwort,
        "imap_host":     data.get("imap_host") or provider_cfg.get("imap_host", ""),
        "imap_port":     int(data.get("imap_port") or provider_cfg.get("imap_port", 993)),
        "smtp_host":     data.get("smtp_host") or provider_cfg.get("smtp_host", ""),
        "smtp_port":     int(data.get("smtp_port") or provider_cfg.get("smtp_port", 587)),
        "konfiguriert_am": __import__("datetime").datetime.now().isoformat(),
    }
    os.makedirs(os.path.dirname(_EMAIL_CONFIG_PATH), exist_ok=True)
    with open(_EMAIL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(new_cfg, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "message": "E-Mail-Einstellungen gespeichert."})

@app.route("/api/email-providers")
def get_email_providers():
    return jsonify(_EMAIL_PROVIDERS)


# ── Telegram-Einstellungen ────────────────────────────────────
_TG_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "telegram", "telegram_config.json")

@app.route("/api/telegram-settings", methods=["GET"])
def get_telegram_settings():
    cfg = {}
    if os.path.exists(_TG_CONFIG_PATH):
        try:
            with open(_TG_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    if cfg.get("token"):
        t = cfg["token"]
        cfg["token"] = t[:8] + "****" if len(t) > 8 else "****"
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    allowed_users = ""
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("TELEGRAM_ALLOWED_USERS="):
                    allowed_users = line.strip().split("=", 1)[1]
    cfg["allowed_users"] = allowed_users
    return jsonify(cfg)

@app.route("/api/telegram-settings", methods=["POST"])
def save_telegram_settings():
    data = request.get_json() or {}
    cfg = {}
    if os.path.exists(_TG_CONFIG_PATH):
        try:
            with open(_TG_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    token = data.get("token", "")
    if "****" in token:
        token = cfg.get("token", "")
    new_cfg = {
        "token":           token,
        "chat_id":         data.get("chat_id", cfg.get("chat_id", "")),
        "konfiguriert_am": __import__("datetime").datetime.now().isoformat(),
    }
    os.makedirs(os.path.dirname(_TG_CONFIG_PATH), exist_ok=True)
    with open(_TG_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(new_cfg, f, ensure_ascii=False, indent=2)
    # TELEGRAM_ALLOWED_USERS in .env schreiben
    allowed = data.get("allowed_users", "")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_lines = f.readlines()
    found = False
    for i, line in enumerate(env_lines):
        if line.strip().startswith("TELEGRAM_ALLOWED_USERS=") or line.strip().startswith("#TELEGRAM_ALLOWED_USERS="):
            if allowed:
                env_lines[i] = f"TELEGRAM_ALLOWED_USERS={allowed}\n"
            else:
                env_lines[i] = f"#TELEGRAM_ALLOWED_USERS=\n"
            found = True
            break
    if not found and allowed:
        env_lines.append(f"TELEGRAM_ALLOWED_USERS={allowed}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(env_lines)
    return jsonify({"ok": True, "message": "Telegram-Einstellungen gespeichert."})


# ── FritzBox-Einstellungen ────────────────────────────────────
_SIP_KEYS = ["SIP_SERVER", "SIP_PORT", "SIP_USER", "SIP_PASSWORD", "SIP_MY_IP", "SIP_MIC_ID"]

def _load_env_dict():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    d = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
    return d

def _save_env_keys(new_vars: dict):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    for key, value in new_vars.items():
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"#{key}="):
                lines[i] = f"{key}={value}\n" if value else f"#{key}=\n"
                found = True
                break
        if not found and value:
            lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

@app.route("/api/fritzbox-settings", methods=["GET"])
def get_fritzbox_settings():
    env = _load_env_dict()
    result = {k: env.get(k, "") for k in _SIP_KEYS}
    if result.get("SIP_PASSWORD"):
        result["SIP_PASSWORD"] = "****"
    return jsonify(result)

@app.route("/api/fritzbox-settings", methods=["POST"])
def save_fritzbox_settings():
    data  = request.get_json() or {}
    env   = _load_env_dict()
    patch = {}
    for key in _SIP_KEYS:
        val = data.get(key, "")
        if key == "SIP_PASSWORD" and "****" in str(val):
            val = env.get("SIP_PASSWORD", "")
        patch[key] = val
    _save_env_keys(patch)
    return jsonify({"ok": True, "message": "FritzBox-Einstellungen gespeichert."})

# ── Eigener Endpunkt ─────────────────────────────────────────
_CUSTOM_EP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "custom_endpoint.json")

@app.route("/api/custom-endpoint", methods=["GET"])
def get_custom_endpoint():
    try:
        with open(_CUSTOM_EP_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {"url": "", "api_key": "", "model": ""}
    if cfg.get("api_key"):
        cfg["api_key"] = "****"
    return jsonify(cfg)

@app.route("/api/custom-endpoint", methods=["POST"])
def save_custom_endpoint():
    global kernel
    data = request.get_json() or {}
    try:
        with open(_CUSTOM_EP_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        old = {}
    cfg = {
        "url":     old.get("url", "") if "****" in str(data.get("url", "")) else data.get("url", "").strip(),
        "api_key": old.get("api_key", "") if "****" in str(data.get("api_key", "")) else data.get("api_key", "").strip(),
        "model":   data.get("model", "").strip(),
    }
    os.makedirs(os.path.dirname(_CUSTOM_EP_PATH), exist_ok=True)
    with open(_CUSTOM_EP_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    with kernel_lock:
        kernel = None
    return jsonify({"ok": True, "message": "Eigener Endpunkt gespeichert."})

@app.route("/api/custom-endpoint/test", methods=["POST"])
def test_custom_endpoint():
    data = request.get_json() or {}
    url  = (data.get("url") or "").strip().rstrip("/")
    key  = (data.get("api_key") or "custom").strip() or "custom"
    if not url:
        return jsonify({"ok": False, "message": "Kein URL angegeben."})
    try:
        import requests as req
        r = req.get(f"{url}/models", headers={"Authorization": f"Bearer {key}"}, timeout=6)
        count = len(r.json().get("data", []))
        return jsonify({"ok": True, "message": f"Verbunden ✓ – {count} Modell(e) gefunden"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Nicht erreichbar: {e}"})


@app.route("/api/fritzbox-test", methods=["POST"])
def test_fritzbox():
    import socket
    data   = request.get_json() or {}
    server = data.get("server", "fritz.box")
    port   = int(data.get("port", 5060))
    try:
        sock = socket.create_connection((server, port), timeout=4)
        sock.close()
        return jsonify({"ok": True, "message": f"FritzBox erreichbar auf {server}:{port}"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Nicht erreichbar: {e}"})


# ── Server-Einstellungen ──────────────────────────────────────
@app.route("/api/server-settings", methods=["GET"])
def get_server_settings():
    env = _load_env_dict()
    return jsonify({
        "port":      env.get("PORT", "5001"),
        "debug":     env.get("DEBUG", "false").lower() == "true",
        "web_user":  env.get("WEB_USER", ""),
        "web_pw_set": bool(env.get("WEB_PASSWORD")),
    })

@app.route("/api/server-settings", methods=["POST"])
def save_server_settings():
    data = request.get_json() or {}
    patch = {}
    if "port"  in data: patch["PORT"]  = str(data["port"])
    if "debug" in data: patch["DEBUG"] = "true" if data["debug"] else "false"
    if data.get("web_user"): patch["WEB_USER"] = data["web_user"]
    if data.get("web_pw") and "****" not in data["web_pw"]: patch["WEB_PASSWORD"] = data["web_pw"]
    _save_env_keys(patch)
    return jsonify({"ok": True, "message": "Server-Einstellungen gespeichert."})


# ── Eingangskanäle (Telefon + WhatsApp) ──────────────────────
_PHONE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone_config.json")
_WA_CONFIG_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "whatsapp", "whatsapp_config.json")

@app.route("/api/eingangskanale-settings", methods=["GET"])
def get_eingangskanale_settings():
    phone = {}
    if os.path.exists(_PHONE_CONFIG_PATH):
        try:
            with open(_PHONE_CONFIG_PATH, "r", encoding="utf-8") as f:
                phone = json.load(f)
        except Exception:
            pass
    wa = {}
    if os.path.exists(_WA_CONFIG_PATH):
        try:
            with open(_WA_CONFIG_PATH, "r", encoding="utf-8") as f:
                wa = json.load(f)
        except Exception:
            pass
    return jsonify({"phone": phone, "whatsapp": wa})

@app.route("/api/eingangskanale-settings", methods=["POST"])
def save_eingangskanale_settings():
    data  = request.get_json() or {}
    phone = data.get("phone", {})
    wa    = data.get("whatsapp", {})
    if phone:
        with open(_PHONE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(phone, f, ensure_ascii=False, indent=2)
    if wa:
        os.makedirs(os.path.dirname(_WA_CONFIG_PATH), exist_ok=True)
        with open(_WA_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(wa, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "message": "Eingangskanal-Einstellungen gespeichert."})


# ── DMS-Einstellungen ─────────────────────────────────────────
@app.route("/api/dms-settings", methods=["GET"])
def get_dms_settings():
    try:
        from skills.dms import _get_config as _dms_cfg
        cfg = _dms_cfg()
    except Exception:
        cfg = {"archiv_pfad": "data/dms/archiv", "import_pfad": "data/dms/import"}
    return jsonify(cfg)

@app.route("/api/dms-settings", methods=["POST"])
def save_dms_settings():
    data = request.get_json() or {}
    try:
        from skills.dms import _get_config as _dms_cfg, _save_config as _dms_save
        cfg = _dms_cfg()
        if data.get("archiv_pfad"): cfg["archiv_pfad"] = data["archiv_pfad"]
        if data.get("import_pfad"): cfg["import_pfad"] = data["import_pfad"]
        # Passwort als SHA-256 speichern
        pw = data.get("passwort", "")
        if pw and "****" not in pw:
            import hashlib
            cfg["passwort_hash"] = hashlib.sha256(pw.encode()).hexdigest()
        elif data.get("passwort_entfernen"):
            cfg.pop("passwort_hash", None)
        _dms_save(cfg)
        return jsonify({"ok": True, "message": "DMS-Einstellungen gespeichert."})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


# ── Google-Status ─────────────────────────────────────────────
@app.route("/api/google-status")
def get_google_status():
    """
    Status aller 4 Google-Services + Credential-Typ-Info für die UI.

    Response-Struktur:
      {
        credentials_ok:       bool,          # credentials.json ist hochgeladen
        credentials_type:     "installed"|"web"|null,
        credentials_client_id: str|null,     # erstes Kürzel zur Identifikation
        redirect_uri_suggested: str,         # je nach Typ die passende URL
        services: { gmail, google_drive, google_docs, google_kalender }
      }
    """
    from skills.google_oauth_helper import credentials_info
    info = credentials_info()
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base, "data")
    services = {
        "gmail":           os.path.exists(os.path.join(data_dir, "gmail",           "token.json")),
        "google_drive":    os.path.exists(os.path.join(data_dir, "google_drive",    "token.json")),
        "google_docs":     os.path.exists(os.path.join(data_dir, "google_docs",     "token.json")),
        "google_kalender": os.path.exists(os.path.join(data_dir, "google_kalender", "token.json")),
    }
    # Welche redirect_uri sollte der User in Google Cloud Console eintragen?
    # Je nach Typ unterschiedlich — Desktop-Creds können nur localhost,
    # Webanwendungs-Creds erlauben alles was in der Console steht
    from skills.google_oauth_helper import _CREDENTIALS_PATH  # noqa
    def _lan_ip_local():
        import socket as _s
        try:
            sk = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
            sk.connect(("8.8.8.8", 80))
            ip = sk.getsockname()[0]
            sk.close()
            return ip
        except OSError:
            return "127.0.0.1"
    port = int(os.environ.get("PORT", 5001))
    if info["type"] == "installed":
        suggested = f"http://localhost:{port}/api/google-oauth-callback"
    elif info["type"] == "web":
        # Konsistenz mit /api/google-oauth-start: wenn credentials.json schon
        # eine passende redirect_uri enthält, zeige die, sonst LAN-IP-Vorschlag
        configured = info.get("redirect_uris_configured") or []
        callback_uris = [u for u in configured if u.endswith("/api/google-oauth-callback")]
        if callback_uris:
            suggested = callback_uris[0]
        else:
            suggested = f"http://{_lan_ip_local()}:{port}/api/google-oauth-callback"
    else:
        suggested = f"http://localhost:{port}/api/google-oauth-callback"
    return jsonify({
        "credentials_ok":        info["exists"],
        "credentials_type":      info["type"],
        "credentials_client_id": (info["client_id"] or "")[:40],
        "redirect_uri_suggested": suggested,
        "services":              services,
    })


@app.route("/api/google-credentials-upload", methods=["POST"])
def upload_google_credentials():
    from flask import request as _req
    if "file" not in _req.files:
        return jsonify({"ok": False, "message": "Keine Datei"}), 400
    f = _req.files["file"]
    if not f.filename.endswith(".json"):
        return jsonify({"ok": False, "message": "Nur JSON-Dateien erlaubt"}), 400
    try:
        content = json.loads(f.read().decode("utf-8"))
    except Exception:
        return jsonify({"ok": False, "message": "Ungültige JSON-Datei"}), 400
    if "installed" not in content and "web" not in content:
        return jsonify({"ok": False, "message": "Keine gültige Google credentials.json"}), 400
    base = os.path.dirname(os.path.abspath(__file__))
    dest = os.path.join(base, "data", "google_kalender", "credentials.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as out:
        json.dump(content, out, ensure_ascii=False, indent=2)
    cred_type = "installed" if "installed" in content else "web"
    return jsonify({"ok": True, "message": "credentials.json erfolgreich installiert.",
                    "type": cred_type})


# ── Google-OAuth-Flow ─────────────────────────────────────────
@app.route("/api/google-oauth-start/<service>", methods=["POST"])
def google_oauth_start(service):
    """
    Startet den OAuth-Flow für einen Google-Service.
    Frontend ruft das auf, bekommt die auth_url zurück und öffnet die in
    einem neuen Browser-Tab via window.open().

    URL wird so gebaut dass die redirect_uri zum Credential-Typ passt:
    - Desktop-Credentials: http://localhost:5001/api/google-oauth-callback
    - Webanwendungs-Credentials: http://<ilija-lan-ip>:5001/api/google-oauth-callback
    """
    from skills.google_oauth_helper import start_oauth, credentials_info
    info = credentials_info()
    if not info["exists"]:
        return jsonify({"ok": False, "error": "credentials.json fehlt – "
                        "bitte zuerst hochladen"}), 400

    port = int(os.environ.get("PORT", 5001))
    if info["type"] == "installed":
        # Desktop-App: Google akzeptiert nur localhost/127.0.0.1
        redirect_uri = f"http://localhost:{port}/api/google-oauth-callback"
    elif info["type"] == "web":
        # Webanwendung: die redirect_uri die wir hier übergeben MUSS in der
        # Google Cloud Console als "Authorized redirect URI" eingetragen sein.
        # Strategie – wir nehmen die beste Übereinstimmung aus den vorhandenen
        # Quellen in dieser Reihenfolge:
        #   1) /api/google-oauth-callback-URI aus credentials.json
        #      (so wie der User sie in der Console eingetragen hat)
        #   2) Fallback: LAN-IP (für direkten LAN-Zugriff ohne Port-Forwarding)
        configured = info.get("redirect_uris_configured") or []
        callback_uris = [u for u in configured if u.endswith("/api/google-oauth-callback")]
        if callback_uris:
            redirect_uri = callback_uris[0]
        else:
            import socket as _s
            try:
                sk = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
                sk.connect(("8.8.8.8", 80))
                lan_ip = sk.getsockname()[0]
                sk.close()
            except OSError:
                lan_ip = "localhost"
            redirect_uri = f"http://{lan_ip}:{port}/api/google-oauth-callback"
    else:
        return jsonify({"ok": False, "error": "credentials.json ist weder "
                        "'installed' noch 'web' – bitte korrekte OAuth-"
                        "Credentials aus der Google Cloud Console laden"}), 400

    try:
        auth_url, state = start_oauth(service, redirect_uri)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"OAuth-Start fehlgeschlagen: {e}"}), 500

    return jsonify({
        "ok":           True,
        "auth_url":     auth_url,
        "state":        state,
        "redirect_uri": redirect_uri,
    })


@app.route("/api/google-oauth-callback")
def google_oauth_callback():
    """
    Google redirectet nach erfolgreichem Login hierher mit ?code=...&state=...
    Wir tauschen den code gegen das Token, speichern es und zeigen eine
    Erfolgsseite die sich selbst schließt.
    """
    from skills.google_oauth_helper import complete_oauth
    code  = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    def _html_response(ok, title, message, service=None):
        color = "#2dd4bf" if ok else "#ef4444"
        service_js = f"'{service}'" if service else "null"
        return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>Ilija OS · Google-Autorisierung</title>
<style>
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
       display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px}}
  .box{{max-width:500px;text-align:center;background:#1e293b;border:1px solid {color};
       padding:40px 30px;border-radius:12px}}
  h1{{color:{color};margin:0 0 12px;font-size:1.4rem}}
  p{{margin:8px 0;line-height:1.5}}
  .small{{font-size:.85rem;color:#94a3b8;margin-top:20px}}
</style></head><body>
<div class="box">
  <h1>{title}</h1>
  <p>{message}</p>
  <p class="small">Dieses Fenster schließt sich automatisch in 3 Sekunden.</p>
</div>
<script>
  // Dreifach-Benachrichtigung: postMessage, BroadcastChannel, localStorage.
  // Grund: Chrome's COOP-Policy kann window.opener nach dem Google-Redirect
  // auf null setzen; BroadcastChannel und localStorage-Events ueberleben das.
  var _evt = {{type:'google-oauth', ok:{str(ok).lower()}, service:{service_js}, ts:Date.now()}};
  try {{ if (window.opener) window.opener.postMessage(_evt, '*'); }} catch(_) {{}}
  try {{ var _bc = new BroadcastChannel('ilija-google-oauth'); _bc.postMessage(_evt); _bc.close(); }} catch(_) {{}}
  try {{ localStorage.setItem('ilija-google-oauth-event', JSON.stringify(_evt)); }} catch(_) {{}}
  setTimeout(() => window.close(), 3000);
</script>
</body></html>"""

    if error:
        return _html_response(False, "Abgebrochen",
                              f"Google hat die Autorisierung abgebrochen: {error}"), 400
    if not code or not state:
        return _html_response(False, "Fehler",
                              "Fehlende Parameter – OAuth konnte nicht abgeschlossen werden."), 400
    try:
        service = complete_oauth(code, state)
    except ValueError as e:
        return _html_response(False, "Autorisierung fehlgeschlagen", str(e)), 400
    except Exception as e:
        return _html_response(False, "Technischer Fehler", str(e)), 500

    label = {"gmail": "Gmail", "google_drive": "Google Drive",
             "google_docs": "Google Docs", "google_kalender": "Google Kalender"}.get(service, service)
    return _html_response(True, "Verbunden ✓",
                          f"{label} wurde erfolgreich mit Ilija OS verknüpft.",
                          service=service)


@app.route("/api/google-revoke/<service>", methods=["POST"])
def google_revoke(service):
    """Löscht das token.json eines Google-Services (lokaler Logout)."""
    from skills.google_oauth_helper import revoke
    ok = revoke(service)
    return jsonify({"ok": ok})


@app.route("/api/whatsapp", methods=["POST"])
def whatsapp_bridge():
    """Empfängt WhatsApp-Nachrichten vom Baileys-Bridge und gibt Ilijas Antwort zurück."""
    data = request.get_json(silent=True) or {}
    sender_jid = (data.get("from") or "").strip()
    name       = (data.get("name") or sender_jid or "Unbekannt").strip()
    text       = (data.get("text") or "").strip()

    if not text:
        return jsonify({"reply": ""}), 200

    with _wa_lock:
        auto_reply_on = _wa_state.get("auto_reply", True)
    if not auto_reply_on:
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
