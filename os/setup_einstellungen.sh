#!/usr/bin/env bash
# Erstellt den Desktop-Shortcut für die Einstellungsseite.
# Aufruf: sudo bash /opt/ilija-os/ilija/os/setup_einstellungen.sh

DESKTOP="/home/manuel/Desktop"
SHORTCUT="$DESKTOP/ilija-einstellungen.desktop"

mkdir -p "$DESKTOP"
cat > "$SHORTCUT" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Einstellungen
GenericName=Ilija OS
Comment=Einstellungen – Ilija OS
Exec=/usr/local/bin/ilija-app http://localhost:5001/einstellungen ilija-einstellungen
Icon=/usr/share/ilija-os/branding/assets/ilija-app-icon.png
Terminal=false
Categories=Settings;
StartupWMClass=ilija-einstellungen
StartupNotify=true
EOF

chmod +x "$SHORTCUT"
chown manuel:manuel "$SHORTCUT"
sudo -u manuel gio set "$SHORTCUT" metadata::trusted true 2>/dev/null || true

echo "✅ Shortcut erstellt: $SHORTCUT"
