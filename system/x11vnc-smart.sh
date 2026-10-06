#!/bin/bash
# x11vnc-smart.sh — Hybrid VNC-Launcher fuer Ilija OS.
#
# Phase 1: 60s auf echte User-Session auf :0 warten → exec x11vnc an :0
# Phase 2: Fallback auf :1 (Xvfb) + kontinuierliche Hintergrund-Ueberwachung
#          von :0. Sobald :0 verfuegbar wird (z.B. User loggt sich ein, oder
#          SDDM-Session kommt spaet hoch), wechseln wir dynamisch auf :0.
#
# Diese Datei liegt im Repo (system/x11vnc-smart.sh) und wird vom Installer
# bzw. Update-Script nach /opt/ilija-os/x11vnc-smart.sh kopiert.

# ---- Phase 1: Initial-Warte auf :0 --------------------------------------
for i in $(seq 1 60); do
    # timeout 2 verhindert dass xdpyinfo auf headless-Systemen (Thin-Clients
    # ohne Monitor) ewig in poll() haengt und den gesamten Loop blockiert.
    if timeout 2 bash -c 'DISPLAY=:0 xdpyinfo >/dev/null 2>&1'; then
        echo "[x11vnc] Verbinde mit :0 (Versuch $i)" | systemd-cat -t x11vnc
        exec /usr/bin/x11vnc -display :0 -forever -nopw -listen localhost -rfbport 5900
    fi
    sleep 1
done

# ---- Phase 2: Fallback auf :1 + Monitor-Loop fuer :0 --------------------
echo "[x11vnc] Fallback auf :1 (Xvfb), ueberwache weiter :0" | systemd-cat -t x11vnc
/usr/bin/x11vnc -display :1 -forever -nopw -listen localhost -rfbport 5900 &
VNC_PID=$!

while true; do
    sleep 10
    # :0 verfuegbar geworden? -> Wechsel
    if timeout 2 bash -c 'DISPLAY=:0 xdpyinfo >/dev/null 2>&1'; then
        echo "[x11vnc] :0 ist jetzt verfuegbar – wechsle von :1 auf :0" | systemd-cat -t x11vnc
        kill "$VNC_PID" 2>/dev/null
        wait "$VNC_PID" 2>/dev/null
        exec /usr/bin/x11vnc -display :0 -forever -nopw -listen localhost -rfbport 5900
    fi
    # Falls x11vnc auf :1 aus irgendeinem Grund gestorben ist, neu starten
    if ! kill -0 "$VNC_PID" 2>/dev/null; then
        echo "[x11vnc] x11vnc auf :1 war weg - starte neu" | systemd-cat -t x11vnc
        /usr/bin/x11vnc -display :1 -forever -nopw -listen localhost -rfbport 5900 &
        VNC_PID=$!
    fi
done
