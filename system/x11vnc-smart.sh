#!/bin/bash
# x11vnc-smart.sh — Hybrid VNC-Launcher fuer Ilija OS.
# Versucht erst eine echte User-Session auf :0, faellt sonst auf :1 (Xvfb).
#
# Diese Datei liegt im Repo (system/x11vnc-smart.sh) und wird vom
# Installer bzw. Update-Script nach /opt/ilija-os/x11vnc-smart.sh kopiert.

for i in $(seq 1 60); do
    # timeout 2 verhindert dass xdpyinfo auf headless-Systemen (Thin-Clients
    # ohne Monitor) ewig in poll() haengt und den gesamten Loop blockiert.
    if timeout 2 bash -c 'DISPLAY=:0 xdpyinfo >/dev/null 2>&1'; then
        echo "[x11vnc] Verbinde mit :0 (Versuch $i)" | systemd-cat -t x11vnc
        exec /usr/bin/x11vnc -display :0 -forever -nopw -listen localhost -rfbport 5900
    fi
    sleep 1
done
echo "[x11vnc] Fallback auf :1 (Xvfb)" | systemd-cat -t x11vnc
exec /usr/bin/x11vnc -display :1 -forever -nopw -listen localhost -rfbport 5900
