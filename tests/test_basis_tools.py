"""
test_basis_tools.py – Tests für skills/basis_tools.py
======================================================
Testet: uhrzeit_datum, notiz_speichern, notizen_lesen, taschenrechner, einheit_umrechnen
"""
import os
import sys
import pytest
from datetime import datetime
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skills.basis_tools import (
    uhrzeit_datum,
    notiz_speichern,
    notizen_lesen,
    taschenrechner,
    einheit_umrechnen,
)


# ── uhrzeit_datum ─────────────────────────────────────────────────────────────

class TestUhrzeitDatum:

    def test_gibt_string_zurueck(self):
        result = uhrzeit_datum()
        assert isinstance(result, str)

    def test_enthaelt_datum_symbol(self):
        result = uhrzeit_datum()
        assert "📅" in result

    def test_enthaelt_uhrzeit_symbol(self):
        result = uhrzeit_datum()
        assert "🕐" in result

    def test_enthaelt_aktuelles_jahr(self):
        result = uhrzeit_datum()
        assert str(datetime.now().year) in result

    def test_enthaelt_uhr_suffix(self):
        result = uhrzeit_datum()
        assert "Uhr" in result

    def test_format_zweiteilig(self):
        result = uhrzeit_datum()
        zeilen = [z for z in result.split("\n") if z.strip()]
        assert len(zeilen) == 2


# ── notiz_speichern ───────────────────────────────────────────────────────────

class TestNotizSpeichern:

    def test_erfolgsmeldung(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = notiz_speichern(text="Test-Notiz")
        assert "✅" in result
        assert "notizen.txt" in result

    def test_datei_wird_erstellt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Meine Notiz")
        pfad = tmp_path / "data" / "notizen" / "notizen.txt"
        assert pfad.exists()

    def test_inhalt_korrekt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Wichtige Info")
        pfad = tmp_path / "data" / "notizen" / "notizen.txt"
        inhalt = pfad.read_text(encoding="utf-8")
        assert "Wichtige Info" in inhalt

    def test_zeitstempel_im_inhalt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Test")
        pfad = tmp_path / "data" / "notizen" / "notizen.txt"
        inhalt = pfad.read_text(encoding="utf-8")
        assert str(datetime.now().year) in inhalt

    def test_mehrere_notizen_werden_angehaengt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Erste")
        notiz_speichern(text="Zweite")
        pfad = tmp_path / "data" / "notizen" / "notizen.txt"
        inhalt = pfad.read_text(encoding="utf-8")
        assert "Erste" in inhalt
        assert "Zweite" in inhalt

    def test_benutzerdefinierter_dateiname(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Projekt-Notiz", datei="projekt.txt")
        pfad = tmp_path / "data" / "notizen" / "projekt.txt"
        assert pfad.exists()

    def test_path_traversal_verhindert(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # ../../evil.txt sollte zu evil.txt bereinigt werden
        notiz_speichern(text="Test", datei="../../evil.txt")
        # Böse Datei darf nicht außerhalb des Notiz-Ordners entstehen
        assert not (tmp_path / "evil.txt").exists()
        # Bereinigter Name muss im Notiz-Ordner landen
        pfad = tmp_path / "data" / "notizen" / "evil.txt"
        assert pfad.exists()

    def test_dateiname_bekommt_txt_endung(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Test", datei="memo")
        pfad = tmp_path / "data" / "notizen" / "memo.txt"
        assert pfad.exists()


# ── notizen_lesen ─────────────────────────────────────────────────────────────

class TestNotizenLesen:

    def test_keine_notizen_vorhanden(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = notizen_lesen()
        assert "Keine Notizen" in result

    def test_liest_gespeicherte_notiz(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Lesetest")
        result = notizen_lesen()
        assert "Lesetest" in result

    def test_ausgabe_enthaelt_symbol(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        notiz_speichern(text="Symbol-Test")
        result = notizen_lesen()
        assert "📝" in result

    def test_leeres_notizbuch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Leere Datei erstellen
        (tmp_path / "data" / "notizen").mkdir(parents=True)
        (tmp_path / "data" / "notizen" / "notizen.txt").write_text("", encoding="utf-8")
        result = notizen_lesen()
        assert "leer" in result.lower() or "Keine" in result

    def test_path_traversal_verhindert(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = notizen_lesen(datei="../../etc/passwd")
        # Darf nicht den Inhalt einer Systemdatei zurückgeben
        assert "Keine Notizen" in result or "Fehler" in result or "leer" in result.lower()


# ── taschenrechner ────────────────────────────────────────────────────────────

class TestTaschenrechner:

    def test_addition(self):
        result = taschenrechner("2 + 3")
        assert "5" in result

    def test_subtraktion(self):
        result = taschenrechner("10 - 4")
        assert "6" in result

    def test_multiplikation(self):
        result = taschenrechner("7 * 6")
        assert "42" in result

    def test_division(self):
        result = taschenrechner("10 / 4")
        assert "2.5" in result

    def test_potenz(self):
        result = taschenrechner("2 ** 8")
        assert "256" in result

    def test_komplexer_ausdruck(self):
        result = taschenrechner("(1250 * 1.19) + 48.50")
        assert "1536" in result  # 1487.5 + 48.5 = 1536.0

    def test_modulo(self):
        result = taschenrechner("17 % 5")
        assert "2" in result

    def test_negatives_ergebnis(self):
        result = taschenrechner("3 - 10")
        assert "-7" in result

    def test_division_durch_null(self):
        result = taschenrechner("5 / 0")
        assert "❌" in result
        assert "Null" in result or "null" in result.lower()

    def test_ungueltige_eingabe(self):
        result = taschenrechner("abc + 1")
        assert "❌" in result

    def test_import_verboten(self):
        # Sicherheit: import os darf nicht ausgeführt werden
        result = taschenrechner("__import__('os').system('echo pwned')")
        assert "❌" in result

    def test_ergebnis_enthaelt_ausdruck(self):
        result = taschenrechner("3 + 4")
        assert "3 + 4" in result

    def test_symbol_im_output(self):
        result = taschenrechner("1 + 1")
        assert "🧮" in result


# ── einheit_umrechnen ─────────────────────────────────────────────────────────

class TestEinheitUmrechnen:

    def test_km_zu_meilen(self):
        result = einheit_umrechnen("100", "km", "meilen")
        assert "62" in result  # ~62.14 Meilen

    def test_meilen_zu_km(self):
        result = einheit_umrechnen("1", "meilen", "km")
        assert "1.609" in result

    def test_celsius_zu_fahrenheit(self):
        result = einheit_umrechnen("0", "celsius", "fahrenheit")
        assert "32" in result

    def test_fahrenheit_zu_celsius(self):
        result = einheit_umrechnen("212", "fahrenheit", "celsius")
        assert "100" in result

    def test_celsius_zu_kelvin(self):
        result = einheit_umrechnen("0", "celsius", "kelvin")
        assert "273.15" in result

    def test_kg_zu_pfund(self):
        result = einheit_umrechnen("1", "kg", "pfund")
        assert "2.2" in result

    def test_euro_zu_dollar(self):
        result = einheit_umrechnen("100", "euro", "dollar")
        assert "109" in result

    def test_unbekannte_einheit(self):
        result = einheit_umrechnen("5", "parsec", "lichtjahr")
        assert "❌" in result

    def test_ungueltige_zahl(self):
        result = einheit_umrechnen("abc", "km", "meilen")
        assert "❌" in result

    def test_case_insensitiv(self):
        result = einheit_umrechnen("100", "KM", "MEILEN")
        assert "62" in result

    def test_symbol_im_output(self):
        result = einheit_umrechnen("10", "m", "ft")
        assert "🔢" in result

    def test_ergebnis_enthaelt_einheiten(self):
        result = einheit_umrechnen("5", "kg", "pfund")
        assert "kg" in result
        assert "pfund" in result
