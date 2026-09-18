# Branding — Ilija OS

Die visuelle Identität von Ilija OS. Master-Dateien liegen in diesem Ordner.

## Logo

Stilisierter **KI-Kopf im Profil** (gold) mit **Schaltkreis-Gehirn** (blau),
umschlossen von einem gold-blauen Ring. Darum die Symbole, die Ilijas
Funktionen abbilden:

- **Ordner/Dokumente** → DMS
- **Telefon** → Telefon-Assistent
- **Chat-Sprechblase** → Chat/Assistent
- **Kalender mit Haken** → Kalender

Darunter der Schriftzug **„ILIJA"** (gold, das „A" als Aufwärts-Pfeil/Chevron).

**Master-Dateien:**
- `ilija-splash.png` — **16:9 (1671×941)**, sattes Glühen + Bodenspiegelung.
  Für **Boot-Splash und Desktop-Hintergrund** (füllt Vollbild). *(Empfohlen für
  großflächige Verwendung.)*
- `ilija-logo.png` — kompaktere Fassung (1254×863). Für **Logo/App-Icon** und
  kleine Kontexte.

Noch abzuleiten: `ilija-logo.svg` (vektorisiert, falls möglich), `ilija-icon.png`
(quadratisch aus dem Kopf, Größen 16/32/48/64/128/256).

Animierter Startbildschirm (Web, HTML/CSS) als Vorschau:
https://claude.ai/code/artifact/1b642ee8-d5c5-411f-bf41-5e7c9419feb0

## Farbpalette (aus dem Logo, ungefähr — aus Master verfeinern)

| Rolle | Farbe |
|---|---|
| Grund (Schwarz) | `#000000` |
| Gold (Primär) | ~`#D4AF37` / metallic |
| Elektroblau (Akzent) | ~`#1E9FE0` |
| Blau dunkel | ~`#0E6FB0` |
| Text hell | `#F5F5F5` |

Dark-first. Gold für Struktur/Text-Akzente, Blau für aktive/technische
Elemente, Schwarz als Grund.

## Wo das Branding hin soll (siehe ../OFFEN.md)

- **OS-Identität:** `/etc/os-release` (PRETTY_NAME „Ilija OS"), `/etc/issue`
- **Boot-Splash:** Plymouth-Theme mit `ilija-splash.png`
- **Anmeldung:** SDDM/LightDM-Theme + Logo
- **Desktop (LXQt):** Hintergrund `ilija-wallpaper.png`, Panel-Icon, Theme in
  Gold/Blau
- **App-/Startmenü-Icon:** `ilija-icon.png`
- **„Über"/Systeminfo:** Logo + „Ilija OS"
- **Eigene ISO (Cubic):** Calamares-Branding (Logo, Begrüßung, Slideshow)
- Später (Weg B): Web-Dashboard im selben Look
