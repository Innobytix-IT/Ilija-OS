#!/bin/bash
# x11vnc-smart.sh — Hybrid VNC-Launcher fuer Ilija OS.
#
# Strategie:
#   1) 30 Sekunden lang pruefen ob eine User-Session auf :0 bereit ist
#      (Lubuntu-LXQt / SDDM, VirtualBox-GUI, Thin-Client, etc). Wenn ja,
#      daran andocken – x11vnc findet die Xauthority ueber -auth guess.
#   2) Wenn kein echter Desktop auftaucht: Fallback auf :1 (Xvfb). Dort
#      startet openbox als Minimal-Window-Manager, damit der Browser
#      ueber noVNC nicht nur den schwarzen Root-Hintergrund sieht.
#
# -auth guess ist der Schluessel: ohne das scheitert x11vnc an
# MIT-MAGIC-COOKIE und noVNC bleibt schwarz – x11vnc-Prozess laeuft zwar,
# zeigt aber nichts.
#
# Diese Datei liegt im Repo (system/x11vnc-smart.sh) und wird vom
# Installer nach /opt/ilija-os/x11vnc-smart.sh kopiert. Updates ueber
# das Web-UI aktualisieren die aktive Kopie beim naechsten Pull.

# Versuche eine echte User-Session auf :0 zu finden
for i in $(seq 1 30); do
    if DISPLAY=:0 xdpyinfo >/dev/null 2>&1; then
        echo "[x11vnc] Verbinde mit :0 (Versuch $i)" | systemd-cat -t x11vnc
        exec /usr/bin/x11vnc -display :0 -auth guess \
             -forever -shared -nopw -listen localhost -rfbport 5900 \
             -noxdamage -noxfixes
    fi
    sleep 1
done

# Fallback: Xvfb-Desktop auf :1 – braucht Window-Manager damit was zu sehen ist
echo "[x11vnc] Fallback auf :1 (Xvfb) – starte openbox" | systemd-cat -t x11vnc
if ! pgrep -f "openbox.*:1" >/dev/null 2>&1; then
    DISPLAY=:1 openbox-session >/dev/null 2>&1 &
    sleep 1
fi
exec /usr/bin/x11vnc -display :1 \
     -forever -shared -nopw -listen localhost -rfbport 5900 \
     -noxdamage -noxfixes
