# Ilija OS – ISO bauen

`build-iso.sh` erzeugt aus einem **eingerichteten Ilija-OS-System** (Ubuntu/Lubuntu
24.04 „noble") ein bootfähiges, installierbares ISO (Live-Session mit Casper +
Calamares-Installer, hybrider Start für **BIOS und UEFI**).

## Warum kein „mal eben"-Build

Ilija OS ist ein vollständig eingerichtetes System: Die Anwendungen
(Ilija AI Agent, OpenPhönix ERP, AHPT) liegen samt Python-venvs **im Home**
(`~/Ilija-AI-Agent-Public-Edition`, `~/OpenPhoenix-ERP`, `~/.ahpt`). Ein ISO muss
deshalb dieses Home **mitnehmen**, aber gleichzeitig **alle Geheimnisse und
persönlichen Daten entfernen**. Beides erledigt `build-iso.sh` über eine
Snapshot-+-Sanitize-Methode.

## Voraussetzungen (Build-Host)

| Ressource | Minimum | Empfohlen |
|-----------|---------|-----------|
| Freier Plattenplatz (Scratch `$BUILD_DIR`) | 25 GB | **40–60 GB** |
| RAM | 3 GB (langsam) | **4–8 GB** |
| CPU | egal | mehr Kerne = schnelleres squashfs |

> Die Standard-Proxmox-VM (30 GB Platte, 2,8 GB RAM, ~15 GB frei) reicht dafür
> **nicht**. Optionen: VM-Platte in Proxmox temporär vergrößern (z. B. auf 80 GB,
> dann `growpart`/`resize2fs`), auf einem größeren Build-Host bauen, oder eine
> Kopie der VM zum Bauen verwenden.

Der Build braucht `squashfs-tools xorriso isolinux syslinux-common grub-pc-bin
grub-efi-amd64-bin mtools dosfstools rsync` (installiert das Skript bei Bedarf
selbst) und installiert `casper` + `calamares` **ins Live-System** (landen im
squashfs, werden vom Installer aber nicht ins Zielsystem übernommen).

## Aufruf

```bash
sudo ./build-iso.sh
# Optionen per Umgebungsvariable:
sudo BUILD_DIR=/mnt/scratch OUT=/mnt/scratch/ilija-os.iso COMP=xz ./build-iso.sh
```

Wichtige Variablen: `QUELL_USER` (dessen Home ins ISO wandert, Standard
`innobytix`), `BUILD_DIR`, `OUT`, `COMP` (`zstd` schnell / `xz` kleiner),
`VOLID`, `CASPER_USER` (Live-Benutzer).

## Konten-Modell

Die App-Pfade sind fest auf `$HOME` verdrahtet (siehe `setup/apply.py`). Damit die
vorinstallierten Apps im Zielsystem stimmen, muss der bei der Installation
angelegte Benutzer denselben Namen haben wie `QUELL_USER`. Zwei saubere Wege:

1. **Fester Standardbenutzer** (einfach, empfohlen für v1): Calamares legt den
   Benutzer `innobytix` (bzw. `QUELL_USER`) an; dessen sanitisiertes Home kommt
   aus dem ISO. → Vorinstallierte Apps passen sofort.
2. **Relocation nach `/opt/ilija-os`** (sauberer, größerer Umbau): Apps aus dem
   Home nach `/opt` verschieben und `apply.py` + systemd-Dienste auf `/opt`
   umstellen. Dann ist der Benutzername frei wählbar. → Separater Meilenstein.

## Was NICHT ins ISO kommt (Sanitize)

`build-iso.sh` schließt u. a. aus: `.env` (API-Keys), `.ssh`, `.ahpt/*.key` +
`geheimnis`, `web-auth`-Hash, Ilija-`data/`, OpenPhönix-`*.db` + `config.toml`
(Firmendaten), die komplette `Ilija-Ablage` (persönliche Dokumente/Belege),
Chromium-App-Profile, `machine-id`, SSH-Host-Keys, NetworkManager-Verbindungen,
Logs, Caches, Bash-History. **Liste in `build-iso.sh` (`EXCLUDES`) vor jeder
Verteilung prüfen.**

## Pflicht-Prüfung vor Verteilung

1. **Boot-Test** in einer Wegwerf-VM (QEMU/Proxmox), **BIOS und UEFI**, und
   einmal wirklich **installieren** (Calamares durchlaufen, neu booten, anmelden).
2. **Sanitize-Kontrolle**:
   ```bash
   unsquashfs -l /var/tmp/ilija-iso/iso/casper/filesystem.squashfs \
     | grep -Ei '\.env|\.key|geheimnis|\.db$|Ilija-Ablage|web-auth' || echo "OK: nichts gefunden"
   ```
3. Erst dann veröffentlichen.

## Upload zu GitHub – Größenlimit beachten

GitHub-**Release-Assets** sind auf **2 GiB pro Datei** begrenzt. Ein Ilija-OS-ISO
(App-Payload) liegt darüber. Deshalb in Teile splitten und als mehrere Assets
eines Releases hochladen:

```bash
# splitten (< 2 GiB je Teil)
split -b 1900M -d ilija-os-24.04-amd64.iso ilija-os-24.04-amd64.iso.part
sha256sum ilija-os-24.04-amd64.iso ilija-os-24.04-amd64.iso.part* > SHA256SUMS.txt

# Release anlegen + Teile hochladen
gh release create v0.1.0 --repo Innobytix-IT/Ilija-OS \
  --title "Ilija OS 24.04 (v0.1.0)" \
  --notes "Bootfähiges Live+Installer-ISO. Zum Wiederzusammenfügen siehe unten." \
  ilija-os-24.04-amd64.iso.part* SHA256SUMS.txt

# Wiederzusammenfügen (Endanwender):
cat ilija-os-24.04-amd64.iso.part* > ilija-os-24.04-amd64.iso
sha256sum -c SHA256SUMS.txt
```

(Alternativen für ein ungesplittetes ISO: eigener Webspace/Objektspeicher,
oder – falls eingerichtet – die AHPT/Ilija Cloud.)
