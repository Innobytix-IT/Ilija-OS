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
#
# WICHTIG: Script laeuft als root (systemd system-service). Zugriff auf
# einen User-Session-X-Server (SDDM/LXQt) braucht aber die passende
# Xauthority-Datei — die liegt bei SDDM in /run/sddm/xauth_XXXXXX und
# gehoert dem jeweiligen Anmeldenutzer, NICHT root. Ohne diese Datei
# meldet `xdpyinfo :0` als root "connection refused" und der Monitor-Loop
# wechselt nie von :1 auf :0. Deshalb suchen wir die Xauth dynamisch
# (SDDM, LightDM, tmp, User-Home) und uebergeben sie an xdpyinfo und
# x11vnc. Bug entdeckt am 14.10.2026 auf Manuels Futro S720.

_find_xauth_for_0() {
    # Mehrere typische Orte durchprobieren, in Reihenfolge der Haeufigkeit.
    # Shell-Glob kann hier NICHT mit "2>/dev/null" vermischt werden
    # (fuehrt zu "syntax error near unexpected token" -> Script crasht).
    # Deshalb pro Pfad einen for-Loop und mit [ -f ] die Nicht-Treffer
    # (unerweiterter Glob) abfangen.
    local xa
    # SDDM (haeufigster Fall)
    for xa in /run/sddm/xauth_*; do
        [ -f "$xa" ] && echo "$xa" && return 0
    done
    # SDDM-Helper /tmp
    for xa in /tmp/xauth_*; do
        [ -f "$xa" ] && echo "$xa" && return 0
    done
    # LightDM
    for xa in /var/run/lightdm/root/*; do
        [ -f "$xa" ] && echo "$xa" && return 0
    done
    # User-Home (bei startx)
    for xa in /home/*/.Xauthority; do
        [ -f "$xa" ] && echo "$xa" && return 0
    done
    return 1
}

_check_display_0() {
    # Pruefen ob :0 bereit ist. timeout 2 schuetzt vor haengendem
    # xdpyinfo auf headless-Systemen ohne Monitor.
    local xa
    xa=$(_find_xauth_for_0)
    if [ -n "$xa" ]; then
        XAUTHORITY="$xa" timeout 2 bash -c 'DISPLAY=:0 xdpyinfo >/dev/null 2>&1'
    else
        # Kein Xauth gefunden — probieren ohne (manchmal reicht's)
        timeout 2 bash -c 'DISPLAY=:0 xdpyinfo >/dev/null 2>&1'
    fi
}

_exec_vnc_0() {
    # x11vnc gegen :0 starten MIT der richtigen Xauthority
    local xa
    xa=$(_find_xauth_for_0)
    echo "[x11vnc] Verbinde mit :0 (xauth=${xa:-none})" | systemd-cat -t x11vnc
    if [ -n "$xa" ]; then
        exec /usr/bin/x11vnc -display :0 -auth "$xa" -forever -nopw \
                             -listen localhost -rfbport 5900
    else
        exec /usr/bin/x11vnc -display :0 -forever -nopw \
                             -listen localhost -rfbport 5900
    fi
}

# ---- Phase 1: Initial-Warte auf :0 --------------------------------------
for i in $(seq 1 60); do
    if _check_display_0; then
        _exec_vnc_0
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
    if _check_display_0; then
        echo "[x11vnc] :0 ist jetzt verfuegbar – wechsle von :1 auf :0" | systemd-cat -t x11vnc
        kill "$VNC_PID" 2>/dev/null
        wait "$VNC_PID" 2>/dev/null
        _exec_vnc_0
    fi
    # Falls x11vnc auf :1 aus irgendeinem Grund gestorben ist, neu starten
    if ! kill -0 "$VNC_PID" 2>/dev/null; then
        echo "[x11vnc] x11vnc auf :1 war weg - starte neu" | systemd-cat -t x11vnc
        /usr/bin/x11vnc -display :1 -forever -nopw -listen localhost -rfbport 5900 &
        VNC_PID=$!
    fi
done
