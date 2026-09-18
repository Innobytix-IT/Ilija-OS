"""
agent_routes.py – API-Routen für den Ilija Coding-/Cowork-Agenten
================================================================
Integration in web_server.py:
    from agent_routes import register_agent_routes
    register_agent_routes(app)
"""

import os
import requests
from flask import request, jsonify
import agent_core


def _gemini_models():
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        return []
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": key}, timeout=10)
        out = []
        for m in r.json().get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                name = m.get("name", "").replace("models/", "")
                if name.startswith("gemini"):
                    out.append(name)
        return sorted(out)
    except Exception:
        return []


def _openai_models():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return []
    try:
        r = requests.get("https://api.openai.com/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        return sorted([i for i in ids if i.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))])
    except Exception:
        return []


def _anthropic_models():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return []
    try:
        r = requests.get("https://api.anthropic.com/v1/models",
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                         timeout=10)
        return sorted([m.get("id", "") for m in r.json().get("data", []) if m.get("id")])
    except Exception:
        return []


def _ollama_models():
    try:
        import ollama
        return sorted([m.get("name", "") for m in ollama.list().get("models", []) if m.get("name")])
    except Exception:
        return []


def _custom_models():
    from providers import _load_custom_endpoint_cfg
    cfg = _load_custom_endpoint_cfg()
    url = cfg.get("url", "").rstrip("/")
    if not url:
        return []
    try:
        key = cfg.get("api_key") or "custom"
        r = requests.get(f"{url}/models",
                         headers={"Authorization": f"Bearer {key}"},
                         timeout=8)
        data = r.json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        return sorted([i for i in ids if i])
    except Exception:
        # Fallback: konfigurierten Modellnamen als einzigen Eintrag
        m = cfg.get("model", "")
        return [m] if m else []


def register_agent_routes(app):

    @app.route("/api/models/available")
    def models_available():
        return jsonify({"gemini": _gemini_models(), "openai": _openai_models(),
                        "anthropic": _anthropic_models(), "ollama": _ollama_models(),
                        "custom": _custom_models()})

    @app.route("/api/agent/coding", methods=["POST"])
    def agent_coding():
        data = request.get_json() or {}
        msg  = (data.get("message") or "").strip()
        mode = data.get("mode", "plan")
        prov = data.get("provider", "auto")
        if not msg:
            return jsonify({"error": "Leere Nachricht"}), 400
        result = agent_core.run_coding(msg, mode=mode, provider_mode=prov,
                                       sid=data.get("session", "default"))
        return jsonify(result)

    @app.route("/api/agent/coding/start", methods=["POST"])
    def agent_coding_start():
        data = request.get_json() or {}
        msg  = (data.get("message") or "").strip()
        if not msg:
            return jsonify({"error": "Leere Nachricht"}), 400
        rid = agent_core.start_run(msg, mode=data.get("mode", "plan"),
                                   provider_mode=data.get("provider", "auto"),
                                   sid=data.get("session", "default"))
        return jsonify({"run_id": rid})

    @app.route("/api/agent/cowork/start", methods=["POST"])
    def agent_cowork_start():
        data = request.get_json() or {}
        msg  = (data.get("message") or "").strip()
        if not msg:
            return jsonify({"error": "Leere Nachricht"}), 400
        try:
            from web_server import get_kernel, kernel_lock
            with kernel_lock:
                k = get_kernel()
        except Exception as e:
            return jsonify({"error": f"Kernel nicht verfügbar: {e}"}), 500
        rid = agent_core.start_run(msg, mode="cowork",
                                   provider_mode=data.get("provider", "auto"),
                                   sid=data.get("session", "default"),
                                   kind="cowork", kernel=k)
        return jsonify({"run_id": rid})

    @app.route("/api/agent/coding/poll")
    def agent_coding_poll():
        rid = request.args.get("run_id", "")
        return jsonify(agent_core.poll_run(rid))

    @app.route("/api/agent/coding/decide", methods=["POST"])
    def agent_coding_decide():
        data = request.get_json() or {}
        ok = agent_core.decide_run(data.get("run_id", ""), bool(data.get("allow")))
        return jsonify({"ok": ok})

    @app.route("/api/agent/clear", methods=["POST"])
    def agent_clear():
        data = request.get_json(silent=True) or {}
        return jsonify({"message": agent_core.clear_history(data.get("session", "default"))})

    @app.route("/api/agent/shell", methods=["GET", "POST"])
    def agent_shell():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            state = agent_core.set_shell_enabled(bool(data.get("enabled")))
            return jsonify({"enabled": state})
        return jsonify({"enabled": agent_core.shell_enabled()})

    @app.route("/api/agent/workspace", methods=["GET", "POST"])
    def agent_workspace():
        if request.method == "POST":
            data = request.get_json() or {}
            try:
                ws = agent_core.set_workspace(data.get("path", ""))
                return jsonify({"workspace": ws})
            except Exception as e:
                return jsonify({"error": str(e)}), 400
        return jsonify(agent_core.workspace_info())

    @app.route("/api/agent/upload", methods=["POST"])
    def agent_upload():
        if "files" not in request.files:
            return jsonify({"error": "Keine Datei"}), 400
        saved = []
        for f in request.files.getlist("files"):
            if f and f.filename:
                saved.append(agent_core.save_upload(f.filename, f.read()))
        return jsonify({"anzahl": len(saved), "dateien": saved,
                        "workspace": agent_core.workspace_info()["workspace"]})
