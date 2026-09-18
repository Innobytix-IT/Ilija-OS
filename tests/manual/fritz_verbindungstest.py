import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from skills.fritzbox_skill import telefon_starten, _phone
import skills.fritzbox_skill as fs

ok = telefon_starten()
print(f"\nErgebnis: {ok}")
if fs._phone:
    print("Log:")
    for msg in fs._phone._status_log:
        print(f"  {msg}")
