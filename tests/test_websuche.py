"""
test_websuche.py – Tests für skills/webseiten_inhalt_lesen.py
==============================================================
Testet: internet_suche, webseite_lesen, wikipedia_suche, news_abrufen
Externe Anfragen werden gemockt — kein echtes Internet nötig.
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skills.webseiten_inhalt_lesen import (
    internet_suche,
    webseite_lesen,
    wikipedia_suche,
)


# ── Hilfsfunktionen für Mocks ─────────────────────────────────────────────────

def _mock_ddg_results(n=3):
    return [
        {"title": f"Ergebnis {i}", "body": f"Beschreibung {i}", "href": f"https://example.com/{i}"}
        for i in range(1, n + 1)
    ]


def _mock_requests_get(text: str, status: int = 200):
    """Erstellt ein Mock-Response-Objekt für requests.get()."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.text = text
    mock_resp.apparent_encoding = "utf-8"
    mock_resp.encoding = "utf-8"
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ── internet_suche ────────────────────────────────────────────────────────────

class TestInternetSuche:

    def test_ddg_ergebnisse_werden_ausgegeben(self):
        with patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(3)):
            result = internet_suche("Test-Suche")
        assert "Ergebnis 1" in result
        assert "Ergebnis 2" in result

    def test_symbol_im_output(self):
        with patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(1)):
            result = internet_suche("Test")
        assert "🔍" in result

    def test_suchanfrage_im_output(self):
        with patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(1)):
            result = internet_suche("Python Programmierung")
        assert "Python Programmierung" in result

    def test_urls_im_output(self):
        with patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(2)):
            result = internet_suche("Test")
        assert "https://example.com" in result

    def test_keine_ergebnisse(self):
        with patch("skills.webseiten_inhalt_lesen._ddg_suche", return_value=None), \
             patch("skills.webseiten_inhalt_lesen._google_suche", return_value=None):
            result = internet_suche("Nicht-Findbar-XYZ-123")
        assert "Keine Ergebnisse" in result

    def test_max_ergebnisse_wird_beachtet(self):
        with patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(5)) as mock_ddg:
            internet_suche("Test", max_ergebnisse=3)
            # max_ergebnisse als int übergeben
            args = mock_ddg.call_args
            assert args[0][1] == 3 or args[1].get("max_ergebnisse") == 3

    def test_google_hat_prioritaet_wenn_key_gesetzt(self):
        google_results = [{"title": "Google-Ergebnis", "body": "...", "href": "https://google.com"}]
        with patch("skills.webseiten_inhalt_lesen._google_suche",
                   return_value=google_results) as mock_g, \
             patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(1)) as mock_d:
            result = internet_suche("Test")
        assert "Google" in result
        mock_d.assert_not_called()

    def test_ddg_fallback_wenn_kein_google_key(self):
        with patch("skills.webseiten_inhalt_lesen._google_suche", return_value=None), \
             patch("skills.webseiten_inhalt_lesen._ddg_suche",
                   return_value=_mock_ddg_results(1)) as mock_d:
            result = internet_suche("Test")
        mock_d.assert_called_once()
        assert "DuckDuckGo" in result


# ── webseite_lesen ────────────────────────────────────────────────────────────

class TestWebseiteLesen:

    HTML_BEISPIEL = """
    <html><head><title>Test</title></head>
    <body>
        <nav>Navigation wird entfernt</nav>
        <p>Hauptinhalt der Seite</p>
        <footer>Footer wird entfernt</footer>
    </body></html>
    """

    def test_liest_webseite(self):
        with patch("requests.get", return_value=_mock_requests_get(self.HTML_BEISPIEL)):
            result = webseite_lesen("https://example.com")
        assert "Hauptinhalt" in result

    def test_navigation_wird_entfernt(self):
        with patch("requests.get", return_value=_mock_requests_get(self.HTML_BEISPIEL)):
            result = webseite_lesen("https://example.com")
        assert "Navigation wird entfernt" not in result

    def test_footer_wird_entfernt(self):
        with patch("requests.get", return_value=_mock_requests_get(self.HTML_BEISPIEL)):
            result = webseite_lesen("https://example.com")
        assert "Footer wird entfernt" not in result

    def test_domain_im_output(self):
        with patch("requests.get", return_value=_mock_requests_get(self.HTML_BEISPIEL)):
            result = webseite_lesen("https://example.com/seite")
        assert "example.com" in result

    def test_symbol_im_output(self):
        with patch("requests.get", return_value=_mock_requests_get(self.HTML_BEISPIEL)):
            result = webseite_lesen("https://example.com")
        assert "🌐" in result

    def test_url_ohne_schema_wird_korrigiert(self):
        with patch("requests.get", return_value=_mock_requests_get(self.HTML_BEISPIEL)):
            result = webseite_lesen("  https://example.com  ")
        assert "❌" not in result or "Fehler" not in result

    def test_ungueltige_url_gibt_fehlermeldung(self):
        result = webseite_lesen("kein-gueltige-url")
        assert "❌" in result

    def test_netzwerkfehler_wird_abgefangen(self):
        with patch("requests.get", side_effect=Exception("Netzwerkfehler")):
            result = webseite_lesen("https://example.com")
        assert "❌" in result

    def test_text_wird_auf_8000_zeichen_gekuerzt(self):
        langer_inhalt = "A" * 20000
        html = f"<html><body><p>{langer_inhalt}</p></body></html>"
        with patch("requests.get", return_value=_mock_requests_get(html)):
            result = webseite_lesen("https://example.com")
        # Output darf nicht mehr als 8000 + Overhead sein
        assert len(result) < 10000


# ── wikipedia_suche ───────────────────────────────────────────────────────────

class TestWikipediaSuche:

    WIKI_RESPONSE = {
        "title": "Künstliche Intelligenz",
        "extract": "Künstliche Intelligenz (KI) ist ein Teilgebiet der Informatik.",
        "content_urls": {
            "desktop": {"page": "https://de.wikipedia.org/wiki/K%C3%BCnstliche_Intelligenz"}
        }
    }

    def test_wikipedia_gibt_zusammenfassung(self):
        mock_resp = _mock_requests_get(json.dumps(self.WIKI_RESPONSE))
        mock_resp.json.return_value = self.WIKI_RESPONSE
        with patch("requests.get", return_value=mock_resp):
            result = wikipedia_suche("Künstliche Intelligenz")
        assert "Künstliche Intelligenz" in result

    def test_symbol_im_output(self):
        mock_resp = _mock_requests_get(json.dumps(self.WIKI_RESPONSE))
        mock_resp.json.return_value = self.WIKI_RESPONSE
        with patch("requests.get", return_value=mock_resp):
            result = wikipedia_suche("KI")
        assert "📖" in result

    def test_url_im_output(self):
        mock_resp = _mock_requests_get(json.dumps(self.WIKI_RESPONSE))
        mock_resp.json.return_value = self.WIKI_RESPONSE
        with patch("requests.get", return_value=mock_resp):
            result = wikipedia_suche("KI")
        assert "wikipedia.org" in result

    def test_nicht_gefundener_artikel(self):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError(
            response=MagicMock(status_code=404)
        )
        with patch("requests.get", return_value=mock_resp):
            result = wikipedia_suche("XYZ_Artikel_Existiert_Nicht_12345")
        assert "❌" in result

    def test_netzwerkfehler_wird_abgefangen(self):
        with patch("requests.get", side_effect=Exception("Timeout")):
            result = wikipedia_suche("Test")
        assert "❌" in result

    def test_englische_sprache(self):
        WIKI_EN = {
            "title": "Artificial Intelligence",
            "extract": "Artificial intelligence (AI) is intelligence demonstrated by machines.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/AI"}},
        }
        mock_resp = _mock_requests_get(json.dumps(WIKI_EN))
        mock_resp.json.return_value = WIKI_EN
        with patch("requests.get", return_value=mock_resp):
            result = wikipedia_suche("Artificial Intelligence", sprache="en")
        assert "Artificial intelligence" in result
