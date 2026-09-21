"""
fristen_routes.py – Fristen & Vorlagen Modul
Verwaltet Frist-Vorlagen, Empfänger und Erinnerungseinstellungen.
"""

import os
import json
import uuid
import shutil
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, current_app
from werkzeug.utils import secure_filename

fristen_bp = Blueprint("fristen", __name__)

_BASE   = os.path.dirname(os.path.abspath(__file__))
_DATA   = os.path.join(_BASE, "data", "fristen")
_INDEX  = os.path.join(_DATA, "vorlagen.json")
_FILES  = os.path.join(_DATA, "dateien")

os.makedirs(_FILES, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(_INDEX):
        return []
    try:
        with open(_INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(data: list):
    os.makedirs(_DATA, exist_ok=True)
    with open(_INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find(vorlagen: list, vid: str):
    return next((v for v in vorlagen if v["id"] == vid), None)


# ── Seite ─────────────────────────────────────────────────────────────────────

@fristen_bp.route("/fristen")
def fristen_page():
    return render_template("fristen.html")


# ── API ───────────────────────────────────────────────────────────────────────

@fristen_bp.route("/api/fristen", methods=["GET"])
def api_list():
    vorlagen = _load()
    # Nächste Frist berechnen (für Sortierung)
    heute = datetime.today().date()
    for v in vorlagen:
        try:
            fd = datetime.strptime(v["frist_datum"], "%Y-%m-%d").date()
            v["_tage_bis_frist"] = (fd - heute).days
        except Exception:
            v["_tage_bis_frist"] = 9999
    vorlagen.sort(key=lambda v: v["_tage_bis_frist"])
    return jsonify(vorlagen)


@fristen_bp.route("/api/fristen", methods=["POST"])
def api_create():
    d = request.get_json(force=True) or {}
    vorlage = {
        "id":               str(uuid.uuid4()),
        "name":             d.get("name", "").strip(),
        "beschreibung":     d.get("beschreibung", "").strip(),
        "datei":            "",
        "frist_datum":      d.get("frist_datum", ""),
        "wiederholung":     d.get("wiederholung", None),
        "erinnerung_wochen": d.get("erinnerung_wochen", [4, 2, 1]),
        "empfaenger": {
            "name":  d.get("empf_name", "").strip(),
            "email": d.get("empf_email", "").strip(),
            "fax":   d.get("empf_fax", "").strip(),
        },
        "benachrichtigung": d.get("benachrichtigung", ["chat"]),
        "erstellt":         datetime.now().isoformat(),
        "zuletzt_gesendet": None,
    }
    if not vorlage["name"]:
        return jsonify({"ok": False, "error": "Name fehlt"}), 400
    vorlagen = _load()
    vorlagen.append(vorlage)
    _save(vorlagen)
    return jsonify({"ok": True, "id": vorlage["id"]})


@fristen_bp.route("/api/fristen/<vid>", methods=["PUT"])
def api_update(vid):
    d = request.get_json(force=True) or {}
    vorlagen = _load()
    v = _find(vorlagen, vid)
    if not v:
        return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
    v["name"]             = d.get("name", v["name"]).strip()
    v["beschreibung"]     = d.get("beschreibung", v.get("beschreibung", "")).strip()
    v["frist_datum"]      = d.get("frist_datum", v["frist_datum"])
    v["wiederholung"]     = d.get("wiederholung", v.get("wiederholung"))
    v["erinnerung_wochen"] = d.get("erinnerung_wochen", v["erinnerung_wochen"])
    v["empfaenger"]["name"]  = d.get("empf_name",  v["empfaenger"]["name"]).strip()
    v["empfaenger"]["email"] = d.get("empf_email", v["empfaenger"]["email"]).strip()
    v["empfaenger"]["fax"]   = d.get("empf_fax",   v["empfaenger"]["fax"]).strip()
    v["benachrichtigung"] = d.get("benachrichtigung", v["benachrichtigung"])
    _save(vorlagen)
    return jsonify({"ok": True})


@fristen_bp.route("/api/fristen/<vid>", methods=["DELETE"])
def api_delete(vid):
    vorlagen = _load()
    v = _find(vorlagen, vid)
    if not v:
        return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
    # Datei mitlöschen
    if v.get("datei"):
        fp = os.path.join(_FILES, v["datei"])
        if os.path.exists(fp):
            os.remove(fp)
    vorlagen = [x for x in vorlagen if x["id"] != vid]
    _save(vorlagen)
    return jsonify({"ok": True})


@fristen_bp.route("/api/fristen/<vid>/upload", methods=["POST"])
def api_upload(vid):
    vorlagen = _load()
    v = _find(vorlagen, vid)
    if not v:
        return jsonify({"ok": False, "error": "Vorlage nicht gefunden"}), 404
    if "datei" not in request.files:
        return jsonify({"ok": False, "error": "Keine Datei"}), 400
    f = request.files["datei"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Kein Dateiname"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".odt"):
        return jsonify({"ok": False, "error": "Nur PDF, DOCX, ODT erlaubt"}), 400
    filename = secure_filename(f"{vid}{ext}")
    # Alte Datei löschen wenn vorhanden
    if v.get("datei"):
        old = os.path.join(_FILES, v["datei"])
        if os.path.exists(old):
            os.remove(old)
    f.save(os.path.join(_FILES, filename))
    v["datei"] = filename
    _save(vorlagen)
    return jsonify({"ok": True, "datei": filename})
