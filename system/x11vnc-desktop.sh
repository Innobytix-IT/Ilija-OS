#!/bin/bash
# x11vnc-desktop.sh — Zweiter x11vnc, der direkt an die echte User-Session
# auf Display :0 andockt (fuer den "Live-Desktop"-noVNC-Button).
#
# Faellt NICHT auf :1 zurueck — wenn kein echter Desktop da ist, wartet er
# bis einer kommt. Fuer den Headless/Openbox-Fallback gibt es x11vnc-smart.sh
# auf Port 5900 (noVNC 6080).
#
# Besonderheit: SDDM erzeugt die Xauthority unter zufaelligem Namen in
# /run/sddm/ (z.B. xauth_EXMyUc). Deshalb nicht -auth guess, sondern den
# aktuellen SDDM-xauth dynamisch finden.
#
# Laeuft als root (im systemd-Service), damit es /run/sddm/* lesen kann.

PORT="${PORT:-5901}"

# Warte bis SDDM-Session + xauth bereit sind (max 10 Min)
for i in $(seq 1 600); do
    XAUTH=$(ls /run/sddm/xauth_* 2>/dev/null | head -1)
    if [ -n "$XAUTH" ] && [ -S /tmp/.X11-unix/X0 ]; then
        echo "[x11vnc-desktop] SDDM-xauth gefunden: $XAUTH (Versuch $i)" | systemd-cat -t x11vnc-desktop
        break
    fi
    sleep 1
done

if [ -z "$XAUTH" ]; then
    echo "[x11vnc-desktop] Keine SDDM-Session nach 10 Min – gebe auf" | systemd-cat -t x11vnc-desktop
    exit 1
fi

exec /usr/bin/x11vnc -display :0 -auth "$XAUTH" \
     -forever -shared -nopw -listen localhost -rfbport "$PORT" \
     -noxdamage -noxfixes
