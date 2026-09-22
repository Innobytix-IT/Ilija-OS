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
  "home/*/.ahpt/*.key" "home/*/.ahpt/geheimnis" "home/*/.ahpt/client*.key"
  "home/*/.config/ilija-os/web-auth"
  # Ilija: .env (API-Keys), Laufzeitdaten, DB, Logs, DMS-/Cloud-Archive
  "home/*/Ilija-AI-Agent-Public-Edition/*/.env"
  "home/*/Ilija-AI-Agent-Public-Edition/*/data/*"
  "home/*/Ilija-AI-Agent-Public-Edition/*/*.log"
  "home/*/Ilija-AI-Agent-Public-Edition/*/__pycache__/*"
  # OpenPhönix: Datenbank, config.toml (Firmendaten), erzeugte Dokumente
  "home/*/OpenPhoenix-ERP/*/*.db" "home/*/OpenPhoenix-ERP/*/*.db-*"
  "home/*/OpenPhoenix-ERP/*/config.toml"
  # Gemeinsame Ablage (persönliche Dokumente/Belege) – NIE verteilen
  "home/*/Ilija-Ablage/*"
  # Chromium-App-Profile (Cookies/Sessions der Apps)
  "home/*/snap/chromium/common/ilija-os-apps/*"
)

# --------------------------------------------------------------- Preflight ---
say "Preflight: Werkzeuge & benötigte Pakete"
BUILD_PKGS=(squashfs-tools xorriso isolinux syslinux-common grub-pc-bin grub-efi-amd64-bin mtools dosfstools rsync)
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
update-initramfs -u || die "update-initramfs fehlgeschlagen"

# Platz grob prüfen
FREE_KB="$(df --output=avail -k "$(dirname "$BUILD_DIR")" 2>/dev/null | tail -1 | tr -d ' ')"
if [ -n "${FREE_KB:-}" ] && [ "$FREE_KB" -lt $((25*1024*1024)) ]; then
  echo "  WARNUNG: < 25 GB frei unter $(dirname "$BUILD_DIR"). Build kann scheitern."
fi

# ------------------------------------------------------------- ISO-Baum ------
say "ISO-Baum vorbereiten: $ISO"
rm -rf "$ISO"
mkdir -p "$ISO/casper" "$ISO/isolinux" "$ISO/boot/grub" "$ISO/.disk" "$ISO/EFI/boot"

cp "/boot/vmlinuz-$KVER"  "$ISO/casper/vmlinuz"
cp "/boot/initrd.img-$KVER" "$ISO/casper/initrd"

echo "$DISTRO_NAME $DISTRO_VER \"noble\" - Release amd64" > "$ISO/.disk/info"
: > "$ISO/.disk/base_installable"
echo "full_cd/single" > "$ISO/.disk/cd_type"

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
say "Bootloader: isolinux (BIOS) + GRUB-EFI (UEFI)"
# --- BIOS / isolinux ---
cp /usr/lib/ISOLINUX/isolinux.bin "$ISO/isolinux/"
cp /usr/lib/syslinux/modules/bios/*.c32 "$ISO/isolinux/" 2>/dev/null || true
cat > "$ISO/isolinux/isolinux.cfg" <<CFG
UI vesamenu.c32
DEFAULT live
TIMEOUT 50
PROMPT 0
MENU TITLE $DISTRO_NAME $DISTRO_VER
LABEL live
  MENU LABEL ^$DISTRO_NAME starten / installieren
  KERNEL /casper/vmlinuz
  APPEND initrd=/casper/initrd boot=casper quiet splash ---
LABEL check
  MENU LABEL Medium ^prüfen
  KERNEL /casper/vmlinuz
  APPEND initrd=/casper/initrd boot=casper integrity-check quiet splash ---
CFG

# --- UEFI / GRUB ---
cat > "$ISO/boot/grub/grub.cfg" <<CFG
set default=0
set timeout=5
menuentry "$DISTRO_NAME starten / installieren" {
    linux /casper/vmlinuz boot=casper quiet splash ---
    initrd /casper/initrd
}
menuentry "Medium prüfen" {
    linux /casper/vmlinuz boot=casper integrity-check quiet splash ---
    initrd /casper/initrd
}
CFG

# EFI-Boot-Image (bootx64.efi) standalone bauen und in ein FAT-Image (efiboot.img) legen
grub-mkstandalone \
  --format=x86_64-efi \
  --output="$BUILD_DIR/bootx64.efi" \
  --locales="" --fonts="" \
  "boot/grub/grub.cfg=$ISO/boot/grub/grub.cfg"

( cd "$BUILD_DIR"
  rm -f efiboot.img
  dd if=/dev/zero of=efiboot.img bs=1M count=16
  mkfs.vfat efiboot.img >/dev/null
  mmd  -i efiboot.img ::/EFI ::/EFI/BOOT
  mcopy -i efiboot.img bootx64.efi ::/EFI/BOOT/BOOTX64.EFI
)
cp "$BUILD_DIR/efiboot.img" "$ISO/EFI/boot/efiboot.img"
cp "$BUILD_DIR/bootx64.efi" "$ISO/EFI/boot/bootx64.efi"

# ------------------------------------------------------------- md5 + ISO -----
say "md5sum.txt"
( cd "$ISO" && find . -type f -not -path './isolinux/isolinux.bin' -not -name md5sum.txt \
    -exec md5sum {} \; > md5sum.txt )

say "ISO schreiben: $OUT"
rm -f "$OUT"
xorriso -as mkisofs \
  -iso-level 3 -full-iso9660-filenames \
  -volid "$VOLID" \
  -eltorito-boot isolinux/isolinux.bin \
    -eltorito-catalog isolinux/boot.cat \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
  -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
  -eltorito-alt-boot -e EFI/boot/efiboot.img -no-emul-boot -isohybrid-gpt-basdat \
  -output "$OUT" \
  "$ISO"

say "Fertig: $OUT"
ls -lh "$OUT"
echo
echo "NÄCHSTER SCHRITT (PFLICHT vor Verteilung):"
echo "  1) In einer Wegwerf-VM booten (BIOS UND UEFI) und wirklich INSTALLIEREN."
echo "  2) Sanitize prüfen:  unsquashfs -l '$SFS' | grep -Ei '\\.env|\\.key|\\.db|Ilija-Ablage|web-auth' || echo OK"
echo "  3) Erst danach hochladen (bei > 2 GB in Teile splitten – siehe README)."
