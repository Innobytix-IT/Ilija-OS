#!/usr/bin/env bash
# Einmalige Installation der Baileys WhatsApp Bridge auf dem EliteBook.
# Aufruf: bash /opt/ilija-os/ilija/os/setup_bridge.sh

set -e
BRIDGE_DIR="/opt/ilija-os/ilija/baileys-bridge"
SERVICE_SRC="/opt/ilija-os/ilija/os/services/whatsapp-bridge.service"
SERVICE_DST="/etc/systemd/system/whatsapp-bridge.service"

echo "==> Node.js prüfen..."
node --version || { echo "FEHLER: node nicht gefunden – bitte installieren"; exit 1; }
npm  --version || { echo "FEHLER: npm nicht gefunden – bitte installieren"; exit 1; }

echo "==> npm install in $BRIDGE_DIR ..."
cd "$BRIDGE_DIR"
npm install

echo "==> systemd-Service installieren..."
cp "$SERVICE_SRC" "$SERVICE_DST"
systemctl daemon-reload
systemctl enable whatsapp-bridge.service

echo ""
echo "====================================================="
echo "  Setup abgeschlossen."
echo "  Jetzt QR-Code scannen:"
echo "    sudo -u ilija node $BRIDGE_DIR/bridge.js"
echo ""
echo "  Wenn eingeloggt (Strg+C drücken), dann starten:"
echo "    sudo systemctl start whatsapp-bridge.service"
echo "    sudo systemctl status whatsapp-bridge.service"
echo "====================================================="
