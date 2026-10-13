#!/usr/bin/env python3
"""
update_selbsttest.py – prueft nach einem Update ob Ilija OS gesund ist.

Exit-Codes:
  0  = alles ok
  1  = kritischer Fehler, Rollback empfohlen (Grund in stdout)
  2  = Pre-Check: System war VOR dem Update bereits defekt – kein
       Rollback erzwingen, damit man nicht in defekter Version steckt

Aufruf:
  python3 update_selbsttest.py pre     # vor dem git pull
  python3 update_selbsttest.py post    # nach dem Update

Was gecheckt wird:
  - Python-Imports (web_server, kernel) crashen nicht
  - systemd-Service "ilija" ist nach Restart aktiv
  - HTTP /api/setup-status antwortet 200 innerhalb 10s
  - Journal der letzten 60s hat keinen Python-Traceback vom Service
"""
import json
import os
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError

REPO = "/opt/ilija-os/ilija"
PORT = 5001
HEALTH_URL = f"http://127.0.0.1:{PORT}/api/setup-status"


def _laufe(cmd, timeout=15, env=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None


def check_imports():
    """python3 -c 'import web_server, kernel' im venv."""
    venv_py = os.path.join(REPO, "venv", "bin", "python3")
    py = venv_py if os.path.exists(venv_py) else sys.executable
    r = _laufe([py, "-c", "import web_server, kernel"], timeout=30)
    if r is None:
        return False, "Import-Check: Timeout"
    if r.returncode != 0:
        return False, f"Import-Check: {r.stderr.strip()[:400]}"
    return True, "Imports OK"


def check_service_aktiv(wartesekunden=15):
    """systemctl is-active ilija nach dem Restart."""
    time.sleep(wartesekunden)
    r = _laufe(["systemctl", "is-active", "ilija"], timeout=5)
    if r is None:
        return False, "Service-Check: Timeout"
    state = r.stdout.strip()
    if state != "active":
        return False, f"Service-Check: ilija ist '{state}', nicht 'active'"
    return True, "Service aktiv"


def check_http():
    """HTTP-Health auf /api/setup-status."""
    letzter_fehler = ""
    for _ in range(10):
        try:
            with urlopen(HEALTH_URL, timeout=3) as resp:
                if resp.status == 200:
                    return True, "HTTP OK"
                letzter_fehler = f"HTTP {resp.status}"
        except URLError as e:
            letzter_fehler = f"URLError: {e.reason}"
        except Exception as e:
            letzter_fehler = f"{type(e).__name__}: {e}"
        time.sleep(1)
    return False, f"HTTP-Check: {letzter_fehler}"


def check_journal_sauber():
    """Letzte 60s Journal von ilija nach Traceback scannen."""
    r = _laufe(["journalctl", "-u", "ilija", "--since", "60 seconds ago",
                "--no-pager", "-q"], timeout=10)
    if r is None or r.returncode != 0:
        return True, "Journal-Check: uebersprungen (nicht lesbar)"
    log = r.stdout or ""
    # Harte Trigger: Traceback-Zeilen vom Startup
    for marker in ("Traceback (most recent call last):",
                   "ModuleNotFoundError",
                   "ImportError:",
                   "SyntaxError:"):
        if marker in log:
            # Kontextzeile extrahieren
            idx  = log.find(marker)
            kontext = log[max(0, idx - 60):idx + 300].replace("\n", " ")
            return False, f"Journal-Check: {marker} im Startup-Log – {kontext}"
    return True, "Journal sauber"


def laufe_alle_checks(nach_update=True):
    """Fuehrt alle Checks aus. Liefert (ok, Liste von (name, ok, msg))."""
    ergebnisse = []

    for name, func in [("Imports",      check_imports),
                       ("Service",      check_service_aktiv),
                       ("HTTP-Health",  check_http),
                       ("Journal",      check_journal_sauber)]:
        try:
            ok, msg = func()
        except Exception as e:
            ok, msg = False, f"{name}: Exception {e}"
        ergebnisse.append((name, ok, msg))
        if not ok:
            # Weitere Checks sind sinnlos wenn ein harter failt
            break

    gesamt_ok = all(ok for _, ok, _ in ergebnisse)
    return gesamt_ok, ergebnisse


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "post"
    ok, ergebnisse = laufe_alle_checks(nach_update=(phase == "post"))

    for name, erg_ok, msg in ergebnisse:
        marker = "OK" if erg_ok else "FAIL"
        print(f"  [{marker}] {name}: {msg}")

    if ok:
        print("Selbsttest: BESTANDEN")
        sys.exit(0)

    if phase == "pre":
        # System schon vorher defekt – Rollback nicht erzwingen
        print("Selbsttest: System war bereits VOR dem Update defekt – "
              "Rollback-Schutz deaktiviert.")
        sys.exit(2)

    # Post-Fehler: Grund in strukturierter Form fuer das Shell-Script
    gruende = [msg for _, erg_ok, msg in ergebnisse if not erg_ok]
    print("Selbsttest: FEHLGESCHLAGEN")
    with open("/tmp/ilija_selbsttest_grund.txt", "w") as f:
        f.write("\n".join(gruende))
    sys.exit(1)


if __name__ == "__main__":
    main()
