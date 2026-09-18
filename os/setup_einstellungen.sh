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
Name=Ilija Einstellungen
Comment=Kalender und Sync konfigurieren
Exec=xdg-open http://localhost:5001/einstellungen
Icon=preferences-system
Terminal=false
StartupNotify=false
EOF

chmod +x "$SHORTCUT"
chown manuel:manuel "$SHORTCUT"
# GNOME: Shortcut als vertrauenswürdig markieren
sudo -u manuel gio set "$SHORTCUT" metadata::trusted true 2>/dev/null || true

echo "✅ Shortcut erstellt: $SHORTCUT"
