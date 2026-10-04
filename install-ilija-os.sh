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

# ----------------------------------------------------------------------- 7b. Desktop-Integration
say "7b/8 Desktop-Integration (Menü-Eintrag, Icon, Autostart)"

# .desktop-Datei fuer Menue und Starter – benutzt xdg-open auf die lokale URL,
# so dass der Default-Browser des Users geoeffnet wird (Firefox, Chromium, ...).
cat > /usr/share/applications/ilija-os.desktop << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Ilija OS
GenericName=KI-Assistent
Comment=Dein persoenlicher KI-Assistent – lokal und privat
Exec=xdg-open http://localhost:5001
Terminal=false
Categories=Network;WebBrowser;Office;
Keywords=KI;AI;Assistent;Chat;DMS;Ilija;
StartupNotify=true
DESKTOP

# Icon – wenn das Repo ein branding/icon hat, nehmen wir das, sonst Generisch
if [ -f "$ILIJA_DIR/branding/ilija-icon.png" ]; then
    cp "$ILIJA_DIR/branding/ilija-icon.png" /usr/share/icons/hicolor/256x256/apps/ilija-os.png 2>/dev/null || true
    echo "Icon=ilija-os" >> /usr/share/applications/ilija-os.desktop
    gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
else
    echo "Icon=applications-internet" >> /usr/share/applications/ilija-os.desktop
fi

# Autostart im User-Home: Browser oeffnet beim Login die Ilija-Web-UI
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cp /usr/share/applications/ilija-os.desktop "$AUTOSTART_DIR/ilija-os.desktop"
# Autostart erst 5 Sekunden nach Login, damit Service bis dahin laeuft
sed -i 's|^Exec=.*|Exec=sh -c "sleep 5; xdg-open http://localhost:5001"|' \
    "$AUTOSTART_DIR/ilija-os.desktop"
chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.config/autostart"

# Desktop-Icon fuer den User (optional, falls LXQt/XFCE Desktop-Icons zeigen)
DESKTOP_DIR="$TARGET_HOME/Desktop"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$TARGET_HOME/Schreibtisch"
if [ -d "$DESKTOP_DIR" ]; then
    cp /usr/share/applications/ilija-os.desktop "$DESKTOP_DIR/ilija-os.desktop"
    chmod +x "$DESKTOP_DIR/ilija-os.desktop"
    chown "$TARGET_USER:$TARGET_USER" "$DESKTOP_DIR/ilija-os.desktop"
    # LXQt/LXDE: "trusted" Flag setzen damit das Icon nicht grau mit Warnhinweis bleibt
    sudo -u "$TARGET_USER" gio set "$DESKTOP_DIR/ilija-os.desktop" "metadata::trusted" true 2>/dev/null || true
fi

update-desktop-database >/dev/null 2>&1 || true
ok "Menü-Eintrag + Autostart + Desktop-Icon eingerichtet"

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
echo -e "${CYAN}So startest du Ilija:${RESET}"
echo "  • Icon 'Ilija OS' auf dem Desktop oder im Startmenü anklicken"
echo "  • Oder im Browser: http://localhost:5001 (bzw. http://${LOCAL_IP}:5001 von einem anderen Gerät)"
echo "  • Beim nächsten Login startet Ilija automatisch im Standard-Browser"
echo ""
echo -e "${CYAN}API-Keys:${RESET}     im Web-UI unter Einstellungen eintragen"
echo -e "${CYAN}Boot-Splash:${RESET}  wird nach dem nächsten Neustart aktiv"
echo -e "${CYAN}Auto-Update:${RESET}  täglich 03:00 Uhr, oder im Web-UI der Update-Button"
echo ""
echo "Neustart empfohlen (für Plymouth-Boot-Splash + Autostart-Test):"
echo "  sudo reboot"
echo ""
