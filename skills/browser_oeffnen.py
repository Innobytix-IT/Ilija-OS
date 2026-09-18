"""
Öffnet einen Chrome Browser, der offen bleibt.
"""
import os
import subprocess
import glob as _glob
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from urllib.parse import urlparse

driver = None

_PROFIL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "outlook_profil"
)
_DEBUG_PORT = "9223"


def _is_driver_alive() -> bool:
    global driver
    if driver is None:
        return False
    try:
        _ = driver.title
        return True
    except Exception:
        return False


def _verbinde_mit_chrome():
    """Hängt sich an einen bereits laufenden Chrome-Prozess auf dem Debug-Port."""
    try:
        opts = webdriver.ChromeOptions()
        opts.debugger_address = f"127.0.0.1:{_DEBUG_PORT}"
        d = webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=opts)
        _ = d.title
        print(f"♻️  An laufende Chrome-Session angehängt (Port {_DEBUG_PORT})")
        return d
    except Exception:
        return None


def _starte_chrome_neu(url: str):
    """Beendet laufendes Chrome, löscht Locks, startet neu."""
    subprocess.run(
        ["pkill", "-f", f"google-chrome.*{_PROFIL_DIR}"],
        capture_output=True
    )
    import time
    time.sleep(1.5)

    for lock in _glob.glob(os.path.join(_PROFIL_DIR, "Singleton*")):
        try:
            os.remove(lock)
        except OSError:
            pass

    opts = webdriver.ChromeOptions()
    opts.binary_location = "/usr/bin/google-chrome"
    opts.add_experimental_option("detach", True)
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-session-crashed-bubble")
    opts.add_argument("--disable-infobars")
    opts.add_argument(f"--user-data-dir={_PROFIL_DIR}")
    opts.add_argument(f"--remote-debugging-port={_DEBUG_PORT}")

    print(f"🚀 Starte Browser (Profil: {_PROFIL_DIR}) für {url}...")
    return webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=opts)


def browser_oeffnen(url: str) -> str:
    """Öffnet eine Webseite in einem sichtbaren Chrome-Browser-Fenster."""
    global driver
    url = url.strip()
    _parsed = urlparse(url)
    if _parsed.scheme not in ("http", "https"):
        return f"❌ URL-Schema '{_parsed.scheme}' ist nicht erlaubt. Nur http:// und https:// sind zulässig."
    if not _parsed.netloc:
        return f"❌ Ungültige URL: Kein Hostname gefunden in '{url}'"

    try:
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"

        # Erst bestehende Session wiederverwenden
        if not _is_driver_alive():
            driver = _verbinde_mit_chrome()

        # Sonst: Chrome neu starten
        if not _is_driver_alive():
            driver = _starte_chrome_neu(url)

        driver.get(url)
        return f"✅ Browser gestartet und auf {url} navigiert."
    except Exception as e:
        return f"❌ Fehler beim Browser-Start: {str(e)}"


AVAILABLE_SKILLS = [browser_oeffnen]
