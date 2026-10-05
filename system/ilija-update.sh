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

    # Self-Update: neue Version dieses Skripts aus Repo übernehmen
    NEW_SCRIPT="$ILIJA_DIR/system/ilija-update.sh"
    if [ -f "$NEW_SCRIPT" ] && ! cmp -s "$NEW_SCRIPT" "$UPDATE_SCRIPT"; then
        echo "--- Update-Skript selbst aktualisieren ---"
        sudo cp "$NEW_SCRIPT" "$UPDATE_SCRIPT"
        sudo chmod +x "$UPDATE_SCRIPT"
        echo "--- Update-Skript aktualisiert (wird beim naechsten Update aktiv) ---"
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
