"""
fristen_routes.py – Fristen & Vorlagen Modul
Verwaltet Frist-Vorlagen, Empfänger, Brief-Generierung und Kontaktdaten-Suche.
"""

import os
import json
import uuid
import re
from datetime import datetime
from flask import request, jsonify, render_template
from werkzeug.utils import secure_filename

_BASE      = os.path.dirname(os.path.abspath(__file__))
_DATA      = os.path.join(_BASE, "data", "fristen")
_INDEX     = os.path.join(_DATA, "vorlagen.json")
_FILES     = os.path.join(_DATA, "dateien")
_ABSENDER  = os.path.join(_DATA, "absender.json")

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


def _load_absender() -> dict:
    if not os.path.exists(_ABSENDER):
        return {"name": "", "adresse": "", "email": ""}
    try:
        with open(_ABSENDER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"name": "", "adresse": "", "email": ""}


def _save_absender(data: dict):
    os.makedirs(_DATA, exist_ok=True)
    with open(_ABSENDER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tage_bis(datum_str: str) -> int:
    try:
        d = datetime.strptime(datum_str, "%Y-%m-%d").date()
        return (d - datetime.today().date()).days
    except Exception:
        return 9999


# ── Registrierung ─────────────────────────────────────────────────────────────

def register_fristen_routes(app, get_kernel_func=None, kernel_lock=None):

    # ── Seite ─────────────────────────────────────────────────────────────────

    @app.route("/fristen")
    def fristen_page():
        return render_template("fristen.html")

    # ── Vorlagen-API ──────────────────────────────────────────────────────────

    @app.route("/api/fristen", methods=["GET"])
    def fristen_list():
        vorlagen = _load()
        heute = datetime.today().date()
        for v in vorlagen:
            try:
                fd = datetime.strptime(v["frist_datum"], "%Y-%m-%d").date()
                v["_tage_bis_frist"] = (fd - heute).days
            except Exception:
                v["_tage_bis_frist"] = 9999
        vorlagen.sort(key=lambda v: v["_tage_bis_frist"])
        return jsonify(vorlagen)

    @app.route("/api/fristen", methods=["POST"])
    def fristen_create():
        d = request.get_json(force=True) or {}
        vorlage = {
            "id":                   str(uuid.uuid4()),
            "typ":                  d.get("typ", "antrag"),
            "name":                 d.get("name", "").strip(),
            "beschreibung":         d.get("beschreibung", "").strip(),
            "datei":                "",
            "frist_datum":          d.get("frist_datum", ""),
            "wiederholung":         d.get("wiederholung", None),
            "erinnerung_wochen":    d.get("erinnerung_wochen", [4, 2, 1]),
            # Kündigung-spezifisch
            "vertragsbeginn":       d.get("vertragsbeginn", ""),
            "laufzeit_monate":      d.get("laufzeit_monate", 24),
            "kuendigungsfrist_wochen": d.get("kuendigungsfrist_wochen", 4),
            "kundennummer":         d.get("kundennummer", "").strip(),
            # Empfänger
            "empfaenger": {
                "name":    d.get("empf_name", "").strip(),
                "adresse": d.get("empf_adresse", "").strip(),
                "email":   d.get("empf_email", "").strip(),
                "fax":     d.get("empf_fax", "").strip(),
            },
            "benachrichtigung":     d.get("benachrichtigung", ["chat"]),
            "erstellt":             datetime.now().isoformat(),
            "zuletzt_gesendet":     None,
        }
        if not vorlage["name"]:
            return jsonify({"ok": False, "error": "Name fehlt"}), 400
        vorlagen = _load()
        vorlagen.append(vorlage)
        _save(vorlagen)
        return jsonify({"ok": True, "id": vorlage["id"]})

    @app.route("/api/fristen/<vid>", methods=["PUT"])
    def fristen_update(vid):
        d = request.get_json(force=True) or {}
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        v["typ"]              = d.get("typ", v.get("typ", "antrag"))
        v["name"]             = d.get("name", v["name"]).strip()
        v["beschreibung"]     = d.get("beschreibung", v.get("beschreibung", "")).strip()
        v["frist_datum"]      = d.get("frist_datum", v["frist_datum"])
        v["wiederholung"]     = d.get("wiederholung", v.get("wiederholung"))
        v["erinnerung_wochen"] = d.get("erinnerung_wochen", v["erinnerung_wochen"])
        v["vertragsbeginn"]   = d.get("vertragsbeginn", v.get("vertragsbeginn", ""))
        v["laufzeit_monate"]  = d.get("laufzeit_monate", v.get("laufzeit_monate", 24))
        v["kuendigungsfrist_wochen"] = d.get("kuendigungsfrist_wochen", v.get("kuendigungsfrist_wochen", 4))
        v["kundennummer"]     = d.get("kundennummer", v.get("kundennummer", "")).strip()
        v["empfaenger"]["name"]    = d.get("empf_name",    v["empfaenger"]["name"]).strip()
        v["empfaenger"]["adresse"] = d.get("empf_adresse", v["empfaenger"].get("adresse", "")).strip()
        v["empfaenger"]["email"]   = d.get("empf_email",   v["empfaenger"]["email"]).strip()
        v["empfaenger"]["fax"]     = d.get("empf_fax",     v["empfaenger"]["fax"]).strip()
        v["benachrichtigung"]      = d.get("benachrichtigung", v["benachrichtigung"])
        _save(vorlagen)
        return jsonify({"ok": True})

    @app.route("/api/fristen/<vid>", methods=["DELETE"])
    def fristen_delete(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        if v.get("datei"):
            fp = os.path.join(_FILES, v["datei"])
            if os.path.exists(fp):
                os.remove(fp)
        vorlagen = [x for x in vorlagen if x["id"] != vid]
        _save(vorlagen)
        return jsonify({"ok": True})

    @app.route("/api/fristen/<vid>/upload", methods=["POST"])
    def fristen_upload(vid):
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
        if v.get("datei"):
            old = os.path.join(_FILES, v["datei"])
            if os.path.exists(old):
                os.remove(old)
        f.save(os.path.join(_FILES, filename))
        v["datei"] = filename
        _save(vorlagen)
        return jsonify({"ok": True, "datei": filename})

    # ── Absender-Profil ───────────────────────────────────────────────────────

    @app.route("/api/fristen/absender", methods=["GET"])
    def fristen_absender_get():
        return jsonify(_load_absender())

    @app.route("/api/fristen/absender", methods=["POST"])
    def fristen_absender_post():
        d = request.get_json(force=True) or {}
        data = {
            "name":    d.get("name", "").strip(),
            "adresse": d.get("adresse", "").strip(),
            "email":   d.get("email", "").strip(),
        }
        _save_absender(data)
        return jsonify({"ok": True})

    # ── Brief-Generierung ─────────────────────────────────────────────────────

    @app.route("/api/fristen/<vid>/brief", methods=["POST"])
    def fristen_brief(vid):
        if get_kernel_func is None:
            return jsonify({"ok": False, "error": "KI nicht verfügbar"}), 503

        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Vorlage nicht gefunden"}), 404

        absender = _load_absender()
        typ = v.get("typ", "antrag")
        heute = datetime.today().strftime("%d.%m.%Y")

        empf = v["empfaenger"]
        empf_block = empf.get("name", "")
        if empf.get("adresse"):
            empf_block += "\n" + empf["adresse"]

        if typ == "kuendigung":
            betreff = f"Kündigung meines Vertrages"
            if v.get("kundennummer"):
                betreff += f" (Kundennummer: {v['kundennummer']})"
            anlass = (
                f"Ich kündige hiermit meinen Vertrag fristgemäß zum {_fmt_datum(v['frist_datum'])}."
            )
            if v.get("kundennummer"):
                anlass += f"\n\nMeine Kundennummer: {v['kundennummer']}"
            if v.get("beschreibung"):
                anlass += f"\n\nVertrag: {v['beschreibung']}"
            typ_text = "Kündigung"
        else:
            betreff = v["name"]
            anlass = v.get("beschreibung") or f"Ich beantrage hiermit: {v['name']}"
            typ_text = "Schreiben"

        prompt = f"""Schreibe ein formelles {typ_text} auf Deutsch. Gib NUR den fertigen Brieftext aus, ohne Erklärungen oder Kommentare davor oder danach.

Absender:
{absender.get('name') or '[Name des Absenders]'}
{absender.get('adresse') or '[Adresse des Absenders]'}
{absender.get('email') or ''}

Datum: {heute}

Empfänger:
{empf_block or '[Name und Adresse des Empfängers]'}

Betreff: {betreff}

Inhalt:
{anlass}

Bitte schreibe einen vollständigen, professionellen deutschen Geschäftsbrief im DIN-5008-Format. Schließe mit einer höflichen Schlussformel ab. Verwende keine Markdown-Formatierung."""

        try:
            lock = kernel_lock
            if lock:
                with lock:
                    k = get_kernel_func()
                    brief_text = k.chat(prompt)
            else:
                k = get_kernel_func()
                brief_text = k.chat(prompt)
            return jsonify({"ok": True, "brief": brief_text})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Kontaktdaten-Suche ────────────────────────────────────────────────────

    @app.route("/api/fristen/kontakt-suchen", methods=["POST"])
    def fristen_kontakt_suchen():
        if get_kernel_func is None:
            return jsonify({"ok": False, "error": "KI nicht verfügbar"}), 503

        d = request.get_json(force=True) or {}
        anbieter = d.get("anbieter", "").strip()
        typ = d.get("typ", "antrag")
        if not anbieter:
            return jsonify({"ok": False, "error": "Kein Anbieter angegeben"}), 400

        zweck = "Kündigung" if typ == "kuendigung" else "Antrag/Schreiben"
        prompt = f"""Suche die offiziellen Kontaktdaten für ein {zweck}-Schreiben an: "{anbieter}"

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne jeden weiteren Text davor oder danach:
{{"adresse": "Straße Hausnummer, PLZ Ort", "email": "...", "fax": "..."}}

Wenn du eine Information nicht kennst oder nicht sicher bist, setze den Wert auf "".
Wichtig: Nur echte, offizielle Adressen. Keine erfundenen Daten."""

        try:
            lock = kernel_lock
            if lock:
                with lock:
                    k = get_kernel_func()
                    antwort = k.chat(prompt)
            else:
                k = get_kernel_func()
                antwort = k.chat(prompt)

            # JSON aus der Antwort extrahieren
            match = re.search(r'\{[^{}]+\}', antwort, re.DOTALL)
            if match:
                kontakt = json.loads(match.group())
                return jsonify({"ok": True, "kontakt": kontakt, "rohantwort": antwort})
            else:
                return jsonify({"ok": True, "kontakt": {"adresse": "", "email": "", "fax": ""}, "rohantwort": antwort})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500


def _fmt_datum(datum_str: str) -> str:
    try:
        return datetime.strptime(datum_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return datum_str
