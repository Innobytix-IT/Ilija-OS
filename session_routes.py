"""
session_routes.py – Persistente Chat-Sessions für Coworking & Coding.
Sessions liegen in data/sessions/ (server-seitig, nicht per UI löschbar).
"""

import os
import json
import uuid
from datetime import datetime
from flask import request, jsonify

SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)


def _path(sid: str) -> str:
    # Pfad-Traversal verhindern
    clean = "".join(c for c in sid if c.isalnum() or c in "-_")
    return os.path.join(SESSION_DIR, f"{clean}.json")


def _load(sid: str) -> dict | None:
    p = _path(sid)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save(session: dict) -> None:
    with open(_path(session["id"]), "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def _list_all() -> list[dict]:
    result = []
    try:
        for fname in os.listdir(SESSION_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(SESSION_DIR, fname), "r", encoding="utf-8") as f:
                    s = json.load(f)
                # Nur Metadaten zurückgeben (keine messages)
                result.append({
                    "id":         s.get("id", ""),
                    "title":      s.get("title", "Unterhaltung"),
                    "mode":       s.get("mode", "coworking"),
                    "created_at": s.get("created_at", ""),
                    "updated_at": s.get("updated_at", ""),
                    "msg_count":  len(s.get("messages", [])),
                })
            except Exception:
                pass
    except Exception:
        pass
    return sorted(result, key=lambda x: x.get("updated_at", ""), reverse=True)


def register_session_routes(app, get_kernel, kernel_lock):

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        mode = request.args.get("mode", "")
        sessions = _list_all()
        if mode:
            sessions = [s for s in sessions if s.get("mode") == mode]
        return jsonify(sessions)

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        data = request.get_json() or {}
        sid  = str(uuid.uuid4())[:12]
        now  = datetime.now().isoformat()
        session = {
            "id":         sid,
            "title":      (data.get("title") or "Neue Unterhaltung")[:80],
            "mode":       data.get("mode", "coworking"),
            "created_at": now,
            "updated_at": now,
            "messages":   data.get("messages", []),
        }
        _save(session)
        return jsonify({"ok": True, "id": sid})

    @app.route("/api/sessions/<sid>", methods=["GET"])
    def get_session(sid):
        s = _load(sid)
        if s is None:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        return jsonify(s)

    @app.route("/api/sessions/<sid>", methods=["PUT"])
    def update_session(sid):
        s = _load(sid)
        if s is None:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        data = request.get_json() or {}
        if "title" in data:
            s["title"] = str(data["title"])[:80]
        if "messages" in data:
            s["messages"] = data["messages"]
        s["updated_at"] = datetime.now().isoformat()
        _save(s)
        return jsonify({"ok": True})

    @app.route("/api/sessions/<sid>", methods=["DELETE"])
    def delete_session(sid):
        p = _path(sid)
        if os.path.exists(p):
            os.remove(p)
        return jsonify({"ok": True})

    @app.route("/api/sessions/<sid>/load", methods=["POST"])
    def load_session_into_kernel(sid):
        """Lädt Session-Verlauf in den Kernel (nur Coworking)."""
        s = _load(sid)
        if s is None:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        msgs = s.get("messages", [])
        with kernel_lock:
            k = get_kernel()
            k.state.chat_history  = [m for m in msgs if m.get("role") in ("user", "assistant")]
            k.state.message_count = len(k.state.chat_history)
        return jsonify({"ok": True, "message_count": len(msgs)})
