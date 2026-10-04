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

## Ilija OS bekommen — 4 Wege

Welcher Weg der richtige ist, hängt davon ab was du schon hast und wie tief Ilija OS integriert sein soll.

### Weg 1: Ilija OS als Betriebssystem (empfohlen)

**Für wen:** Du hast einen freien PC/Mini-PC/Thin-Client, auf dem Ilija OS laufen soll.
**Was du bekommst:** Komplettes Betriebssystem (Ubuntu-Basis + Ilija OS) mit allem drin, inklusive Plymouth-Boot-Logo, Autostart, Desktop-Integration, noVNC-Fernzugriff.

1. ISO aus den [Releases](https://github.com/Innobytix-IT/Ilija-OS/releases) laden (als 5 Teile)
2. Teile zusammenfügen:
   ```bash
   cat ilija-os-24.04-amd64.iso.part* > ilija-os-24.04-amd64.iso
   sha256sum -c SHA256SUMS.txt
   ```
3. Auf USB-Stick schreiben (Balena Etcher oder Rufus unter Windows; `sudo dd if=...iso of=/dev/sdX bs=4M status=progress` unter Linux)
4. Vom USB-Stick booten, Calamares-Installer durchlaufen — fertig.

### Weg 2: Vorhandenes Linux zu einem echten Ilija OS aufwerten

**Für wen:** Du hast schon Ubuntu/Lubuntu/Debian installiert und willst es zu einem Ilija OS machen — mit Plymouth-Boot-Logo, systemd-Service, GPU-Integration, Autostart. Am Ende so tief integriert wie Weg 1.

```bash
git clone https://github.com/Innobytix-IT/Ilija-OS.git /opt/ilija-os/ilija
cd /opt/ilija-os/ilija
sudo ./install-ilija-os.sh
```

Das Skript installiert:
- Python-App + Dependencies
- Plymouth-Boot-Theme mit Ilija-Logo
- GPU-Module ins initramfs (für Boot-Splash)
- `ilija.service` als systemd-Service (startet beim Boot)
- Update-Skript + sudoers-Regeln
- Chromium für die WhatsApp-Brücke

### Weg 3: Ilija als Anwendung (ohne OS-Integration)

**Für wen:** Du willst Ilija nur als normale Anwendung ausprobieren oder auf einem Server ohne grafische Oberfläche laufen lassen. Kein Boot-Logo, kein Autostart beim Hochfahren — nur die App.

```bash
git clone https://github.com/Innobytix-IT/Ilija-OS.git
cd Ilija-OS
./install.sh
```

Richtet Ilija in deinem Home-Verzeichnis ein mit venv, systemd-Service (optional) und API-Key-Setup. Deutlich leichtgewichtiger als Weg 2.

### Weg 4: Nur die Python-App (Entwickler)

**Für wen:** Du willst am Code arbeiten oder nur mal reinschauen.

```bash
git clone https://github.com/Innobytix-IT/Ilija-OS.git
cd Ilija-OS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # API-Key eintragen
python web_server.py
```

Danach im Browser: **http://localhost:5001**. Kein Service, kein Autostart, kein Boot-Logo — manuell starten.

---

## Automatische Updates

Bei **Weg 1** und **Weg 2** ist das automatische Update eingerichtet: `/opt/ilija-os/ilija-update.sh` wird jede Nacht um 03:00 Uhr per Cron ausgeführt und zieht System-Updates (`apt`) + Code-Änderungen (git pull) + Plymouth-Theme + Python-Pakete nach. Außerdem gibt es im Web-UI einen "Update"-Button.

Bei **Weg 3** optional einrichtbar während `./install.sh` läuft.

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
| OS (Weg 2/3/4) | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 LTS |
| Python | 3.10 | 3.12 |
| RAM | 512 MB | 2 GB |
| Speicher | 2 GB | 10 GB |

Weg 1 (ISO) läuft auf jeder BIOS/UEFI-fähigen x86-64-Hardware. Weg 2–4 laufen auch auf: Raspberry Pi 4/5, Windows (WSL2), macOS.

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
