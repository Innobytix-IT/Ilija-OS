# Ilija OS

**Dein persönlicher KI-Assistent — lokal, privat, frei.**

Ilija OS ist ein KI-Betriebssystem das auf deinem eigenen Gerät läuft. Kein Cloud-Zwang, keine Datenweitergabe, vollständige Kontrolle. Du bedienst es über deinen Browser — egal ob auf dem Laptop, einem Heimserver oder einem kleinen Einplatinencomputer.

[![Lizenz: AGPL v3](https://img.shields.io/badge/Lizenz-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## Was kann Ilija OS?

| Funktion | Beschreibung |
|---|---|
| 💬 **KI-Chat** | Gespräche mit Claude, Gemini, GPT oder lokalem Ollama-Modell |
| 📅 **Kalender** | Termine verwalten, freie Slots finden, WhatsApp-Buchung |
| 🏢 **ERP** | Rechnungen, Angebote, Lager, Mahnwesen (OpenPhoenix) |
| 📋 **Workflow Studio** | n8n-ähnliche Automatisierungen ohne Code |
| 📱 **WhatsApp-Brücke** | Ilija antwortet automatisch auf WhatsApp-Nachrichten |
| ✉️ **Telegram-Bot** | Nachrichten senden & empfangen |
| 📄 **Fristen & Vorlagen** | Dokumente ausfüllen, Fristen im Blick behalten |
| 🔍 **Web-Suche** | DuckDuckGo oder Google Custom Search |
| 🖥️ **DMS** | Dokumentenmanagement mit OCR |

---

## Schnellstart

```bash
# 1. Repository klonen
git clone https://github.com/Innobytix-IT/Ilija-OS.git
cd Ilija-OS

# 2. Python-Umgebung einrichten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Konfiguration anlegen
cp .env.example .env
nano .env   # Mindestens einen KI-API-Key eintragen

# 4. Starten
python web_server.py
```

Danach Ilija OS im Browser öffnen: **http://localhost:5001**

---

## Automatische Updates (Linux/systemd)

```bash
sudo cp system/ilija-update /usr/local/bin/ilija-update
sudo chmod 755 /usr/local/bin/ilija-update
sudo cp system/ilija-update.service /etc/systemd/system/
sudo cp system/ilija-update.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ilija-update.timer
```

Ilija OS aktualisiert sich dann täglich um 03:00 Uhr automatisch.

---

## Unterstützte KI-Anbieter

- **Anthropic Claude** (empfohlen für komplexe Aufgaben)
- **Google Gemini** (gut & günstig, empfohlen für den Alltag)
- **OpenAI ChatGPT**
- **Ollama** (vollständig lokal, kein API-Key nötig)

---

## Systemvoraussetzungen

| | Minimum | Empfohlen |
|---|---|---|
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 LTS |
| Python | 3.10 | 3.12 |
| RAM | 512 MB | 2 GB |
| Speicher | 2 GB | 10 GB |

Läuft auch auf: Raspberry Pi 4/5, Windows (WSL2), macOS

---

## Lizenz

Ilija OS ist freie Software — veröffentlicht unter der **GNU Affero General Public License v3** (AGPL-3.0).

Du kannst Ilija OS frei nutzen, verändern und weitergeben. Wer eine modifizierte Version als Netzwerkdienst für andere betreibt, muss den Quellcode ebenfalls veröffentlichen.

→ Details: [LICENSE](LICENSE) · [gnu.org/licenses/agpl-3.0](https://www.gnu.org/licenses/agpl-3.0)

---

## Mitwirken

Pull Requests sind willkommen. Bitte erstelle zuerst ein Issue um größere Änderungen abzustimmen.

---

*Entwickelt von [Innobytix-IT](https://github.com/Innobytix-IT)*
