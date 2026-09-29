#!/bin/bash
# =============================================================================
# Ilija OS – ISO-Builder (bootfähiges Live + Installer, BIOS + UEFI)
# =============================================================================
# Erzeugt aus einem eingerichteten Ilija-OS-System (Ubuntu/Lubuntu 24.04 „noble")
# ein verteilbares, installierbares ISO. Methode: Snapshot des laufenden Systems
# per mksquashfs (kein Zwischen-Kopieren -> spart Platz), Casper-Live-Boot,
# Calamares-Installer, hybrider Boot (isolinux/BIOS + GRUB-EFI/UEFI) via xorriso.
#
# WICHTIG – vor dem echten Einsatz lesen:
#   * Muss als root laufen: sudo ./build-iso.sh
#   * BENÖTIGT VIEL PLATZ: Faustregel freier Platz >= (2 x squashfs) + 4 GB,
#     realistisch >= 40–60 GB frei auf $BUILD_DIR und >= 4 GB RAM.
#     Auf der Standard-VM (30 GB Platte) NICHT genug -> auf Build-Host mit
#     mehr Platz bauen oder VM-Platte temporär vergrößern.
#   * SANITIZE: Home-Geheimnisse/Daten/Identität werden bewusst AUSGESCHLOSSEN
#     (siehe EXCLUDES). Prüfe die Liste, bevor du verteilst!
#   * Das erzeugte ISO ist bis zum Boot-Test in einer VM UNGETESTET. Immer erst
#     in einer Wegwerf-VM (Proxmox/QEMU) booten UND installieren, dann verteilen.
#   * Idempotent genug: räumt $BUILD_DIR/iso vor jedem Lauf auf.
#
# Konten-Modell (ILIJA_ACCOUNT):
#   Die Apps liegen unter /home/<user> mit fest verdrahteten $HOME-Pfaden
#   (siehe setup/apply.py). Der Installer (Calamares) legt beim Installieren
#   einen Benutzer an; damit die vorinstallierten Apps stimmen, sollte dieser
#   Benutzer denselben Namen haben wie der, dessen Home ins ISO wandert.
#   Standard: das Home des unten gewählten $QUELL_USER wird 1:1 (sanitisiert)
#   übernommen; Calamares wird so vorkonfiguriert, dass es diesen Benutzernamen
#   vorschlägt. (Alternative Refaktorierung nach /opt ist ein separater Schritt.)
# =============================================================================
set -euo pipefail

# ------------------------------------------------------------------ Konfig ---
QUELL_USER="${QUELL_USER:-innobytix}"          # dessen Home wird (sanitisiert) übernommen
DISTRO_NAME="${DISTRO_NAME:-Ilija OS}"
DISTRO_VER="${DISTRO_VER:-24.04}"
VOLID="${VOLID:-ILIJA_OS_2404}"                 # ISO-Volume-Label (max 32 Zeichen)
BUILD_DIR="${BUILD_DIR:-/var/tmp/ilija-iso}"    # Scratch (viel Platz nötig!)
OUT="${OUT:-$BUILD_DIR/ilija-os-${DISTRO_VER}-amd64.iso}"
COMP="${COMP:-zstd}"                            # squashfs-Kompression: zstd|xz
CASPER_USER="${CASPER_USER:-ilija}"             # Live-Sitzungs-Benutzer

ISO="$BUILD_DIR/iso"
SFS="$ISO/casper/filesystem.squashfs"

say(){ echo -e "\n\033[1;33m==> $*\033[0m"; }
die(){ echo -e "\033[1;31mFEHLER: $*\033[0m" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "Bitte als root ausführen (sudo)."

# ------------------------------------------------------------- Sanitize ------
# Pfade, die NICHT ins ISO dürfen (Geheimnisse, Nutzerdaten, Maschinenidentität,
# Caches/Logs, Laufzeit). Relativ zu / (mksquashfs -wildcards -e).
EXCLUDES=(
  # Pseudo-/Laufzeit-Dateisysteme
  "proc/*" "sys/*" "dev/*" "run/*" "tmp/*" "mnt/*" "media/*"
  "var/tmp/*" "var/crash/*" "lost+found"
  "swapfile" "swap.img"
  "${BUILD_DIR#/}/*"                 # eigener Scratch niemals einpacken (relativ, kein fuehrendes /)
  # Logs & Caches
  "var/log/*" "var/cache/apt/archives/*.deb" "var/lib/apt/lists/*"
  "root/.cache/*" "root/.bash_history"
  "home/*/.cache/*" "home/*/.bash_history" "home/*/.python_history"
  "home/*/.local/share/Trash/*"
  # Maschinen-Identität (Live/Installer erzeugt neu)
  "etc/machine-id" "var/lib/dbus/machine-id"
  "etc/ssh/ssh_host_*"
  "etc/NetworkManager/system-connections/*"   # WLAN-Passwörter etc.
  # --- GEHEIMNISSE / persönliche Daten (Ilija/ERP/AHPT) ---
  "home/*/.ssh/*"
  # AHPT: Home-Pfad und /opt-Pfad (geheimnis* deckt geheimnis_elitebook etc.)
  "home/*/.ahpt/*.key" "home/*/.ahpt/geheimnis*" "home/*/.ahpt/client*.key"
  "home/*/.ahpt/*.toml"
  "opt/ilija-os/.ahpt/*"
  "home/*/.config/ilija-os/web-auth"
  # Ilija: .env (API-Keys) – Home-Pfad UND /opt-Pfad
  "home/*/Ilija-AI-Agent-Public-Edition/*/.env"
  "opt/ilija-os/ilija/.env"
  # Ilija: Laufzeitdaten, Logs, Caches
  "home/*/Ilija-AI-Agent-Public-Edition/*/data/*"
  "home/*/Ilija-AI-Agent-Public-Edition/*/*.log"
  "home/*/Ilija-AI-Agent-Public-Edition/*/__pycache__/*"
  "opt/ilija-os/ilija/data/*"
  "opt/ilija-os/ilija/*.log"
  # OpenPhönix: Datenbank, config.toml – Home-Pfad UND /opt-Pfad
  "home/*/OpenPhoenix-ERP/*/*.db" "home/*/OpenPhoenix-ERP/*/*.db-*"
  "home/*/OpenPhoenix-ERP/*/config.toml"
  "opt/ilija-os/openphoenix/*.db" "opt/ilija-os/openphoenix/*.db-*"
  "opt/ilija-os/openphoenix/config.toml"
  # Gemeinsame Ablage (persönliche Dokumente/Belege) – NIE verteilen
  "home/*/Ilija-Ablage/*"
  "srv/ilija-ablage/*"
  # Browser-Profile (Cookies, Passwörter, Login-Daten)
  "home/*/.mozilla/*" "home/*/snap/firefox/*"
  "home/*/.config/google-chrome/*" "home/*/snap/chromium/*"
  "opt/ilija-os/.local/share/pki/*"
  "home/*/.local/share/pki/*"
  # GNOME Keyring (gespeicherte Passwörter, Zertifikate)
  "home/*/.local/share/keyrings/*"
  "root/.local/share/keyrings/*"
  # Outlook/Browser-Profil in Ilija-Daten
  "home/*/data/outlook_profil"
  "home/*/data/outlook_profil/*"
  "opt/ilija-os/ilija/data/outlook_profil/*"
  # Chromium-App-Profile (Cookies/Sessions der Apps)
  "home/*/snap/chromium/common/ilija-os-apps/*"
  # Persönliche Ablage-Verzeichnisse (auch leere Ordner)
  "home/*/Ilija-Ablage"
  "srv/ilija-ablage"
)

# --------------------------------------------------------------- Preflight ---
say "Preflight: Werkzeuge & benötigte Pakete"
BUILD_PKGS=(squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin mtools dosfstools rsync)
missing=()
for p in "${BUILD_PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "  installiere Build-Pakete: ${missing[*]}"
  apt-get update -qq && apt-get install -y "${missing[@]}" || die "Build-Pakete fehlgeschlagen"
fi

# Live-Boot & Installer MÜSSEN im System (squashfs) vorhanden sein.
say "Preflight: Live-Boot (casper) & Installer (calamares) im System"
LIVE_PKGS=()
dpkg -s casper       >/dev/null 2>&1 || LIVE_PKGS+=(casper)
dpkg -s calamares    >/dev/null 2>&1 || LIVE_PKGS+=(calamares)
if [ "${#LIVE_PKGS[@]}" -gt 0 ]; then
  echo "  Diese Pakete gehören INS Live-System und werden jetzt installiert: ${LIVE_PKGS[*]}"
  echo "  (Sie landen anschließend im squashfs.)"
  apt-get install -y "${LIVE_PKGS[@]}" || die "casper/calamares-Installation fehlgeschlagen"
fi

KVER="$(uname -r)"
[ -e "/boot/vmlinuz-$KVER" ] || die "Kernel /boot/vmlinuz-$KVER nicht gefunden"
# Casper-fähiges initrd sicherstellen
say "initramfs mit Casper aktualisieren"
# FRAMEBUFFER=y noetig damit der Plymouth-Hook greift (Boot-Splash im initramfs)
grep -q '^FRAMEBUFFER=y' /etc/initramfs-tools/initramfs.conf \
  || echo 'FRAMEBUFFER=y' >> /etc/initramfs-tools/initramfs.conf
update-initramfs -u || die "update-initramfs fehlgeschlagen"

# Platz grob prüfen
FREE_KB="$(df --output=avail -k "$(dirname "$BUILD_DIR")" 2>/dev/null | tail -1 | tr -d ' ')"
if [ -n "${FREE_KB:-}" ] && [ "$FREE_KB" -lt $((25*1024*1024)) ]; then
  echo "  WARNUNG: < 25 GB frei unter $(dirname "$BUILD_DIR"). Build kann scheitern."
fi

# ------------------------------------------------------------- ISO-Baum ------
say "ISO-Baum vorbereiten: $ISO"
rm -rf "$ISO"
mkdir -p "$ISO/casper" "$ISO/boot/grub" "$ISO/.disk" "$ISO/EFI/boot"

cp "/boot/vmlinuz-$KVER"  "$ISO/casper/vmlinuz"
cp "/boot/initrd.img-$KVER" "$ISO/casper/initrd"

echo "$DISTRO_NAME $DISTRO_VER \"noble\" - Release amd64" > "$ISO/.disk/info"
: > "$ISO/.disk/base_installable"
echo "full_cd/single" > "$ISO/.disk/cd_type"

# fixconkeys-part2 sicherstellen (wird von Calamares in den Chroot kopiert)
[ -f /usr/libexec/fixconkeys-part2 ] || cat > /usr/libexec/fixconkeys-part2 << 'FIXSCRIPT'
#!/bin/bash
LAYOUT=$(cat /dev/shm/fixconkeys-layout 2>/dev/null || echo "")
if [ -n "$LAYOUT" ] && [ -f /etc/default/keyboard ]; then
    sed -i "s/XKBLAYOUT=.*/XKBLAYOUT=\"$LAYOUT\"/" /etc/default/keyboard 2>/dev/null || true
fi
exit 0
FIXSCRIPT
chmod +x /usr/libexec/fixconkeys-part2

# removeusers: läuft als Calamares shellprocess (dontChroot:true) NACH unpackfs und VOR users.
# Findet die Zielpartition via /tmp/calamares-root-* Glob, entfernt UID>=1000 aus passwd+group.
cat > /usr/libexec/removeusers << 'RMSCRIPT'
#!/bin/bash
LOG=/run/removeusers.log
echo "=== removeusers ===" >> "$LOG"; date >> "$LOG"
TARGET="${CALAMARES_TARGET_MOUNT:-}"
for d in /tmp/calamares-root-* /tmp/calamares-root /target /mnt/target; do
    for exp in $d; do
        [ -f "$exp/etc/passwd" ] && TARGET="$exp" && break 2
    done
done
echo "TARGET=${TARGET:-LEER}" >> "$LOG"
if [ -n "$TARGET" ] && [ -f "$TARGET/etc/passwd" ]; then
    awk -F: '$3 < 1000 || $1 == "nobody"' "$TARGET/etc/passwd" > "$TARGET/etc/passwd.new"
    mv "$TARGET/etc/passwd.new" "$TARGET/etc/passwd"
    awk -F: '$3 < 1000 || $1 == "nobody"' "$TARGET/etc/group" > "$TARGET/etc/group.new" 2>/dev/null \
        && mv "$TARGET/etc/group.new" "$TARGET/etc/group" || true
    echo "ERLEDIGT" >> "$LOG"
else
    echo "KEIN TARGET" >> "$LOG"
fi
exit 0
RMSCRIPT
chmod +x /usr/libexec/removeusers

# Calamares settings.conf: removeusers-Instanz und exec-Reihenfolge sicherstellen
python3 - << 'PYFIX'
import re, sys
path = "/etc/calamares/settings.conf"
try:
    txt = open(path).read()
except FileNotFoundError:
    sys.exit(0)
changed = False
# 1. instances-Eintrag hinzufügen falls fehlend
if "id: removeusers" not in txt:
    txt = txt.replace(
        "\nsequence:",
        "\n- id: removeusers\n  module: shellprocess\n  config: shellprocess_removeusers.conf\n\nsequence:",
        1
    )
    changed = True
# 2. shellprocess@removeusers vor users einfügen falls fehlend
if "shellprocess@removeusers" not in txt:
    txt = re.sub(r'(\n  - users\b)', r'\n  - shellprocess@removeusers\1', txt, count=1)
    changed = True
if changed:
    open(path, "w").write(txt)
    print("settings.conf angepasst")
PYFIX

# shellprocess_removeusers.conf schreiben
mkdir -p /etc/calamares/modules
cat > /etc/calamares/modules/shellprocess_removeusers.conf << 'MODCONF'
---
dontChroot: true
timeout: 60
script:
    - /usr/libexec/removeusers
MODCONF

# ------------------------------------------------------------- squashfs ------
say "squashfs erzeugen ($COMP) – das dauert (CPU/RAM-intensiv)"
EXARGS=()
for e in "${EXCLUDES[@]}"; do EXARGS+=("$e"); done
# Wichtig: von / bauen, Sanitize per -wildcards -e; -no-progress optional.
mksquashfs / "$SFS" -comp "$COMP" -noappend -wildcards -e "${EXARGS[@]}"

printf '%s' "$(du -sx --block-size=1 / 2>/dev/null | cut -f1)" > "$ISO/casper/filesystem.size"
# Manifest der installierten Pakete (Calamares entfernt daraus die Live-only-Pakete)
dpkg-query -W --showformat='${Package} ${Version}\n' > "$ISO/casper/filesystem.manifest"
cp "$ISO/casper/filesystem.manifest" "$ISO/casper/filesystem.manifest-desktop"
# Live-only-Pakete, die der Installer NICHT ins Zielsystem übernimmt:
for p in casper calamares live-boot live-boot-initramfs-tools; do
  sed -i "/^$p /d" "$ISO/casper/filesystem.manifest-desktop" 2>/dev/null || true
done

# ------------------------------------------------------------- Bootloader ----
# Lubuntu 24.04 (Noble) nutzt GRUB2 fuer BIOS UND UEFI – kein isolinux.
# BIOS: grub-mkimage erzeugt i386-pc core.img + cdboot.img = eltorito.img
# UEFI: grub-mkimage erzeugt x86_64-efi image, kein Standalone (kein baked cfg)
#        -> GRUB sucht boot/grub/grub.cfg auf dem ISO9660-Dateisystem
say "Bootloader: GRUB2 BIOS (i386-pc) + GRUB2 UEFI (x86_64-efi)"

# --- BIOS / GRUB i386-pc ---
mkdir -p "$ISO/boot/grub/i386-pc"
cp /usr/lib/grub/i386-pc/*.mod "$ISO/boot/grub/i386-pc/" 2>/dev/null || true
cp /usr/lib/grub/i386-pc/*.lst "$ISO/boot/grub/i386-pc/" 2>/dev/null || true

grub-mkimage \
  --format=i386-pc \
  --directory=/usr/lib/grub/i386-pc \
  --prefix=/boot/grub \
  --output="$BUILD_DIR/grub-core-bios.img" \
  biosdisk iso9660 normal search search_fs_file linux echo ls cat part_gpt part_msdos

cat /usr/lib/grub/i386-pc/cdboot.img "$BUILD_DIR/grub-core-bios.img" \
    > "$ISO/boot/grub/i386-pc/eltorito.img"

# --- UEFI / GRUB x86_64-efi ---
# grub-mkimage mit prefix=/boot/grub: GRUB laedt boot/grub/grub.cfg vom ISO
grub-mkimage \
  --format=x86_64-efi \
  --directory=/usr/lib/grub/x86_64-efi \
  --prefix=/boot/grub \
  --output="$ISO/EFI/boot/bootx64.efi" \
  part_gpt part_msdos fat iso9660 normal search search_fs_file \
  search_fs_uuid search_label efi_gop linux gzio all_video echo ls cat

# EFI FAT-Image (fuer El Torito EFI-Eintrag)
( rm -f "$BUILD_DIR/efiboot.img"
  dd if=/dev/zero of="$BUILD_DIR/efiboot.img" bs=1M count=16 2>/dev/null
  mkfs.vfat "$BUILD_DIR/efiboot.img" >/dev/null
  mmd  -i "$BUILD_DIR/efiboot.img" ::/EFI ::/EFI/BOOT
  mcopy -i "$BUILD_DIR/efiboot.img" "$ISO/EFI/boot/bootx64.efi" ::/EFI/BOOT/BOOTX64.EFI
)
cp "$BUILD_DIR/efiboot.img" "$ISO/EFI/boot/efiboot.img"

# --- Einheitliche grub.cfg fuer BIOS und UEFI ---
cat > "$ISO/boot/grub/grub.cfg" <<CFG
set default=0
set timeout=10
set gfxpayload=keep

menuentry "$DISTRO_NAME starten / installieren" {
    linux  /casper/vmlinuz boot=casper quiet splash ---
    initrd /casper/initrd
}
menuentry "Medium pruefen" {
    linux  /casper/vmlinuz boot=casper integrity-check quiet splash ---
    initrd /casper/initrd
}
CFG

# ------------------------------------------------------------- md5 + ISO -----
say "md5sum.txt"
( cd "$ISO" && find . -type f -not -name md5sum.txt \
    -exec md5sum {} \; > md5sum.txt )

say "ISO schreiben: $OUT"
rm -f "$OUT"
xorriso -as mkisofs \
  -iso-level 3 \
  --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
  --mbr-force-bootable \
  -partition_offset 16 \
  --grub2-boot-info \
  -no-emul-boot -boot-info-table --grub2-boot-info \
  -eltorito-boot boot/grub/i386-pc/eltorito.img \
    -eltorito-catalog boot.catalog \
  -eltorito-alt-boot -e EFI/boot/efiboot.img -no-emul-boot -isohybrid-gpt-basdat \
  -joliet \
  -volid "$VOLID" \
  -output "$OUT" \
  "$ISO"

say "Fertig: $OUT"
ls -lh "$OUT"
echo
echo "NÄCHSTER SCHRITT (PFLICHT vor Verteilung):"
echo "  1) In einer Wegwerf-VM booten (BIOS UND UEFI) und wirklich INSTALLIEREN."
echo "  2) Sanitize prüfen:  unsquashfs -l '$SFS' | grep -Ei '\\.env|\\.key|\\.db|Ilija-Ablage|web-auth' || echo OK"
echo "  3) Erst danach hochladen (bei > 2 GB in Teile splitten – siehe README)."
