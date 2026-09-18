#!/bin/bash
# Ilija OS - Rebranding-Schicht (idempotent).
# Stellt das Ilija-Branding aus /usr/share/ilija-os/branding wieder her.
# Wird per apt-Hook nach jedem install/upgrade ausgefuehrt, damit Paket-Updates
# das Branding nicht zuruecksetzen. Muss als root laufen.
set -u
BR=/usr/share/ilija-os/branding
TREE=$BR/tree
EXE="/usr/bin/Ilija OS Update"     # App-Name der Benachrichtigung = Dateiname
log(){ logger -t ilija-rebrand "$*" 2>/dev/null; echo "[ilija-rebrand] $*"; }

changed_plymouth=0
changed_grub=0

restore(){ # $1 = Zielpfad (absolut), $2 = Domain (plymouth|grub|other)
  local p="$1" dom="$2" src="$TREE$1"
  [ -e "$src" ] || return 0
  if [ -d "$src" ]; then
    if ! diff -rq "$src" "$p" >/dev/null 2>&1; then
      mkdir -p "$p"; cp -a "$src/." "$p/" 2>/dev/null && \
        { log "aktualisiert (dir): $p"; [ "$dom" = plymouth ] && changed_plymouth=1; [ "$dom" = grub ] && changed_grub=1; }
    fi
  else
    if ! cmp -s "$src" "$p" 2>/dev/null; then
      mkdir -p "$(dirname "$p")"; cp -a "$src" "$p" && \
        { log "aktualisiert: $p"; [ "$dom" = plymouth ] && changed_plymouth=1; [ "$dom" = grub ] && changed_grub=1; }
    fi
  fi
}

patch_title(){  # $1 = Binary: Fenstertitel "Lubuntu Update" -> "Ilija Update"
  # (fest kompilierter Qt-setWindowTitle; nur per Byte-Patch aenderbar).
  # Ersetzt genau die EINE null-terminierte Stelle; die "Lubuntu Update !!! ..."
  # -Marker (Konfig/Log) bleiben unberuehrt. Gleiche Byte-Laenge (15).
  local b="$1"; [ -f "$b" ] || return 0
  python3 - "$b" <<'PY'
import sys
p=sys.argv[1]; d=open(p,"rb").read()
alt=b"Lubuntu Update\x00"; neu=b"Ilija Update\x00\x00\x00"
if d.count(alt)==1:
    open(p,"wb").write(d.replace(alt,neu)); print("PATCHED")
PY
}

# --- 1) Bild-/Datei-Branding aus dem Snapshot ---
restore "/usr/share/lxqt/themes/Lubuntu Arc/mainmenu.svg" other
restore "/usr/share/sddm/themes/lubuntu/Main.qml" other
restore "/usr/share/sddm/themes/lubuntu/theme.conf" other
restore "/usr/share/sddm/themes/lubuntu/ilija-splash.png" other
restore "/usr/share/plymouth/themes/lubuntu-logo/lubuntu-logo.plymouth" plymouth
restore "/usr/share/plymouth/themes/lubuntu-logo/lubuntu_logo.png" plymouth
restore "/usr/share/plymouth/themes/lubuntu-logo/watermark.png" plymouth
restore "/usr/share/plymouth/themes/lubuntu-logo/spinner" plymouth
restore "/usr/share/grub/themes/lubuntu-grub-theme/background.png" grub
restore "/usr/share/grub/themes/lubuntu-grub-theme/icons/ilija.png" grub
restore "/usr/share/grub/themes/lubuntu-grub-theme/icons/lubuntu.png" grub
restore "/usr/share/grub/themes/lubuntu-grub-theme/icons/ubuntu.png" grub
restore "/boot/grub/ilija-splash.png" grub

# --- 2) Update-Melder: Fenstertitel patchen + echte Kopie unter "Ilija OS Update" ---
# Erst die Quelle patchen (ueberlebt so kein Paket-Upgrade -> Hook patcht neu),
# dann die als App gestartete Kopie daraus ziehen.
[ "$(patch_title /usr/bin/lubuntu-update)" = PATCHED ] && log "Fenstertitel gepatcht (lubuntu-update)"
if [ -x /usr/bin/lubuntu-update ]; then
  if [ ! -e "$EXE" ] || ! cmp -s /usr/bin/lubuntu-update "$EXE"; then
    cp -f /usr/bin/lubuntu-update "$EXE"; chmod 755 "$EXE"; log "Update-Melder-Exe aktualisiert"
  fi
fi
rm -f /usr/bin/ilija-update 2>/dev/null
D=/usr/share/applications/lubuntu-update.desktop
if [ -f "$D" ]; then
  sed -i -e 's#^Exec=.*#Exec="/usr/bin/Ilija OS Update"#' \
         -e 's#^Name=.*#Name=Ilija OS Update#' \
         -e 's#^GenericName=.*#GenericName=Ilija OS Update#' "$D"
fi
A=/etc/xdg/autostart/lubuntu-update-autostart.desktop
if [ -f "$A" ]; then
  sed -i -e 's#^Exec=.*#Exec="/usr/bin/Ilija OS Update"#' \
         -e 's#^Name=.*#Name=Ilija OS Update Autostart#' "$A"
fi

# --- 3) Sitzungsname ---
S=/usr/share/xsessions/Lubuntu.desktop
[ -f "$S" ] && sed -i -e 's/^Name=Lubuntu$/Name=Ilija OS/' \
                      -e 's/^Comment=.*/Comment=Ilija OS-Sitzung (LXQt)/' "$S"

# --- 4) OS-Identitaet ---
[ -f /etc/os-release ] && sed -i -e 's/^PRETTY_NAME=.*/PRETTY_NAME="Ilija OS"/' \
                                 -e 's/^NAME=.*/NAME="Ilija OS"/' /etc/os-release

# --- 5) pcmanfm-qt System-Default: kein "Lubuntu Manual" ---
# WICHTIG: NUR die DesktopShortcuts-Zeile wird angefasst. Das Desktop-Wallpaper
# (Schluessel "Wallpaper=" in der USER-Config ~/.config/pcmanfm-qt/...) wird
# bewusst NICHT verwaltet - der Nutzer kann seinen Hintergrund jederzeit frei
# wechseln. Wir aendern hier nur den System-Default fuer NEUE Nutzer und
# entfernen ausschliesslich den "Lubuntu Manual"-Eintrag.
for f in /etc/xdg/xdg-Lubuntu/pcmanfm-qt/lxqt/settings.conf /etc/xdg/pcmanfm-qt/lxqt/settings.conf; do
  [ -f "$f" ] && sed -i '/^DesktopShortcuts=/ s/,[[:space:]]*Lubuntu Manual//' "$f"
done

# --- 6) GRUB /etc/default/grub ---
G=/etc/default/grub
if [ -f "$G" ]; then
  before=$(md5sum "$G" | cut -d" " -f1)
  if grep -q '^GRUB_DISTRIBUTOR=' "$G"; then sed -i 's#^GRUB_DISTRIBUTOR=.*#GRUB_DISTRIBUTOR="Ilija OS"#' "$G"; else echo 'GRUB_DISTRIBUTOR="Ilija OS"' >> "$G"; fi
  if grep -q '^GRUB_BACKGROUND=' "$G"; then sed -i 's#^GRUB_BACKGROUND=.*#GRUB_BACKGROUND="/boot/grub/ilija-splash.png"#' "$G"; else echo 'GRUB_BACKGROUND="/boot/grub/ilija-splash.png"' >> "$G"; fi
  [ "$before" != "$(md5sum "$G" | cut -d" " -f1)" ] && changed_grub=1
fi

# --- 7) bei Bedarf neu bauen ---
[ "$changed_plymouth" = 1 ] && { log "update-initramfs (Plymouth geaendert)"; update-initramfs -u >/dev/null 2>&1 || true; }
[ "$changed_grub" = 1 ]     && { log "update-grub (GRUB geaendert)";     update-grub        >/dev/null 2>&1 || true; }
log "fertig (plymouth=$changed_plymouth grub=$changed_grub)"
exit 0
