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

# ----------------------------------------------------------------------- 1. System-Deps
say "1/8 System-Abhängigkeiten installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev build-essential \
    git curl wget \
    plymouth plymouth-themes \
    tesseract-ocr tesseract-ocr-deu \
    portaudio19-dev \
    chromium-browser 2>/dev/null \
    || apt-get install -y -qq chromium
ok "System-Pakete installiert"

# ----------------------------------------------------------------------- 2. Python-venv
say "2/8 Python-venv + Ilija-Dependencies"
cd "$ILIJA_DIR"
if [ ! -d venv ]; then
    sudo -u "$TARGET_USER" python3 -m venv venv
    ok "venv angelegt"
else
    ok "venv existiert bereits"
fi

sudo -u "$TARGET_USER" bash -c "source venv/bin/activate && pip install --quiet --upgrade pip"
if [ -f requirements.txt ]; then
    sudo -u "$TARGET_USER" bash -c "source venv/bin/activate && pip install --quiet -r requirements.txt"
    ok "requirements.txt installiert"
fi

# ----------------------------------------------------------------------- 3. Ownership + .env
say "3/8 /opt/ilija-os an $TARGET_USER übergeben"
chown -R "$TARGET_USER:$TARGET_USER" /opt/ilija-os
ok "chown abgeschlossen"

if [ ! -f .env ] && [ -f .env.example ]; then
    sudo -u "$TARGET_USER" cp .env.example .env
    info "   .env angelegt – API-Keys trägst du nach dem Setup unter Einstellungen ein."
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
grep -q '^FRAMEBUFFER=y' /etc/initramfs-tools/initramfs.conf \
    || echo 'FRAMEBUFFER=y' >> /etc/initramfs-tools/initramfs.conf

GPU_INFO=$(lspci 2>/dev/null | grep -iE 'vga|display|3d' || echo "")
GPU_MODS=""
if   echo "$GPU_INFO" | grep -qi 'amd\|ati\|radeon'; then GPU_MODS="amdgpu radeon"
elif echo "$GPU_INFO" | grep -qi 'intel';            then GPU_MODS="i915"
elif echo "$GPU_INFO" | grep -qi 'nvidia';           then GPU_MODS="nouveau"
fi
for m in $GPU_MODS; do
    grep -q "^$m\$" /etc/initramfs-tools/modules || echo "$m" >> /etc/initramfs-tools/modules
done
info "   GPU erkannt: ${GPU_MODS:-keine spezifischen Module nötig}"
update-initramfs -u -k all >/dev/null 2>&1 && ok "initramfs neu gebaut"

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
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ilija
$TARGET_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart ilija
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/update-initramfs
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/update-alternatives
SUDO
chmod 440 /etc/sudoers.d/ilija-update-rules
ok "sudoers-Regeln für passwortloses Update installiert"

# Cron-Job: nächtliches Auto-Update
if [ -f "$UPDATE_SCRIPT" ]; then
    CRON_LINE="0 3 * * * $UPDATE_SCRIPT >> $TARGET_HOME/ilija-update.log 2>&1"
    (sudo -u "$TARGET_USER" crontab -l 2>/dev/null | grep -v ilija-update.sh; echo "$CRON_LINE") \
        | sudo -u "$TARGET_USER" crontab -
    ok "Cron-Job eingerichtet (täglich 03:00 Uhr)"
fi

# ----------------------------------------------------------------------- 8. Start
say "8/8 Dienst starten"
systemctl start ilija.service
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
echo -e "${CYAN}Web-UI:${RESET}       http://${LOCAL_IP}:5001"
echo -e "${CYAN}API-Keys:${RESET}     im Browser unter Einstellungen eintragen"
echo -e "${CYAN}Boot-Splash:${RESET}  wird nach dem nächsten Neustart aktiv"
echo -e "${CYAN}Auto-Update:${RESET}  täglich 03:00 Uhr, oder im Web-UI der Update-Button"
echo ""
echo "Neustart empfohlen (für Plymouth-Boot-Splash):"
echo "  sudo reboot"
echo ""
