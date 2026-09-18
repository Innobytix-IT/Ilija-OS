"""
Öffnet einen Chrome Browser, der offen bleibt.
"""
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from urllib.parse import urlparse

# Wir definieren den driver global, damit er nicht gelöscht wird
driver = None

# Gespeichertes Chrome-Profil: enthält Outlook + WhatsApp-Sessions
_PROFIL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "outlook_profil"
)

def browser_oeffnen(url: str) -> str:
    """
    Öffnet eine Webseite in einem sichtbaren Chrome-Browser-Fenster.
    Das Fenster bleibt nach dem Öffnen bestehen (detach-Modus).
    Nutzt das gespeicherte Profil (data/outlook_profil) mit persistenten Sessions.
    Benötigt: pip install selenium
    Beispiel: browser_oeffnen(url="https://web.whatsapp.com")
    """
    global driver

    # URL-Validierung: nur http und https erlaubt
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
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"

        options = webdriver.ChromeOptions()
        options.binary_location = "/usr/bin/google-chrome"
        options.add_experimental_option("detach", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument(f"--user-data-dir={_PROFIL_DIR}")
        options.add_argument("--remote-debugging-port=9223")

        print(f"🚀 Starte Browser (Profil: {_PROFIL_DIR}) für {url}...")

        driver = webdriver.Chrome(
            service=Service("/usr/local/bin/chromedriver"),
            options=options
        )

        driver.get(url)
        return f"✅ Browser gestartet und auf {url} navigiert."
    except Exception as e:
        return f"❌ Fehler beim Browser-Start: {str(e)}"

AVAILABLE_SKILLS = [browser_oeffnen]
