"""
Öffnet einen Chrome Browser, der offen bleibt.
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from urllib.parse import urlparse

# Wir definieren den driver global, damit er nicht gelöscht wird
driver = None

def browser_oeffnen(url: str) -> str:
    """
    Öffnet eine Webseite in einem sichtbaren Chrome-Browser-Fenster.
    Das Fenster bleibt nach dem Öffnen bestehen (detach-Modus).
    Benötigt: pip install selenium webdriver-manager
    Beispiel: browser_oeffnen(url="https://www.google.de")
    """
    global driver

    # URL-Validierung: nur http und https erlaubt (kein javascript:, file:, data: etc.)
    url = url.strip()
    _parsed = urlparse(url)
    if _parsed.scheme not in ("http", "https"):
        return (
            f"❌ URL-Schema '{_parsed.scheme}' ist nicht erlaubt. "
            f"Nur http:// und https:// sind zulässig."
        )
    if not _parsed.netloc:
        return f"❌ Ungültige URL: Kein Hostname gefunden in '{url}'"

    try:
        # Chrome Optionen: Detach sorgt dafür, dass das Fenster offen bleibt!
        import os as _os
        if "DISPLAY" not in _os.environ:
            _os.environ["DISPLAY"] = ":0"
        options = webdriver.ChromeOptions()
        options.binary_location = "/usr/bin/google-chrome"
        options.add_experimental_option("detach", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--remote-debugging-port=9223")

        print(f"🚀 Starte Browser für {url}...")

        # Initialisiere den Driver
        driver = webdriver.Chrome(
            service=Service("/usr/local/bin/chromedriver"),
            options=options
        )

        driver.get(url)
        return f"✅ Browser gestartet und auf {url} navigiert. Das Fenster sollte nun offen sein."
    except Exception as e:
        return f"❌ Fehler beim Browser-Start: {str(e)}"

AVAILABLE_SKILLS = [browser_oeffnen]
