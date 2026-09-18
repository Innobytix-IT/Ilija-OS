import os
import json
import uuid
from flask import request, jsonify, render_template

LOCAL_CALENDAR_FILE  = os.path.join("data", "local_calendar_events.json")
VERFUEGBARKEIT_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "verfuegbarkeit.txt")

VERFUEGBARKEIT_DEFAULT = """\
# ══════════════════════════════════════════════════════════════════
#  VERFÜGBARKEIT & ÖFFNUNGSZEITEN
#  Bearbeitung: Kalender → Schaltfläche "📋 Verfügbarkeit"
# ══════════════════════════════════════════════════════════════════
#
# FORMAT:
#   [MO] bis [SO]     Reguläre Öffnungszeiten pro Wochentag
#   [FEIERTAG]        Einzelner Feiertag:  [FEIERTAG] JJJJ-MM-TT  Bezeichnung
#   [URLAUB]          Zeitraum:            [URLAUB]   JJJJ-MM-TT - JJJJ-MM-TT  Bezeichnung
#   [HINWEIS]         Freier Hinweistext:  [HINWEIS]  Text für Kunden
#   Zeilen mit # sind Kommentare und werden ignoriert.
#
# ── SLOT-DAUER FÜR TERMINBUCHUNGEN ──────────────────────────────
[SLOT_DAUER]  60
#
# ── REGULÄRE ÖFFNUNGSZEITEN ──────────────────────────────────────
[MO]  08:30 - 12:00 und 13:00 - 17:00
[DI]  08:30 - 12:00 und 13:00 - 17:00
[MI]  08:30 - 12:00 und 13:00 - 17:00
[DO]  08:30 - 12:00 und 13:00 - 17:00
[FR]  08:30 - 15:00
[SA]  Geschlossen
[SO]  Geschlossen
#
# ── URLAUB / BETRIEBSFERIEN ──────────────────────────────────────
# [URLAUB]  2026-08-03 - 2026-08-14  Sommerurlaub
# [URLAUB]  2026-12-23 - 2027-01-02  Weihnachtsferien
#
# ── FEIERTAGE (Deutschland) ──────────────────────────────────────
[FEIERTAG]  2026-01-01  Neujahr
[FEIERTAG]  2026-04-03  Karfreitag
[FEIERTAG]  2026-04-06  Ostermontag
[FEIERTAG]  2026-05-01  Tag der Arbeit
[FEIERTAG]  2026-05-14  Christi Himmelfahrt
[FEIERTAG]  2026-05-25  Pfingstmontag
[FEIERTAG]  2026-10-03  Tag der Deutschen Einheit
[FEIERTAG]  2026-11-01  Allerheiligen
[FEIERTAG]  2026-12-25  1. Weihnachtstag
[FEIERTAG]  2026-12-26  2. Weihnachtstag
#
# ── HINWEISE FÜR KUNDEN ──────────────────────────────────────────
# [HINWEIS]  Bitte vereinbaren Sie Termine telefonisch oder per E-Mail.
# [HINWEIS]  Kurzfristige Terminanfragen bitte mindestens 24h im Voraus.
"""

def load_local_events():
    if not os.path.exists(LOCAL_CALENDAR_FILE):
        return []
    try:
        with open(LOCAL_CALENDAR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_local_events(events):
    os.makedirs(os.path.dirname(LOCAL_CALENDAR_FILE), exist_ok=True)
    with open(LOCAL_CALENDAR_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

def register_local_calendar_routes(app):
    @app.route("/local_calendar")
    def local_calendar_page():
        return render_template("local_calendar.html")

    @app.route("/api/local_calendar/events", methods=["GET"])
    def get_local_events():
        return jsonify(load_local_events())

    @app.route("/api/local_calendar/events", methods=["POST"])
    def save_local_event():
        data = request.get_json()
        events = load_local_events()
        
        event_id = data.get("id")
        
        # Update: Das ganze Objekt überschreiben (um Wechsel zwischen Serie <-> Normal sauber zu halten)
        if event_id:
            for i, ev in enumerate(events):
                if ev["id"] == event_id:
                    data["id"] = event_id
                    events[i] = data
                    save_local_events(events)
                    return jsonify({"status": "updated", "event": data})
        
        # Neu
        data["id"] = str(uuid.uuid4())
        events.append(data)
        save_local_events(events)
        return jsonify({"status": "created", "event": data})

    @app.route("/api/local_calendar/events/<event_id>", methods=["DELETE"])
    def delete_local_event(event_id):
        events = load_local_events()
        events = [ev for ev in events if ev["id"] != event_id]
        save_local_events(events)
        return jsonify({"status": "deleted"})

    # ── Verfügbarkeit / Öffnungszeiten ───────────────────────────────────────

    @app.route("/api/verfuegbarkeit", methods=["GET"])
    def get_verfuegbarkeit():
        try:
            if not os.path.exists(VERFUEGBARKEIT_FILE):
                return jsonify({"content": "", "exists": False})
            with open(VERFUEGBARKEIT_FILE, "r", encoding="utf-8") as f:
                return jsonify({"content": f.read(), "exists": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/verfuegbarkeit", methods=["POST"])
    def save_verfuegbarkeit():
        try:
            data = request.get_json()
            content = data.get("content", "")
            with open(VERFUEGBARKEIT_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            return jsonify({"status": "saved"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/verfuegbarkeit/default", methods=["GET"])
    def get_verfuegbarkeit_default():
        return jsonify({"content": VERFUEGBARKEIT_DEFAULT})

    # ── Notizen (Telefon + WhatsApp) ─────────────────────────────────────────

    _BASE = os.path.dirname(os.path.abspath(__file__))

    @app.route("/api/notizen", methods=["GET"])
    def get_notizen():
        def _lese(pfad):
            try:
                if not os.path.exists(pfad):
                    return ""
                with open(pfad, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                return f"[Fehler beim Lesen: {e}]"

        telefon = _lese(os.path.join(_BASE, "data", "notizen", "telefon_notizen.txt"))
        whatsapp = _lese(os.path.join(_BASE, "data", "whatsapp_log.txt"))
        return jsonify({
            "telefon":  telefon  or "(Keine Telefon-Notizen vorhanden)",
            "whatsapp": whatsapp or "(Keine WhatsApp-Nachrichten vorhanden)",
        })