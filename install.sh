#!/bin/bash
# =============================================================================
#  Ilija Public Edition – Installationsskript
#  Persönlicher KI-Assistent: DMS, WhatsApp, Telegram, Web-Interface
# =============================================================================

set -e

RED='\033[0;31m';  GREEN='\033[0;32m';  YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m';   MAGENTA='\033[0;35m'
BOLD='\033[1m';    RESET='\033[0m'

print_header() {
    echo ""
    echo -e "${BLUE}${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BLUE}${BOLD}║${RESET}  ${CYAN}${BOLD}$1${RESET}"
    echo -e "${BLUE}${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
    echo ""
}
print_step()  { echo -e "${GREEN}${BOLD}▶  $1${RESET}"; }
print_info()  { echo -e "${CYAN}   ℹ  $1${RESET}"; }
print_warn()  { echo -e "${YELLOW}   ⚠  $1${RESET}"; }
print_ok()    { echo -e "${GREEN}   ✅  $1${RESET}"; }
print_error() { echo -e "${RED}   ❌  $1${RESET}"; }
divider()     { echo -e "${BLUE}──────────────────────────────────────────────────────────────${RESET}"; }

clear
echo ""
echo -e "${MAGENTA}${BOLD}"
echo "  ██╗██╗     ██╗     ██╗ █████╗ "
echo "  ██║██║     ██║     ██║██╔══██╗"
echo "  ██║██║     ██║     ██║███████║"
echo "  ██║██║     ██║██   ██║██╔══██║"
echo "  ██║███████╗██║╚█████╔╝██║  ██║"
echo "  ╚═╝╚══════╝╚═╝ ╚════╝ ╚═╝  ╚═╝"
echo -e "${RESET}"
echo -e "${CYAN}${BOLD}         Ilija Public Edition – Setup${RESET}"
echo -e "${CYAN}         Dein persönlicher KI-Assistent wartet auf dich...${RESET}"
echo ""; divider; echo ""
echo "  Dieses Skript installiert alle Abhängigkeiten und"
echo "  richtet Ilija Public Edition vollständig ein."
echo ""; divider
sleep 1

# =============================================================================
# SCHRITT 0: Installationspfad
# =============================================================================
print_header "SCHRITT 0/7 – Installationspfad"

DEFAULT_INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "  ${BOLD}Wo soll Ilija installiert werden?${RESET}"
echo ""
echo -e "  Standard: ${CYAN}${DEFAULT_INSTALL_DIR}${RESET}"
echo "  [1] Standard-Pfad verwenden"
echo "  [2] Eigenen Pfad angeben"
echo ""
read -rp "  Deine Wahl [1/2]: " PATH_CHOICE

INSTALL_DIR="$DEFAULT_INSTALL_DIR"
if [ "$PATH_CHOICE" = "2" ]; then
    echo ""
    read -rp "  Pfad eingeben: " CUSTOM_PATH
    CUSTOM_PATH="${CUSTOM_PATH/#\~/$HOME}"
    if [ -n "$CUSTOM_PATH" ]; then
        INSTALL_DIR="$CUSTOM_PATH"
        mkdir -p "$INSTALL_DIR"
        if [ "$INSTALL_DIR" != "$DEFAULT_INSTALL_DIR" ]; then
            print_step "Kopiere Projektdateien nach $INSTALL_DIR ..."
            cp -r "$DEFAULT_INSTALL_DIR"/. "$INSTALL_DIR/"
            print_ok "Dateien kopiert"
        fi
    fi
fi

print_ok "Installationspfad: ${INSTALL_DIR}"
cd "$INSTALL_DIR"

# =============================================================================
# SCHRITT 1: Python prüfen
# =============================================================================
print_header "SCHRITT 1/7 – Python prüfen"

if ! command -v python3 &> /dev/null; then
    print_error "Python3 nicht gefunden!"
    echo "  → sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    print_error "Python $PYTHON_VERSION gefunden – mindestens 3.10 benötigt!"
    echo "  → sudo apt install python3.10"; exit 1
fi
print_ok "Python $PYTHON_VERSION ✓"

# =============================================================================
# SCHRITT 2: Lokales KI-Modell (Ollama)
# =============================================================================
print_header "SCHRITT 2/7 – Lokales KI-Modell (Ollama)"

OLLAMA_INSTALLED=false
OLLAMA_HAS_MODELS=false
SELECTED_LOCAL_MODEL=""

if command -v ollama &> /dev/null; then
    OLLAMA_INSTALLED=true
    print_ok "Ollama ist bereits installiert"
    MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | grep -v "^$" || true)
    if [ -n "$MODELS" ]; then
        OLLAMA_HAS_MODELS=true
        echo ""
        print_ok "Vorhandene lokale Modelle:"
        ollama list 2>/dev/null | tail -n +2 | awk '{printf "      \U0001F916  %s\n", $1}'
        SELECTED_LOCAL_MODEL=$(ollama list 2>/dev/null | tail -n +2 | awk 'NR==1{print $1}')
        print_info "Standardmäßig wird '${SELECTED_LOCAL_MODEL}' als Fallback verwendet."
    else
        print_warn "Ollama installiert, aber kein Modell vorhanden."
    fi
else
    print_warn "Ollama nicht installiert."
fi

select_and_pull_model() {
    echo ""; divider; echo ""
    echo -e "  ${BOLD}Verfügbare lokale Modelle:${RESET}"; echo ""
    echo "  [1] qwen2.5:7b     ~ 4.7 GB  Empfohlen"
    echo "  [2] llama3.2:3b    ~ 2.0 GB  Sehr schnell, wenig RAM"
    echo "  [3] mistral:7b     ~ 4.1 GB  Stark in Deutsch & Logik"
    echo "  [4] gemma3:4b      ~ 3.3 GB  Google-Modell, effizient"
    echo "  [5] llama3.1:8b    ~ 4.7 GB  Meta bestes 8B Modell"
    echo "  [6] qwen2.5:14b    ~ 9.0 GB  Sehr intelligent"
    echo "  [7] deepseek-r1:8b ~ 4.9 GB  Stark in Reasoning"
    echo "  [8] Überspringen"; echo ""
    read -rp "  Deine Wahl [1-8]: " MODEL_CHOICE
    case $MODEL_CHOICE in
        1) SELECTED_LOCAL_MODEL="qwen2.5:7b" ;;
        2) SELECTED_LOCAL_MODEL="llama3.2:3b" ;;
        3) SELECTED_LOCAL_MODEL="mistral:7b" ;;
        4) SELECTED_LOCAL_MODEL="gemma3:4b" ;;
        5) SELECTED_LOCAL_MODEL="llama3.1:8b" ;;
        6) SELECTED_LOCAL_MODEL="qwen2.5:14b" ;;
        7) SELECTED_LOCAL_MODEL="deepseek-r1:8b" ;;
        8) print_info "Übersprungen."; return ;;
        *) print_warn "Ungültig – überspringe."; return ;;
    esac
    print_step "Lade '$SELECTED_LOCAL_MODEL' herunter..."
    print_warn "Das kann einige Minuten dauern..."
    ollama pull "$SELECTED_LOCAL_MODEL"
    print_ok "'$SELECTED_LOCAL_MODEL' bereit!"
}

if [ "$OLLAMA_HAS_MODELS" = false ]; then
    echo ""
    read -rp "  Lokales Modell installieren? [j/N]: " LOCAL_CHOICE
    if [[ "$LOCAL_CHOICE" =~ ^[jJ]$ ]]; then
        if [ "$OLLAMA_INSTALLED" = false ]; then
            print_step "Installiere Ollama..."
            curl -fsSL https://ollama.com/install.sh | sh
            OLLAMA_INSTALLED=true
            print_ok "Ollama installiert"
            sleep 2
        fi
        select_and_pull_model
    else
        print_info "Lokales Modell übersprungen."
    fi
fi

# =============================================================================
# SCHRITT 3: Python-Abhängigkeiten
# =============================================================================
print_header "SCHRITT 3/7 – Python-Abhängigkeiten installieren"

if [ ! -d "venv" ]; then
    print_step "Erstelle virtuelle Python-Umgebung..."
    python3 -m venv venv
    print_ok "Virtuelle Umgebung erstellt"
else
    print_ok "Virtuelle Umgebung bereits vorhanden"
fi

source venv/bin/activate
print_ok "Virtuelle Umgebung aktiviert"

print_step "Aktualisiere pip..."
pip install --upgrade pip --quiet
print_ok "pip aktualisiert"

print_step "Installiere Kern-Pakete..."
pip install \
    "flask>=3.0.0" "flask-cors>=4.0.0" "python-dotenv>=1.0.0" \
    "requests>=2.31.0" "anthropic>=0.40.0" "openai>=1.54.0" \
    "ollama>=0.1.0" "google-generativeai>=0.8.0" \
    "beautifulsoup4>=4.12.0" "lxml>=4.9.0" \
    --quiet 2>&1 | grep -E "(Successfully|already|error|ERROR)" || true
print_ok "Kern-Pakete installiert"

print_step "Installiere ChromaDB (Langzeitgedächtnis)..."
pip install "chromadb>=0.4.0" --quiet
print_ok "ChromaDB installiert"

print_step "Installiere Sentence-Transformer..."
print_warn "Dauert beim ersten Mal etwas länger (~90 MB)..."
pip install "sentence-transformers>=2.2.0" --quiet
print_ok "Sentence-Transformer installiert"

print_step "Installiere Telegram-Bot-Bibliothek..."
pip install "python-telegram-bot>=20.0" --quiet
print_ok "Telegram-Bot installiert"

print_step "Installiere Selenium & WebDriver (für WhatsApp Web)..."
pip install "selenium>=4.0.0" "webdriver-manager>=4.0.0" --quiet
print_ok "Selenium & WebDriver installiert"

print_step "Installiere DMS-Pakete (Dokument-Verarbeitung)..."
pip install "pdfplumber>=0.9.0" "PyPDF2>=3.0.0" "python-docx>=1.0.0" \
    "openpyxl>=3.1.0" "python-pptx>=0.6.0" "Pillow>=10.0.0" \
    --quiet 2>&1 | grep -E "(Successfully|already|error|ERROR)" || true
print_ok "DMS-Pakete installiert"

# OCR (Tesseract)
echo ""
print_info "OCR für Bild-Scans (Tesseract) – optional"
read -rp "  OCR-Unterstützung installieren (pytesseract)? [j/N]: " OCR_CHOICE
if [[ "$OCR_CHOICE" =~ ^[jJ]$ ]]; then
    pip install pytesseract --quiet
    sudo apt-get install -y tesseract-ocr tesseract-ocr-deu 2>/dev/null || \
        print_warn "Tesseract muss manuell installiert werden: sudo apt install tesseract-ocr"
    print_ok "OCR installiert"
else
    print_info "OCR übersprungen."
fi

# Telefon-Assistent (FritzBox / pyaudio / edge-tts)
echo ""
print_info "Telefon-Assistent (FritzBox SIP) – optional"
read -rp "  FritzBox-Telefon-Assistent installieren (pyaudio + edge-tts)? [j/N]: " FRITZ_CHOICE
if [[ "$FRITZ_CHOICE" =~ ^[jJ]$ ]]; then
    sudo apt-get install -y portaudio19-dev 2>/dev/null || \
        print_warn "portaudio19-dev konnte nicht installiert werden – pyaudio evtl. nicht funktionsfaehig"
    pip install "pyaudio>=0.2.11" "edge-tts>=6.1.0" --quiet
    print_ok "Telefon-Assistent-Pakete installiert"
    print_info "SIP-Zugangsdaten in .env eintragen: SIP_SERVER, SIP_USER, SIP_PASSWORD"
else
    print_info "Telefon-Assistent uebersprungen."
fi

# Google Chrome
echo ""
if command -v google-chrome &> /dev/null || command -v google-chrome-stable &> /dev/null; then
    CHROME_VER=$(google-chrome --version 2>/dev/null || google-chrome-stable --version 2>/dev/null)
    print_ok "Google Chrome: $CHROME_VER"
else
    print_warn "Google Chrome nicht gefunden (für WhatsApp-Skill benötigt)"
    read -rp "  Chrome jetzt installieren? [j/N]: " CHROME_CHOICE
    if [[ "$CHROME_CHOICE" =~ ^[jJ]$ ]]; then
        wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb
        sudo apt install -y /tmp/chrome.deb
        rm /tmp/chrome.deb
        print_ok "Google Chrome installiert"
    fi
fi

# Ordner & .env
mkdir -p data/dms/import data/dms/archiv data/uploads data/notizen memory skills/.skill_backups
touch data/dms/import/.gitkeep data/dms/archiv/.gitkeep memory/.gitkeep

if [ ! -f ".env" ]; then
    cp .env.example .env
    print_ok ".env erstellt aus .env.example"
fi
grep -q "ANONYMIZED_TELEMETRY" .env || echo "ANONYMIZED_TELEMETRY=False" >> .env

# Gedächtnis-Modell vorladen
print_step "Lade Gedächtnis-Modell vor (all-MiniLM-L6-v2)..."
python3 -c "
from sentence_transformers import SentenceTransformer
import warnings; warnings.filterwarnings('ignore')
SentenceTransformer('all-MiniLM-L6-v2')
" 2>/dev/null && print_ok "Gedächtnis-Modell bereit" || print_warn "Modell wird beim ersten Start geladen"

# =============================================================================
# SCHRITT 4: Cloud-Provider & API-Keys
# =============================================================================
print_header "SCHRITT 4/7 – Cloud-Provider & API-Keys"

EXISTING_CLAUDE=$(grep "^ANTHROPIC_API_KEY=" .env 2>/dev/null | cut -d'=' -f2 || echo "")
EXISTING_OPENAI=$(grep "^OPENAI_API_KEY="    .env 2>/dev/null | cut -d'=' -f2 || echo "")
EXISTING_GOOGLE=$(grep "^GOOGLE_API_KEY="    .env 2>/dev/null | cut -d'=' -f2 || echo "")

configure_provider() {
    local NAME="$1" VAR="$2" URL="$3" EXISTING="$4"
    if [ -n "$EXISTING" ]; then
        print_ok "$NAME bereits konfiguriert."
        read -rp "     Neu überschreiben? [j/N]: " OW
        [[ "$OW" =~ ^[jJ]$ ]] || return
    fi
    print_info "Key beantragen: $URL"
    echo -n "     $NAME API-Key eingeben (leer = überspringen): "
    read -rs KEY; echo ""
    if [ -n "$KEY" ]; then
        grep -q "^${VAR}=" .env 2>/dev/null && sed -i "/^${VAR}=/d" .env
        echo "${VAR}=${KEY}" >> .env
        print_ok "$NAME Key gespeichert"
    else
        print_info "$NAME übersprungen."
    fi
}

echo "  [1] Claude (Anthropic)  – Beste Qualität"
echo "  [2] ChatGPT (OpenAI)"
echo "  [3] Gemini (Google)     – Kostenloses Kontingent!"
echo "  [4] Alle drei einrichten"
echo "  [5] Keinen – nur Ollama"
echo ""
read -rp "  Deine Wahl [1-5]: " PROV_CHOICE

case $PROV_CHOICE in
    1) configure_provider "Claude"  "ANTHROPIC_API_KEY" "https://console.anthropic.com" "$EXISTING_CLAUDE" ;;
    2) configure_provider "ChatGPT" "OPENAI_API_KEY"    "https://platform.openai.com/api-keys" "$EXISTING_OPENAI" ;;
    3) configure_provider "Gemini"  "GOOGLE_API_KEY"    "https://aistudio.google.com/app/apikey" "$EXISTING_GOOGLE" ;;
    4)
        configure_provider "Claude"  "ANTHROPIC_API_KEY" "https://console.anthropic.com" "$EXISTING_CLAUDE"
        configure_provider "ChatGPT" "OPENAI_API_KEY"    "https://platform.openai.com/api-keys" "$EXISTING_OPENAI"
        configure_provider "Gemini"  "GOOGLE_API_KEY"    "https://aistudio.google.com/app/apikey" "$EXISTING_GOOGLE"
        ;;
    5) print_info "Nur Ollama wird verwendet." ;;
    *) print_warn "Überspringe Provider." ;;
esac

# =============================================================================
# SCHRITT 5: Telegram-Bot
# =============================================================================
print_header "SCHRITT 5/7 – Telegram-Bot einrichten (optional)"

EXISTING_TG=$(grep "^TELEGRAM_BOT_TOKEN=" .env 2>/dev/null | cut -d'=' -f2 || echo "")
TG_SKIP=false

if [ -n "$EXISTING_TG" ]; then
    print_ok "Telegram-Bot bereits konfiguriert."
    read -rp "  Neu konfigurieren? [j/N]: " TG_RECONFIG
    [[ "$TG_RECONFIG" =~ ^[jJ]$ ]] || TG_SKIP=true
fi

if [ "$TG_SKIP" = false ]; then
    read -rp "  Telegram-Bot einrichten? [j/N]: " TG_CHOICE
    if [[ "$TG_CHOICE" =~ ^[jJ]$ ]]; then
        echo ""
        echo -e "  ${CYAN}${BOLD}── Anleitung (ca. 2 Minuten) ───────────────────────────────${RESET}"
        echo "  1. Öffne Telegram → suche @BotFather"
        echo "  2. Tippe /newbot → Name eingeben → Username eingeben (endet auf 'bot')"
        echo "  3. Token kopieren"
        echo "  4. Deine User-ID über @userinfobot herausfinden"
        echo ""
        divider; echo ""
        echo -n "  Bot-Token eingeben: "
        read -rs TG_TOKEN; echo ""
        if [ -n "$TG_TOKEN" ]; then
            grep -q "^TELEGRAM_BOT_TOKEN=" .env && sed -i "/^TELEGRAM_BOT_TOKEN=/d" .env
            echo "TELEGRAM_BOT_TOKEN=${TG_TOKEN}" >> .env
            print_ok "Bot-Token gespeichert"
        fi
        echo -n "  Deine Telegram User-ID: "
        read -r TG_UID
        if [ -n "$TG_UID" ]; then
            grep -q "^TELEGRAM_ALLOWED_USERS=" .env && sed -i "/^TELEGRAM_ALLOWED_USERS=/d" .env
            echo "TELEGRAM_ALLOWED_USERS=${TG_UID}" >> .env
            print_ok "User-ID gespeichert"
        fi
        print_ok "Telegram-Bot eingerichtet!"
    else
        print_info "Telegram-Bot übersprungen."
    fi
fi

# =============================================================================
# SCHRITT 6: Info
# =============================================================================
print_header "SCHRITT 6/7 – Was kann Ilija Public Edition?"

echo -e "${BOLD}  🗂  DMS – Dokumentenmanagementsystem${RESET}"
echo "     Dokumente automatisch per KI kategorisieren & archivieren"
echo "     PDF, Word, Excel, Bilder, Scans – alle gängigen Formate"
echo "     Web-GUI unter http://localhost:5000/dms"; echo ""
echo -e "${BOLD}  🧠  Langzeitgedächtnis${RESET}"
echo "     Ilija merkt sich alles – auch nach dem Neustart"; echo ""
echo -e "${BOLD}  💬  WhatsApp-Assistent${RESET}"
echo "     Überwacht Chats, vereinbart Termine, nimmt Nachrichten an"; echo ""
echo -e "${BOLD}  📱  Telegram-Fernsteuerung${RESET}"
echo "     Steuere Ilija von überall – auch Dokumente per Telegram senden"; echo ""
echo -e "${BOLD}  🔍  Internet-Recherche${RESET}"
echo "     DuckDuckGo-Suche, Wikipedia, Webseiten lesen"; echo ""
echo -e "${BOLD}  🌐  Web-Interface${RESET}"
echo "     Moderner Browser-Chat – auch auf dem Handy nutzbar"; echo ""
divider
read -rp "  Drücke ENTER um fortzufahren..." _

# =============================================================================
# SCHRITT 7: Starten
# =============================================================================
print_header "SCHRITT 7/7 – Ilija starten"

TG_TOKEN_SET=$(grep "^TELEGRAM_BOT_TOKEN=" .env 2>/dev/null | cut -d'=' -f2 || echo "")

echo -e "  ${GREEN}[1] Web-Interface${RESET}   (empfohlen)"
echo "         http://localhost:5000  |  /dms für Dokumentenverwaltung"; echo ""

if [ -n "$TG_TOKEN_SET" ]; then
    echo -e "  ${CYAN}[2] Telegram-Bot${RESET}"
    echo "         Fernsteuerung per Telegram-App"; echo ""
    echo -e "  ${YELLOW}[3] Web + Telegram gleichzeitig${RESET}   (empfohlen für Dauerbetrieb)"; echo ""
fi

echo -e "  ${BLUE}[4] Terminal-Modus${RESET}   (für Entwickler)"; echo ""

if [ -n "$TG_TOKEN_SET" ]; then
    read -rp "  Deine Wahl [1/2/3/4]: " START_CHOICE
else
    read -rp "  Deine Wahl [1/4]: " START_CHOICE
fi

# =============================================================================
clear; echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║                                                              ║"
echo "  ║      Ilija Public Edition ist bereit!                       ║"
echo "  ║                                                              ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"; sleep 1

echo -e "${CYAN}  Konfigurierte Provider:${RESET}"
[ -n "$(grep '^ANTHROPIC_API_KEY=' .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  Claude (Anthropic)"   || echo "     --  Claude (nicht konfiguriert)"
[ -n "$(grep '^OPENAI_API_KEY='    .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  ChatGPT (OpenAI)"     || echo "     --  ChatGPT (nicht konfiguriert)"
[ -n "$(grep '^GOOGLE_API_KEY='    .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  Gemini (Google)"      || echo "     --  Gemini (nicht konfiguriert)"
[ -n "$SELECTED_LOCAL_MODEL" ] \
    && echo "     OK  Ollama ($SELECTED_LOCAL_MODEL)" || echo "     --  Ollama (kein Modell)"
[ -n "$(grep '^TELEGRAM_BOT_TOKEN=' .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  Telegram-Bot"         || echo "     --  Telegram-Bot (nicht eingerichtet)"
echo ""

case "$START_CHOICE" in
    2)
        echo -e "${CYAN}${BOLD}  Starte Telegram-Bot...${RESET}"; sleep 1
        python3 telegram_bot.py ;;
    3)
        echo -e "${YELLOW}${BOLD}  Starte Web + Telegram...${RESET}"
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "?")
        echo "  http://localhost:5000  |  http://${LOCAL_IP}:5000"; sleep 1
        python3 telegram_bot.py &
        TG_PID=$!
        trap "kill $TG_PID 2>/dev/null || true" EXIT
        python3 web_server.py ;;
    4)
        echo -e "${BLUE}${BOLD}  Starte Terminal-Modus...${RESET}"; sleep 1
        python3 kernel.py ;;
    *)
        echo -e "${GREEN}${BOLD}  Starte Web-Interface...${RESET}"
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "?")
        echo "  http://localhost:5000  |  DMS: http://localhost:5000/dms"; sleep 1
        python3 web_server.py ;;
esac
