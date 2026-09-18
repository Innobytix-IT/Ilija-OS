"""
test_skills_einfach.py – Tests für einfache Zufalls-Skills
===========================================================
Testet: wuerfeln, muenze_werfen
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skills.wuerfeln import wuerfeln
from skills.muenze_werfen import muenze_werfen


# ── wuerfeln ──────────────────────────────────────────────────────────────────

class TestWuerfeln:

    def test_gibt_string_zurueck(self):
        assert isinstance(wuerfeln(), str)

    def test_ergebnis_im_bereich_1_bis_6(self):
        for _ in range(50):
            result = wuerfeln(max=6)
            # Zahl aus dem Ergebnis extrahieren
            zahl = int(result.split("**")[1])
            assert 1 <= zahl <= 6

    def test_d20_im_bereich(self):
        for _ in range(50):
            result = wuerfeln(max=20)
            zahl = int(result.split("**")[1])
            assert 1 <= zahl <= 20

    def test_d100_im_bereich(self):
        for _ in range(100):
            result = wuerfeln(max=100)
            zahl = int(result.split("**")[1])
            assert 1 <= zahl <= 100

    def test_symbol_im_output(self):
        assert "🎲" in wuerfeln()

    def test_max_im_output(self):
        result = wuerfeln(max=12)
        assert "12" in result

    def test_min_wert_korrekt(self):
        result = wuerfeln(max=1)
        assert "1" in result

    def test_zufaelligkeit_vorhanden(self):
        # Bei 30 Würfen sollte nicht immer dasselbe Ergebnis herauskommen
        ergebnisse = {wuerfeln(max=6) for _ in range(30)}
        assert len(ergebnisse) > 1

    def test_standard_max_ist_6(self):
        result = wuerfeln()
        assert "1–6" in result


# ── muenze_werfen ─────────────────────────────────────────────────────────────

class TestMuenzeWerfen:

    def test_gibt_string_zurueck(self):
        assert isinstance(muenze_werfen(), str)

    def test_ergebnis_ist_kopf_oder_zahl(self):
        for _ in range(20):
            result = muenze_werfen()
            assert "Kopf" in result or "Zahl" in result

    def test_symbol_im_output(self):
        assert "🪙" in muenze_werfen()

    def test_zufaelligkeit_vorhanden(self):
        ergebnisse = {muenze_werfen() for _ in range(30)}
        # Beide Ergebnisse sollten statistisch auftreten
        assert len(ergebnisse) == 2

    def test_kein_anderes_ergebnis(self):
        for _ in range(20):
            result = muenze_werfen()
            # Exakt eines von beiden
            assert ("Kopf" in result) ^ ("Zahl" in result) or \
                   ("Kopf" in result and "Zahl" not in result) or \
                   ("Zahl" in result and "Kopf" not in result)
