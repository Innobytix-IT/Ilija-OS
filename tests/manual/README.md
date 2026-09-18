# tests/manual/ – Manuelle FritzBox-Tests

Diese Skripte testen die echte FritzBox-Hardware.  
Sie sind NICHT Teil der automatischen pytest-Suite (laufen nicht bei `pytest tests/`).

## Voraussetzungen

- FritzBox muss erreichbar sein (Heimnetz oder VPN)
- `.env` muss korrekt befuellt sein (SIP_SERVER, SIP_USER, SIP_PASSWORD)
- Python-Paket `pyaudio` muss installiert sein

## Skripte

### fritz_sip_debug.py

Testet die vollstaendige SIP-Registrierung via TCP.

Ablauf:
1. Stellt TCP-Verbindung zu FritzBox:5060 her
2. Sendet REGISTER-Anfrage
3. Verarbeitet 401 Unauthorized + Digest-Auth
4. Gibt Erfolg (200 OK) oder Fehler aus

Ausfuehren:
```bash
source venv/bin/activate
python tests/manual/fritz_sip_debug.py
```

Erwartete Ausgabe bei Erfolg:
```
FB_IP=fritz.box  USER=deine_nummer  MY_IP=192.168.178.xx
PASS=**********

Verbinde zu fritz.box:5060 (TCP)...
Verbunden!

-> REGISTER senden ...
<- SIP/2.0 401 Unauthorized
   nonce=abc123...  realm=fritz.box
-> REGISTER mit Auth senden...
<- SIP/2.0 200 OK

SUCCESS! Registrierung erfolgreich.
```

Moegliche Fehler:
- `TIMEOUT` -> FritzBox nicht erreichbar (Netzwerk pruefen)
- `401 ohne nonce` -> SIP-Konto in FritzBox nicht eingerichtet
- `403 Forbidden` -> Falsches Passwort
- `PASS = LEER!` -> SIP_PASSWORD in .env nicht gesetzt

---

### fritz_verbindungstest.py

Einfacher TCP-Verbindungstest ohne SIP-Protokoll.

Ausfuehren:
```bash
python tests/manual/fritz_verbindungstest.py
```

Testet nur: Ist Port 5060 der FritzBox erreichbar?

---

## Hinweis

Diese Skripte benoetigen immer eine `.env`-Datei mit echten Zugangsdaten.  
Niemals Zugangsdaten direkt in den Skripten hardcoden.
