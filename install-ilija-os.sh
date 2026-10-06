#!/bin/bash
# =============================================================================
# install-ilija-os.sh
#
# Macht aus einem bereits installierten Linux (Ubuntu/Lubuntu/Debian) ein
# echtes Ilija OS – mit Plymouth-Boot-Logo, systemd-Service, Autostart,
# GPU-Integration, Update-System. Am Ende so tief integriert wie die ISO.
#
# Erwartung: Dieses Repo liegt unter /opt/ilija-os/ilija/
# Aufruf:    sudo ./install-ilija-os.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'
BOLD='\033[1m'; RESET='\033[0m'

say()  { echo -e "\n${BLUE}${BOLD}==> $*${RESET}"; }
info() { echo -e "   ${CYAN}$*${RESET}"; }
ok()   { echo -e "   ${GREEN}OK${RESET} $*"; }
warn() { echo -e "   ${YELLOW}WARNUNG${RESET} $*"; }
die()  { echo -e "${RED}FEHLER:${RESET} $*" >&2; exit 1; }

# Spinner mit Live-Uhr fuer stille Operationen. Zeigt alle 0.3s eine
# rotierende Figur + Beschreibung + verstrichene Sekunden. Bei Fehler
# werden die letzten 20 Log-Zeilen angezeigt.
run_quiet() {
    local msg="$1"; shift
    local logfile; logfile=$(mktemp /tmp/ilija-install.XXXXXX.log)
    "$@" >"$logfile" 2>&1 &
    local pid=$! chars='|/-\' i=0 start=$SECONDS
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r   ${CYAN}%s${RESET} %s ... (%ds)" \
            "${chars:$((i % 4)):1}" "$msg" "$((SECONDS - start))"
        sleep 0.3
        i=$((i + 1))
    done
    wait "$pid"; local rc=$?
    local elapsed=$((SECONDS - start))
    if [ "$rc" -eq 0 ]; then
        printf "\r   ${GREEN}OK${RESET} %s (%ds)                                \n" "$msg" "$elapsed"
        rm -f "$logfile"
    else
        printf "\r   ${RED}FEHLER${RESET} %s (nach %ds)                        \n" "$msg" "$elapsed"
        echo "   Letzte Log-Zeilen:"
        tail -20 "$logfile" | sed 's/^/      /'
        rm -f "$logfile"
        return $rc
    fi
}

# ----------------------------------------------------------------------- Preflight
[ "$(id -u)" = 0 ] || die "Bitte als root ausführen: sudo $0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ILIJA_DIR="/opt/ilija-os/ilija"
UPDATE_SCRIPT="/opt/ilija-os/ilija-update.sh"

if [ "$SCRIPT_DIR" != "$ILIJA_DIR" ]; then
    warn "Dieses Repo liegt nicht unter $ILIJA_DIR, sondern unter $SCRIPT_DIR."
    read -rp "   Nach $ILIJA_DIR verschieben? [J/n]: " ans
    if [[ ! "$ans" =~ ^[nN]$ ]]; then
        mkdir -p /opt/ilija-os
        if [ -d "$ILIJA_DIR" ]; then
            die "$ILIJA_DIR existiert bereits – bitte vorher aufräumen."
        fi
        cp -r "$SCRIPT_DIR" "$ILIJA_DIR"
        ok "Nach $ILIJA_DIR verschoben"
        info "Weiter mit: sudo $ILIJA_DIR/install-ilija-os.sh"
        exit 0
    fi
    ILIJA_DIR="$SCRIPT_DIR"
    UPDATE_SCRIPT="$(dirname "$ILIJA_DIR")/ilija-update.sh"
fi

# Zielbenutzer bestimmen (erster normaler User mit UID >= 1000)
TARGET_USER=$(awk -F: '$3 >= 1000 && $3 < 65000 && $1 != "nobody" {print $1; exit}' /etc/passwd)
[ -n "$TARGET_USER" ] || die "Konnte keinen Benutzer mit UID >= 1000 finden."
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
info "Service-User wird: $TARGET_USER (Home: $TARGET_HOME)"

# ----------------------------------------------------------------------- Banner
clear
echo -e "${MAGENTA}${BOLD}"
cat <<'BANNER'
  ██╗██╗     ██╗     ██╗ █████╗      ██████╗ ███████╗
  ██║██║     ██║     ██║██╔══██╗    ██╔═══██╗██╔════╝
  ██║██║     ██║     ██║███████║    ██║   ██║███████╗
  ██║██║     ██║██   ██║██╔══██║    ██║   ██║╚════██║
  ██║███████╗██║╚█████╔╝██║  ██║    ╚██████╔╝███████║
  ╚═╝╚══════╝╚═╝ ╚════╝ ╚═╝  ╚═╝     ╚═════╝ ╚══════╝
BANNER
echo -e "${RESET}"
echo -e "${CYAN}${BOLD}  Weg 2: Vorhandenes Linux zu einem echten Ilija OS aufwerten${RESET}"
echo ""

# ----------------------------------------------------------------------- 0. Ownership
# WICHTIG und MUSS ganz zuerst passieren: Wenn das Repo mit `sudo git clone`
# geholt wurde, gehört /opt/ilija-os/ aktuell root. venv, pip & Co. laufen
# aber im nachfolgenden Schritt als TARGET_USER – ohne diesen chown hier
# knallt es dort mit Permission denied.
say "0/8 Besitzrechte /opt/ilija-os -> $TARGET_USER"
chown -R "$TARGET_USER:$TARGET_USER" /opt/ilija-os
ok "chown abgeschlossen"

# ----------------------------------------------------------------------- 1. System-Deps
say "1/8 System-Abhängigkeiten installieren"
export DEBIAN_FRONTEND=noninteractive

run_quiet "Paketlisten aktualisieren (apt-get update)" apt-get update -qq

run_quiet "Basis-Pakete installieren (python3, git, plymouth, tesseract-ocr, ca. 15 Pakete)" \
    apt-get install -y -qq \
        python3 python3-venv python3-pip python3-dev python3-tk build-essential \
        git curl wget \
        plymouth plymouth-themes \
        tesseract-ocr tesseract-ocr-deu \
        portaudio19-dev

info "   Chromium installieren (unter Lubuntu meist via Snap – kann 2-5 Min dauern)"
run_quiet "Chromium" bash -c "apt-get install -y -qq chromium-browser 2>/dev/null || apt-get install -y -qq chromium"

ok "System-Pakete installiert"

# ----------------------------------------------------------------------- 2. Python-venv
say "2/8 Python-venv + Ilija-Dependencies"
cd "$ILIJA_DIR"
if [ ! -d venv ]; then
    run_quiet "venv anlegen (python3 -m venv)" sudo -u "$TARGET_USER" python3 -m venv venv
else
    ok "venv existiert bereits"
fi

run_quiet "pip aktualisieren" \
    sudo -u "$TARGET_USER" bash -c "source venv/bin/activate && pip install --quiet --upgrade pip"

if [ -f requirements.txt ]; then
    PKG_COUNT=$(grep -cv '^\s*$\|^\s*#' requirements.txt || echo "?")

    # Zuerst torch CPU-only vorinstallieren, bevor requirements.txt sentence-
    # transformers/openai-whisper installiert. Grund: diese Deps ziehen sonst
    # transitiv torch mit GPU-CUDA-Variante (~2 GB inkl. nvidia-cublas,
    # nvidia-cudnn etc.). CPU-only ist deutlich schlanker (~250 MB) und
    # funktioniert fuer alle Ilija-Features (Whisper laeuft auf CPU, Embeddings
    # laufen auf CPU). Dedizierter CPU-Index von pytorch.org.
    run_quiet "PyTorch CPU-only installieren (~250 MB statt ~2 GB mit CUDA)" \
        sudo -u "$TARGET_USER" bash -c "source venv/bin/activate && pip install --quiet --resume-retries 50 --timeout 180 --index-url https://download.pytorch.org/whl/cpu torch"

    # Hohe Retry-Zahl + grosszuegiger Timeout, damit grosse transitive Downloads
    # (z.B. nvidia-cublas, ~400 MB) auch auf wackeliger VM-NAT-Verbindung
    # oder lahmen Mobile-Hotspots zuverlaessig durchkommen. Ohne das kippt
    # pip nach 6 Resume-Versuchen und das Script bricht ab.
    run_quiet "Python-Pakete installieren (${PKG_COUNT} aus requirements.txt, dauert 2-10 Min)" \
        sudo -u "$TARGET_USER" bash -c "source venv/bin/activate && pip install --quiet --resume-retries 50 --timeout 180 -r requirements.txt"
fi

# ----------------------------------------------------------------------- 3. .env anlegen
say "3/8 .env-Konfiguration anlegen"
if [ ! -f .env ] && [ -f .env.example ]; then
    sudo -u "$TARGET_USER" cp .env.example .env
    ok ".env angelegt – API-Keys trägst du im Web-UI unter Einstellungen ein."
else
    ok ".env existiert bereits oder keine .env.example vorhanden"
fi

# ----------------------------------------------------------------------- 4. Plymouth-Theme
say "4/8 Plymouth-Boot-Theme 'ilija' installieren"
PLYMOUTH_SRC="$ILIJA_DIR/system/plymouth"
PLYMOUTH_DST="/usr/share/plymouth/themes/ilija"
if [ -d "$PLYMOUTH_SRC" ] && ls "$PLYMOUTH_SRC"/*.plymouth >/dev/null 2>&1; then
    mkdir -p "$PLYMOUTH_DST/spinner"
    cp -r "$PLYMOUTH_SRC"/. "$PLYMOUTH_DST/"
    find "$PLYMOUTH_DST" -type f -exec chmod 644 {} \;
    update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
        default.plymouth "$PLYMOUTH_DST/ilija.plymouth" 200 >/dev/null 2>&1 || true
    update-alternatives --set default.plymouth "$PLYMOUTH_DST/ilija.plymouth" >/dev/null 2>&1 || true
    ok "Plymouth-Theme 'ilija' installiert"
else
    warn "system/plymouth/ fehlt im Repo – überspringe"
fi

# ----------------------------------------------------------------------- 5. initramfs mit GPU
say "5/8 initramfs mit FRAMEBUFFER + GPU-Modulen neu bauen (Boot-Splash)"

# Virtualisierung erkennen – in VMs ist FRAMEBUFFER=y + reale GPU-Module
# kontraproduktiv (konfligiert mit VBoxVGA/QXL/virtio-vga), fuehrt zu Boot-
# Hang am Plymouth-Logo. In VMs: einfach "vboxvideo" oder "qxl" nachladen,
# aber kein FRAMEBUFFER=y erzwingen.
IS_VM=0
if command -v systemd-detect-virt &>/dev/null; then
    VIRT_TYPE=$(systemd-detect-virt 2>/dev/null || echo "none")
    [ "$VIRT_TYPE" != "none" ] && IS_VM=1
fi

if [ "$IS_VM" = "1" ]; then
    info "   Virtualisierung erkannt: $VIRT_TYPE – überspringe FRAMEBUFFER=y"
    # Vorhandene FRAMEBUFFER=y rausnehmen falls aus vorherigem Lauf drin
    sed -i '/^FRAMEBUFFER=y$/d' /etc/initramfs-tools/initramfs.conf 2>/dev/null || true
    # Passendes VM-Grafik-Modul ins initramfs
    case "$VIRT_TYPE" in
        oracle|virtualbox) GPU_MODS="vboxvideo" ;;
        kvm|qemu)          GPU_MODS="qxl virtio_gpu" ;;
        vmware)            GPU_MODS="vmwgfx" ;;
        *)                 GPU_MODS="" ;;
    esac
else
    # Echte Hardware: FRAMEBUFFER=y damit Plymouth-Grafik frueh greift
    grep -q '^FRAMEBUFFER=y' /etc/initramfs-tools/initramfs.conf \
        || echo 'FRAMEBUFFER=y' >> /etc/initramfs-tools/initramfs.conf
    GPU_INFO=$(lspci 2>/dev/null | grep -iE 'vga|display|3d' || echo "")
    GPU_MODS=""
    if   echo "$GPU_INFO" | grep -qi 'amd\|ati\|radeon'; then GPU_MODS="amdgpu radeon"
    elif echo "$GPU_INFO" | grep -qi 'intel';            then GPU_MODS="i915"
    elif echo "$GPU_INFO" | grep -qi 'nvidia';           then GPU_MODS="nouveau"
    fi
fi

for m in $GPU_MODS; do
    grep -q "^$m\$" /etc/initramfs-tools/modules || echo "$m" >> /etc/initramfs-tools/modules
done
info "   GPU-Module: ${GPU_MODS:-keine spezifischen Module nötig}"

# In VMs: splash aus Kernel-Cmdline + plymouth.enable=0 anhaengen.
# Grund: selbst mit korrektem Framebuffer rendert Plymouth in VirtualBox
# unzuverlaessig und haelt den Boot fuer unbegrenzte Zeit am Logo an,
# so dass nach Reboot nur ein Hard-Reset hilft. Ohne splash bootet
# Lubuntu klassisch mit systemd-Fortschritt, kein Plymouth-Fenster, kein
# Hang. Echte Hardware behaelt den schoenen Boot-Splash.
if [ "$IS_VM" = "1" ]; then
    GRUB_FILE="/etc/default/grub"
    if [ -f "$GRUB_FILE" ]; then
        CHANGED=0
        # splash aus GRUB_CMDLINE_LINUX_DEFAULT nehmen (haeufigste Position)
        if grep -qE '^GRUB_CMDLINE_LINUX_DEFAULT=.*splash' "$GRUB_FILE"; then
            sed -i -E 's/(^GRUB_CMDLINE_LINUX_DEFAULT="[^"]*)\bsplash\b/\1/' "$GRUB_FILE"
            CHANGED=1
        fi
        # plymouth.enable=0 anhaengen, falls noch nicht drin
        if ! grep -qE '^GRUB_CMDLINE_LINUX_DEFAULT=.*plymouth\.enable=0' "$GRUB_FILE"; then
            sed -i -E 's/^(GRUB_CMDLINE_LINUX_DEFAULT="[^"]*)"/\1 plymouth.enable=0"/' "$GRUB_FILE"
            CHANGED=1
        fi
        # Doppel-Leerzeichen in Cmdline zusammenziehen
        sed -i -E 's/(^GRUB_CMDLINE_LINUX_DEFAULT="[^"]*)  +/\1 /g' "$GRUB_FILE"
        if [ "$CHANGED" = "1" ]; then
            info "   VM: splash raus + plymouth.enable=0 angehaengt (verhindert Boot-Hang)"
            update-grub >/dev/null 2>&1 || true
        fi
    fi
fi

run_quiet "initramfs für alle Kernel neu bauen (1-3 Min)" update-initramfs -u -k all

# ----------------------------------------------------------------------- 6. systemd-Service
say "6/8 ilija.service einrichten (Autostart beim Boot)"
cat > /etc/systemd/system/ilija.service << SVC
[Unit]
Description=Ilija OS – KI-Assistent Web-UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_USER
WorkingDirectory=$ILIJA_DIR
Environment=PORT=5001
ExecStart=$ILIJA_DIR/venv/bin/python $ILIJA_DIR/web_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable ilija.service >/dev/null 2>&1
ok "ilija.service enabled (startet automatisch beim Boot)"

# ----------------------------------------------------------------------- AI-API-Proxy (optional)
# Mitgelieferter OpenAI-kompatibler Proxy fuer Google Gemini. Eigenes venv
# damit Dependencies nicht mit Ilijas kollidieren. Service wird angelegt
# aber NICHT enabled; erst wenn der User in der Web-UI einen Gemini-API-Key
# eintraegt, enabled Flask ihn + startet ihn.
AI_PROXY_SRC="$ILIJA_DIR/vendor/ai-api-proxy"
if [ -d "$AI_PROXY_SRC" ]; then
    say "6b/8 Ilija AI-API-Proxy einrichten (Gemini-Proxy, Port 8642)"
    AI_PROXY_VENV="$AI_PROXY_SRC/venv"
    if [ ! -d "$AI_PROXY_VENV" ]; then
        run_quiet "AI-Proxy venv anlegen" python3 -m venv "$AI_PROXY_VENV"
    fi
    run_quiet "AI-Proxy Python-Deps installieren" \
        "$AI_PROXY_VENV/bin/pip" install --quiet -r "$AI_PROXY_SRC/requirements.txt"

    cat > /etc/systemd/system/ai-api-proxy.service << AIPROXY
[Unit]
Description=Ilija AI-API-Proxy (OpenAI-kompatibler Gemini-Proxy)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_USER
WorkingDirectory=$AI_PROXY_SRC
# Default-Port 8642 setzen; wird von .env ueberschrieben wenn dort "port=..."
Environment=port=8642
EnvironmentFile=-$AI_PROXY_SRC/.env
ExecStart=$AI_PROXY_VENV/bin/python -m uvicorn main:app --host 0.0.0.0 --port \${port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
AIPROXY
    systemctl daemon-reload
    # Default: enabled – Web-Config-UI soll von Anfang an erreichbar sein.
    # Server toleriert fehlenden API-Key (zeigt dann nur die Config-UI).
    systemctl enable ai-api-proxy.service >/dev/null 2>&1
    ok "ai-api-proxy.service enabled (startet beim Boot; Config via Web-UI)"
fi

# ----------------------------------------------------------------------- 7. Update-Script + sudoers
say "7/8 Update-System einrichten (Cron + Web-UI-Button)"
if [ -f "$ILIJA_DIR/system/ilija-update.sh" ]; then
    cp "$ILIJA_DIR/system/ilija-update.sh" "$UPDATE_SCRIPT"
    chmod +x "$UPDATE_SCRIPT"
    chown "$TARGET_USER:$TARGET_USER" "$UPDATE_SCRIPT"
    ok "$UPDATE_SCRIPT installiert (self-updating)"
else
    warn "system/ilija-update.sh nicht gefunden – kein Update-Script installiert"
fi

cat > /etc/sudoers.d/ilija-update-rules << SUDO
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/apt-get
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ilija, /usr/bin/systemctl restart x11vnc, /usr/bin/systemctl restart x11vnc.service, /usr/bin/systemctl restart x11vnc-desktop, /usr/bin/systemctl restart x11vnc-desktop.service, /usr/bin/systemctl restart xvfb, /usr/bin/systemctl restart xvfb.service, /usr/bin/systemctl restart novnc, /usr/bin/systemctl restart novnc.service, /usr/bin/systemctl restart novnc-desktop, /usr/bin/systemctl restart novnc-desktop.service
$TARGET_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart ilija, /bin/systemctl restart x11vnc, /bin/systemctl restart x11vnc.service, /bin/systemctl restart x11vnc-desktop, /bin/systemctl restart x11vnc-desktop.service, /bin/systemctl restart xvfb, /bin/systemctl restart xvfb.service, /bin/systemctl restart novnc, /bin/systemctl restart novnc.service, /bin/systemctl restart novnc-desktop, /bin/systemctl restart novnc-desktop.service
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable ai-api-proxy, /usr/bin/systemctl enable ai-api-proxy.service, /usr/bin/systemctl disable ai-api-proxy, /usr/bin/systemctl disable ai-api-proxy.service, /usr/bin/systemctl restart ai-api-proxy, /usr/bin/systemctl restart ai-api-proxy.service, /usr/bin/systemctl stop ai-api-proxy, /usr/bin/systemctl stop ai-api-proxy.service, /usr/bin/systemctl start ai-api-proxy, /usr/bin/systemctl start ai-api-proxy.service
$TARGET_USER ALL=(ALL) NOPASSWD: /bin/systemctl enable ai-api-proxy, /bin/systemctl enable ai-api-proxy.service, /bin/systemctl disable ai-api-proxy, /bin/systemctl disable ai-api-proxy.service, /bin/systemctl restart ai-api-proxy, /bin/systemctl restart ai-api-proxy.service, /bin/systemctl stop ai-api-proxy, /bin/systemctl stop ai-api-proxy.service, /bin/systemctl start ai-api-proxy, /bin/systemctl start ai-api-proxy.service
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/update-initramfs
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/update-alternatives
SUDO
chmod 440 /etc/sudoers.d/ilija-update-rules
ok "sudoers-Regeln für passwortloses Update installiert"

# Cron-Job: nächtliches Auto-Update
# WICHTIG: `crontab -l` returned exit 1 wenn der User noch keinen Crontab hat,
# ebenso `grep -v` wenn nichts matched. Mit set -o pipefail würde das die
# ganze Pipeline killen → explizites `|| true` an beiden Stellen.
if [ -f "$UPDATE_SCRIPT" ]; then
    CRON_LINE="0 3 * * * $UPDATE_SCRIPT >> $TARGET_HOME/ilija-update.log 2>&1"
    EXISTING=$(sudo -u "$TARGET_USER" crontab -l 2>/dev/null || true)
    FILTERED=$(printf '%s\n' "$EXISTING" | grep -v 'ilija-update\.sh' || true)
    printf '%s\n%s\n' "$FILTERED" "$CRON_LINE" | sudo -u "$TARGET_USER" crontab - || warn "Cron-Setup fehlgeschlagen – manuell via 'crontab -e' nachtragen"
    ok "Cron-Job eingerichtet (täglich 03:00 Uhr)"
fi

# ----------------------------------------------------------------------- 7b. Desktop-Integration
say "7b/8 Desktop-Integration (App-Launcher, 5 Icons, Autostart)"

# Alte Reste von frueheren Script-Versionen entfernen:
# - Generische Ilija-OS-Desktopverknuepfung (System + User-Desktop)
# - Browser-Autostart der nach jedem Login Chromium mit localhost:5001 oeffnet
#   (unerwuenscht – der User soll Ilija per Icon selbst starten)
rm -f /usr/share/applications/ilija-os.desktop
rm -f "$TARGET_HOME/Desktop/ilija-os.desktop" "$TARGET_HOME/Schreibtisch/ilija-os.desktop" 2>/dev/null
rm -f "$TARGET_HOME/.config/autostart/ilija-os.desktop" 2>/dev/null

# Branding-Assets system-weit ablegen (werden von den .desktop-Dateien referenziert)
mkdir -p /usr/share/ilija-os/branding/assets
if [ -d "$ILIJA_DIR/branding/assets" ]; then
    cp "$ILIJA_DIR/branding/assets/"*.png /usr/share/ilija-os/branding/assets/ 2>/dev/null || true
fi
# Auch die Top-Level-Branding-Dateien übernehmen (ilija-icon.png etc.)
cp "$ILIJA_DIR/branding/"*.png /usr/share/ilija-os/branding/assets/ 2>/dev/null || true

# ilija-app Launcher: oeffnet eine URL als eigenstaendiges App-Fenster
# via Chromium --app= statt im normalen Browser mit URL-Leiste. Jede App
# bekommt eigenes User-Profile + WM-Klasse (eigenes Taskbar-Icon).
cat > /usr/local/bin/ilija-app << 'LAUNCHER'
#!/bin/bash
# Ilija OS: oeffnet eine Ilija-Seite als eigenstaendiges App-Fenster
# (Chromium App-Modus, ohne Browser-Leiste).
# Aufruf: ilija-app <URL> <WM-Klasse>
set -u
URL="${1:-http://localhost:5001/}"
KLASSE="${2:-ilija-app}"
BROWSER="$(command -v chromium-browser || command -v chromium)"
if [ -z "$BROWSER" ]; then
  echo "Chromium nicht gefunden." >&2
  exit 1
fi
# Snap-Chromium darf nicht in ~/.config schreiben -> snap-eigener Ordner
if [ -d "$HOME/snap/chromium" ]; then
  BASIS="$HOME/snap/chromium/common/ilija-os-apps"
else
  BASIS="${XDG_CONFIG_HOME:-$HOME/.config}/ilija-os/app-profile"
fi
PROFIL="$BASIS/$KLASSE"
mkdir -p "$PROFIL"
exec "$BROWSER" --app="$URL" --class="$KLASSE" --name="$KLASSE" \
     --user-data-dir="$PROFIL" --start-maximized \
     --no-first-run --no-default-browser-check >/dev/null 2>&1
LAUNCHER
chmod 755 /usr/local/bin/ilija-app

# Eine Hilfsfunktion fuer die immer gleichen .desktop-Eintraege
mk_app_desktop() {
    local slug="$1" name="$2" category="$3" url="$4"
    cat > "/usr/share/applications/ilija-$slug.desktop" << APP
[Desktop Entry]
Version=1.0
Type=Application
Name=$name
GenericName=Ilija OS
Comment=$name – Ilija OS
Exec=/usr/local/bin/ilija-app $url ilija-$slug
Icon=/usr/share/ilija-os/branding/assets/ilija-app-icon.png
Terminal=false
Categories=$category
StartupWMClass=ilija-$slug
StartupNotify=true
APP
}

# Die 5 Standard-Ilija-Apps (identisch zur ISO)
mk_app_desktop "chat"     "Chat"            "Network;"              "http://localhost:5001/chat"
mk_app_desktop "dms"      "DMS"             "Office;"               "http://localhost:5001/dms"
mk_app_desktop "kalender" "Kalender"        "Office;"               "http://localhost:5001/local_calendar"
mk_app_desktop "workflow" "Workflow Studio" "Development;"          "http://localhost:5001/"
mk_app_desktop "cloud"    "Cloud"           "Network;FileManager;"  "http://localhost:5001/cloud"

# OpenPhoenix ERP – nur wenn installiert
if [ -d /opt/ilija-os/openphoenix ] && [ -f /opt/ilija-os/openphoenix/main.py ]; then
    cat > /usr/local/bin/openphoenix << 'OPX'
#!/bin/bash
cd "/opt/ilija-os/openphoenix" || exit 1
exec "/opt/ilija-os/openphoenix/venv/bin/python" "/opt/ilija-os/openphoenix/main.py" "$@"
OPX
    chmod 755 /usr/local/bin/openphoenix
    cat > /usr/share/applications/openphoenix-erp.desktop << OPXD
[Desktop Entry]
Type=Application
Name=OpenPhönix ERP
Comment=Warenwirtschaft / ERP
Exec=/usr/local/bin/openphoenix
Icon=/opt/ilija-os/openphoenix/resources/icons/myicon.png
Terminal=false
Categories=Office;Finance;
OPXD
    info "   OpenPhönix ERP erkannt – Icon zusätzlich angelegt"
fi

# Icons auf den Desktop kopieren (fuer User die Desktop-Icons sehen wollen)
DESKTOP_DIR="$TARGET_HOME/Desktop"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$TARGET_HOME/Schreibtisch"
if [ -d "$DESKTOP_DIR" ]; then
    for slug in chat dms kalender workflow cloud; do
        cp "/usr/share/applications/ilija-$slug.desktop" "$DESKTOP_DIR/"
        chmod +x "$DESKTOP_DIR/ilija-$slug.desktop"
        chown "$TARGET_USER:$TARGET_USER" "$DESKTOP_DIR/ilija-$slug.desktop"
    done
    [ -f /usr/share/applications/openphoenix-erp.desktop ] && \
        cp /usr/share/applications/openphoenix-erp.desktop "$DESKTOP_DIR/" && \
        chmod +x "$DESKTOP_DIR/openphoenix-erp.desktop" && \
        chown "$TARGET_USER:$TARGET_USER" "$DESKTOP_DIR/openphoenix-erp.desktop"
fi

# Autostart-Trust-Script: markiert alle Desktop-.desktop-Dateien beim Login als
# vertrauenswürdig, damit sie nicht grau mit "nicht vertraut"-Hinweis erscheinen.
# (LXQt-Spezifikum – ohne das sieht man beim ersten Login nur Fragezeichen-Icons)
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
sudo -u "$TARGET_USER" mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/ilija-trust-desktop.desktop" << TRUST
[Desktop Entry]
Type=Application
Name=Ilija OS Desktop-Icons
Comment=Markiert die Desktop-Starter als vertrauenswuerdig, damit sie erscheinen
Exec=bash -c 'sleep 3; for f in "\$HOME"/Desktop/*.desktop "\$HOME"/Schreibtisch/*.desktop; do [ -f "\$f" ] || continue; chmod +x "\$f" 2>/dev/null; gio set "\$f" metadata::trusted true 2>/dev/null; touch "\$f" 2>/dev/null; done'
NoDisplay=true
X-LXQt-Need-Tray=false
TRUST
chown "$TARGET_USER:$TARGET_USER" "$AUTOSTART_DIR/ilija-trust-desktop.desktop"

# Fuer die aktuell laufende Session direkt vertrauenswuerdig markieren,
# damit nach dem Install (ohne Logout) die Icons sofort sichtbar sind
if [ -d "$DESKTOP_DIR" ]; then
    for f in "$DESKTOP_DIR"/*.desktop; do
        [ -f "$f" ] || continue
        sudo -u "$TARGET_USER" gio set "$f" "metadata::trusted" true 2>/dev/null || true
    done
fi

update-desktop-database >/dev/null 2>&1 || true
ok "App-Launcher + 5 Ilija-Icons (Chat/DMS/Kalender/Workflow/Cloud) + Trust-Autostart eingerichtet"

# ----------------------------------------------------------------------- Startsound beim Desktop-Login
# Spielt beim ersten Erscheinen des LXQt-Desktops den Ilija-OS-Jingle.
# Nicht beim Boot (da gibt es noch keinen Audio-Kontext) und nicht als Teil
# des systemd-Services (der laeuft als Daemon ohne User-Session).
# Einrichtungsassistent-Autostart: oeffnet beim Login den Browser auf dem
# Wizard. User kann im Wizard Step 5 "nicht mehr zeigen" ankreuzen; das
# schreibt eine Flag-Datei, die das Autostart-Script dann respektiert.
WIZARD_SCRIPT_SRC="$ILIJA_DIR/system/show-setup-wizard.sh"
WIZARD_SCRIPT_DST="/opt/ilija-os/show-setup-wizard.sh"
if [ -f "$WIZARD_SCRIPT_SRC" ]; then
    cp "$WIZARD_SCRIPT_SRC" "$WIZARD_SCRIPT_DST"
    chmod 755 "$WIZARD_SCRIPT_DST"
    cat > "$AUTOSTART_DIR/ilija-setup-wizard.desktop" << WIZARD
[Desktop Entry]
Type=Application
Name=Ilija OS Einrichtungsassistent
Comment=Oeffnet beim Login den Einrichtungsassistenten (deaktivierbar im Wizard)
Exec=$WIZARD_SCRIPT_DST
NoDisplay=true
X-LXQt-Need-Tray=false
X-GNOME-Autostart-enabled=true
WIZARD
    chown "$TARGET_USER:$TARGET_USER" "$AUTOSTART_DIR/ilija-setup-wizard.desktop"
    ok "Einrichtungsassistent-Autostart installiert"
fi

SOUND_SRC="$ILIJA_DIR/sounds/Ilija_OS_Start_Sound.wav"
if [ -f "$SOUND_SRC" ]; then
    SOUND_DST_DIR="/opt/ilija-os/sounds"
    SOUND_DST="$SOUND_DST_DIR/startup.wav"
    mkdir -p "$SOUND_DST_DIR"
    cp "$SOUND_SRC" "$SOUND_DST"
    chmod 644 "$SOUND_DST"

    # Audio-Player bereitstellen; paplay deckt PipeWire-Pulse und PulseAudio ab
    # und ist unter Lubuntu 24.04 Standard. Falls fehlt, nachinstallieren.
    if ! command -v paplay >/dev/null 2>&1; then
        run_quiet "pulseaudio-utils fuer Startsound installieren" \
            apt-get install -y -qq pulseaudio-utils
    fi

    # XDG-Autostart-Eintrag: triggert nach dem Desktop-Login
    cat > "$AUTOSTART_DIR/ilija-startsound.desktop" << SOUND
[Desktop Entry]
Type=Application
Name=Ilija OS Startsound
Comment=Spielt den Ilija-OS-Jingle einmal beim Login
Exec=bash -c 'sleep 1; paplay --volume=45000 $SOUND_DST 2>/dev/null || aplay -q $SOUND_DST 2>/dev/null || true'
NoDisplay=true
X-LXQt-Need-Tray=false
X-GNOME-Autostart-enabled=true
SOUND
    chown "$TARGET_USER:$TARGET_USER" "$AUTOSTART_DIR/ilija-startsound.desktop"
    ok "Startsound installiert (spielt beim Desktop-Login)"
fi

# ----------------------------------------------------------------------- System-Branding-Overlay
# LXQt-Startbutton + SDDM-Login-Screen + GRUB-Theme auf Ilija-OS umstellen
if [ -d "$ILIJA_DIR/branding/overlay" ]; then
    info "   System-Branding anwenden: LXQt-Startbutton, SDDM-Login, GRUB-Theme"
    cp -r "$ILIJA_DIR/branding/overlay/"* / 2>/dev/null || true
    # Falls GRUB-Config existiert, Theme aktivieren und update-grub (silent)
    if [ -f /etc/default/grub ] && [ -f /boot/grub/ilija-splash.png ]; then
        if ! grep -q '^GRUB_BACKGROUND=' /etc/default/grub; then
            echo 'GRUB_BACKGROUND="/boot/grub/ilija-splash.png"' >> /etc/default/grub
        fi
        update-grub >/dev/null 2>&1 || true
    fi
    ok "System-Branding (Startbutton, SDDM, GRUB) umgestellt"
fi

# "Lubuntu Manual"-Icon dauerhaft entfernen – aus dem User-Desktop UND
# aus /etc/skel/Desktop/ (sonst legt Lubuntu es bei jedem neuen Login/
# User-Neuanlage wieder an). Fuer bestehende User zusaetzlich alle
# /home/*/Desktop/-Instanzen suchen.
# Die LXQt-automatischen Shortcuts (Rechner, Papierkorb, User, Netzwerk)
# BLEIBEN – gewuenschtes Verhalten.
LUBUNTU_MANUAL_REMOVED=0
# 1) User-Desktop des Target-Users
if [ -d "$DESKTOP_DIR" ]; then
    if find "$DESKTOP_DIR" -maxdepth 1 -iname "*lubuntu*manual*" -print -delete 2>/dev/null | grep -q .; then
        LUBUNTU_MANUAL_REMOVED=1
    fi
fi
# 2) Schablonen-Verzeichnis fuer neue Nutzer
if [ -d /etc/skel/Desktop ]; then
    if find /etc/skel/Desktop -maxdepth 1 -iname "*lubuntu*manual*" -print -delete 2>/dev/null | grep -q .; then
        LUBUNTU_MANUAL_REMOVED=1
    fi
fi
# 3) Alle bestehenden User-Desktops im System (falls mehrere Nutzer)
for user_desktop in /home/*/Desktop /home/*/Schreibtisch; do
    [ -d "$user_desktop" ] || continue
    find "$user_desktop" -maxdepth 1 -iname "*lubuntu*manual*" -delete 2>/dev/null || true
done
if [ "$LUBUNTU_MANUAL_REMOVED" = "1" ]; then
    ok "Lubuntu-Manual-Icon dauerhaft entfernt (User + /etc/skel/)"
else
    ok "Keine Lubuntu-Manual-Datei gefunden (schon weg oder nie da)"
fi

# LXQt-Panel neu starten, damit der neu kopierte mainmenu.svg (Startbutton-
# Icon aus dem Overlay) in der laufenden Session direkt sichtbar wird.
# Ohne das muesste der Nutzer sich ab-/anmelden.
USER_UID=$(id -u "$TARGET_USER")
DBUS_ADDR="unix:path=/run/user/$USER_UID/bus"
if pgrep -u "$TARGET_USER" lxqt-panel >/dev/null 2>&1; then
    sudo -u "$TARGET_USER" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" DISPLAY=:0 \
        bash -c 'pkill lxqt-panel; sleep 0.5; (lxqt-panel >/dev/null 2>&1 &) ; sleep 1' 2>/dev/null || true
    info "   LXQt-Panel neu geladen (Startbutton zeigt neues Icon direkt)"
fi

# ----------------------------------------------------------------------- Wallpaper
# Ilija-OS-Wallpaper – identischer Pfad + Mode wie bei der ISO, damit
# Verhalten und Erscheinungsbild übereinstimmen.
WALLPAPER_SRC="$ILIJA_DIR/branding/ilija-splash.png"
WALLPAPER_DST="/usr/share/ilija-os/branding/assets/ilija-splash.png"
if [ -f "$WALLPAPER_SRC" ]; then
    # Datei liegt dort schon vom Branding-Asset-Copy weiter oben,
    # trotzdem zur Sicherheit nochmal (falls alte Script-Version lief)
    mkdir -p /usr/share/ilija-os/branding/assets
    cp "$WALLPAPER_SRC" "$WALLPAPER_DST"
    chmod 644 "$WALLPAPER_DST"

    # LXQt (Lubuntu): pcmanfm-qt-Konfig fuer alle Profile unter dem User
    LXQT_CFG_DIR="$TARGET_HOME/.config/pcmanfm-qt"
    sudo -u "$TARGET_USER" mkdir -p "$LXQT_CFG_DIR/lxqt"
    for profile in "$LXQT_CFG_DIR"/*/; do
        [ -d "$profile" ] || continue
        cfg="${profile}settings.conf"
        # Idempotent: existierende Config lesen, Desktop-Keys setzen/updaten
        sudo -u "$TARGET_USER" python3 - "$cfg" "$WALLPAPER_DST" << 'PYSET'
import sys, os, configparser
cfg, wp = sys.argv[1], sys.argv[2]
cp = configparser.ConfigParser(interpolation=None, strict=False)
cp.optionxform = str
if os.path.exists(cfg):
    try: cp.read(cfg)
    except Exception: pass
if "Desktop" not in cp:
    cp["Desktop"] = {}
cp["Desktop"]["Wallpaper"] = wp
cp["Desktop"]["WallpaperMode"] = "fit"
cp["Desktop"]["BgColor"] = "#000000"
cp["Desktop"]["FgColor"] = "#ffffff"
cp["Desktop"]["PerScreenWallpaper"] = "true"
os.makedirs(os.path.dirname(cfg), exist_ok=True)
with open(cfg, "w") as f:
    cp.write(f, space_around_delimiters=False)
PYSET
    done
    info "   Wallpaper-Config in pcmanfm-qt gesetzt (Mode: fit, Pfad: $WALLPAPER_DST)"

    # Fuer die LAUFENDE Session: pcmanfm-qt direkt anweisen, Wallpaper neu zu laden.
    # Ohne das muesste der User sich erst aus-/einloggen.
    USER_UID=$(id -u "$TARGET_USER")
    DBUS_ADDR="unix:path=/run/user/$USER_UID/bus"
    sudo -u "$TARGET_USER" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" DISPLAY=:0 \
        pcmanfm-qt --set-wallpaper="$WALLPAPER_DST" --wallpaper-mode=fit 2>/dev/null || true

    # GNOME / Cinnamon / Unity
    if command -v gsettings &>/dev/null; then
        sudo -u "$TARGET_USER" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" \
            gsettings set org.gnome.desktop.background picture-uri "file://$WALLPAPER_DST" 2>/dev/null || true
        sudo -u "$TARGET_USER" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" \
            gsettings set org.gnome.desktop.background picture-uri-dark "file://$WALLPAPER_DST" 2>/dev/null || true
        sudo -u "$TARGET_USER" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" \
            gsettings set org.gnome.desktop.background picture-options "zoom" 2>/dev/null || true
    fi

    # XFCE
    if command -v xfconf-query &>/dev/null; then
        sudo -u "$TARGET_USER" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" \
            bash -c 'for p in $(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep -E "last-image$"); do xfconf-query -c xfce4-desktop -p "$p" -s "'"$WALLPAPER_DST"'"; done' 2>/dev/null || true
    fi

    ok "Ilija-OS-Wallpaper gesetzt (ggf. Logout/Login nötig damit es sichtbar wird)"
else
    warn "branding/ilija-splash.png fehlt – Wallpaper übersprungen"
fi

# ----------------------------------------------------------------------- 7c. WhatsApp-Bridge
say "7c/8 WhatsApp-Bridge (Baileys / Node.js) einrichten"

WA_BRIDGE_DIR="$ILIJA_DIR/baileys-bridge"
if [ -d "$WA_BRIDGE_DIR" ] && [ -f "$WA_BRIDGE_DIR/package.json" ]; then
    # Node 20+ installieren (Baileys 6.7+ fordert >=20; Lubuntu-Default ist nur
    # Node 18, deshalb NodeSource-Repo einbinden). Nur wenn aktuelles node
    # nicht bereits >=20 ist.
    NODE_MAJOR=0
    if command -v node &>/dev/null; then
        NODE_MAJOR=$(node -v 2>/dev/null | sed 's/^v\([0-9]\+\).*/\1/')
    fi
    if [ "${NODE_MAJOR:-0}" -lt 20 ]; then
        info "   Node $([ "$NODE_MAJOR" = "0" ] && echo "fehlt" || echo "$NODE_MAJOR ist zu alt") – installiere Node 20 LTS via NodeSource"
        run_quiet "NodeSource-Repo einrichten (setup_20.x)" \
            bash -c "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -"
        run_quiet "Node.js 20 installieren" apt-get install -y -qq nodejs
    else
        info "   Node $NODE_MAJOR bereits installiert – ok"
    fi

    run_quiet "Node-Dependencies installieren (npm install, 1-3 Min)" \
        sudo -u "$TARGET_USER" bash -c "cd '$WA_BRIDGE_DIR' && npm install --omit=dev --no-audit --no-fund --silent"

    cat > /etc/systemd/system/whatsapp-bridge.service << WABRIDGE
[Unit]
Description=Ilija WhatsApp Bridge (Baileys)
After=network-online.target ilija.service
Wants=network-online.target ilija.service

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_USER
WorkingDirectory=$WA_BRIDGE_DIR
Environment=ILIJA_API=http://localhost:5001/api/whatsapp
Environment=AUTH_DIR=$WA_BRIDGE_DIR/auth_info
Environment=LOG_LEVEL=silent
ExecStart=/usr/bin/node bridge.js
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
WABRIDGE
    systemctl daemon-reload
    systemctl enable whatsapp-bridge.service >/dev/null 2>&1

    # Sudoers damit Ilija (als TARGET_USER) den whatsapp-bridge-Service
    # ueber /api/whatsapp/bridge starten/stoppen kann (ohne Passwort-Prompt)
    cat > /etc/sudoers.d/ilija-whatsapp-bridge << SUDOWA
$TARGET_USER ALL=(ALL) NOPASSWD: /bin/systemctl start whatsapp-bridge, /bin/systemctl stop whatsapp-bridge, /bin/systemctl restart whatsapp-bridge
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start whatsapp-bridge, /usr/bin/systemctl stop whatsapp-bridge, /usr/bin/systemctl restart whatsapp-bridge
SUDOWA
    chmod 440 /etc/sudoers.d/ilija-whatsapp-bridge
    ok "whatsapp-bridge.service eingerichtet + sudoers (Start/Stop via Web-UI)"
else
    warn "baileys-bridge/ fehlt – WhatsApp-Bridge übersprungen"
fi

# ----------------------------------------------------------------------- 7d. noVNC-Fernzugriff
say "7d/8 noVNC-Fernzugriff einrichten (Browser-Remote-Desktop auf Port 6080)"

run_quiet "noVNC + x11vnc + xvfb + openbox installieren" apt-get install -y -qq novnc x11vnc xvfb websockify openbox

# Hybrid-Launcher aus Repo installieren (siehe system/x11vnc-smart.sh).
# Script getrennt ins Repo gelegt, damit es bei Updates automatisch
# mitgezogen wird (siehe deploy_runtime_scripts in ilija-update.sh).
X11VNC_SCRIPT_SRC="$ILIJA_DIR/system/x11vnc-smart.sh"
X11VNC_SCRIPT_DST="/opt/ilija-os/x11vnc-smart.sh"
if [ -f "$X11VNC_SCRIPT_SRC" ]; then
    cp "$X11VNC_SCRIPT_SRC" "$X11VNC_SCRIPT_DST"
    chmod 755 "$X11VNC_SCRIPT_DST"
    ok "x11vnc-smart.sh installiert"
else
    warn "$X11VNC_SCRIPT_SRC fehlt – noVNC Launcher nicht installiert"
fi

# xvfb.service – virtueller X-Server als Fallback wenn kein echter Desktop da ist
cat > /etc/systemd/system/xvfb.service << 'XVFB'
[Unit]
Description=X Virtual Frame Buffer (Xvfb)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/Xvfb :1 -screen 0 1280x1024x24 -nolisten tcp
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
XVFB

# x11vnc.service – VNC-Server (nutzt den Hybrid-Launcher oben)
cat > /etc/systemd/system/x11vnc.service << 'X11VNC'
[Unit]
Description=x11vnc VNC Server (hybrid: :0 oder :1)
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
ExecStart=/opt/ilija-os/x11vnc-smart.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
X11VNC

# novnc.service – WebSocket-Proxy, macht VNC über HTTPS/WS im Browser nutzbar
cat > /etc/systemd/system/novnc.service << 'NOVNC'
[Unit]
Description=noVNC WebSocket Proxy (Headless-Fallback)
After=x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
ExecStart=/usr/bin/websockify --web=/usr/share/novnc 6080 localhost:5900
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
NOVNC

# x11vnc-desktop.service – zweiter VNC-Server, der DIREKT an die echte
# User-Session (:0) andockt. Laeuft als root, damit er die SDDM-Xauthority
# in /run/sddm/ lesen kann. Bindet auf Port 5901.
X11VNC_DESKTOP_SH=/opt/ilija-os/x11vnc-desktop.sh
if [ -f "$ILIJA_DIR/system/x11vnc-desktop.sh" ]; then
    cp "$ILIJA_DIR/system/x11vnc-desktop.sh" "$X11VNC_DESKTOP_SH"
    chmod 755 "$X11VNC_DESKTOP_SH"
fi
cat > /etc/systemd/system/x11vnc-desktop.service << 'X11VNC_D'
[Unit]
Description=x11vnc VNC Server (User-Desktop :0)
After=sddm.service graphical.target

[Service]
Type=simple
User=root
Environment=PORT=5901
ExecStart=/opt/ilija-os/x11vnc-desktop.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
X11VNC_D

# novnc-desktop.service – zweiter WebSocket-Proxy, 6081 -> localhost:5901
cat > /etc/systemd/system/novnc-desktop.service << 'NOVNC_D'
[Unit]
Description=noVNC WebSocket Proxy (Echter Desktop)
After=x11vnc-desktop.service
Requires=x11vnc-desktop.service

[Service]
Type=simple
ExecStart=/usr/bin/websockify --web=/usr/share/novnc 6081 localhost:5901
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
NOVNC_D

systemctl daemon-reload
systemctl enable xvfb.service x11vnc.service novnc.service \
                 x11vnc-desktop.service novnc-desktop.service >/dev/null 2>&1
systemctl restart xvfb.service x11vnc.service novnc.service \
                  x11vnc-desktop.service novnc-desktop.service >/dev/null 2>&1 || true
ok "noVNC auf Port 6080 (Headless) + 6081 (Echter Desktop) verfügbar"

# ----------------------------------------------------------------------- 8. Start
say "8/8 Dienst starten"

# Finaler chown: alle data/-Files und baileys-bridge/-Artefakte an TARGET_USER
# (manche werden während des Script-Laufs mit root erzeugt, der Dienst läuft
# aber als TARGET_USER und bekäme sonst PermissionError beim Schreiben)
chown -R "$TARGET_USER:$TARGET_USER" /opt/ilija-os

systemctl start ilija.service
if [ -f /etc/systemd/system/whatsapp-bridge.service ]; then
    systemctl start whatsapp-bridge.service 2>/dev/null || true
fi
sleep 3
if systemctl is-active --quiet ilija.service; then
    ok "ilija.service läuft"
else
    warn "ilija.service nicht aktiv – journalctl -u ilija prüfen"
fi

# ----------------------------------------------------------------------- Fertig
echo ""
echo -e "${GREEN}${BOLD}"
cat <<'DONE'
  ╔════════════════════════════════════════════════════════════╗
  ║                                                            ║
  ║     Ilija OS Installation abgeschlossen                    ║
  ║                                                            ║
  ╚════════════════════════════════════════════════════════════╝
DONE
echo -e "${RESET}"

LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo -e "${CYAN}So startest du Ilija:${RESET}"
echo "  • Eines der Icons (Chat / DMS / Kalender / Workflow / Cloud) anklicken"
echo "  • Oder im Browser: http://localhost:5001 (bzw. http://${LOCAL_IP}:5001 von einem anderen Gerät)"
echo ""
echo -e "${CYAN}API-Keys:${RESET}     im Web-UI unter Einstellungen eintragen"
echo -e "${CYAN}Boot-Splash:${RESET}  wird nach dem nächsten Neustart aktiv"
echo -e "${CYAN}Auto-Update:${RESET}  täglich 03:00 Uhr, oder im Web-UI der Update-Button"
echo ""
echo "Neustart empfohlen (für Plymouth-Boot-Splash + Autostart-Test):"
echo "  sudo reboot"
echo ""
