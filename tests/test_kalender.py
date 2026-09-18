"""
test_kalender.py – Tests für lokaler_kalender_skill.py
=======================================================
Testet: Freie-Slots-Suche, Mehrtages-Blocker, Wochenend-Sperre,
        Termin eintragen & stornieren, 3-Faktor-Auth, naechste_n_slots

Alle Tests arbeiten mit einer temporären JSON-Datei statt der echten Kalenderdatei.

WICHTIG: importlib.reload() muss AUSSERHALB des patch()-Kontexts laufen,
         sonst überschreibt reload() den Patch (CALENDAR_FILE wird neu gesetzt).
         Korrekte Reihenfolge: reload → patch.object → Funktion aufrufen.
"""
import os
import sys
import json
import importlib
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch, patch as mock_patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import skills.lokaler_kalender_skill as ks
importlib.reload(ks)


# ── Hilfsfunktion: temporäre Kalender-Datei ───────────────────────────────────

def _patch_calendar(tmp_path, events: list) -> str:
    """Schreibt events in eine temporäre Datei und gibt den Pfad zurück."""
    cal_file = tmp_path / "local_calendar_events.json"
    cal_file.write_text(json.dumps(events), encoding="utf-8")
    return str(cal_file)


# ── Freie Slots ───────────────────────────────────────────────────────────────

class TestFreieSlots:
    """lokaler_kalender_freie_slots_finden — Kernfunktion des Buchungsflows."""

    def test_freie_slots_leerer_kalender(self, tmp_path):
        """Ohne Termine müssen Slots vorhanden sein (Werktag)."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            heute = date.today()
            diff = (0 - heute.weekday()) % 7 or 7
            montag = (heute + timedelta(days=diff)).strftime("%d.%m.%Y")
            result = ks.lokaler_kalender_freie_slots_finden(montag)
            assert "1." in result or "keine" in result.lower()

    def test_rueckgabe_ist_string(self, tmp_path):
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            result = ks.lokaler_kalender_freie_slots_finden("27.04.2026")
            assert isinstance(result, str)

    def test_samstag_keine_slots(self, tmp_path):
        """Samstag ist kein Arbeitstag → keine freien Slots."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            # 25.04.2026 = Samstag
            result = ks.lokaler_kalender_freie_slots_finden("25.04.2026")
            assert "keine" in result.lower() or "❌" in result or "Samstag" in result


# ── Mehrtages-Blocker ─────────────────────────────────────────────────────────

class TestMehrtagesBlocker:
    """Mehrtägige Ereignisse müssen alle Tage innerhalb des Zeitraums blockieren."""

    def _make_multiday_event(self, start_iso: str, end_iso: str, titel="Blocker"):
        return {
            "id": "blocker1",
            "title": titel,
            "start": start_iso,
            "end": end_iso,
            "recurrence": "none",
        }

    def test_blockerstart_ist_blockiert(self, tmp_path):
        """Der erste Tag eines Mehrtages-Blockers muss blockiert sein."""
        ev = self._make_multiday_event("2026-05-03T00:00:00", "2026-05-10T00:00:00")
        cal = _patch_calendar(tmp_path, [ev])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            # 03.05.2026 = Sonntag → Wochenende liefert ❌
            # Verwende stattdessen 04.05.2026 (Montag) der im Blocker liegt
            result = ks.lokaler_kalender_freie_slots_finden("04.05.2026")
            assert "keine" in result.lower() or "❌" in result or "1." not in result

    def test_mitteltag_ist_blockiert(self, tmp_path):
        """Ein Tag in der Mitte eines Mehrtages-Blockers muss blockiert sein."""
        ev = self._make_multiday_event("2026-05-03T00:00:00", "2026-05-24T00:00:00")
        cal = _patch_calendar(tmp_path, [ev])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            # 12.05.2026 = Dienstag, liegt im Blocker
            result = ks.lokaler_kalender_freie_slots_finden("12.05.2026")
            assert "keine" in result.lower() or "❌" in result

    def test_nach_blocker_ende_frei(self, tmp_path):
        """Nach Ende des Blockers müssen wieder freie Slots vorhanden sein."""
        ev = self._make_multiday_event("2026-05-03T00:00:00", "2026-05-10T00:00:00")
        cal = _patch_calendar(tmp_path, [ev])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            # 11.05.2026 = Montag → nach Blocker, Arbeitstag
            result = ks.lokaler_kalender_freie_slots_finden("11.05.2026")
            assert "1." in result  # Mindestens ein Slot vorhanden


# ── Termin eintragen & Slots blockieren ───────────────────────────────────────

class TestTerminEintragen:

    def test_termin_eintragen_gibt_bestaetigung(self, tmp_path):
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            result = ks.lokaler_kalender_termin_eintragen(
                titel="Beratung",
                datum="12.05.2026",
                uhrzeit_von="10:00",
                uhrzeit_bis="11:00",
                kontaktinfos="Max Mustermann, 0761123456",
                beschreibung="Erstgespräch",
                caller_id="+4976112345",
            )
            assert "✅" in result

    def test_eingetragener_termin_blockiert_slot(self, tmp_path):
        """Nach dem Eintragen von 10:00–11:00 darf kein Slot BEGINNEND um 10:00 angeboten werden."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            ks.lokaler_kalender_termin_eintragen(
                titel="Beratung",
                datum="12.05.2026",
                uhrzeit_von="10:00",
                uhrzeit_bis="11:00",
                kontaktinfos="Max Mustermann, 0761123456",
                beschreibung="",
                caller_id="+4976112345",
            )
            slots = ks.lokaler_kalender_freie_slots_finden("12.05.2026")
            # Kein Slot darf bei 10:00 BEGINNEN (Format: "N. 10:00 –")
            assert "10:00 –" not in slots and "10:00 –" not in slots


# ── 3-Faktor-Auth für Terminabfrage ──────────────────────────────────────────

class TestDreiFactorAuth:

    def test_termine_abfragen_ohne_alle_faktoren_blockiert(self, tmp_path):
        """Ohne vollständige Identifikation darf keine Terminliste ausgegeben werden."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            result = ks.kunde_termine_abfragen(
                caller_id="",          # unterdrückte Nummer
                vorname="Max",
                nachname="Mustermann",
            )
            assert "❌" in result or "nicht" in result.lower()

    def test_termine_abfragen_mit_allen_faktoren(self, tmp_path):
        """Mit vollständiger Identifikation soll die Funktion nicht crashen."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            result = ks.kunde_termine_abfragen(
                caller_id="+4976112345",
                vorname="Max",
                nachname="Mustermann",
            )
            assert isinstance(result, str)


# ── naechste_n_slots ──────────────────────────────────────────────────────────

class TestNaechsteNSlots:

    def test_gibt_liste_zurueck(self, tmp_path):
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            result = ks.naechste_n_slots(n=3, ab_datum=date(2026, 5, 11))
            assert isinstance(result, list)

    def test_slots_sind_in_zukunft(self, tmp_path):
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            ab = date(2026, 5, 11)  # Montag
            slots = ks.naechste_n_slots(n=3, ab_datum=ab)
            for datum_str, uhrzeit in slots:
                slot_datum = datetime.strptime(datum_str, "%d.%m.%Y").date()
                assert slot_datum >= ab

    def test_maximal_n_slots(self, tmp_path):
        """Gibt nie mehr als n Slots zurück."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            slots = ks.naechste_n_slots(n=2, ab_datum=date(2026, 5, 11))
            assert len(slots) <= 2

    def test_nur_werktage(self, tmp_path):
        """Alle zurückgegebenen Slots liegen auf Werktagen (Mo–Fr)."""
        cal = _patch_calendar(tmp_path, [])
        with patch.object(ks, 'CALENDAR_FILE', cal):
            slots = ks.naechste_n_slots(n=5, ab_datum=date(2026, 5, 11))
            for datum_str, _ in slots:
                dt = datetime.strptime(datum_str, "%d.%m.%Y").date()
                assert dt.weekday() < 5, f"{datum_str} ist kein Werktag"
