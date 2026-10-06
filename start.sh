#!/bin/bash
# Hybrides Display-Picking: :0 (echter Desktop) falls verfuegbar, sonst :1 (Xvfb)
#
# WICHTIG: xdpyinfo ohne Timeout kann auf manchen Systemen unbegrenzt haengen
# (beobachtet auf Futro-Thin-Client mit AMD Mullins: X-Server existiert, aber
# xdpyinfo blockiert bis zum St.-Nimmerleins-Tag). Dadurch wurde der ganze
# ilija-Service nie gestartet. Timeout 3s ist deshalb Pflicht.
if timeout 3 bash -c 'DISPLAY=:0 xdpyinfo >/dev/null 2>&1'; then
    export DISPLAY=:0
    echo "[Ilija] Starte mit echtem Display :0" | systemd-cat -t ilija
else
    export DISPLAY=:1
    echo "[Ilija] Starte mit Xvfb :1 (headless)" | systemd-cat -t ilija
fi
exec /opt/ilija-os/ilija/venv/bin/python web_server.py
