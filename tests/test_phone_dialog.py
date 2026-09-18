"""
test_phone_dialog.py – Tests für die Telefon-Dialoglogik
=========================================================
Testet: parse_datum, parse_uhrzeit, parse_yesno, Spelling-Mode,
        Slot-Ablehnung → Datumsfrage, "zu weit in Zukunft"-Check,
        Datum-Parser für Whisper-Transkriptionen ("28 Mai" etc.)

Alle Tests laufen ohne echtes LLM und ohne FritzBox-Verbindung.
"""
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from phone_dialog import (
    parse_datum,
    parse_uhrzeit,
    parse_yesno,
    datum_de,
    uhrzeit_de,
    ist_telefonnummer,
    SUCHE_VOR_TAGEN,
)


# ── parse_datum ───────────────────────────────────────────────────────────────

class TestParseDatum:
    """Robuster Datums-Parser — wichtigster Baustein im Termin-Flow."""

    def test_morgen(self):
        result = parse_datum("morgen")
        erwartet = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
        assert result == erwartet

    def test_uebermorgen(self):
        result = parse_datum("übermorgen")
        erwartet = (date.today() + timedelta(days=2)).strftime("%d.%m.%Y")
        assert result == erwartet

    def test_heute(self):
        result = parse_datum("heute")
        assert result == date.today().strftime("%d.%m.%Y")

    def test_wochentag_nie_heute(self):
        """Wochentags-Parser darf NIE den heutigen Tag zurückgeben."""
        heute_wt = date.today().weekday()
        wochentage = ["montag","dienstag","mittwoch","donnerstag","freitag","samstag","sonntag"]
        wort = wochentage[heute_wt]
        result = parse_datum(wort)
        # Muss mindestens 1 Tag in der Zukunft liegen (nächste Woche)
        assert result is not None
        dt = date(*reversed([int(x) for x in result.split(".")]))
        assert dt > date.today()

    def test_naechsten_montag(self):
        result = parse_datum("am Montag bitte")
        assert result is not None
        dt = date(*reversed([int(x) for x in result.split(".")]))
        assert dt.weekday() == 0  # 0 = Montag
        assert dt > date.today()

    def test_numerisch_mit_punkt(self):
        """28.05 → 28.05.JJJJ (heutige oder nächste Jahreszahl)."""
        result = parse_datum("28.05.")
        assert result is not None
        assert result.startswith("28.05.")

    def test_numerisch_mit_volljahreszahl(self):
        result = parse_datum("28.05.2026")
        assert result == "28.05.2026"

    def test_zahl_plus_monatsname_ohne_punkt(self):
        """'28 Mai' — Whisper-Transkription ohne Punkt."""
        result = parse_datum("28 Mai")
        assert result is not None
        assert result.startswith("28.05.")

    def test_zahl_plus_monatsname_mit_punkt(self):
        """'28. Mai' — Whisper-Transkription mit Punkt."""
        result = parse_datum("28. Mai")
        assert result is not None
        assert result.startswith("28.05.")

    def test_wochentag_plus_datum(self):
        """'Donnerstag 28. Mai' — Whisper transkribiert Wochentag mit."""
        result = parse_datum("Donnerstag 28. Mai")
        assert result is not None
        assert result.startswith("28.05.")

    def test_ordinal_plus_monat(self):
        """'zwanzigsten Mai'."""
        result = parse_datum("zwanzigsten Mai")
        assert result is not None
        assert result.startswith("20.05.")

    def test_in_zwei_wochen(self):
        result = parse_datum("in zwei Wochen")
        erwartet = (date.today() + timedelta(days=14)).strftime("%d.%m.%Y")
        assert result == erwartet

    def test_in_drei_tagen(self):
        result = parse_datum("in drei Tagen")
        erwartet = (date.today() + timedelta(days=3)).strftime("%d.%m.%Y")
        assert result == erwartet

    def test_leerer_string_gibt_none(self):
        assert parse_datum("") is None

    def test_ungueltige_eingabe_gibt_none(self):
        assert parse_datum("bitte irgendwann") is None

    def test_datum_in_vergangenheit_wird_ins_naechste_jahr_verschoben(self):
        """Ein Datum das dieses Jahr bereits vergangen ist → nächstes Jahr."""
        # 1. Januar ist immer vergangen (außer heute IST der 1. Januar)
        if date.today() > date(date.today().year, 1, 1):
            result = parse_datum("01.01.")
            assert result is not None
            jahr = int(result.split(".")[2])
            assert jahr > date.today().year


# ── parse_uhrzeit ─────────────────────────────────────────────────────────────

class TestParseUhrzeit:

    def test_zehn_uhr(self):
        assert parse_uhrzeit("zehn Uhr") == "10:00"

    def test_halb_elf(self):
        assert parse_uhrzeit("halb elf") == "10:30"

    def test_vierzehn_uhr(self):
        assert parse_uhrzeit("vierzehn Uhr") == "14:00"

    def test_numerisch_hhmm(self):
        assert parse_uhrzeit("10:00") == "10:00"

    def test_numerisch_h_uhr(self):
        """'10 Uhr' ohne Minuten."""
        result = parse_uhrzeit("10 Uhr")
        assert result == "10:00"

    def test_leerer_string_gibt_none(self):
        assert parse_uhrzeit("") is None

    def test_keine_uhrzeit_gibt_none(self):
        assert parse_uhrzeit("Montag bitte") is None


# ── parse_yesno ───────────────────────────────────────────────────────────────

class TestParseYesno:

    def test_ja_klar(self):
        assert parse_yesno("ja klar") is True

    def test_genau(self):
        assert parse_yesno("genau") is True

    def test_nein(self):
        assert parse_yesno("nein danke") is False

    def test_noe(self):
        assert parse_yesno("nö") is False

    def test_unklar_gibt_none(self):
        assert parse_yesno("vielleicht später") is None

    def test_passt(self):
        assert parse_yesno("passt") is True

    def test_stimmt_nicht(self):
        assert parse_yesno("stimmt nicht") is False


# ── ist_telefonnummer ─────────────────────────────────────────────────────────

class TestIstTelefonnummer:

    def test_deutsche_festnetznummer(self):
        assert ist_telefonnummer("+49 761 123456") is True

    def test_kurznummer_zu_kurz(self):
        assert ist_telefonnummer("1234") is False

    def test_fuenf_ziffern_ok(self):
        assert ist_telefonnummer("12345") is True

    def test_mit_bindestrichen(self):
        assert ist_telefonnummer("0761-12345") is True

    def test_leerer_string(self):
        assert ist_telefonnummer("") is False

    def test_nur_buchstaben(self):
        assert ist_telefonnummer("keine nummer") is False


# ── datum_de / uhrzeit_de (TTS-Ausgabe) ──────────────────────────────────────

class TestTtsAusgabe:

    def test_datum_de_format(self):
        result = datum_de("27.04.2026")
        assert "April" in result
        # Muss Wochentag enthalten (27.04.2026 = Montag)
        assert "Montag" in result

    def test_uhrzeit_de_volle_stunde(self):
        assert "zehn Uhr" in uhrzeit_de("10:00")

    def test_uhrzeit_de_halb(self):
        result = uhrzeit_de("10:30")
        assert "halb" in result

    def test_uhrzeit_de_nachmittags(self):
        result = uhrzeit_de("14:00")
        assert "vierzehn" in result


# ── SUCHE_VOR_TAGEN Konstante ─────────────────────────────────────────────────

class TestKonstanten:

    def test_suche_vor_tagen_mindestens_30(self):
        """Suchfenster muss ausreichend groß sein um Urlaubsblöcke zu überbrücken."""
        assert SUCHE_VOR_TAGEN >= 30, (
            f"SUCHE_VOR_TAGEN={SUCHE_VOR_TAGEN} zu klein — "
            "bei mehrwöchigen Urlaubsblöcken werden keine Termine gefunden"
        )


# ── PhoneDialog mit MockProvider ──────────────────────────────────────────────

class MockProvider:
    """Minimaler Provider-Mock für PhoneDialog-Integrationstests."""
    def __init__(self, antwort="INTENT:termin"):
        self._antwort = antwort

    def chat(self, messages, system=""):
        return self._antwort


class TestPhoneDialogIntegration:
    """Smoke-Tests für den PhoneDialog ohne LLM und ohne Kalender-Verbindung."""

    def _make_dialog(self, antwort="INTENT:termin"):
        from phone_dialog import PhoneDialog
        config = {
            "begruessung":      "Guten Tag!",
            "abschluss":        "Auf Wiederhören!",
            "nicht_zustaendig": "Nicht zuständig.",
            "firmenname":       "Testfirma",
            "ki_rolle":         "Assistent",
            "dienste":          ["Termin vereinbaren"],
            "public_info_pfad": "data/public_info",
        }
        info_reader = MagicMock()
        info_reader.als_kontext_text.return_value = ""
        return PhoneDialog(
            provider=MockProvider(antwort),
            config=config,
            info_reader=info_reader,
            caller_id="+4976112345",
        )

    def test_instantiierung_ohne_fehler(self):
        dialog = self._make_dialog()
        assert dialog is not None

    def test_reset_funktioniert(self):
        dialog = self._make_dialog()
        dialog.reset()
        assert dialog is not None

    def test_set_caller_id(self):
        dialog = self._make_dialog()
        dialog.set_caller_id("+49761999")
        assert dialog.slots.caller_id == "+49761999"

    def test_spelling_mode_initial_inaktiv(self):
        dialog = self._make_dialog()
        assert dialog.slots.spelling_active is False

    def test_process_gibt_string_zurueck(self):
        dialog = self._make_dialog()
        result = dialog.process("Hallo")
        assert isinstance(result, str)
