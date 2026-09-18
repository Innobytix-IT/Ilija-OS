# Ilija – Public Edition

> Persoenlicher KI-Assistent fuer Bueros und Kleinbetriebe:  
> Dokumentenverwaltung · Telefon-Assistent (FritzBox) · WhatsApp · Telegram · Web-Interface · Workflow Studio

---

## Features

| Modul | Beschreibung |
|-------|-------------|
| **DMS** | KI-gestuetztes Dokumentenmanagementsystem (PDF, DOCX, XLSX, Bilder, ...) |
| **Telefon-Assistent** | Nimmt Anrufe via FritzBox entgegen, bucht Termine, spricht mit Kunden |
| **Lokaler Kalender** | Webbasierter Kalender mit freien Slots, Termin-Buchung, Verfuegbarkeitszeiten |
| **Kalender-Sync** | Synchronisierung mit Google Kalender oder Outlook (Push nach Anruf, Pull konfigurierbar) |
| **Langzeitgedaechtnis** | ChromaDB, dauerhaft auch nach Neustart |
| **WhatsApp** | Ueberwacht Chats, vereinbart Termine, nimmt Nachrichten an |
| **Telegram** | Vollstaendige Fernsteuerung, Dokumente per App senden |
| **Web-Interface** | Browser-Chat mit Datei-Upload und DMS-Integration |
| **Workflow Studio** | Visuelle Automatisierung mit 28+ Node-Typen, ohne Programmierung |
| **Multi-Provider** | Claude → GPT → Gemini → Ollama (automatisches Fallback) |

---

## Schnellstart (Linux)

```bash
# 1. System vorbereiten
sudo apt update && sudo apt install -y git curl python3-pip python3-venv wget

# 2. Klonen
git clone https://github.com/Innobytix-IT/Ilija-AI-Agent-Public-Edition.git
cd Ilija-AI-Agent-Public-Edition/ilija_public_edition_v2.0

# 3. Installieren (interaktiv)
chmod +x install.sh
./install.sh
```

### Manuell (Linux)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env oeffnen und mindestens einen API-Key eintragen
python web_server.py
```

### English installer

```bash
chmod +x install_EN.sh
./install_EN.sh
```

---

## Windows – Setup & Control Center

Auf Windows gibt es die grafische Einrichtungsoberflaeche `Ilija_Start_App.py`:

```
python Ilija_Start_App.py
```

Die App enthaelt 9 Reiter fuer die komplette Konfiguration.  
Eine `.env`-Datei wird beim ersten Start automatisch aus `.env.example` erstellt – kein manuelles Kopieren noetig.

| Reiter | Inhalt |
|--------|--------|
| 1. Allgemein | Firmenname, Rolle, Beschreibung |
| 2. KI-Provider | API-Keys fuer Claude, GPT, Gemini, Ollama |
| 3. Gedaechtnis | ChromaDB-Einstellungen |
| 4. Kalender | Verfuegbarkeitszeiten, Terminlaenge, Kalender-Synchronisation |
| 5. DMS | Import- und Archiv-Pfade |
| 6. Server | Port, Debug-Modus |
| 7. FritzBox | SIP-Server, SIP-User, SIP-Passwort, RTP-Ports, Mikrofon-ID |
| 8. Eingangs-kanaele | Telegram, WhatsApp, E-Mail-Einstellungen |
| 9. Start | Starten, Status, Logs |

---

## Telefon-Assistent (FritzBox)

### Voraussetzungen

- FritzBox mit eingerichtetem IP-Telefonie-Konto
- Linux mit `portaudio19-dev`:  
  `sudo apt-get install -y portaudio19-dev`
- Python-Pakete: `pyaudio edge-tts openai-whisper`

### Einrichten

1. **FritzBox**: Telefonie → Eigene Rufnummern → IP-Telefonie-Konto anlegen  
2. **`.env`** eintragen (oder via GUI Reiter 7):

```env
SIP_SERVER=fritz.box
SIP_PORT=5060
SIP_USER=deine_interne_rufnummer
SIP_PASSWORD=dein_sip_passwort
SIP_MY_IP=                 # leer lassen = automatisch ermitteln
SIP_MIC_ID=0               # 0 = Standard-Mikrofon
SIP_RTP_LOW=10000
SIP_RTP_HIGH=10100
```

3. **Wissensbasis befuellen**: Eigene Dokumente in `data/public_info/` ablegen (siehe unten)

4. **Starten**: Via Start-Tab der GUI oder `python start_telefon.py`

### Funktionen

- Begruessung und natuerlicher Telefon-Dialog (kein Sprachauswahl-Menue)
- Freie Terminslots aus lokalem Kalender vorlesen
- Termin buchen (wird in `data/local_calendar_events.json` gespeichert)
- Eigene Termine abfragen (3-Faktor-Auth: Rufnummer + Vor- + Nachname)
- Termin stornieren
- Buchstabier-Modus fuer schwierige Namen (NATO-Alphabet)
- Allgemeine Fragen beantworten (Oeffnungszeiten, Adresse, ...)
- Kundenfragen aus eigenen Dokumenten beantworten (Wissensbasis)
- **Kalender-Synchronisation**: Neue Buchungen werden nach dem Anruf automatisch  
  an Google Kalender oder Outlook uebertragen (konfigurierbar in Setup & Control Center)

---

## Kalender-Synchronisation

Ilija kann neue Terminbuchungen automatisch an einen externen Kalender weitergeben.

| Funktion | Google Kalender | Outlook |
|----------|----------------|---------|
| Push (lokal → extern) | ✅ Automatisch nach Anruf | ✅ Via Chrome (Selenium) |
| Pull (extern → lokal) | ✅ Stündlich / 3× täglich / manuell | ⚠️ Nur manuell |

**Konfiguration**: Setup & Control Center → Reiter 4 → Kalender-Synchronisation

**Hinweis Outlook**: Microsoft stellt keine kostenlose Kalender-API bereit.  
Ilija nutzt daher Browser-Automatisierung (Selenium/Chrome). Das Chrome-Fenster  
oeffnet sich kurz nach dem Anruf – das ist normal und gewollt.

---

## Lokaler Kalender (Webansicht)

Erreichbar unter `http://localhost:5000/local_calendar`

- Monats-, Wochen- und Tagesansicht
- Termine anlegen, bearbeiten, loeschen
- Wiederkehrende Termine
- Farbkategorien
- **Verfuegbarkeit**: Oeffnungszeiten, Feiertage, Urlaub direkt im Browser bearbeiten
- **Notizen**: Telefon- und WhatsApp-Notizen per Klick abrufbar (kein Dateisystem-Suchen)

---

## Workflow Studio

Erreichbar ueber den Web-Chat → Schaltflaeche "Workflows"

Visueller No-Code-Editor fuer automatisierte Aufgaben mit 28+ Node-Typen:

| Kategorie | Nodes |
|-----------|-------|
| Trigger | Zeitplan, Webhook, manuell |
| KI | Chat, Chatfilter, Gedaechtnis |
| Aktionen | E-Mail, Telegram, WhatsApp, HTTP |
| Logik | Bedingung, Schalter, Schleife, Warten |
| Google | Kalender, Sheets, Docs, Drive, Forms, Gmail |
| Daten | Code, Variable setzen, Sub-Workflow |

Fertige Test-Workflows unter `data/workflows/test/` (33 Beispiele).

---

## Wissensbasis – `data/public_info/`

Ilija kann Kundenfragen automatisch aus eigenen Dokumenten beantworten –
zum Beispiel zu Preisen, Leistungen, Produkten oder der Adresse.

### So funktioniert es

Dateien die in `data/public_info/` liegen werden beim Start geladen.
Wenn ein Anrufer oder WhatsApp-Kontakt eine Frage stellt, sucht Ilija
keyword-basiert nach passenden Textabschnitten und antwortet darauf –
ohne dass der Nutzer merkt, dass Ilija gerade ein Dokument nachgeschlagen hat.

> **Ilija erfindet dabei nichts.** Er antwortet ausschliesslich auf Basis
> der gefundenen Passagen. Steht die Antwort nicht in den Dokumenten,
> sagt er das dem Anrufer ehrlich.

### Unterstuetzte Formate

| Format | Hinweis |
|--------|---------|
| `.txt` | Empfohlen, keine Abhaengigkeiten |
| `.md`  | Markdown-Formatierung wird als Text gelesen |
| `.pdf` | Benoetigt `pip install pymupdf` oder `pip install pdfplumber` |

### Beispiel-Struktur

```
data/public_info/
  leistungen.txt        # Beschreibung der angebotenen Dienstleistungen
  preise.txt            # Preisliste
  adresse_kontakt.txt   # Adresse, Telefon, E-Mail
  faq.txt               # Haeufige Fragen und Antworten
```

Dateien die mit `_` beginnen (z.B. `_hinweis.txt`) werden ignoriert
und koennen fuer interne Notizen genutzt werden.

---

## Starten (Linux)

```bash
source venv/bin/activate
```

| Interface | Befehl | URL |
|-----------|--------|-----|
| Web-Interface + Workflows | `python web_server.py` | http://localhost:5000 |
| DMS | `python web_server.py` | http://localhost:5000/dms |
| Lokaler Kalender | `python web_server.py` | http://localhost:5000/local_calendar |
| Telegram-Bot | `python telegram_bot.py` | Telegram-App |
| Web + Telegram | `python telegram_bot.py & python web_server.py` | – |
| Terminal-Modus | `python kernel.py` | Konsole |
| Telefon-Assistent | `python start_telefon.py` | – |

---

## DMS – Dokumentenverwaltung

Unterstuetzte Formate: PDF · DOCX · XLSX · PPTX · JPG · PNG · TXT · CSV · MD

Die KI analysiert jeden Dateiinhalt und archiviert automatisch:
```
data/dms/archiv/Kategorie/Unterkategorie/Jahr/Dateiname.pdf
```

- Duplikat-Erkennung via SHA-256
- Automatische Versionierung (_v2, _v3)
- Drag & Drop in die Web-GUI
- Per Telegram als Datei oder Foto senden
- Manuell in `data/dms/import/` kopieren

---

## Provider konfigurieren

| Provider | .env-Variable | Standard-Modell |
|----------|--------------|----------------|
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | claude-opus-4-6 |
| ChatGPT (OpenAI) | `OPENAI_API_KEY` | gpt-4o |
| Gemini (Google) | `GOOGLE_API_KEY` | gemini-2.5-flash |
| Ollama (lokal) | — | qwen2.5:7b |

Ilija waehlt automatisch den besten verfuegbaren Provider.

---

## Telegram-Bot

1. Telegram → @BotFather → `/newbot` → Token kopieren
2. `TELEGRAM_BOT_TOKEN=...` in `.env` eintragen (oder via GUI)
3. User-ID ueber @userinfobot → `TELEGRAM_ALLOWED_USERS=...`
4. `python telegram_bot.py`

**Verfuegbare Befehle:**

| Befehl | Funktion |
|--------|----------|
| `/start` | Bot starten und Willkommensnachricht |
| `/hilfe` | Alle Befehle anzeigen |
| `/status` | System-Status abfragen |
| `/kalender` | Heutige Termine anzeigen |
| `/termine` | Alle bevorstehenden Termine |
| `/dms_import` | Ausstehende DMS-Importe anzeigen |
| `/dms_sort` | DMS-Sortierung starten |
| `/dms_stats` | DMS-Statistiken |
| `/notizen` | Letzte Telefon- und WhatsApp-Notizen |
| `/workflows` | Aktive Workflows anzeigen |
| Datei/Foto senden | Automatisch in DMS-Import |
| Freitext | Direkter Chat mit Ilija |

---

## Projektstruktur

```
ilija_public_edition_v2.0/
|-- install.sh                  # Installationsskript (Linux, interaktiv, Deutsch)
|-- install_EN.sh               # Installation script (Linux, interactive, English)
|-- Ilija_Start_App.py          # Windows Setup & Control Center (GUI)
|-- web_server.py               # Flask Web-Interface + Kalender-Sync-Scheduler
|-- telegram_bot.py             # Telegram-Bot
|-- kernel.py                   # Zentraler Agent + Terminal-Modus
|-- customer_kernel.py          # Telefon-Assistent-Kernel
|-- phone_dialog.py             # Telefon-Dialog-Logik (Hybrid LLM + Python)
|-- phone_kernel.py             # Telefon-Basisklasse (Injection-Guard, TTS)
|-- start_telefon.py            # Einstiegspunkt Telefon-Assistent
|-- providers.py                # KI-Provider-Management (4 Provider, Auto-Fallback)
|-- skill_manager.py            # Skill-Verwaltung
|-- agent_state.py              # Zustandsverwaltung des Agenten
|-- model_registry.py           # Modell-Konfiguration
|-- workflow_routes.py          # Workflow Studio API + Engine
|-- local_calendar_routes.py    # Kalender-Web-API + Notizen + Verfuegbarkeit
|-- dms_routes.py               # DMS Web-API
|-- public_info_reader.py       # Wissensbasis-Loader
|-- log_cleanup.py              # Log-Rotation
|-- phone_config.json           # Konfiguration des Telefon-Assistenten
|-- models_config.json          # Modell-Definitionen
|-- skills/
|   |-- fritzbox_skill.py       # FritzBox SIP-Verbindung + Anruf-Loop
|   |-- kalender_sync_skill.py  # Kalender-Synchronisation (Google / Outlook)
|   |-- lokaler_kalender_skill.py  # Terminverwaltung (3-Faktor-Auth)
|   |-- verfuegbarkeit_skill.py # Oeffnungszeiten-Verwaltung
|   |-- gedaechtnis.py          # Langzeitgedaechtnis (ChromaDB)
|   |-- dms.py                  # Dokumentenverwaltungs-Skill
|   |-- basis_tools.py          # Datum, Notizen, Rechner, Uhrzeit
|   |-- email_skill.py          # E-Mail senden/empfangen (IMAP/SMTP)
|   |-- telegram_skill.py       # Telegram-Nachrichten senden
|   |-- whatsapp_autonomer_dialog.py  # WhatsApp via Chrome (Selenium)
|   |-- google_kalender.py      # Google Kalender API
|   |-- outlook_kalender.py     # Outlook via Browser-Automatisierung
|   |-- webseiten_inhalt_lesen.py  # Web-Recherche (DuckDuckGo / Google)
|   |-- browser_oeffnen.py      # Browser oeffnen
|   |-- datei_lesen.py          # Lokale Dateien lesen
|   |-- tv_programm.py          # TV-Programm abfragen
|   |-- wetter_offenburg_abfragen.py  # Wetter-Skill (anpassbar)
|   |-- net_fire_monitor_skill.py  # Netzwerk-Monitor
|   |-- openphoenix_erp.py      # OpenPhoenix ERP-Integration
|   |-- senderliste_tool.py     # TV-Senderliste
|   |-- muenze_werfen.py        # Muenze werfen
|   |-- wuerfeln.py             # Wuerfeln
|   `-- assets/
|       `-- senderliste.xml     # TV-Senderliste
|-- templates/
|   |-- index.html              # Web-Chat-Interface
|   |-- indexchat.html          # Chat-Unterseite
|   |-- local_calendar.html     # Kalender-Webansicht
|   `-- dms.html                # DMS Web-GUI
|-- data/
|   |-- local_calendar_events.json   # Lokaler Kalender (nicht committet)
|   |-- verfuegbarkeit.txt           # Verfuegbarkeitszeiten + Feiertage
|   |-- kalender_sync.json           # Sync-Konfiguration (nicht committet)
|   |-- public_info/                 # Infotexte fuer Kunden-Wissensbasis
|   |-- notizen/                     # Telefon-Notizen (nicht committet)
|   |-- workflows/
|   |   `-- test/                    # 33 Beispiel-Workflows
|   |-- dms/
|   |   |-- import/                  # Neue Dokumente hier ablegen
|   |   `-- archiv/                  # Archivierte Dokumente
|   |-- whatsapp/
|   |   `-- whatsapp_config.json     # WhatsApp-Konfiguration
|   |-- telegram/
|   |   `-- telegram_config.json     # Telegram-Konfiguration
|   `-- email/
|       `-- email_config.json        # E-Mail-Konfiguration
|-- tests/
|   |-- test_phone_dialog.py    # Tests: Datums-Parser, Dialog-Logik
|   |-- test_kalender.py        # Tests: Kalender-Skill
|   |-- test_workflow_engine.py # Tests: Workflow-Engine
|   |-- test_workflow_json_files.py  # Tests: alle 33 Beispiel-Workflows
|   |-- test_api.py             # Tests: Web-API
|   |-- test_basis_tools.py     # Tests: Basis-Skills
|   |-- test_dms_logik.py       # Tests: DMS
|   |-- test_sicherheit.py      # Tests: Sicherheit / Injection-Guard
|   |-- conftest.py             # Gemeinsame Fixtures
|   |-- helpers.py              # Test-Hilfsfunktionen
|   `-- manual/                 # Manuelle Tests (kein pytest, echte Hardware)
|       |-- fritz_sip_debug.py  # FritzBox SIP-Verbindungstest
|       `-- fritz_verbindungstest.py
|-- memory/                     # ChromaDB Langzeitgedaechtnis (nicht committet)
|-- .env.example                # Vorlagendatei fuer Konfiguration
|-- .gitignore
|-- requirements.txt
|-- pyproject.toml
|-- HANDBUCH.md                 # Vollstaendiges Benutzerhandbuch
`-- README.md
```

---

## Anforderungen

- **Python** 3.10+
- **Linux** Ubuntu/Debian (oder Windows mit `Ilija_Start_App.py`)
- **Telefon-Assistent**: `portaudio19-dev` (Linux), FritzBox mit IP-Telefonie
- **WhatsApp-Skill**: Google Chrome installiert
- **Kalender-Sync Outlook**: Google Chrome installiert
- Mindestens ein API-Key **oder** lokales Ollama-Modell

---

## Tests ausfuehren

```bash
source venv/bin/activate
pytest tests/ -v
```

Oder mit Coverage:

```bash
pytest tests/ --cov=. --cov-report=term-missing
```

Manuelle FritzBox-Tests (kein pytest, echte Hardware benoetigt):

```bash
python tests/manual/fritz_sip_debug.py
```

---

## Verwandte Projekte

| Version | Repository |
|---------|-----------|
| Ilija EVO (Entwickler-Version) | [ilija-AI-Agent](https://github.com/Innobytix-IT/ilija-AI-Agent) |
| Ilija Public Edition (dieses Repo) | ← du bist hier |

---

## Lizenz

GNU GPL v3 License – kostenlos verwenden, weitergeben und anpassen.

---

---

# Ilija – Public Edition (English)

> Personal AI assistant for offices and small businesses:  
> Document management · Phone assistant (FritzBox) · WhatsApp · Telegram · Web interface · Workflow Studio

---

## Features

| Module | Description |
|--------|-------------|
| **DMS** | AI-powered document management (PDF, DOCX, XLSX, images, ...) |
| **Phone assistant** | Answers calls via FritzBox, books appointments, talks to customers |
| **Local calendar** | Web-based calendar with free slots, appointment booking, availability times |
| **Calendar sync** | Sync with Google Calendar or Outlook (push after call, pull configurable) |
| **Long-term memory** | ChromaDB, persistent across restarts |
| **WhatsApp** | Monitors chats, schedules appointments, takes messages |
| **Telegram** | Full remote control, send documents via app |
| **Web interface** | Browser chat with file upload and DMS integration |
| **Workflow Studio** | Visual automation with 28+ node types, no coding required |
| **Multi-provider** | Claude → GPT → Gemini → Ollama (automatic fallback) |

---

## Quickstart (Linux)

```bash
# 1. Prepare system
sudo apt update && sudo apt install -y git curl python3-pip python3-venv wget

# 2. Clone
git clone https://github.com/Innobytix-IT/Ilija-AI-Agent-Public-Edition.git
cd Ilija-AI-Agent-Public-Edition/ilija_public_edition_v2.0

# 3. Install (interactive)
chmod +x install_EN.sh
./install_EN.sh
```

## Windows – Setup & Control Center

On Windows, use the graphical setup app `Ilija_Start_App.py`:

```
python Ilija_Start_App.py
```

The app has 9 tabs for complete configuration.  
A `.env` file is created automatically on first launch – no manual copying required.

---

## Phone Assistant (FritzBox)

### Prerequisites

- FritzBox with IP telephony account configured
- Linux: `sudo apt-get install -y portaudio19-dev`
- Python packages: `pyaudio edge-tts openai-whisper`

### Setup

1. **FritzBox**: Telephony → Own numbers → Add IP telephony account
2. **`.env`** (or use GUI tab 7):

```env
SIP_SERVER=fritz.box
SIP_PORT=5060
SIP_USER=your_internal_number
SIP_PASSWORD=your_sip_password
SIP_MY_IP=                 # leave empty = auto-detect
SIP_MIC_ID=0               # 0 = default microphone
SIP_RTP_LOW=10000
SIP_RTP_HIGH=10100
```

### Features

- Natural phone dialogue (no voice menu / IVR)
- Reads available appointment slots from local calendar
- Books appointments (stored in `data/local_calendar_events.json`)
- Lets callers query their own appointments (3-factor auth: phone number + first + last name)
- Cancel appointments
- Spelling mode for difficult names (NATO alphabet)
- Answers general questions (opening hours, address, ...)
- Answers customer questions from your own documents (knowledge base)
- **Calendar sync**: New bookings are automatically pushed to Google Calendar or Outlook  
  after each call (configurable in Setup & Control Center)

---

## Calendar Synchronisation

| Function | Google Calendar | Outlook |
|----------|----------------|---------|
| Push (local → external) | ✅ Automatic after call | ✅ Via Chrome (Selenium) |
| Pull (external → local) | ✅ Hourly / 3× daily / manual | ⚠️ Manual only |

**Note on Outlook**: Microsoft does not provide a free Calendar API.  
Ilija uses browser automation (Selenium/Chrome). The Chrome window opens briefly  
after a call – this is expected behaviour.

---

## Local Calendar (Web view)

Available at `http://localhost:5000/local_calendar`

- Month, week and day views
- Create, edit and delete appointments
- Recurring appointments
- Colour categories
- **Availability**: Edit opening hours, holidays and vacation directly in the browser
- **Notes**: Phone and WhatsApp notes accessible with one click

---

## Workflow Studio

Accessible via the web chat → "Workflows" button

Visual no-code editor for automated tasks with 28+ node types:

| Category | Nodes |
|----------|-------|
| Trigger | Schedule, Webhook, Manual |
| AI | Chat, Chat filter, Memory |
| Actions | Email, Telegram, WhatsApp, HTTP |
| Logic | Condition, Switch, Loop, Wait |
| Google | Calendar, Sheets, Docs, Drive, Forms, Gmail |
| Data | Code, Set variable, Sub-workflow |

Ready-made example workflows in `data/workflows/test/` (33 examples).

---

## Knowledge Base – `data/public_info/`

Ilija can automatically answer customer questions from your own documents –
for example about prices, services, products or your address.

> **Ilija never makes things up.** It only answers based on the passages
> found in your documents. If the answer is not in the documents,
> Ilija will say so honestly.

### Supported formats

| Format | Note |
|--------|------|
| `.txt` | Recommended, no dependencies |
| `.md`  | Markdown formatting is read as plain text |
| `.pdf` | Requires `pip install pymupdf` or `pip install pdfplumber` |

### Example structure

```
data/public_info/
  services.txt          # Description of offered services
  pricing.txt           # Price list
  contact_address.txt   # Address, phone, email
  faq.txt               # Frequently asked questions
```

Files starting with `_` (e.g. `_notes.txt`) are ignored and can be used for internal notes.

---

## Telegram Bot

1. Telegram → @BotFather → `/newbot` → copy token
2. `TELEGRAM_BOT_TOKEN=...` in `.env` (or via GUI)
3. Get your user ID from @userinfobot → `TELEGRAM_ALLOWED_USERS=...`
4. `python telegram_bot.py`

**Available commands:**

| Command | Function |
|---------|----------|
| `/start` | Start the bot |
| `/hilfe` | Show all commands |
| `/status` | System status |
| `/kalender` | Today's appointments |
| `/termine` | All upcoming appointments |
| `/dms_import` | Pending DMS imports |
| `/dms_sort` | Start DMS sorting |
| `/dms_stats` | DMS statistics |
| `/notizen` | Latest phone and WhatsApp notes |
| `/workflows` | Active workflows |
| Send file/photo | Automatically imported into DMS |
| Free text | Direct chat with Ilija |

---

## Requirements

- **Python** 3.10+
- **Linux** Ubuntu/Debian (or Windows with `Ilija_Start_App.py`)
- **Phone assistant**: `portaudio19-dev` (Linux), FritzBox with IP telephony
- **WhatsApp skill**: Google Chrome installed
- **Outlook calendar sync**: Google Chrome installed
- At least one API key **or** local Ollama model

---

## Run tests

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## License

GNU GPL v3 License – free to use, share and modify.
