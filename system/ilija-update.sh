#!/bin/bash
# Ilija OS Update-Skript – wird vom Web-UI-Update-Button aufgerufen.
# WICHTIG: Diese Datei aktualisiert sich SELBST aus system/ilija-update.sh
# im Repo. Änderungen bitte dort machen und via git pushen.
export DEBIAN_FRONTEND=noninteractive
echo "=== Ilija OS Update gestartet ==="

ILIJA_DIR=/opt/ilija-os/ilija
UPDATE_SCRIPT=/opt/ilija-os/ilija-update.sh

echo "--- System-Update (apt) ---"
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get autoremove -y -qq
echo "--- System-Update abgeschlossen ---"

echo "--- Ilija OS Update (GitHub) ---"
git config --global --add safe.directory "$ILIJA_DIR" 2>/dev/null || true
cd "$ILIJA_DIR"
BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")
git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    git pull origin main --quiet
    AFTER=$(git rev-parse HEAD)

    SHORT_BEFORE=$(git rev-parse --short "$BEFORE" 2>/dev/null || echo "?")
    SHORT_AFTER=$(git rev-parse --short "$AFTER")
    echo "--- git pull: $SHORT_BEFORE -> $SHORT_AFTER ---"
    # Liste der neuen Commits (max. 10) als Mini-Changelog
    if [ -n "$BEFORE" ]; then
        git log --oneline "$BEFORE..$AFTER" 2>/dev/null | head -10 | sed 's/^/    /'
    fi

    # Python-Abhängigkeiten
    source "$ILIJA_DIR/venv/bin/activate"
    pip install -r "$ILIJA_DIR/requirements.txt" --quiet

    # Plymouth-Theme aktualisieren, falls sich system/plymouth/ geändert hat
    PLYMOUTH_SRC="$ILIJA_DIR/system/plymouth"
    PLYMOUTH_DST="/usr/share/plymouth/themes/ilija"
    if [ -d "$PLYMOUTH_SRC" ] && [ -n "$BEFORE" ]; then
        if git diff --name-only "$BEFORE" "$AFTER" 2>/dev/null | grep -q '^system/plymouth/'; then
            echo "--- Plymouth-Theme aktualisieren ---"
            sudo mkdir -p "$PLYMOUTH_DST/spinner"
            sudo cp -r "$PLYMOUTH_SRC"/. "$PLYMOUTH_DST/"
            sudo find "$PLYMOUTH_DST" -type f -exec chmod 644 {} \;
            sudo update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
                default.plymouth "$PLYMOUTH_DST/ilija.plymouth" 200 2>/dev/null || true
            sudo update-alternatives --set default.plymouth "$PLYMOUTH_DST/ilija.plymouth" 2>/dev/null || true
            sudo update-initramfs -u
            echo "--- Plymouth-Theme aktualisiert (Neustart empfohlen) ---"
        fi
    fi

    # Runtime-Scripts aus dem Repo an ihre Ziele unter /opt/ilija-os/
    # synchronisieren. Datei gehoert laut Installer dem TARGET_USER, der
    # ilija-Service laeuft als derselbe User – also cp OHNE sudo.
    # Hier aufgelistet jedes Script das NICHT direkt aus dem Repo laeuft
    # sondern separat deployed wird. Wenn du ein neues hinzufuegst, einfach
    # unten einen Eintrag "repo-pfad:ziel-pfad" ergaenzen.
    deploy_pair() {
        local src="$ILIJA_DIR/$1"
        local dst="$2"
        local label="$3"
        if [ -f "$src" ] && ! cmp -s "$src" "$dst" 2>/dev/null; then
            echo "--- $label aktualisieren ---"
            if cp "$src" "$dst" 2>/dev/null && chmod +x "$dst" 2>/dev/null; then
                echo "--- $label aktualisiert ---"
                return 0
            else
                echo "WARNUNG: $dst konnte nicht aktualisiert werden."
                echo "         Rechte pruefen: ls -l $dst"
                echo "         Manueller Fix:  sudo chown \$USER:\$USER $dst"
                return 1
            fi
        fi
        return 0
    }

    deploy_pair "system/ilija-update.sh"  "$UPDATE_SCRIPT"                 "Update-Skript"
    deploy_pair "system/show-setup-wizard.sh" "/opt/ilija-os/show-setup-wizard.sh" "Setup-Wizard-Launcher"

    # AI-API-Proxy: venv + requirements + Service-File nachinstallieren falls fehlt
    AI_PROXY_SRC="$ILIJA_DIR/vendor/ai-api-proxy"
    if [ -d "$AI_PROXY_SRC" ]; then
        AI_PROXY_VENV="$AI_PROXY_SRC/venv"
        if [ ! -d "$AI_PROXY_VENV" ]; then
            echo "--- AI-Proxy venv anlegen ---"
            python3 -m venv "$AI_PROXY_VENV" 2>&1 | tail -3
            "$AI_PROXY_VENV/bin/pip" install --quiet -r "$AI_PROXY_SRC/requirements.txt" 2>&1 | tail -3
            echo "--- AI-Proxy Deps installiert ---"
        fi
        # Service-File-Deployment (idempotent)
        AI_PROXY_SERVICE=/etc/systemd/system/ai-api-proxy.service
        AI_PROXY_SERVICE_NEW=/tmp/ai-api-proxy.service.new
        cat > "$AI_PROXY_SERVICE_NEW" << AIPROXY
[Unit]
Description=Ilija AI-API-Proxy (OpenAI-kompatibler Gemini-Proxy)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$AI_PROXY_SRC
Environment=port=8642
EnvironmentFile=-$AI_PROXY_SRC/.env
ExecStart=$AI_PROXY_VENV/bin/python -m uvicorn main:app --host 0.0.0.0 --port \${port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
AIPROXY
        if ! cmp -s "$AI_PROXY_SERVICE_NEW" "$AI_PROXY_SERVICE" 2>/dev/null; then
            echo "--- AI-Proxy Service installieren ---"
            if sudo cp "$AI_PROXY_SERVICE_NEW" "$AI_PROXY_SERVICE" 2>/dev/null; then
                sudo systemctl daemon-reload 2>/dev/null || true
                echo "--- AI-Proxy Service installiert ---"
            else
                echo "WARNUNG: AI-Proxy Service nicht installierbar (sudo cp fehlt in sudoers)"
                echo "         Workaround: einmal sudo cp $AI_PROXY_SERVICE_NEW $AI_PROXY_SERVICE"
            fi
        fi
        rm -f "$AI_PROXY_SERVICE_NEW"
    fi

    # Setup-Wizard-Autostart im User-Home anlegen falls fehlt (ohne sudo)
    WIZARD_AUTOSTART="$HOME/.config/autostart/ilija-setup-wizard.desktop"
    if [ -f /opt/ilija-os/show-setup-wizard.sh ] && [ ! -f "$WIZARD_AUTOSTART" ]; then
        mkdir -p "$(dirname "$WIZARD_AUTOSTART")" 2>/dev/null || true
        cat > "$WIZARD_AUTOSTART" << 'WIZARD_AUTOSTART_EOF'
[Desktop Entry]
Type=Application
Name=Ilija OS Einrichtungsassistent
Comment=Oeffnet beim Login den Einrichtungsassistenten (deaktivierbar im Wizard)
Exec=/opt/ilija-os/show-setup-wizard.sh
NoDisplay=true
X-LXQt-Need-Tray=false
X-GNOME-Autostart-enabled=true
WIZARD_AUTOSTART_EOF
        echo "--- Setup-Wizard-Autostart installiert ---"
    fi

    # Startsound deployen – WAV und Autostart-Eintrag, beides ohne sudo.
    # /opt/ilija-os/sounds/ gehoert laut Installer-Finaler-chown dem User.
    SOUND_SRC="$ILIJA_DIR/sounds/Ilija_OS_Start_Sound.wav"
    SOUND_DST="/opt/ilija-os/sounds/startup.wav"
    if [ -f "$SOUND_SRC" ] && ! cmp -s "$SOUND_SRC" "$SOUND_DST" 2>/dev/null; then
        echo "--- Startsound aktualisieren ---"
        mkdir -p "$(dirname "$SOUND_DST")" 2>/dev/null || true
        if cp "$SOUND_SRC" "$SOUND_DST" 2>/dev/null; then
            chmod 644 "$SOUND_DST" 2>/dev/null || true
            echo "--- Startsound aktualisiert ---"
        else
            echo "WARNUNG: Startsound nicht nach $SOUND_DST kopierbar"
        fi
    fi
    # Audio-Player fuer den Startsound sicherstellen (paplay kommt aus
    # pulseaudio-utils, ist unter Lubuntu nicht per Default dabei).
    # sudo apt-get ist in der sudoers mit NOPASSWD erlaubt – kein Prompt.
    if [ -f "$SOUND_DST" ] && ! command -v paplay >/dev/null 2>&1; then
        echo "--- pulseaudio-utils fuer Startsound nachinstallieren ---"
        sudo apt-get install -y -qq pulseaudio-utils 2>/dev/null \
            && echo "--- paplay verfuegbar ---" \
            || echo "WARNUNG: paplay konnte nicht installiert werden"
    fi
    # Autostart-Eintrag anlegen falls fehlt (im User-Home, ohne sudo)
    AUTOSTART_FILE="$HOME/.config/autostart/ilija-startsound.desktop"
    if [ -f "$SOUND_DST" ] && [ ! -f "$AUTOSTART_FILE" ]; then
        mkdir -p "$(dirname "$AUTOSTART_FILE")" 2>/dev/null || true
        cat > "$AUTOSTART_FILE" << 'SOUND_AUTOSTART'
[Desktop Entry]
Type=Application
Name=Ilija OS Startsound
Comment=Spielt den Ilija-OS-Jingle einmal beim Login
Exec=bash -c 'sleep 1; paplay --volume=45000 /opt/ilija-os/sounds/startup.wav 2>/dev/null || aplay -q /opt/ilija-os/sounds/startup.wav 2>/dev/null || true'
NoDisplay=true
X-LXQt-Need-Tray=false
X-GNOME-Autostart-enabled=true
SOUND_AUTOSTART
        echo "--- Startsound-Autostart installiert (greift beim naechsten Login) ---"
    fi

    # Sudoers-Regel fuer Platten-Mount/Unmount (DMS+AHPT-Button im Web-UI)
    # Idempotent: nur hinzufuegen falls Zeile noch nicht in der sudoers-Datei
    # steht. Datei existiert seit Installation (siehe install-ilija-os.sh).
    SUDOERS_FILE=/etc/sudoers.d/ilija-update-rules
    PLATTE_LINE="$USER ALL=(ALL) NOPASSWD: /bin/mount /mnt/ilija-ablage, /bin/umount /mnt/ilija-ablage, /usr/bin/mount /mnt/ilija-ablage, /usr/bin/umount /mnt/ilija-ablage"
    if [ -f "$SUDOERS_FILE" ] && ! sudo grep -q "/mnt/ilija-ablage" "$SUDOERS_FILE" 2>/dev/null; then
        echo "--- sudoers-Regel fuer Platten-Auswerfen nachtragen ---"
        if echo "$PLATTE_LINE" | sudo tee -a "$SUDOERS_FILE" >/dev/null 2>&1; then
            sudo chmod 440 "$SUDOERS_FILE" 2>/dev/null || true
            echo "--- sudoers-Regel installiert ---"
        else
            echo "WARNUNG: sudoers-Regel konnte nicht nachgetragen werden."
        fi
    fi

    if deploy_pair "system/x11vnc-smart.sh" "/opt/ilija-os/x11vnc-smart.sh" "noVNC-Launcher"; then
        # Wenn das noVNC-Script neu ist, den VNC-Dienst neu starten damit
        # die neue Logik sofort greift (ohne Reboot).
        if [ -f "$ILIJA_DIR/system/x11vnc-smart.sh" ] && \
           ! cmp -s "$ILIJA_DIR/system/x11vnc-smart.sh" "/opt/ilija-os/x11vnc-smart.sh.applied" 2>/dev/null; then
            sudo systemctl restart x11vnc.service 2>/dev/null || true
            cp "$ILIJA_DIR/system/x11vnc-smart.sh" "/opt/ilija-os/x11vnc-smart.sh.applied" 2>/dev/null || true
        fi
    fi

    # WICHTIG: Erst Abschluss-Meldung ausgeben, dann Service neustarten.
    # Der Restart killt die SSE-Verbindung zum Web-UI; alles was danach
    # kommt, sieht der User nicht mehr.
    echo "--- Ilija OS aktualisiert auf $SHORT_AFTER ---"
    echo "=== Fertig ==="
    sudo systemctl restart ilija 2>/dev/null || true
    exit 0
else
    echo "--- Ilija OS ist aktuell (kein Update noetig) ---"
fi
echo "=== Fertig ==="
