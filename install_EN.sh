#!/bin/bash
# =============================================================================
#  Offenes Leuchten v5.0 – Installation Script
#  Ilija: Autonomous AI Agent with Long-Term Memory, WhatsApp & Telegram
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

# =============================================================================
# Welcome
# =============================================================================
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
echo -e "${CYAN}${BOLD}         Offenes Leuchten v5.0 – Setup${RESET}"
echo -e "${CYAN}         Your autonomous AI agent is waiting for you...${RESET}"
echo ""; divider; echo ""
echo "  This script installs all dependencies and sets up"
echo "  Ilija step by step, fully and interactively."
echo ""; divider
sleep 1

# =============================================================================
# STEP 0: Installation path
# =============================================================================
print_header "STEP 0/7 – Installation Path"

DEFAULT_INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "  ${BOLD}Where should Ilija be installed?${RESET}"
echo ""
echo -e "  Default: ${CYAN}${DEFAULT_INSTALL_DIR}${RESET}"
echo "  [1] Use default path"
echo "  [2] Choose a custom path"
echo ""
read -rp "  Your choice [1/2]: " PATH_CHOICE

INSTALL_DIR="$DEFAULT_INSTALL_DIR"
if [ "$PATH_CHOICE" = "2" ]; then
    echo ""
    read -rp "  Enter path: " CUSTOM_PATH
    CUSTOM_PATH="${CUSTOM_PATH/#\~/$HOME}"
    if [ -n "$CUSTOM_PATH" ]; then
        INSTALL_DIR="$CUSTOM_PATH"
        mkdir -p "$INSTALL_DIR"
        if [ "$INSTALL_DIR" != "$DEFAULT_INSTALL_DIR" ]; then
            print_step "Copying project files to $INSTALL_DIR ..."
            cp -r "$DEFAULT_INSTALL_DIR"/. "$INSTALL_DIR/"
            print_ok "Files copied"
        fi
    fi
fi

print_ok "Installation path: ${INSTALL_DIR}"
cd "$INSTALL_DIR"

# =============================================================================
# STEP 1: Check Python
# =============================================================================
print_header "STEP 1/7 – Check Python"

if ! command -v python3 &> /dev/null; then
    print_error "Python3 not found!"
    echo "  → sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    print_error "Python $PYTHON_VERSION found – at least 3.10 required!"
    echo "  → sudo apt install python3.10"; exit 1
fi
print_ok "Python $PYTHON_VERSION ✓"

# =============================================================================
# STEP 2: Local AI Model (Ollama)
# =============================================================================
print_header "STEP 2/7 – Local AI Model (Ollama)"

OLLAMA_INSTALLED=false
OLLAMA_HAS_MODELS=false
SELECTED_LOCAL_MODEL=""

if command -v ollama &> /dev/null; then
    OLLAMA_INSTALLED=true
    print_ok "Ollama is already installed"
    MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | grep -v "^$" || true)
    if [ -n "$MODELS" ]; then
        OLLAMA_HAS_MODELS=true
        echo ""
        print_ok "Existing local models:"
        ollama list 2>/dev/null | tail -n +2 | awk '{printf "      \U0001F916  %s\n", $1}'
        SELECTED_LOCAL_MODEL=$(ollama list 2>/dev/null | tail -n +2 | awk 'NR==1{print $1}')
        print_info "'${SELECTED_LOCAL_MODEL}' will be used as the local fallback."
    else
        print_warn "Ollama is installed but no models found."
    fi
else
    print_warn "Ollama not installed."
fi

select_and_pull_model() {
    echo ""; divider; echo ""
    echo -e "  ${BOLD}Available local models:${RESET}"; echo ""
    echo -e "  ${CYAN}  Standard hardware (8-16 GB RAM):${RESET}"
    echo "  [1] qwen2.5:7b     ~ 4.7 GB  Recommended – fast & intelligent"
    echo "  [2] llama3.2:3b    ~ 2.0 GB  Very fast, low RAM usage"
    echo "  [3] mistral:7b     ~ 4.1 GB  Strong in reasoning & logic"
    echo "  [4] gemma3:4b      ~ 3.3 GB  Google model, efficient"
    echo ""
    echo -e "  ${CYAN}  High-end hardware (32+ GB RAM):${RESET}"
    echo "  [5] llama3.1:8b    ~ 4.7 GB  Meta's best 8B model"
    echo "  [6] qwen2.5:14b    ~ 9.0 GB  Very intelligent"
    echo "  [7] deepseek-r1:8b ~ 4.9 GB  Strong in reasoning"
    echo ""
    echo "  [8] Skip"; echo ""
    read -rp "  Your choice [1-8]: " MODEL_CHOICE
    case $MODEL_CHOICE in
        1) SELECTED_LOCAL_MODEL="qwen2.5:7b" ;;
        2) SELECTED_LOCAL_MODEL="llama3.2:3b" ;;
        3) SELECTED_LOCAL_MODEL="mistral:7b" ;;
        4) SELECTED_LOCAL_MODEL="gemma3:4b" ;;
        5) SELECTED_LOCAL_MODEL="llama3.1:8b" ;;
        6) SELECTED_LOCAL_MODEL="qwen2.5:14b" ;;
        7) SELECTED_LOCAL_MODEL="deepseek-r1:8b" ;;
        8) print_info "Skipped."; return ;;
        *) print_warn "Invalid – skipping."; return ;;
    esac
    echo ""
    print_step "Downloading model '$SELECTED_LOCAL_MODEL'..."
    print_warn "This may take a few minutes..."; echo ""
    ollama pull "$SELECTED_LOCAL_MODEL"
    print_ok "'$SELECTED_LOCAL_MODEL' is ready!"
}

if [ "$OLLAMA_HAS_MODELS" = false ]; then
    echo ""
    echo -e "  ${BOLD}Would you like to install a local AI model?${RESET}"
    echo -e "  ${CYAN}  Advantage: runs offline, no API key needed, perfect fallback${RESET}"; echo ""
    read -rp "  Install local model? [y/N]: " LOCAL_CHOICE
    if [[ "$LOCAL_CHOICE" =~ ^[yY]$ ]]; then
        if [ "$OLLAMA_INSTALLED" = false ]; then
            print_step "Installing Ollama..."
            curl -fsSL https://ollama.com/install.sh | sh
            OLLAMA_INSTALLED=true
            print_ok "Ollama installed"
            sleep 2
        fi
        select_and_pull_model
    else
        print_info "Local model skipped."
    fi
fi

# =============================================================================
# STEP 3: Python Dependencies (COMPLETE)
# =============================================================================
print_header "STEP 3/7 – Install Python Dependencies"

if [ ! -d "venv" ]; then
    print_step "Creating virtual Python environment..."
    python3 -m venv venv
    print_ok "Virtual environment created"
else
    print_ok "Virtual environment already exists"
fi

source venv/bin/activate
print_ok "Virtual environment activated"

print_step "Updating pip..."
pip install --upgrade pip --quiet
print_ok "pip updated"

print_step "Installing core packages..."
echo "   flask, flask-cors, python-dotenv, requests"
echo "   anthropic, openai, ollama"
echo "   beautifulsoup4, lxml (for web scraping)"
pip install \
    "flask>=3.0.0" \
    "flask-cors>=4.0.0" \
    "python-dotenv>=1.0.0" \
    "requests>=2.31.0" \
    "anthropic>=0.40.0" \
    "openai>=1.54.0" \
    "ollama>=0.1.0" \
    "beautifulsoup4>=4.12.0" \
    "lxml>=4.9.0" \
    --quiet 2>&1 | grep -E "(Successfully|already|error|ERROR)" || true
print_ok "Core packages installed"

print_step "Installing ChromaDB (long-term memory)..."
pip install "chromadb>=0.4.0" --quiet
print_ok "ChromaDB installed"

print_step "Installing Sentence-Transformer (memory AI)..."
print_warn "First run takes a moment longer (model download ~90 MB)..."
pip install "sentence-transformers>=2.2.0" --quiet
print_ok "Sentence-Transformer installed"

print_step "Installing Telegram Bot library..."
pip install "python-telegram-bot>=20.0" --quiet
print_ok "Telegram Bot installed"

print_step "Installing Selenium & WebDriver (for WhatsApp Web)..."
pip install "selenium>=4.0.0" "webdriver-manager>=4.0.0" --quiet
print_ok "Selenium & WebDriver installed"

# Phone Assistant (FritzBox / pyaudio / edge-tts)
echo ""
print_info "Phone assistant (FritzBox SIP) – optional"
read -rp "  Install FritzBox phone assistant (pyaudio + edge-tts)? [y/N]: " FRITZ_CHOICE
if [[ "$FRITZ_CHOICE" =~ ^[yY]$ ]]; then
    sudo apt-get install -y portaudio19-dev 2>/dev/null || \
        print_warn "portaudio19-dev could not be installed – pyaudio may not work"
    pip install "pyaudio>=0.2.11" "edge-tts>=6.1.0" --quiet
    print_ok "Phone assistant packages installed"
    print_info "Enter SIP credentials in .env: SIP_SERVER, SIP_USER, SIP_PASSWORD"
else
    print_info "Phone assistant skipped."
fi

# Check Google Chrome
echo ""
if command -v google-chrome &> /dev/null || command -v google-chrome-stable &> /dev/null; then
    CHROME_VER=$(google-chrome --version 2>/dev/null || google-chrome-stable --version 2>/dev/null || echo "Unknown version")
    print_ok "Google Chrome found: $CHROME_VER"
else
    print_warn "Google Chrome not found (required for the WhatsApp skill)"
    echo ""
    read -rp "  Install Chrome automatically now? [y/N]: " CHROME_CHOICE
    if [[ "$CHROME_CHOICE" =~ ^[yY]$ ]]; then
        print_step "Installing Google Chrome..."
        wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb
        sudo apt install -y /tmp/chrome.deb
        rm /tmp/chrome.deb
        print_ok "Google Chrome installed"
    else
        print_info "Chrome can be installed manually later."
        print_info "WhatsApp skill will not work without Chrome."
    fi
fi

# Whisper – Local speech recognition (optional)
echo ""
divider
echo ""
echo -e "  ${BOLD}Speech Recognition (Whisper) – optional${RESET}"
echo -e "  ${CYAN}  Transcribes voice messages in WhatsApp, Telegram & Web Interface.${RESET}"
echo -e "  ${CYAN}  Requires: ~2-3 GB disk space (PyTorch + Whisper model)${RESET}"
echo -e "  ${CYAN}  Without Whisper: OpenAI Whisper API is used as fallback (if OPENAI_API_KEY is set)${RESET}"
echo ""
read -rp "  Install Whisper (local speech recognition)? [y/N]: " WHISPER_CHOICE
if [[ "$WHISPER_CHOICE" =~ ^[yY]$ ]]; then
    print_step "Installing openai-whisper (incl. PyTorch)..."
    print_warn "This may take 5-10 minutes..."
    pip install openai-whisper --quiet
    print_ok "Whisper installed"
else
    print_info "Whisper skipped."
fi

# PDF & Word documents (optional)
echo ""
echo -e "  ${BOLD}PDF & Word Support – optional${RESET}"
echo -e "  ${CYAN}  Read .pdf, .docx, .doc files in the Web Interface & Telegram.${RESET}"
echo ""
read -rp "  Install PDF & Word support? [y/N]: " DOCS_CHOICE
if [[ "$DOCS_CHOICE" =~ ^[yY]$ ]]; then
    print_step "Installing PyPDF2, pdfplumber, python-docx..."
    pip install PyPDF2 pdfplumber python-docx --quiet
    print_ok "PDF & Word support installed"
else
    print_info "Document processing skipped."
fi

# Create folders & prepare .env
mkdir -p memory skills/.skill_backups

if [ ! -f ".env" ]; then
    cp .env.example .env 2>/dev/null || echo "ANONYMIZED_TELEMETRY=False" > .env
fi
grep -q "ANONYMIZED_TELEMETRY" .env || echo "ANONYMIZED_TELEMETRY=False" >> .env

# Pre-load memory model
print_step "Pre-loading memory model (all-MiniLM-L6-v2, ~90 MB)..."
python3 -c "
from sentence_transformers import SentenceTransformer
import warnings
warnings.filterwarnings('ignore')
SentenceTransformer('all-MiniLM-L6-v2')
" 2>/dev/null
print_ok "Memory model ready"

# =============================================================================
# STEP 4: Cloud Providers & API Keys
# =============================================================================
print_header "STEP 4/7 – Cloud Providers & API Keys"

echo -e "  Ilija uses cloud AI providers in addition to Ollama."
echo -e "  It automatically selects the best available provider."
echo ""; divider; echo ""

EXISTING_CLAUDE=$(grep "^ANTHROPIC_API_KEY=" .env 2>/dev/null | cut -d'=' -f2 || echo "")
EXISTING_OPENAI=$(grep "^OPENAI_API_KEY="    .env 2>/dev/null | cut -d'=' -f2 || echo "")
EXISTING_GOOGLE=$(grep "^GOOGLE_API_KEY="    .env 2>/dev/null | cut -d'=' -f2 || echo "")

configure_provider() {
    local NAME="$1" VAR="$2" URL="$3" EXISTING="$4"
    if [ -n "$EXISTING" ]; then
        print_ok "$NAME already configured."
        read -rp "     Overwrite? [y/N]: " OW
        [[ "$OW" =~ ^[yY]$ ]] || return
    fi
    echo ""
    print_info "Get your key at: $URL"
    echo -n "     Enter $NAME API key (leave empty to skip): "
    read -rs KEY; echo ""
    if [ -n "$KEY" ]; then
        grep -q "^${VAR}=" .env 2>/dev/null && sed -i "/^${VAR}=/d" .env
        echo "${VAR}=${KEY}" >> .env
        print_ok "$NAME key saved"
    else
        print_info "$NAME skipped."
    fi
}

echo -e "  ${BOLD}Set up cloud providers:${RESET}"; echo ""
echo "  [1] Claude (Anthropic)  – Best quality"
echo "      console.anthropic.com  (free trial credit)"
echo ""
echo "  [2] ChatGPT (OpenAI)    – Very good & widely used"
echo "      platform.openai.com/api-keys"
echo ""
echo "  [3] Gemini (Google)     – Good & affordable (free tier available!)"
echo "      aistudio.google.com/app/apikey"
echo ""
echo "  [4] Set up all three"
echo "  [5] None – use local Ollama model only"; echo ""
read -rp "  Your choice [1-5]: " PROV_CHOICE

case $PROV_CHOICE in
    1) configure_provider "Claude" "ANTHROPIC_API_KEY" "https://console.anthropic.com" "$EXISTING_CLAUDE" ;;
    2) configure_provider "ChatGPT" "OPENAI_API_KEY" "https://platform.openai.com/api-keys" "$EXISTING_OPENAI" ;;
    3) configure_provider "Gemini" "GOOGLE_API_KEY" "https://aistudio.google.com/app/apikey" "$EXISTING_GOOGLE" ;;
    4)
        configure_provider "Claude" "ANTHROPIC_API_KEY" "https://console.anthropic.com" "$EXISTING_CLAUDE"
        configure_provider "ChatGPT" "OPENAI_API_KEY" "https://platform.openai.com/api-keys" "$EXISTING_OPENAI"
        configure_provider "Gemini" "GOOGLE_API_KEY" "https://aistudio.google.com/app/apikey" "$EXISTING_GOOGLE"
        ;;
    5) print_info "Only Ollama will be used." ;;
    *) print_warn "Skipping provider setup." ;;
esac

# =============================================================================
# STEP 5: Telegram Bot Setup (with full step-by-step guide)
# =============================================================================
print_header "STEP 5/7 – Telegram Bot Setup (optional)"

echo -e "  ${BOLD}What can the Telegram Bot do?${RESET}"; echo ""
echo "   Control Ilija from anywhere in the world (not just your home network)"
echo "   Send text messages, voice messages, images & files"
echo "   Start and stop the WhatsApp listener"
echo "   Reload skills with /reload"
echo "   Retrieve calendar entries and left messages"
echo ""; divider; echo ""

EXISTING_TG=$(grep "^TELEGRAM_BOT_TOKEN=" .env 2>/dev/null | cut -d'=' -f2 || echo "")
TG_SKIP=false

if [ -n "$EXISTING_TG" ]; then
    print_ok "Telegram Bot already configured."
    read -rp "  Reconfigure? [y/N]: " TG_RECONFIG
    if [[ ! "$TG_RECONFIG" =~ ^[yY]$ ]]; then
        print_info "Keeping existing Telegram configuration."
        TG_SKIP=true
    fi
fi

if [ "$TG_SKIP" = false ]; then
    read -rp "  Set up Telegram Bot? [y/N]: " TG_CHOICE
    if [[ "$TG_CHOICE" =~ ^[yY]$ ]]; then

        echo ""
        echo -e "  ${CYAN}${BOLD}── How to create your Telegram Bot (approx. 2 minutes) ─────────${RESET}"
        echo ""
        echo -e "  ${BOLD}STEP A – Create your bot on Telegram:${RESET}"
        echo "   1. Open Telegram (mobile app or telegram.org in your browser)"
        echo "   2. Search for the contact:  @BotFather"
        echo "      (Official Telegram bot with blue checkmark)"
        echo "   3. Type or click:  /newbot"
        echo "   4. Enter a display name, e.g.:  Ilija"
        echo "   5. Enter a unique username, e.g.:  my_ilija_bot"
        echo "      IMPORTANT: The username MUST end with 'bot'!"
        echo "   6. BotFather will send you a token:"
        echo ""
        echo "      Example token:"
        echo -e "      ${YELLOW}1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxX${RESET}"
        echo ""
        echo "      Copy this token now!"
        echo ""
        echo -e "  ${BOLD}STEP B – Find your personal Telegram User ID:${RESET}"
        echo "   1. Search in Telegram for:  @userinfobot"
        echo "   2. Type:  /start"
        echo "   3. The bot replies with your ID:"
        echo ""
        echo "      Example reply:"
        echo -e "      ${YELLOW}Id: 123456789${RESET}"
        echo ""
        echo "      Note down this number!"
        echo ""
        echo -e "  ${YELLOW}  Security note:${RESET}"
        echo "  Only your User ID is allowed to control Ilija."
        echo "  Anyone else who finds your bot will receive no response."
        echo ""
        divider; echo ""
        read -rp "  Have your token and User ID ready? Press ENTER to continue..." _
        echo ""

        echo -n "  Enter Bot Token: "
        read -rs TG_TOKEN; echo ""
        if [ -n "$TG_TOKEN" ]; then
            grep -q "^TELEGRAM_BOT_TOKEN=" .env 2>/dev/null && sed -i "/^TELEGRAM_BOT_TOKEN=/d" .env
            echo "TELEGRAM_BOT_TOKEN=${TG_TOKEN}" >> .env
            print_ok "Bot token saved"
        fi

        echo ""
        echo -n "  Enter your Telegram User ID: "
        read -r TG_UID
        if [ -n "$TG_UID" ]; then
            grep -q "^TELEGRAM_ALLOWED_USERS=" .env 2>/dev/null && sed -i "/^TELEGRAM_ALLOWED_USERS=/d" .env
            echo "TELEGRAM_ALLOWED_USERS=${TG_UID}" >> .env
            print_ok "User ID saved – only you can control Ilija"
        fi

        echo ""
        print_ok "Telegram Bot configured! Test it after startup with /start"
    else
        print_info "Telegram Bot skipped – can be set up at any time later."
    fi
fi

# =============================================================================
# STEP 6: Getting to know Ilija
# =============================================================================
print_header "STEP 6/7 – Getting to Know Ilija"

echo -e "  ${BOLD}What is Ilija?${RESET}"; echo ""
echo "  Ilija is an autonomous AI agent – not a simple chatbot."
echo "  He thinks independently, plans his steps and teaches himself new skills."
echo ""; divider; echo ""
echo -e "${BOLD}  Long-Term Memory${RESET}"
echo "  Ilija remembers everything – even after a restart."
echo "  Example: 'My name is John' – Ilija will know this next time."; echo ""
echo -e "${BOLD}  Skill System (Self-Development)${RESET}"
echo "  Ilija writes new Python skills on-the-fly."
echo "  Example: 'Create a skill that checks the weather' – immediately usable."; echo ""
echo -e "${BOLD}  WhatsApp Assistant${RESET}"
echo "  Monitors chats, schedules appointments, takes messages."; echo ""
echo -e "${BOLD}  Telegram Remote Control${RESET}"
echo "  Control Ilija from anywhere – voice, files, commands."; echo ""
echo -e "${BOLD}  Web Interface${RESET}"
echo "  Modern chat UI – works on mobile too."; echo ""
echo -e "${BOLD}  Multi-Provider: Claude -> GPT -> Gemini -> Ollama${RESET}"
echo "  Ilija automatically selects the best available model."; echo ""
divider; echo ""
echo "  Example commands:"
echo "  'Remember: My name is John'            -> Long-term memory"
echo "  'What do you know about me?'           -> Retrieve memories"
echo "  'Create a skill for X'                 -> Ilija writes it"
echo "  'Monitor all WhatsApp chats'           -> Start listener"
echo "  'Show me the WhatsApp calendar'        -> Show appointments"
echo "  'Show me left messages'                -> Show messages"
echo ""

read -rp "  Press ENTER to continue..." _

# =============================================================================
# STEP 7: Choose start mode
# =============================================================================
print_header "STEP 7/7 – Start Ilija"

TG_TOKEN_SET=$(grep "^TELEGRAM_BOT_TOKEN=" .env 2>/dev/null | cut -d'=' -f2 || echo "")

echo -e "  ${BOLD}How would you like to start Ilija?${RESET}"; echo ""

echo -e "  ${GREEN}[1] Web Interface${RESET}   (recommended for beginners)"
echo "         Browser chat with microphone, file upload & skill reload"
echo "         http://localhost:5000"; echo ""

if [ -n "$TG_TOKEN_SET" ]; then
    echo -e "  ${CYAN}[2] Telegram Bot${RESET}"
    echo "         Remote control via Telegram app"
    echo "         Ideal for on-the-go or permanent server operation"; echo ""

    echo -e "  ${YELLOW}[3] Web Interface + Telegram simultaneously${RESET}   (recommended for continuous use)"
    echo "         Both interfaces running in parallel"; echo ""
fi

echo -e "  ${BLUE}[4] Terminal Mode${RESET}   (for developers)"
echo "         Classic command line directly in the terminal"
echo "         Commands: reload | debug | clear | switch | exit"; echo ""

if [ -n "$TG_TOKEN_SET" ]; then
    read -rp "  Your choice [1/2/3/4]: " START_CHOICE
else
    read -rp "  Your choice [1/4]: " START_CHOICE
fi

# =============================================================================
# Done & Start
# =============================================================================
clear; echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║                                                              ║"
echo "  ║      Installation complete!                                 ║"
echo "  ║      Ilija is ready. Have fun!                              ║"
echo "  ║                                                              ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"; sleep 1

echo -e "${CYAN}  Configured providers:${RESET}"
[ -n "$(grep '^ANTHROPIC_API_KEY=' .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  Claude (Anthropic)"   || echo "     --  Claude (not configured)"
[ -n "$(grep '^OPENAI_API_KEY='    .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  ChatGPT (OpenAI)"     || echo "     --  ChatGPT (not configured)"
[ -n "$(grep '^GOOGLE_API_KEY='    .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  Gemini (Google)"      || echo "     --  Gemini (not configured)"
[ -n "$SELECTED_LOCAL_MODEL" ] \
    && echo "     OK  Ollama ($SELECTED_LOCAL_MODEL)" || echo "     --  Ollama (no model selected)"
[ -n "$(grep '^TELEGRAM_BOT_TOKEN=' .env 2>/dev/null | cut -d'=' -f2)" ] \
    && echo "     OK  Telegram Bot"         || echo "     --  Telegram Bot (not configured)"
echo ""

case "$START_CHOICE" in
    2)
        echo -e "${CYAN}${BOLD}  Starting Telegram Bot...${RESET}"; echo ""
        echo "  Write to your bot in Telegram!"
        echo "  To stop: Ctrl+C"; echo ""; sleep 2
        python3 telegram_bot.py
        ;;
    3)
        echo -e "${YELLOW}${BOLD}  Starting Web Interface + Telegram Bot...${RESET}"; echo ""
        echo "  Browser: http://localhost:5000"
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "?")
        echo "  On your network: http://${LOCAL_IP}:5000"
        echo "  Telegram: Write to your bot"
        echo "  To stop: Ctrl+C"; echo ""; sleep 2
        python3 telegram_bot.py &
        TG_PID=$!
        trap "kill $TG_PID 2>/dev/null || true" EXIT
        python3 web_server.py
        ;;
    4)
        echo -e "${BLUE}${BOLD}  Starting Terminal Mode...${RESET}"; echo ""
        echo "  Commands: reload | debug | clear | switch | exit"
        echo "  To stop: type 'exit' or press Ctrl+C"; echo ""; sleep 1
        python3 kernel.py
        ;;
    *)
        echo -e "${GREEN}${BOLD}  Starting Web Interface...${RESET}"; echo ""
        echo "  Open your browser: http://localhost:5000"
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "?")
        echo "  On your local network: http://${LOCAL_IP}:5000"
        echo "  To stop: Ctrl+C"; echo ""; sleep 2
        python3 web_server.py
        ;;
esac
