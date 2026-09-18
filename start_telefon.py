"""
start_telefon.py – Ilija Telefon-Assistent starten
===================================================
Startet Ilija im Anruf-Empfangs-Modus.
Ilija registriert sich bei der FritzBox und wartet auf eingehende Anrufe.

Starten:
    python start_telefon.py

Beenden:
    Strg+C
"""

import sys
import time
import logging
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    print()
    print("=" * 54)
    print("  Ilija Telefon-Assistent")
    print("=" * 54)

    # 1. CustomerKernel aufbauen (LLM + PhoneDialog)
    print("\n[1/3] Lade KI-Kern (Gemini)...")
    try:
        from customer_kernel import CustomerKernel
        kernel = CustomerKernel()
        print(f"      Begrüßung: \"{kernel.begruessung}\"")
        print("      ✅ KI-Kern bereit")
    except Exception as e:
        print(f"      ❌ Fehler: {e}")
        sys.exit(1)

    # 2. FritzBox-Registrierung
    print("\n[2/3] Verbinde mit FritzBox...")
    try:
        from skills.fritzbox_skill import telefon_starten, skill_ausfuehren, telefon_stoppen
        ok = telefon_starten()
        if not ok:
            print("      ❌ Registrierung fehlgeschlagen.")
            print("      → SIP_SERVER / SIP_USER / SIP_PASSWORD in .env prüfen")
            sys.exit(1)
        print("      ✅ Bei FritzBox registriert")
    except Exception as e:
        print(f"      ❌ Fehler: {e}")
        sys.exit(1)

    # 3. Listen-Modus starten
    print("\n[3/3] Warte auf eingehende Anrufe...")
    try:
        ergebnis = skill_ausfuehren("listen", kernel=kernel)
        print(f"      {ergebnis}")
    except Exception as e:
        print(f"      ❌ Fehler beim Starten des Listen-Modus: {e}")
        telefon_stoppen()
        sys.exit(1)

    print()
    print("=" * 54)
    print("  Ilija ist jetzt erreichbar!")
    print("  Rufe jetzt von deinem Handy an.")
    print("  Beenden: Strg+C")
    print("=" * 54)
    print()

    # Sauber beenden mit Strg+C
    def _shutdown(sig, frame):
        print("\n\nBeende Telefon-Assistent...")
        try:
            telefon_stoppen()
        except Exception:
            pass
        print("Tschüss!")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Hauptloop — hält das Programm am Leben
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
