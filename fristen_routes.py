"""
fristen_routes.py – Fristen & Vorlagen Modul
Verwaltet Frist-Vorlagen, Empfänger, Brief-Generierung und Kontaktdaten-Suche.
"""

import os
import json
import uuid
import re
import base64
import tempfile
import shutil
from datetime import datetime
from flask import request, jsonify, render_template
from werkzeug.utils import secure_filename

_BASE      = os.path.dirname(os.path.abspath(__file__))
_DATA      = os.path.join(_BASE, "data", "fristen")
_INDEX     = os.path.join(_DATA, "vorlagen.json")
_FILES     = os.path.join(_DATA, "dateien")
_ABSENDER          = os.path.join(_DATA, "absender.json")
_UNTERSCHRIFT_BASE = os.path.join(_DATA, "unterschrift")
_UNTERSCHRIFT_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]

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


def _find_unterschrift() -> str | None:
    """Gibt den Pfad zur hinterlegten Unterschrift zurück, oder None."""
    for ext in _UNTERSCHRIFT_EXTS:
        p = _UNTERSCHRIFT_BASE + ext
        if os.path.exists(p):
            return p
    return None


def _delete_unterschrift():
    """Löscht alle hinterlegten Unterschrift-Dateien."""
    for ext in _UNTERSCHRIFT_EXTS:
        p = _UNTERSCHRIFT_BASE + ext
        if os.path.exists(p):
            os.remove(p)


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

    @app.route("/api/fristen/chat-notification", methods=["GET"])
    def fristen_chat_notification():
        """Gibt Fristen zurück, die ≤7 Tage entfernt oder überfällig sind."""
        vorlagen = _load()
        heute = datetime.today().date()
        urgent = []
        for v in vorlagen:
            try:
                fd = datetime.strptime(v["frist_datum"], "%Y-%m-%d").date()
                tage = (fd - heute).days
                if tage <= 7:
                    urgent.append({
                        "id":          v["id"],
                        "name":        v["name"],
                        "typ":         v.get("typ", ""),
                        "frist_datum": v["frist_datum"],
                        "tage":        tage,
                    })
            except Exception:
                pass
        urgent.sort(key=lambda x: x["tage"])
        return jsonify(urgent)

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

        absender  = _load_absender()
        typ       = v.get("typ", "antrag")
        empf      = v["empfaenger"]

        if typ == "kuendigung":
            betreff   = "Kündigung meines Vertrages"
            if v.get("kundennummer"):
                betreff += f"\nIhre Kundennummer: {v['kundennummer']}"
            kontext   = (
                f"Fristgemäße Kündigung zum {_fmt_datum(v.get('frist_datum',''))}."
                + (f"\nVertrag/Beschreibung: {v['beschreibung']}" if v.get("beschreibung") else "")
                + (f"\nKundennummer: {v['kundennummer']}" if v.get("kundennummer") else "")
            )
            typ_text  = "Kündigung"
        else:
            betreff   = v["name"]
            kontext   = v.get("beschreibung") or f"Antrag/Schreiben betreffend: {v['name']}"
            typ_text  = "Schreiben" if typ == "sonstiges" else "Antrag"

        prompt = f"""Schreibe den Briefkörper für ein formelles deutsches {typ_text}-Schreiben.

Empfänger: {empf.get('name') or 'die zuständige Stelle'}
Betreff: {betreff.splitlines()[0]}
Kontext: {kontext}

Schreibe NUR: Anrede → Briefinhalt → Schlussformel ("Mit freundlichen Grüßen").
NICHT: Datum, Adressen, Unterschrift — die werden automatisch hinzugefügt.
Kein Markdown, kein Fettdruck, keine Überschriften."""

        try:
            lock = kernel_lock
            if lock:
                with lock:
                    k = get_kernel_func()
                    koerper = k.chat(prompt)
            else:
                k = get_kernel_func()
                koerper = k.chat(prompt)

            # DIN-5008-Dokument bauen und als Datei speichern
            html = _baue_brief_html(v, absender, betreff, koerper)
            filename = f"{vid}.html"
            with open(os.path.join(_FILES, filename), "w", encoding="utf-8") as f:
                f.write(html)

            # Alte Datei löschen falls eine andere vorhanden war
            if v.get("datei") and v["datei"] != filename:
                old = os.path.join(_FILES, v["datei"])
                if os.path.exists(old):
                    os.remove(old)

            v["datei"] = filename
            _save(vorlagen)

            return jsonify({"ok": True, "doc_url": f"/fristen/dokument/{vid}"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Brief-Dokument anzeigen ───────────────────────────────────────────────

    @app.route("/fristen/dokument/<vid>")
    def fristen_dokument(vid):
        from flask import send_from_directory, abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei", "").endswith(".html"):
            abort(404)
        return send_from_directory(_FILES, v["datei"])

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

    # ── Unterschrift API ──────────────────────────────────────────────────────

    @app.route("/api/fristen/unterschrift", methods=["GET"])
    def fristen_unterschrift_get():
        pfad = _find_unterschrift()
        if not pfad:
            return jsonify({"ok": True, "exists": False})
        ext  = os.path.splitext(pfad)[1].lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        with open(pfad, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return jsonify({"ok": True, "exists": True, "data": f"data:{mime};base64,{data}"})

    @app.route("/api/fristen/unterschrift", methods=["POST"])
    def fristen_unterschrift_post():
        if "datei" in request.files:
            f   = request.files["datei"]
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                return jsonify({"ok": False, "error": "Nur PNG, JPG, GIF, WebP erlaubt"}), 400
            _delete_unterschrift()
            os.makedirs(_DATA, exist_ok=True)
            f.save(_UNTERSCHRIFT_BASE + ext)
            return jsonify({"ok": True})
        d        = request.get_json(force=True) or {}
        data_url = d.get("data", "")
        m = re.match(r"data:image/([^;]+);base64,(.+)", data_url, re.DOTALL)
        if not m:
            return jsonify({"ok": False, "error": "Ungültiges Format"}), 400
        subtype = m.group(1).lower().replace("jpeg", "jpg")
        ext     = "." + (subtype if subtype in ("png", "jpg", "gif", "webp") else "png")
        raw     = base64.b64decode(m.group(2))
        _delete_unterschrift()
        os.makedirs(_DATA, exist_ok=True)
        with open(_UNTERSCHRIFT_BASE + ext, "wb") as f:
            f.write(raw)
        return jsonify({"ok": True})

    @app.route("/api/fristen/unterschrift", methods=["DELETE"])
    def fristen_unterschrift_delete():
        _delete_unterschrift()
        return jsonify({"ok": True})

    # ── PDF-Datei ausliefern (für PDF.js) ────────────────────────────────────

    @app.route("/fristen/datei/<vid>")
    def fristen_datei_raw(vid):
        from flask import send_from_directory, abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei"):
            abort(404)
        return send_from_directory(_FILES, v["datei"])

    # ── Unterschrift-Platzierung (Seite) ──────────────────────────────────────

    @app.route("/fristen/unterschrift-setzen/<vid>")
    def fristen_unterschrift_setzen_page(vid):
        from flask import abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei") or v["datei"].endswith(".html"):
            abort(404)
        return render_template("unterschrift_setzen.html", vid=vid, name=v.get("name", "Dokument"))

    # ── Unterschrift einbetten (PyMuPDF) ──────────────────────────────────────

    @app.route("/api/fristen/<vid>/unterschrift-einbetten", methods=["POST"])
    def fristen_unterschrift_einbetten(vid):
        try:
            import fitz
        except ImportError:
            return jsonify({"ok": False,
                            "error": "PyMuPDF nicht installiert. Bitte: pip install pymupdf"}), 503

        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei"):
            return jsonify({"ok": False, "error": "Keine Datei vorhanden"}), 404
        if not v["datei"].lower().endswith(".pdf"):
            return jsonify({"ok": False,
                            "error": "Unterschrift-Einbettung ist nur für PDF-Dateien möglich"}), 400

        unterschrift_pfad = _find_unterschrift()
        if not unterschrift_pfad:
            return jsonify({"ok": False, "error": "Keine Unterschrift hinterlegt"}), 404

        d        = request.get_json(force=True) or {}
        page_num = max(0, int(d.get("page", 0)))
        x        = float(d.get("x", 0))
        y        = float(d.get("y", 0))
        width    = max(10.0, float(d.get("width", 150)))
        height   = max(5.0,  float(d.get("height", 50)))

        src_path = os.path.join(_FILES, v["datei"])
        out_name = f"{vid}_signed.pdf"
        out_path = os.path.join(_FILES, out_name)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=_FILES) as tmp:
                tmp_path = tmp.name
            doc  = fitz.open(src_path)
            if page_num >= len(doc):
                page_num = len(doc) - 1
            page = doc[page_num]
            rect = fitz.Rect(x, y, x + width, y + height)
            page.insert_image(rect, filename=unterschrift_pfad, keep_proportion=True)
            doc.save(tmp_path)
            doc.close()
            shutil.move(tmp_path, out_path)
            tmp_path = None
            v["datei"] = out_name
            _save(vorlagen)
            return jsonify({"ok": True})
        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            return jsonify({"ok": False, "error": str(e)}), 500


def _fmt_datum(datum_str: str) -> str:
    try:
        return datetime.strptime(datum_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return datum_str


def _baue_brief_html(v: dict, absender: dict, betreff: str, briefkoerper: str) -> str:
    """Baut ein druckbares DIN-5008-konformes HTML-Dokument."""
    heute = datetime.today().strftime("%d.%m.%Y")

    # Hinterlegte Unterschrift laden
    unterschrift_pfad = _find_unterschrift()
    unterschrift_img_html = ""
    name_margin = "margin-top:16mm"  # Leerraum für manuelle Unterschrift
    if unterschrift_pfad:
        ext  = os.path.splitext(unterschrift_pfad)[1].lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        with open(unterschrift_pfad, "rb") as uf:
            udata = base64.b64encode(uf.read()).decode()
        unterschrift_img_html = (
            f'<img src="data:{mime};base64,{udata}" '
            f'style="max-height:55px;max-width:180px;display:block;'
            f'margin-top:12mm;margin-bottom:3mm">'
        )
        name_margin = "margin-top:0"

    def he(s: str) -> str:
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Absender-Kurzzeile (über dem Empfängerfenster — sichtbar im Fensterkuvert)
    abs_name    = absender.get("name", "")
    abs_adresse = absender.get("adresse", "")
    abs_kurz    = abs_name
    if abs_adresse:
        abs_kurz += " · " + abs_adresse.replace("\n", ", ").strip()

    # Ort aus letzter Zeile der Absenderadresse extrahieren
    ort = ""
    if abs_adresse:
        letzte = abs_adresse.strip().splitlines()[-1]
        m = re.match(r"^\d{5}\s+(.+)", letzte.strip())
        if m:
            ort = m.group(1)
    ort_datum = f"{ort + ', ' if ort else ''}{heute}"

    # Empfänger-Block
    empf       = v.get("empfaenger", {})
    empf_zeile = "\n".join(z for z in [empf.get("name", ""), empf.get("adresse", "")] if z)

    # Betreff (ggf. mehrzeilig — erste Zeile fett, Rest normal)
    betreff_zeilen = betreff.strip().splitlines()
    betreff_html   = "<strong>" + he(betreff_zeilen[0]) + "</strong>"
    if len(betreff_zeilen) > 1:
        betreff_html += "<br>" + "<br>".join(he(z) for z in betreff_zeilen[1:])

    # Briefkörper: Zeilenumbrüche → <br>-Paare für Absätze
    koerper_html = briefkoerper.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    abs_email_html = (
        f'<div style="font-size:9pt;color:#555;margin-top:2mm">{he(absender.get("email",""))}</div>'
        if absender.get("email") else ""
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>{he(v.get('name','Brief'))}</title>
<style>
@page {{ size: A4; margin: 10mm 20mm 19mm 25mm; }}
@media print {{
  .no-print {{ display: none !important; }}
  body {{ background: white !important; }}
  .page {{ box-shadow: none !important; margin: 0 !important; }}
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: Arial, Helvetica, sans-serif;
  font-size: 11pt;
  background: #dde3ea;
  color: #000;
}}
.page {{
  width: 210mm;
  min-height: 297mm;
  background: white;
  margin: 16px auto 40px;
  padding: 10mm 20mm 25mm 25mm;
  box-shadow: 0 3px 18px rgba(0,0,0,.18);
}}
/* Absender-Kurzzeile (DIN 5008: Angabe über dem Empfängerfenster) */
.abs-kurz {{
  font-size: 7.5pt;
  color: #555;
  border-bottom: 0.4pt solid #bbb;
  padding-bottom: 1.5mm;
  margin-bottom: 3mm;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
/* Empfänger-Block: 40mm Höhe passt ins Fensterkuvert */
.empf-block {{
  height: 40mm;
  font-size: 11pt;
  line-height: 1.45;
  white-space: pre-line;
  padding-top: 5mm;
}}
/* Datum rechtsbündig */
.datum {{
  text-align: right;
  margin-top: 8mm;
  margin-bottom: 12mm;
  font-size: 11pt;
}}
/* Betreff fett */
.betreff {{
  margin-bottom: 8mm;
  font-size: 11pt;
  line-height: 1.5;
}}
/* Brieftext — white-space:pre-wrap erhält Absätze */
.brieftext {{
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 11pt;
}}
/* Unterschrift-Block */
.unterschrift {{
  margin-top: 12mm;
  font-size: 11pt;
}}
.unterschrift .name {{
  font-weight: bold;
}}
/* Drucken-Leiste (nur am Bildschirm sichtbar) */
.print-bar {{
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 100;
  display: flex;
  gap: 8px;
  background: #10202D;
  border: 1px solid rgba(255,255,255,.12);
  padding: 10px 14px;
  border-radius: 9px;
  box-shadow: 0 4px 18px rgba(0,0,0,.5);
}}
.print-bar button {{
  padding: 7px 18px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}}
.btn-print {{ background: #E0A82E; color: #0B1520; }}
.btn-print:hover {{ background: #C8871B; }}
.btn-close {{ background: #1E3547; color: #E6EEF5; }}
.btn-close:hover {{ background: #274257; }}
@media (max-width: 680px) {{
  .page {{ width: 100%; margin: 0; padding: 8mm 6mm 15mm 8mm; box-shadow: none; }}
}}
</style>
</head>
<body>
<div class="print-bar no-print">
  <button class="btn-print" onclick="window.print()">🖨&nbsp;Drucken / Als PDF speichern</button>
  <button class="btn-close" onclick="window.close()">✕&nbsp;Schließen</button>
</div>

<div class="page">
  <div class="abs-kurz">{he(abs_kurz)}</div>
  <div class="empf-block">{he(empf_zeile)}</div>
  <div class="datum">{he(ort_datum)}</div>
  <div class="betreff">{betreff_html}</div>
  <div class="brieftext">{koerper_html}</div>
  <div class="unterschrift">
    {unterschrift_img_html}
    <div class="name" style="{name_margin}">{he(abs_name)}</div>
    {abs_email_html}
  </div>
</div>
</body>
</html>"""
