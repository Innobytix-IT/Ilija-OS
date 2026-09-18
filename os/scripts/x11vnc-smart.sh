#!/bin/bash
for i in $(seq 1 60); do
    if DISPLAY=:0 xdpyinfo >/dev/null 2>&1; then
        echo "[x11vnc] Verbinde mit :0 (Versuch $i)" | systemd-cat -t x11vnc
        exec /usr/bin/x11vnc -display :0 -forever -nopw -listen localhost -rfbport 5900
    fi
    sleep 1
done
echo "[x11vnc] Fallback auf :1 (Xvfb)" | systemd-cat -t x11vnc
exec /usr/bin/x11vnc -display :1 -forever -nopw -listen localhost -rfbport 5900
