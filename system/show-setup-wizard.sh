#!/bin/bash
# show-setup-wizard.sh — Oeffnet den Einrichtungsassistenten im Browser,
# wenn der User ihn nicht per Checkbox dauerhaft deaktiviert hat.
#
# Wird vom XDG-Autostart-Eintrag ilija-setup-wizard.desktop beim
# Desktop-Login aufgerufen. Prueft eine Flag-Datei:
#     ~/.config/ilija-os/wizard-dismissed
# Existiert sie, laeuft hier nichts – User hat im Wizard Step 5 die
# Checkbox "nicht mehr beim Start zeigen" angehakt. Sonst wartet das
# Script bis der Ilija-Service antwortet (max. 60 s) und oeffnet dann
# den Default-Browser auf dem Wizard.
#
# Diese Datei liegt im Repo (system/show-setup-wizard.sh) und wird vom
# Installer bzw. Update-Script nach /opt/ilija-os/ kopiert.

FLAG="$HOME/.config/ilija-os/wizard-dismissed"
URL="http://localhost:5001/einstellungen#wizard"
MAX_WAIT=60

# Opt-out beachten
if [ -f "$FLAG" ]; then
    exit 0
fi

# Warten bis Ilija-Service erreichbar ist
for i in $(seq 1 "$MAX_WAIT"); do
    if curl -sf --max-time 2 "http://localhost:5001/" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Nach dem Warten nochmal pruefen – nicht oeffnen, falls der Service
# gar nicht hochkommt. Keine Fehlermeldung an den User.
if ! curl -sf --max-time 2 "http://localhost:5001/" >/dev/null 2>&1; then
    exit 0
fi

# Browser oeffnen; xdg-open blockiert nicht
xdg-open "$URL" >/dev/null 2>&1 &
exit 0
