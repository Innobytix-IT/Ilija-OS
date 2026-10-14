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

# User-spezifische Config-Dateien vor einem Pull schuetzen. Sie liegen pro
# Installation (DMS-Pfad, SMTP-Passwort, Telegram-Token, WhatsApp-Prompt).
# Mit skip-worktree ignoriert git lokale Modifikationen UND zieht eine
# Deletion (seit sie in .gitignore stehen) nicht lokal durch.
# Erzeugt die Dateien beim ersten Lauf aus der example-Vorlage.
USER_CONFIGS=(
    "data/dms/dms_config.json:data/dms/dms_config.example.json"
    "data/email/email_config.json:data/email/email_config.example.json"
    "data/telegram/telegram_config.json:data/telegram/telegram_config.example.json"
    "data/whatsapp/whatsapp_config.json:data/whatsapp/whatsapp_config.example.json"
)
for pair in "${USER_CONFIGS[@]}"; do
    real="${pair%%:*}"
    example="${pair##*:}"
    # Fehlt die echte Datei aber die Vorlage ist da? Dann aus Vorlage anlegen.
    if [ ! -f "$real" ] && [ -f "$example" ]; then
        cp "$example" "$real"
        echo "--- $real aus Vorlage angelegt ---"
    fi
    # Falls git die Datei noch als tracked kennt (Altinstallation vor der
    # .gitignore-Umstellung), vor dem Pull auf skip-worktree setzen.
    if git ls-files --error-unmatch -- "$real" >/dev/null 2>&1; then
        git update-index --skip-worktree -- "$real" 2>/dev/null || true
    fi
done

BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")
git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

# ---- Pre-Update-Selbsttest -------------------------------------
# Prueft ob Ilija AKTUELL (vor dem Update) gesund ist. Wenn nicht,
# Rollback-Automatik ausschalten -- sonst steckt der User fuer immer
# in einer kaputten Version fest (jedes Update wuerde zurueckgerollt
# werden auf eine Version, die den Selbsttest auch nicht besteht).
ROLLBACK_SCHUTZ="an"
if [ -f "$ILIJA_DIR/system/update_selbsttest.py" ]; then
    echo "--- Pre-Update-Selbsttest ---"
    if ! python3 "$ILIJA_DIR/system/update_selbsttest.py" pre; then
        echo "WARNUNG: System war bereits VOR dem Update defekt."
        echo "         Update wird dennoch ausgefuehrt, aber ohne"
        echo "         automatischen Rollback -- sonst steckt die"
        echo "         Installation fest in einer kaputten Version."
        ROLLBACK_SCHUTZ="aus"
    fi
fi

if [ "$LOCAL" != "$REMOTE" ]; then
    git pull origin main --quiet
    AFTER=$(git rev-parse HEAD)

    SHORT_BEFORE=$(git rev-parse --short "$BEFORE" 2>/dev/null || echo "?")
    SHORT_AFTER=$(git rev-parse --short "$AFTER")
    echo "--- git pull: $SHORT_BEFORE -> $SHORT_AFTER ---"
    # Liste der neuen Commits (max. 10) als Mini-Changelog
    CHANGELOG=""
    if [ -n "$BEFORE" ]; then
        CHANGELOG=$(git log --oneline "$BEFORE..$AFTER" 2>/dev/null | head -10)
        echo "$CHANGELOG" | sed 's/^/    /'
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

    # AHPT-Agent-Dateien aus vendor/ nach /opt/ilija-os/ahpt-agent/ syncen.
    # Idempotent: Nur kopieren wenn Datei neuer ist. Melanies Odyssee vom
    # 08.10.2026 soll kein User mehr durchmachen – Ilija bringt die Dateien
    # out-of-the-box mit, Einrichtung ueber die UI.
    AHPT_SRC="$ILIJA_DIR/vendor/ahpt"
    AHPT_DST="/opt/ilija-os/ahpt-agent"
    if [ -d "$AHPT_SRC" ]; then
        AHPT_UPDATED=0
        mkdir -p "$AHPT_DST/handler" "$AHPT_DST/portal"
        for f in "$AHPT_SRC"/*.py "$AHPT_SRC"/relay.php \
                 "$AHPT_SRC"/htaccess-beispiel "$AHPT_SRC"/htaccess-ablage-beispiel \
                 "$AHPT_SRC"/config-beispiel.toml "$AHPT_SRC"/README.md ; do
            [ -f "$f" ] || continue
            base=$(basename "$f")
            if ! cmp -s "$f" "$AHPT_DST/$base" 2>/dev/null; then
                cp "$f" "$AHPT_DST/$base" && AHPT_UPDATED=1
            fi
        done
        for f in "$AHPT_SRC"/handler/*.py ; do
            [ -f "$f" ] || continue
            base=$(basename "$f")
            if ! cmp -s "$f" "$AHPT_DST/handler/$base" 2>/dev/null; then
                cp "$f" "$AHPT_DST/handler/$base" && AHPT_UPDATED=1
            fi
        done
        for f in "$AHPT_SRC"/portal/*.html "$AHPT_SRC"/portal/*.js "$AHPT_SRC"/portal/*.py ; do
            [ -f "$f" ] || continue
            base=$(basename "$f")
            if ! cmp -s "$f" "$AHPT_DST/portal/$base" 2>/dev/null; then
                cp "$f" "$AHPT_DST/portal/$base" && AHPT_UPDATED=1
            fi
        done
        if [ "$AHPT_UPDATED" = "1" ]; then
            chmod +x "$AHPT_DST"/*.py 2>/dev/null || true
            echo "--- AHPT-Agent-Dateien aktualisiert ---"
        fi
        # cryptography-Lib (fuer noise_ik) sicherstellen – nur beim ersten Mal
        if ! "$ILIJA_DIR/venv/bin/python" -c "import cryptography" 2>/dev/null; then
            echo "--- AHPT: cryptography installieren ---"
            "$ILIJA_DIR/venv/bin/pip" install --quiet cryptography 2>&1 | tail -3
        fi
        # Falls ein laufender AHPT-Agent-User-Service existiert, nach dem
        # Dateien-Sync neustarten damit er die neue Version nutzt.
        if [ "$AHPT_UPDATED" = "1" ]; then
            HOST_TAG=$(hostname -s | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/^-*//; s/-*$//')
            SVC="ahpt-${HOST_TAG:-agent}"
            if systemctl --user list-unit-files "${SVC}.service" --no-legend 2>/dev/null | grep -q "$SVC"; then
                systemctl --user restart "$SVC" 2>/dev/null || true
                echo "--- $SVC neugestartet (neue Agent-Version aktiv) ---"
            fi
        fi
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

    # Sudoers-Regel fuer manuellen noVNC-Display-Umschalter (UI-Button).
    # Legt /etc/systemd/system/x11vnc.service.d/override.conf an bzw. ab,
    # macht daemon-reload. Idempotent.
    X11VNC_SWITCH_LINE="$USER ALL=(ALL) NOPASSWD: /bin/mkdir /etc/systemd/system/x11vnc.service.d, /usr/bin/mkdir /etc/systemd/system/x11vnc.service.d, /bin/cp /tmp/x11vnc-override.conf.* /etc/systemd/system/x11vnc.service.d/override.conf, /usr/bin/cp /tmp/x11vnc-override.conf.* /etc/systemd/system/x11vnc.service.d/override.conf, /bin/rm -f /etc/systemd/system/x11vnc.service.d/override.conf, /usr/bin/rm -f /etc/systemd/system/x11vnc.service.d/override.conf, /bin/systemctl daemon-reload, /usr/bin/systemctl daemon-reload"
    if [ -f "$SUDOERS_FILE" ] && ! sudo grep -q "x11vnc.service.d" "$SUDOERS_FILE" 2>/dev/null; then
        echo "--- sudoers-Regel fuer noVNC-Display-Umschalter nachtragen ---"
        echo "$X11VNC_SWITCH_LINE" | sudo tee -a "$SUDOERS_FILE" >/dev/null 2>&1 \
            && sudo chmod 440 "$SUDOERS_FILE" 2>/dev/null \
            && echo "--- noVNC-Switch-sudoers installiert ---" \
            || echo "WARNUNG: noVNC-Switch-sudoers konnte nicht nachgetragen werden."
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

    # WICHTIG: Erst Abschluss-Meldung ausgeben, dann Service neustarten
    # und Selbsttest fahren. Der Restart killt die SSE-Verbindung zum
    # Web-UI; was DANACH noch im Log steht, sieht der User im Log-Modal
    # nicht mehr (sondern erst nach erneutem Oeffnen).
    echo "--- Ilija OS aktualisiert auf $SHORT_AFTER ---"
    echo "=== Fertig ==="
    sudo systemctl restart ilija 2>/dev/null || true

    # ---- Post-Update-Selbsttest + Rollback-Automatik ----------
    if [ "$ROLLBACK_SCHUTZ" = "an" ] && \
       [ -f "$ILIJA_DIR/system/update_selbsttest.py" ]; then
        echo "--- Post-Update-Selbsttest ---"
        if python3 "$ILIJA_DIR/system/update_selbsttest.py" post; then
            echo "--- Selbsttest bestanden – Update bleibt aktiv ---"
            python3 "$ILIJA_DIR/system/update_history_eintrag.py" \
                --von "$BEFORE" --nach "$AFTER" --status ok \
                --changelog "$CHANGELOG" 2>/dev/null || true
        else
            GRUND=$(cat /tmp/ilija_selbsttest_grund.txt 2>/dev/null || echo "unbekannt")
            echo "!!! ROLLBACK !!! Selbsttest fehlgeschlagen:"
            echo "$GRUND" | sed 's/^/    /'
            # Alte Version wiederherstellen
            git -C "$ILIJA_DIR" reset --hard "$BEFORE" --quiet
            # Alte Deps wiederherstellen
            source "$ILIJA_DIR/venv/bin/activate"
            pip install -r "$ILIJA_DIR/requirements.txt" --quiet 2>&1 | tail -3
            # Service nochmal durchstarten
            sudo systemctl restart ilija 2>/dev/null || true
            # In History schreiben + Benachrichtigung erzeugen
            python3 "$ILIJA_DIR/system/update_history_eintrag.py" \
                --von "$BEFORE" --nach "$AFTER" --status rollback \
                --grund "$GRUND" --changelog "$CHANGELOG" 2>/dev/null || true
            echo "--- Rollback abgeschlossen, zurueck auf $SHORT_BEFORE ---"
        fi
    else
        # Entweder Selbsttest-Script fehlt oder Pre-Check hatte den Schutz
        # ausgeschaltet (System war schon vorher kaputt).
        python3 "$ILIJA_DIR/system/update_history_eintrag.py" \
            --von "$BEFORE" --nach "$AFTER" --status ok \
            --changelog "$CHANGELOG" 2>/dev/null || true
    fi
    exit 0
else
    echo "--- Ilija OS ist aktuell (kein Update noetig) ---"
fi
echo "=== Fertig ==="
