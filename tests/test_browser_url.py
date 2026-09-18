"""
test_browser_url.py – Tests für URL-Validierung in skills/browser_oeffnen.py
=============================================================================
Testet die URL-Validierungslogik ohne echten Browser-Start (Selenium gemockt).
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ── Hilfsfunktion: URL-Validierung isoliert testen ────────────────────────────
# Selenium wird komplett gemockt damit kein Browser startet

def _browser_oeffnen_mit_mock(url: str) -> str:
    """Ruft browser_oeffnen mit gemocktem Selenium auf."""
    mock_driver = MagicMock()
    mock_options = MagicMock()
    mock_service = MagicMock()

    with patch.dict("sys.modules", {
        "selenium": MagicMock(),
        "selenium.webdriver": MagicMock(),
        "selenium.webdriver.chrome.service": MagicMock(),
        "webdriver_manager": MagicMock(),
        "webdriver_manager.chrome": MagicMock(),
    }):
        # Direkt importieren und ausführen
        import importlib
        import skills.browser_oeffnen as bo
        importlib.reload(bo)

        # Selenium-Objekte mocken
        with patch.object(bo.webdriver, "Chrome", return_value=mock_driver), \
             patch.object(bo.webdriver, "ChromeOptions", return_value=mock_options), \
             patch("skills.browser_oeffnen.ChromeDriverManager") as mock_cdm:
            mock_cdm.return_value.install.return_value = "/mock/chromedriver"
            return bo.browser_oeffnen(url)


# ── URL-Validierung ───────────────────────────────────────────────────────────

class TestBrowserUrlValidierung:

    def test_gueltige_https_url_erlaubt(self, monkeypatch):
        """https:// URLs werden akzeptiert."""
        import skills.browser_oeffnen as bo
        # Selenium-Call mocken damit kein Browser startet
        mock_driver = MagicMock()
        with patch("skills.browser_oeffnen.webdriver") as mock_wd, \
             patch("skills.browser_oeffnen.ChromeDriverManager") as mock_cdm, \
             patch("skills.browser_oeffnen.Service"):
            mock_wd.Chrome.return_value = mock_driver
            mock_wd.ChromeOptions.return_value = MagicMock()
            mock_cdm.return_value.install.return_value = "/mock/driver"
            result = bo.browser_oeffnen("https://www.google.de")
        assert "❌" not in result or "Schema" not in result

    def test_gueltige_http_url_erlaubt(self):
        """http:// URLs werden akzeptiert."""
        import skills.browser_oeffnen as bo
        with patch("skills.browser_oeffnen.webdriver") as mock_wd, \
             patch("skills.browser_oeffnen.ChromeDriverManager") as mock_cdm, \
             patch("skills.browser_oeffnen.Service"):
            mock_wd.Chrome.return_value = MagicMock()
            mock_wd.ChromeOptions.return_value = MagicMock()
            mock_cdm.return_value.install.return_value = "/mock/driver"
            result = bo.browser_oeffnen("http://localhost:8080")
        assert "Schema" not in result

    def test_javascript_schema_blockiert(self):
        """javascript: URLs werden blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("javascript:alert('xss')")
        assert "❌" in result
        assert "javascript" in result.lower() or "Schema" in result

    def test_file_schema_blockiert(self):
        """file:// URLs werden blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("file:///etc/passwd")
        assert "❌" in result

    def test_data_schema_blockiert(self):
        """data: URLs werden blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("data:text/html,<script>evil()</script>")
        assert "❌" in result

    def test_ftp_schema_blockiert(self):
        """ftp:// URLs werden blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("ftp://server.com/file")
        assert "❌" in result

    def test_leere_url_blockiert(self):
        """Leere URL wird blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("")
        assert "❌" in result

    def test_url_ohne_schema_blockiert(self):
        """URL ohne Schema wird blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("www.google.de")
        assert "❌" in result

    def test_url_ohne_hostname_blockiert(self):
        """URL nur mit Schema aber ohne Host wird blockiert."""
        import skills.browser_oeffnen as bo
        result = bo.browser_oeffnen("https://")
        assert "❌" in result
