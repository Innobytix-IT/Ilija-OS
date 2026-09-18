# Ilija Public Edition – Benutzerhandbuch

> **Version:** Public Edition  
> **Sprache:** Deutsch  
> Dieses Handbuch erklärt alle Funktionen von Ilija — vom ersten Start bis zur täglichen Nutzung.

---

## Inhaltsverzeichnis

1. [Schnellstart](#1-schnellstart)
2. [Ilija Chat](#2-ilija-chat)
3. [Workflow Studio](#3-workflow-studio)
4. [Lokaler Kalender](#4-lokaler-kalender)
5. [Kalender-Synchronisation](#5-kalender-synchronisation)
6. [Telegram-Bot](#6-telegram-bot)
7. [Telefon-Assistent (FritzBox)](#7-telefon-assistent-fritzbox)
8. [WhatsApp-Assistent](#8-whatsapp-assistent)
9. [Dokumentenverwaltung (DMS)](#9-dokumentenverwaltung-dms)
10. [Google-Dienste](#10-google-dienste)
11. [E-Mail](#11-e-mail)
12. [Notizen](#12-notizen)
13. [Alle verfügbaren Skills](#13-alle-verfuegbaren-skills)
14. [Wissensbasis (data/public_info)](#14-wissensbasis-datapublic_info)
15. [Langzeitgedächtnis](#15-langzeitgedaechtnis)

---

## 1. Schnellstart

### Voraussetzungen
- Python 3.10 oder neuer
- Mindestens ein KI-API-Schlüssel (Anthropic, OpenAI, Google Gemini) **oder** ein lokales Ollama-Modell

### Starten

**Mit dem Setup & Control Center (empfohlen):**
```
python Ilija_Start_App.py
```
Hier alle Zugangsdaten eintragen (Tab 1–8) und im Tab „9. Start" die gewünschten Module starten.

**Direkt im Terminal:**
```bash
# Web-Server (Workflow Studio + Chat + Kalender)
python web_server.py

# Nur Terminal-Chat
python kernel.py

# Telegram-Bot
python telegram_bot.py

# Telefon-Assistent
python start_telefon.py
```

### Erreichbarkeit im Browser
| Modul | Adresse |
|---|---|
| Workflow Studio | `http://localhost:5000` |
| Chat | `http://localhost:5000/chat` |
| Kalender | `http://localhost:5000/local_calendar` |
| DMS | `http://localhost:5000/dms` |

---

## 2. Ilija Chat

Der Chat ist die direkteste Art mit Ilija zu sprechen. Ilija versteht natürliche Sprache auf Deutsch und Englisch und kann alle verfügbaren Skills selbstständig aufrufen.

### Öffnen
- Browser: `http://localhost:5000/chat`
- Terminal: `python kernel.py`
- Telegram: Nachrichten direkt an den Bot schreiben

### Beispiel-Anfragen
```
"Was ist heute für ein Tag?"
"Rechne 1250 * 1.19"
"Trag einen Termin ein: Montag 14 Uhr, Beratung mit Herrn Müller"
"Such im Internet nach dem Wetter in Berlin"
"Zeig mir meine Termine für nächste Woche"
"Speicher die Notiz: Strom ablesen nicht vergessen"
"Was steht in meinen WhatsApp-Nachrichten?"
```

Ilija entscheidet selbst welcher Skill aufgerufen wird — du musst keine Befehle kennen.

### Verfügbare Slash-Befehle im Web-Chat
| Befehl | Funktion |
|---|---|
| `/clear` | Chat-Verlauf löschen |
| `/reload` | Skills neu laden (nach Änderungen) |
| `/status` | System-Status anzeigen |
| `/switch auto` | KI-Anbieter automatisch wählen |
| `/switch claude` | Auf Anthropic Claude wechseln |
| `/switch gemini` | Auf Google Gemini wechseln |
| `/switch openai` | Auf OpenAI ChatGPT wechseln |
| `/switch ollama` | Auf lokales Ollama-Modell wechseln |

---

## 3. Workflow Studio

Das Workflow Studio ist Ilijas visuelle Automatisierungs-Umgebung — ähnlich wie n8n, aber direkt in Ilija integriert. Workflows werden als Knotennetz (Graph) aufgebaut und können automatisch ausgelöst werden.

### Öffnen
Browser: `http://localhost:5000`

### Grundprinzip
Ein Workflow besteht aus **Nodes (Knoten)** die miteinander verbunden sind. Daten fließen von links nach rechts. Jeder Node verarbeitet die Eingabe und gibt ein Ergebnis weiter.

```
[Trigger] → [Skill] → [Bedingung] → [E-Mail senden]
                              ↓
                        [Telegram senden]
```

### Workflow erstellen
1. Klick auf **„＋ Neuer Workflow"**
2. Knoten per Rechtsklick oder aus der Seitenleiste hinzufügen
3. Knoten mit der Maus verbinden (Ausgang → Eingang)
4. Workflow mit **▶ Ausführen** testen oder **Speichern**

---

### Verfügbare Node-Typen

#### Auslöser (Trigger)

| Node | Beschreibung |
|---|---|
| **trigger** | Manueller Start — Workflow wird nur per Klick auf „Ausführen" gestartet |
| **schedule_trigger** | Zeitgesteuerter Start — z.B. täglich um 08:00, stündlich, wöchentlich |
| **webhook** | HTTP-Webhook — Workflow startet wenn eine externe Anfrage eingeht |

**Schedule Trigger konfigurieren:**
- `cron`: Cron-Ausdruck, z.B. `0 8 * * 1-5` (Mo–Fr um 8 Uhr)
- `interval_minutes`: Einfaches Intervall in Minuten (z.B. `60` = stündlich)

---

#### KI & Chat

| Node | Beschreibung |
|---|---|
| **chat** | Sendet eine Nachricht an Ilija und erhält eine Antwort. Ilija kann dabei alle Skills nutzen. |
| **chatfilter** | Wertet Ilijas Antwort aus und leitet basierend auf dem Inhalt weiter (Ja/Nein, Kategorie) |
| **skill** | Ruft direkt einen einzelnen Skill auf (z.B. `lokaler_kalender_lesen`) mit festen Parametern |

**Chat-Node Felder:**
- `prompt`: Die Nachricht an Ilija
- `system`: Optionaler System-Prompt (Rolle/Kontext)
- `memory_window` / `memory_summary`: Gesprächsgedächtnis aktivieren

**Skill-Node Felder:**
- `skill`: Name der Funktion (z.B. `google_kalender_lesen`)
- `params`: Parameter als JSON-Objekt

---

#### Logik & Steuerung

| Node | Beschreibung |
|---|---|
| **condition** | Verzweigung: prüft eine Bedingung und leitet zu „Ja"- oder „Nein"-Pfad weiter |
| **switch** | Mehrfachverzweigung: verteilt auf verschiedene Pfade basierend auf einem Wert |
| **loop** | Schleife: führt verbundene Knoten für jedes Element einer Liste aus |
| **wait** | Pause: wartet eine konfigurierbare Zeit bevor es weitergeht |
| **set** | Variablen setzen: speichert Werte für spätere Nodes |
| **code** | Python-Code direkt im Workflow ausführen |
| **sub_workflow** | Ruft einen anderen gespeicherten Workflow als Unterroutine auf |
| **error_handler** | Fängt Fehler ab und führt einen Alternativpfad aus |
| **note** | Kommentar-Zettel (nur zur Dokumentation, keine Funktion) |

**Condition-Node Beispiele:**
```
{{ output }} enthält "Termin"
{{ output }} == "Ja"
{{ anzahl }} > 5
```

---

#### Kommunikation

| Node | Beschreibung |
|---|---|
| **telegram** | Sendet eine Nachricht über den Telegram-Bot |
| **email** | Sendet eine E-Mail über den konfigurierten E-Mail-Provider |
| **whatsapp** | Sendet eine WhatsApp-Nachricht über die WhatsApp Business API |
| **http** | HTTP-Request an eine externe URL (GET/POST/PUT/DELETE) |
| **rss** | Liest RSS-Feeds und gibt Artikel als Liste weiter |

---

#### Google-Dienste

| Node | Beschreibung |
|---|---|
| **google_kalender** | Google Kalender lesen, Termine eintragen oder löschen |
| **google_sheets** | Google Sheets lesen oder Zeilen einfügen |
| **google_docs** | Google Docs Inhalt lesen |
| **google_drive** | Google Drive Dateien auflisten oder hochladen |
| **google_forms** | Google Forms Antworten lesen |
| **gmail** | Gmail-Posteingang lesen oder E-Mails senden |

---

#### Gedächtnis

| Node | Beschreibung |
|---|---|
| **memory_window** | Gleitendes Fenster: speichert die letzten N Nachrichten als Kontext |
| **memory_summary** | Zusammenfassungs-Gedächtnis: komprimiert ältere Nachrichten automatisch |

---

### Daten zwischen Nodes übergeben

Jeder Node gibt sein Ergebnis als `{{ output }}` weiter. Auf frühere Nodes kann per `{{ node_name.output }}` zugegriffen werden.

**Beispiele:**
```
{{ output }}              → Ergebnis des direkten Vorgängers
{{ skill_1.output }}      → Ergebnis des Nodes namens "skill_1"
{{ trigger.data }}        → Webhook-Eingabe-Daten
```

### Workflow-Beispiel: Tägliche Zusammenfassung per Telegram
```
[schedule_trigger: täglich 08:00]
    ↓
[skill: lokaler_kalender_lesen]
    ↓
[chat: "Fasse die heutigen Termine kurz zusammen: {{ output }}"]
    ↓
[telegram: "{{ output }}"]
```

---

## 4. Lokaler Kalender

Der lokale Kalender ist Ilijas internes Terminsystem. Alle Buchungen aus Telefonaten und WhatsApp landen hier. Die Daten werden in `data/local_calendar_events.json` gespeichert.

### Öffnen
Browser: `http://localhost:5000/local_calendar`

### Ansichten
Oben rechts im Kalender umschalten zwischen:
- **Monat** — Gesamtübersicht
- **Woche** — Detailansicht mit Uhrzeiten
- **Tag** — Stundengenaue Ansicht
- **Liste** — Listenansicht aller Termine

### Termin erstellen
1. Klick auf **„＋ Neuer Termin"** (Sidebar) oder direkt auf eine Uhrzeit im Kalender
2. Felder ausfüllen: Titel, Datum, Uhrzeit von/bis, Kategorie, Beschreibung, Kontaktinfos
3. Serientermin: Häufigkeit wählen (täglich, wöchentlich, monatlich, jährlich)
4. Klick auf **„💾 Speichern"**

### Termin bearbeiten / löschen
- Klick auf einen Termin → Modal öffnet sich → Felder ändern → **Speichern**
- Zum Löschen: **🗑 Löschen** im Modal

### Termin-Kategorien
| Farbe | Kategorie | Bedeutung |
|---|---|---|
| 🟩 Grün | Standard | Normale Termine (Buchungen von Kunden) |
| 🟠 Orange | Wichtig | Dringende Termine |
| 🟦 Blau | Privat | Persönliche Termine (nicht für Kunden sichtbar) |
| ⬛ Grau | Blocker | Sperrt Zeitfenster für automatische KI-Buchungen |

**Wichtig:** Blocker verhindern dass Ilija in dieser Zeit Termine bucht. Urlaub, Besprechungen oder private Termine als Blocker eintragen.

### Verfügbarkeit & Öffnungszeiten
Klick auf **„📋 Verfügbarkeit"** in der Sidebar:
- Öffnungszeiten pro Wochentag eintragen (z.B. `[MO] 08:30 - 17:00`)
- Feiertage: `[FEIERTAG] 2026-12-25 Weihnachten`
- Urlaub: `[URLAUB] 2026-08-01 - 2026-08-14 Sommerurlaub`
- Hinweis für Kunden: `[HINWEIS] Bitte 24h im Voraus buchen`
- Slot-Dauer: `[SLOT_DAUER] 30` (Terminlänge in Minuten)

Änderungen gelten sofort für alle KI-Kanäle (Telefon, WhatsApp).

### Notizen anzeigen
Klick auf **„📝 Notizen"** in der Sidebar — öffnet alle hinterlassenen Nachrichten:
- **Links:** Telefon-Notizen (`data/notizen/telefon_notizen.txt`)
- **Rechts:** WhatsApp-Nachrichten (`data/whatsapp_log.txt`)

---

## 5. Kalender-Synchronisation

Die Synchronisation verbindet den lokalen Kalender mit einem externen Anbieter (Google oder Outlook). Der lokale Kalender bleibt dabei immer die primäre Quelle — externe Kalender werden ergänzt, nicht ersetzt.

### Einrichten
Setup & Control Center → Tab **„8. Eingangskanäle"** → Abschnitt **„📅 Kalender-Synchronisation"**

### Einstellungen

| Einstellung | Optionen | Bedeutung |
|---|---|---|
| Provider | `keiner`, `google`, `outlook` | Welcher externe Kalender synchronisiert wird |
| Pull-Intervall | `manuell`, `3x_taeglich`, `stuendlich` | Wie oft externe Termine in den lokalen Kalender importiert werden |
| Auto-Push | Checkbox | Neue Buchungen nach jedem Anruf automatisch zum Provider senden |

### Push (Lokal → Provider)
Nach jeder neuen Buchung durch den Telefon-Assistenten wird der Termin automatisch im Hintergrund zum Provider übertragen — **nach dem Gespräch**, nicht während (um CPU/RAM während des Anrufs zu schonen).

### Pull (Provider → Lokal)
Externe Termine werden in den lokalen Kalender importiert. Duplikate werden automatisch erkannt und übersprungen.

### Besonderheit Outlook
Microsoft bietet keine kostenfreie Kalender-API. Ilija steuert Outlook daher über Browser-Automatisierung (Selenium/Chrome):
- **Push funktioniert** — ein Chrome-Fenster öffnet sich kurz nach dem Anruf und trägt den Termin ein
- **Pull ist nicht möglich** — Selenium liest nur den Tagestext, keine strukturierten Rohdaten
- **Voraussetzung:** Einmalig `outlook_login_einrichten()` im Chat ausführen (öffnet Chrome zum Anmelden)

### Google Kalender einrichten
1. Unter `data/google_kalender/credentials.json` die OAuth-Datei aus der Google Cloud Console ablegen
2. Beim ersten Aufruf öffnet sich einmalig ein Browser-Fenster → Google-Konto autorisieren
3. Das Token wird automatisch in `data/google_kalender/token.json` gespeichert

---

## 6. Telegram-Bot

Der Telegram-Bot ist Ilijas mobile Schnittstelle. Über Telegram kann Ilija mit natürlicher Sprache gesteuert werden, Dokumente empfangen, und sogar den Telefon-Assistenten bedienen.

### Einrichten
1. Bei [@BotFather](https://t.me/BotFather) einen neuen Bot anlegen → `/newbot`
2. Token kopieren → in `.env` als `TELEGRAM_BOT_TOKEN=...` eintragen
3. Deine Telegram User-ID ermitteln (bei [@userinfobot](https://t.me/userinfobot)) → `TELEGRAM_ALLOWED_USERS=...`
4. Bot starten: `python telegram_bot.py` oder über Setup & Control Center

### Befehle

#### Allgemein
| Befehl | Funktion |
|---|---|
| `/start` | Begrüßung und Übersicht aller Funktionen |
| `/help` | Vollständige Befehlsliste |
| `/status` | Aktuellen System-Status anzeigen |
| `/clear` | Chat-Verlauf zurücksetzen |
| `/reload` | Skills neu laden (nach Konfigurationsänderungen) |
| `/switch` | KI-Anbieter wechseln (auto / claude / gemini / openai / ollama) |

#### Sprache
| Befehl | Funktion |
|---|---|
| `/voice` | Sprach-Modus umschalten — Ilija antwortet als Sprachnachricht (OGG/Opus) |

Im Sprach-Modus sendet Ilija alle Antworten als Audiodatei (Google TTS, Deutsch, 1.2× Geschwindigkeit).

#### Dokumentenverwaltung (DMS)
| Befehl | Funktion |
|---|---|
| `/dms_import` | Dateien im Import-Ordner anzeigen |
| `/dms_sort` | Alle Dateien im Import-Ordner per KI einsortieren |
| `/dms_stats` | Archiv-Statistiken (Anzahl, Größe, Kategorien) |

#### Telefonie (FritzBox)
| Befehl | Funktion |
|---|---|
| `/listen` | Anrufbeantworter-Modus starten — Ilija nimmt alle eingehenden Anrufe an |
| `/call <Nummer>` | Ausgehenden Anruf starten (Ilija führt das Gespräch als KI) |
| `/hangup` | Laufendes Gespräch beenden |
| `/phone_status` | Aktuellen Telefonstatus anzeigen |

### Medien und Dokumente
- **Sprachnachrichten:** Werden automatisch transkribiert (Whisper lokal oder OpenAI) und als Text an Ilija weitergegeben
- **Dokumente (PDF, Word, etc.):** Werden automatisch in `data/dms/import/` gespeichert und können mit `/dms_sort` einsortiert werden
- **Fotos:** Werden als Scan gespeichert (`scan_[id].jpg`)

### Sicherheit
Nur die in `TELEGRAM_ALLOWED_USERS` eingetragenen User-IDs können den Bot nutzen. Alle anderen werden ignoriert.

---

## 7. Telefon-Assistent (FritzBox)

Der Telefon-Assistent nimmt eingehende Anrufe automatisch entgegen und führt selbstständig Gespräche — Terminbuchungen, Öffnungszeiten, Nachrichten entgegennehmen.

### Voraussetzungen
- Fritz!Box im Heimnetz
- Ein angelegtes IP-Telefon in der Fritz!Box (Telefonie → Telefoniegeräte → Neues Gerät → IP-Telefon)
- SIP-Zugangsdaten in `.env` eingetragen

### Einrichten
```env
SIP_SERVER=fritz.box        # oder IP: 192.168.178.1
SIP_PORT=5060
SIP_USER=ilija              # Benutzername des IP-Telefons in der Fritz!Box
SIP_PASSWORD=deinpasswort
SIP_MY_IP=                  # leer lassen = automatisch ermitteln
SIP_MIC_ID=0                # Mikrofon-ID (0 = Standard)
WHISPER_MODEL=base          # tiny | base | small | medium
```

### Starten
- Über Setup & Control Center: Tab „9. Start" → **„▶ Telefon-Assistent starten"**
- Direkt: `python start_telefon.py`
- Über Telegram: `/listen`

### Was Ilija am Telefon kann
- **Begrüßung** — spricht die konfigurierte Begrüßung
- **Öffnungszeiten nennen** — liest aus `data/verfuegbarkeit.txt`
- **Termine buchen** — fragt Datum, Uhrzeit, Namen und bestätigt
- **Termine abfragen** — Anrufer kann eigene Termine hören (3-Faktor-Authentifizierung: Rufnummer + Vor- + Nachname)
- **Termine stornieren** — sicher über dieselbe 3-Faktor-Authentifizierung
- **Nachrichten entgegennehmen** — speichert in `data/notizen/telefon_notizen.txt`
- **Wissensbasis nutzen** — beantwortet Fragen aus `data/public_info/`
- **Buchstabier-Modus** — falls ein Name nicht verstanden wird, fragt Ilija buchstabenweise nach

### Konfiguration (phone_config.json)
Setup & Control Center → Tab **„8. Eingangskanäle"** → Telefon:
- **Firmenname:** Wie das Unternehmen heißt
- **Begrüßung:** Was Ilija beim Abheben sagt
- **Angebotene Dienste:** Was Ilija dem Anrufer anbietet (eine Zeile pro Dienst)
- **Rolle:** Wie Ilija sich verhält
- **Verabschiedung:** Abschlussformel
- **Wissensbasis-Ordner:** Pfad zu öffentlichen Infodokumenten

### Buchungs-Ablauf (vereinfacht)
```
Anrufer ruft an
    → Ilija hebt ab und begrüßt
    → Anrufer nennt Anliegen
    → Ilija erkennt: Termin buchen
    → Fragt: Vorname? Nachname?
    → Fragt: Datum? Uhrzeit?
    → Bestätigt: "Mittwoch, 14. Mai um 10 Uhr — ist das korrekt?"
    → Anrufer sagt "Ja"
    → Termin wird in Kalender eingetragen
    → Push an externen Kalender (falls konfiguriert)
    → Verabschiedung
```

### Qualität der Spracherkennung verbessern
| Whisper-Modell | Geschwindigkeit | Qualität | RAM-Bedarf |
|---|---|---|---|
| `tiny` | sehr schnell | niedrig | ~400 MB |
| `base` | schnell | gut (Standard) | ~700 MB |
| `small` | mittel | besser | ~1,5 GB |
| `medium` | langsam | sehr gut | ~5 GB |

---

## 8. WhatsApp-Assistent

Der WhatsApp-Assistent überwacht WhatsApp-Chats und antwortet automatisch. Er nutzt WhatsApp Web über Browser-Automatisierung (Selenium/Chrome) — es wird kein Business-Account benötigt.

> **Hinweis:** Diese Implementierung nutzt WhatsApp Web über den privaten Account (Selenium). Eine offizielle WhatsApp Business API ist in dieser Version nicht enthalten. Für den Einsatz im geschäftlichen Umfeld empfehlen wir die Nutzung über einen persönlichen WhatsApp-Account der ausschließlich für Ilija eingerichtet wird.

### Voraussetzungen
- Google Chrome installiert
- Ein WhatsApp-Account (Smartphone + WhatsApp-App zum Scannen des QR-Codes)
- Bei der ersten Nutzung: QR-Code in WhatsApp Web scannen

### Starten (über Chat / Telegram)
```
whatsapp_autonomer_dialog(modus="alle")
```
Oder in natürlicher Sprache: *„Starte WhatsApp für alle Chats"*

### Modi

| Modus | Funktion |
|---|---|
| `alle` | Überwacht alle Chats und antwortet auf neue Nachrichten |
| `kontakt` | Überwacht nur einen bestimmten Kontakt |
| `anrufbeantworter` | Nimmt Nachrichten entgegen und meldet sich als Assistent |

### Konfiguration
Setup & Control Center → Tab **„8. Eingangskanäle"** → WhatsApp:
- **Firmenname:** Wird in der KI-Rolle verwendet
- **Begrüßung:** Erste Nachricht an neue Kontakte
- **Angebotene Dienste:** Was Ilija in WhatsApp anbietet
- **Rolle:** Wie Ilija sich verhält
- **Wissensbasis-Ordner:** Pfad zu öffentlichen Infodokumenten

### Was Ilija in WhatsApp kann
- Allgemeine Fragen beantworten
- Öffnungszeiten nennen
- Termine buchen, abfragen und stornieren
- Nachrichten entgegennehmen
- Aus der Wissensbasis antworten (Produktinfos, FAQ, Preise)
- Sprachnachrichten transkribieren und beantworten

### Logs und Nachrichten
- Alle Gespräche: `data/whatsapp_log.txt`
- Hinterlassene Nachrichten: `data/whatsapp_nachrichten.txt`
- Beide Dateien sind im Kalender unter **„📝 Notizen"** erreichbar

### Wichtige Befehle (im Ilija Chat)
| Befehl | Funktion |
|---|---|
| `whatsapp_listener_status()` | Status des laufenden Listeners prüfen |
| `whatsapp_listener_stoppen()` | Listener beenden |
| `whatsapp_log_lesen()` | Gesprächslog lesen |
| `whatsapp_nachrichten_lesen()` | Hinterlassene Nachrichten lesen |
| `whatsapp_nachricht_senden("Kontakt", "Text")` | Nachricht senden |

### Sicherheit
- Jeder Kontakt kann nur seine eigenen Termine sehen und verwalten
- System-Prompts und interne Befehle werden aus Nutzernachrichten herausgefiltert
- Keine Termintitel oder Namen anderer Kunden werden preisgegeben

---

## 9. Dokumentenverwaltung (DMS)

Das DMS archiviert Dokumente automatisch: KI liest den Inhalt, benennt die Datei sinnvoll um und sortiert sie in Kategorien ein.

### Öffnen
- Browser: `http://localhost:5000/dms`
- Telegram: `/dms_import`, `/dms_sort`, `/dms_stats`

### Dokument einsortieren
1. Datei in den **Import-Ordner** legen (Standard: `data/dms/import/`)
2. Im DMS auf **„Dokumente einsortieren"** klicken oder `/dms_sort` in Telegram schreiben
3. KI analysiert, benennt um und archiviert das Dokument

### Struktur des Archivs
```
data/dms/archiv/
├── Arbeit/
│   ├── Vertraege/
│   └── Rechnungen/
├── Privat/
│   ├── Versicherungen/
│   └── Allgemein/
└── Sonstiges/
```

Kategorien und Unterordner werden von der KI automatisch vergeben. Eigene Kategorien können im Chat definiert werden.

### DMS-Befehle (im Chat)
| Funktion | Beschreibung |
|---|---|
| `dms_import_scan()` | Zeigt alle Dateien im Import-Ordner |
| `dms_einsortieren()` | Alle Import-Dateien per KI archivieren |
| `dms_suchen("Rechnung")` | Archiv nach Begriff durchsuchen |
| `dms_archiv_uebersicht()` | Kategorien und Anzahl anzeigen |
| `dms_archiv_baum()` | Vollständige Ordnerstruktur anzeigen |
| `dms_stats()` | Statistiken (Anzahl, Größe, etc.) |
| `dms_verschieben("Datei", "Kategorie", "Sub")` | Datei verschieben |
| `dms_loeschen("Datei")` | Datei löschen |
| `dms_pfad_setzen(archiv, import)` | Pfade konfigurieren |

### Passwortschutz
Für das DMS kann ein Passwort aktiviert werden. Einrichten im DMS-Interface oder über Setup & Control Center → Tab „5. DMS".

---

## 10. Google-Dienste

Ilija kann verschiedene Google-Dienste nutzen. Alle benötigen eine einmalige OAuth-Autorisierung.

### Einrichten (einmalig)
1. [Google Cloud Console](https://console.cloud.google.com/) aufrufen
2. Neues Projekt erstellen
3. Gewünschte APIs aktivieren (Calendar, Sheets, Drive, Docs, Gmail, Forms)
4. OAuth 2.0 Anmeldedaten erstellen → JSON herunterladen
5. Datei ablegen unter `data/google_kalender/credentials.json` (gilt für alle Google-Skills)
6. Beim ersten Aufruf: Browser öffnet sich einmalig zum Autorisieren → Token wird gespeichert

### Google Kalender
| Skill | Beschreibung |
|---|---|
| `google_kalender_lesen(datum)` | Termine eines Tages lesen (Format: `TT.MM.JJJJ`) |
| `google_freie_slots_finden(datum, dauer_minuten)` | Freie Zeitfenster finden |
| `google_termin_eintragen(titel, datum, von, bis, kontakt, beschreibung)` | Termin eintragen |
| `google_termin_loeschen(titel, datum)` | Termin löschen |

### Outlook Kalender
| Skill | Beschreibung |
|---|---|
| `outlook_login_einrichten()` | Einmalige Einrichtung — öffnet Chrome zum Anmelden |
| `outlook_kalender_lesen()` | Heutige Termine lesen (Selenium) |
| `outlook_freie_slots_finden(datum)` | Freie Slots suchen |
| `outlook_termin_eintragen(titel, datum, von, bis)` | Termin eintragen (Chrome öffnet sich kurz) |
| `outlook_termin_loeschen(titel, datum)` | Termin löschen |

### Weitere Google-Skills (im Workflow Studio)
Diese Skills stehen als Workflow-Nodes zur Verfügung:
- **Google Sheets:** Zeilen lesen, einfügen, aktualisieren
- **Google Docs:** Dokument-Inhalt lesen
- **Google Drive:** Dateien auflisten, hochladen, herunterladen
- **Google Forms:** Formular-Antworten lesen
- **Gmail:** E-Mails lesen und senden

---

## 11. E-Mail

### Einrichten
Setup & Control Center → Tab **„4. E-Mail"** oder im Chat:
```
email_konfigurieren(provider="gmail", email_adresse="deine@gmail.com", passwort="app-passwort")
```

**Für Gmail:** App-Passwort verwenden (Google-Konto → Sicherheit → App-Passwörter)

### E-Mail-Befehle
| Skill | Beschreibung |
|---|---|
| `emails_lesen(anzahl)` | Neueste E-Mails aus dem Posteingang lesen |
| `email_senden(an, betreff, text)` | E-Mail senden |
| `email_beantworten(message_id, text)` | E-Mail beantworten |
| `email_verbinden()` | Verbindung testen |
| `email_status()` | Aktuelle Konfiguration anzeigen |

---

## 12. Notizen

Ilija speichert Notizen in Textdateien. Es gibt mehrere Arten:

### Allgemeine Notizen (Ilija-Chat)
```
"Speichere die Notiz: Strom ablesen am Monatsende"
"Zeig mir meine Notizen"
```
Gespeichert in: `data/notizen/notizen.txt`

### Telefon-Notizen
Wenn ein Anrufer eine Nachricht hinterlässt, wird diese gespeichert in:
`data/notizen/telefon_notizen.txt`

### WhatsApp-Nachrichten
Hinterlassene Nachrichten aus WhatsApp:
`data/whatsapp_nachrichten.txt`

### WhatsApp-Gesprächslog
Alle WhatsApp-Gespräche (mit Zeitstempel pro Kontakt):
`data/whatsapp_log.txt`

### Notizen anzeigen
- Im Browser: Kalender öffnen → **„📝 Notizen"**-Button
- Im Chat: `notizen_lesen()` oder `"Zeig mir meine Notizen"`
- Telegram: Einfach fragen: *„Was steht in meinen Notizen?"*

### Automatische Bereinigung
Alle Log-Dateien werden automatisch bereinigt: Einträge die älter als **12 Wochen** sind werden beim nächsten Start gelöscht.

---

## 13. Alle verfügbaren Skills

Diese Skills können im Chat, per Telegram oder in Workflows verwendet werden. Ilija ruft sie automatisch auf wenn passende Anfragen gestellt werden.

### Datum & Zeit
| Skill | Beschreibung |
|---|---|
| `uhrzeit_datum()` | Aktuelles Datum und Uhrzeit |

### Mathematik & Einheiten
| Skill | Beschreibung |
|---|---|
| `taschenrechner("1250 * 1.19")` | Mathematischen Ausdruck berechnen |
| `einheit_umrechnen(10, "km", "meilen")` | Einheiten umrechnen (Länge, Gewicht, Temperatur, Währung) |

### Internet & Recherche
| Skill | Beschreibung |
|---|---|
| `internet_suche("Begriff")` | Im Internet suchen (Google oder DuckDuckGo) |
| `webseite_lesen("https://...")` | Inhalt einer Webseite lesen |
| `suche_und_lese_erste_seite("Frage")` | Suchen und erste Seite direkt lesen |
| `news_abrufen("Thema")` | Aktuelle Nachrichten zu einem Thema |
| `wikipedia_suche("Begriff")` | Wikipedia-Zusammenfassung abrufen |
| `browser_oeffnen("https://...")` | Webseite in Chrome öffnen |

### TV-Programm
| Skill | Beschreibung |
|---|---|
| `tv_jetzt()` | Was läuft gerade auf allen öffentlich-rechtlichen Sendern |
| `tv_sender("ARD")` | Was läuft auf einem bestimmten Sender |
| `tv_sender_liste()` | Alle verfügbaren Sender anzeigen |

Verfügbare Sender: ARD, ZDF, arte, 3sat, phoenix, KiKA, BR, HR, MDR, NDR, RBB, SWR, WDR, ORF 1, ORF 2, SRF 1, SRF 2 und mehr.

### Dateien
| Skill | Beschreibung |
|---|---|
| `datei_lesen("pfad/zur/datei.txt")` | Textinhalt einer lokalen Datei lesen |

### Sonstiges
| Skill | Beschreibung |
|---|---|
| `muenze_werfen()` | Münze werfen (Kopf oder Zahl) |
| `wuerfeln(6)` | Würfeln (1 bis Maximum) |
| `wetter_offenburg_abfragen()` | Aktuelles Wetter für Offenburg |

### ERP-Integration (OpenPhoenix)
Ilija kann sich mit OpenPhoenix ERP (V2 oder V3) verbinden und Buchhaltung, Rechnungen und Lager verwalten. Einrichten: `erp_pfad_setzen("pfad/zu/openphoenix")`.

### Netzwerk-Monitoring (Net-Fire-Monitor)
Ilija kann einen laufenden Net-Fire-Monitor überwachen, IP-Adressen analysieren, Whitelist/Blacklist verwalten und Firewall-Entscheidungen autonom treffen.

---

## 14. Wissensbasis (data/public_info)

Die Wissensbasis erlaubt es Ilija, Kundenfragen aus eigenen Dokumenten zu beantworten — ohne dass Kunden merken, dass Ilija gerade etwas nachschlägt.

### Dokumente hinzufügen
Einfach Textdateien in den Ordner `data/public_info/` legen:

```
data/public_info/
├── preisliste.txt
├── faq.md
├── leistungen.pdf
└── anfahrt.txt
```

Unterstützte Formate: `.txt`, `.md`, `.pdf`

### Wie es funktioniert
1. Beim Start liest Ilija alle Dokumente in `data/public_info/`
2. Bei jeder Anfrage sucht Ilija keyword-basiert nach passenden Stellen
3. Relevante Abschnitte werden automatisch in den Kontext eingebettet
4. Ilija antwortet basierend auf dem Dokumenteninhalt — ohne zu erfinden

### Gilt für alle Kanäle
Die Wissensbasis ist aktiv für:
- Telefon-Assistent
- WhatsApp-Assistent
- Ilija Chat (wenn gewünscht)

### Proaktives Anbieten
Damit Ilija die Wissensbasis auch aktiv anbietet, den entsprechenden Dienst in „Angebotene Dienste" eintragen:
```
Fragen zu unseren Leistungen und Preisen beantworten
```

---

## 15. Langzeitgedächtnis

Ilija kann sich Informationen dauerhaft merken — über einzelne Gespräche hinaus. Das Gedächtnis wird in einer lokalen ChromaDB-Datenbank gespeichert (`memory/`).

### Nutzen
```
"Merke dir: Frau Schmidt bevorzugt Termine vormittags"
"Was weißt du über Frau Schmidt?"
"Wie viele Erinnerungen hast du?"
"Lösch dein gesamtes Gedächtnis"
```

### Skills
| Skill | Beschreibung |
|---|---|
| `gedaechtnis_speichern("Information")` | Information dauerhaft speichern |
| `gedaechtnis_suchen("Suchbegriff")` | Im Gedächtnis suchen |
| `gedaechtnis_anzahl()` | Anzahl gespeicherter Erinnerungen |
| `gedaechtnis_loeschen_alles()` | Gesamtes Gedächtnis löschen |

### Hinweis
Das Gedächtnis ist benutzerspezifisch und wird **nicht** mit anderen synchronisiert. Bei einem Reset des Projekts wird `memory/` geleert.

---

## Häufige Fragen

**Ilija antwortet nicht auf Deutsch.**  
→ Im System-Prompt oder in der `ki_rolle`-Einstellung explizit auf Deutsch hinweisen: *„Antworte immer auf Deutsch."*

**Whisper erkennt meine Sprache schlecht.**  
→ Whisper-Modell auf `small` oder `medium` erhöhen (`.env`: `WHISPER_MODEL=small`). Mehr RAM wird benötigt.

**Der WhatsApp-Listener startet nicht.**  
→ Chrome muss installiert sein. Beim ersten Start öffnet sich ein Chrome-Fenster — QR-Code in WhatsApp scannen. Danach bleibt der Login gespeichert.

**Google Kalender: „credentials.json nicht gefunden"**  
→ OAuth-Datei aus der [Google Cloud Console](https://console.cloud.google.com/) herunterladen und unter `data/google_kalender/credentials.json` ablegen.

**Termin-Buchungen erscheinen nicht im Kalender.**  
→ Prüfen ob `data/local_calendar_events.json` beschreibbar ist. Evtl. Pfad-Berechtigungen prüfen.

**Ilija startet nicht / ImportError**  
→ Abhängigkeiten installieren: `pip install -r requirements.txt`

---

*Dieses Handbuch gilt für Ilija Public Edition. Für die Entwickler-Version (Ilija EVO) mit erweiterten Funktionen siehe das separate EVO-Handbuch.*
