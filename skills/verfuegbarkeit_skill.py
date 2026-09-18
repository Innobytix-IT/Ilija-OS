"""
Verfügbarkeits-Skill – liest Öffnungszeiten, Urlaub und Feiertage
aus verfuegbarkeit.txt und gibt sie strukturiert zurück.

Die Datei liegt im Projekt-Root (neben web_server.py).
"""

import os
import re
from datetime import datetime, date, timedelta

# Pfad zur Datei: skills/ → eine Ebene hoch = Projekt-Root → data/
VERFUEGBARKEIT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "verfuegbarkeit.txt"
)

WOCHENTAG_KÜRZEL = {0: "MO", 1: "DI", 2: "MI", 3: "DO", 4: "FR", 5: "SA", 6: "SO"}
WOCHENTAG_LANG   = {
    "MO": "Montag", "DI": "Dienstag", "MI": "Mittwoch",
    "DO": "Donnerstag", "FR": "Freitag", "SA": "Samstag", "SO": "Sonntag"
}


def _lade_datei() -> str:
    if not os.path.exists(VERFUEGBARKEIT_FILE):
        return ""
    with open(VERFUEGBARKEIT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def _parse_datei(inhalt: str) -> dict:
    """Parst verfuegbarkeit.txt in strukturierte Daten."""
    oeffnungszeiten = {}   # "MO": "09:00–17:00" | "Geschlossen"
    urlaub = []            # [(start_date, end_date, bezeichnung)]
    feiertage = []         # [(date, bezeichnung)]
    sonstige_hinweise = [] # freie Textzeilen unter [HINWEIS]

    for zeile in inhalt.splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue

        # ── Wochentag-Öffnungszeiten ──────────────────────────────
        for tag in ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]:
            if zeile.upper().startswith(f"[{tag}]"):
                wert = zeile[len(f"[{tag}]"):].strip().lstrip(":").strip()
                oeffnungszeiten[tag] = wert
                break

        # ── Feiertag ──────────────────────────────────────────────
        if zeile.upper().startswith("[FEIERTAG]"):
            rest = zeile[len("[FEIERTAG]"):].strip()
            parts = rest.split(None, 1)
            if parts:
                try:
                    d = date.fromisoformat(parts[0])
                    name = parts[1].lstrip("#").strip() if len(parts) > 1 else ""
                    feiertage.append((d, name))
                except ValueError:
                    pass

        # ── Urlaub / Betriebsferien ────────────────────────────────
        if zeile.upper().startswith("[URLAUB]") or zeile.upper().startswith("[FERIEN]"):
            prefix_len = 8  # len("[URLAUB]") = len("[FERIEN]") = 8
            rest = zeile[prefix_len:].strip()
            m = re.match(r"(\d{4}-\d{2}-\d{2})\s*[-–]\s*(\d{4}-\d{2}-\d{2})\s*(.*)", rest)
            if m:
                try:
                    start = date.fromisoformat(m.group(1))
                    end   = date.fromisoformat(m.group(2))
                    name  = m.group(3).lstrip("#").strip()
                    urlaub.append((start, end, name))
                except ValueError:
                    pass

        # ── Sonstige Hinweise ─────────────────────────────────────
        if zeile.upper().startswith("[HINWEIS]"):
            text = zeile[9:].strip().lstrip(":").strip()
            if text:
                sonstige_hinweise.append(text)

    return {
        "oeffnungszeiten": oeffnungszeiten,
        "urlaub": urlaub,
        "feiertage": feiertage,
        "hinweise": sonstige_hinweise
    }


def _ist_verfuegbar(ziel: date, daten: dict) -> tuple:
    """
    Prüft ob am Zieldatum geöffnet/verfügbar ist.
    Gibt (ist_offen: bool, info: str) zurück.
    """
    # Feiertag?
    for (fd, fname) in daten["feiertage"]:
        if fd == ziel:
            label = f"Feiertag: {fname}" if fname else "Feiertag"
            return False, label

    # Urlaub?
    for (us, ue, uname) in daten["urlaub"]:
        if us <= ziel <= ue:
            label = f"Betriebsferien: {uname}" if uname else "Betriebsferien / Urlaub"
            return False, label

    # Regulärer Wochentag
    tag = WOCHENTAG_KÜRZEL[ziel.weekday()]
    zeiten = daten["oeffnungszeiten"].get(tag, "")
    if not zeiten or zeiten.strip().lower() in ("geschlossen", "frei", "zu", "-", ""):
        return False, f"Regulär geschlossen ({WOCHENTAG_LANG[tag]})"

    return True, zeiten


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche Skills
# ─────────────────────────────────────────────────────────────────────────────

def verfuegbarkeit_lesen() -> str:
    """
    Liest alle Verfügbarkeitszeiten und Öffnungszeiten.
    Nutze diesen Skill wenn Kunden fragen wann du erreichbar/geöffnet bist,
    z.B. 'Wann haben Sie geöffnet?', 'Bin ich heute noch rechtzeitig?',
    'Wann können wir uns treffen?', 'Wann bist du verfügbar?'
    Enthält Öffnungszeiten, Urlaub, Feiertage und besondere Hinweise.
    """
    inhalt = _lade_datei()
    if not inhalt:
        return "❌ Keine Verfügbarkeitsdaten vorhanden. Bitte verfuegbarkeit.txt anlegen."

    daten  = _parse_datei(inhalt)
    heute  = date.today()
    zeilen = ["📅 VERFÜGBARKEIT & ÖFFNUNGSZEITEN\n"]

    # Reguläre Öffnungszeiten
    oz = daten["oeffnungszeiten"]
    if oz:
        zeilen.append("🕐 Reguläre Öffnungszeiten:")
        for tag in ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]:
            if tag in oz:
                zeilen.append(f"   {WOCHENTAG_LANG[tag]:12s}: {oz[tag]}")

    # Heutige Verfügbarkeit
    tag_heute = WOCHENTAG_LANG[WOCHENTAG_KÜRZEL[heute.weekday()]]
    ist_offen, info = _ist_verfuegbar(heute, daten)
    if ist_offen:
        zeilen.append(f"\n✅ Heute ({heute.strftime('%d.%m.%Y')}, {tag_heute}): Geöffnet {info}")
    else:
        zeilen.append(f"\n❌ Heute ({heute.strftime('%d.%m.%Y')}, {tag_heute}): {info}")

    # Nächste Schließzeiten (Feiertage + Urlaub)
    kommend = []
    for (fd, fname) in sorted(daten["feiertage"], key=lambda x: x[0]):
        if fd >= heute:
            label = fname if fname else "Feiertag"
            kommend.append((fd, f"🗓 {fd.strftime('%d.%m.%Y')}: {label}"))
    for (us, ue, uname) in sorted(daten["urlaub"], key=lambda x: x[0]):
        if ue >= heute:
            label = uname if uname else "Urlaub / Betriebsferien"
            kommend.append((us, f"🏖 {us.strftime('%d.%m.')}–{ue.strftime('%d.%m.%Y')}: {label}"))
    kommend.sort(key=lambda x: x[0])
    if kommend:
        zeilen.append("\n📌 Kommende Schließzeiten:")
        zeilen.extend([t for _, t in kommend[:6]])

    # Sonstige Hinweise
    if daten["hinweise"]:
        zeilen.append("\nℹ️ Hinweise:")
        for h in daten["hinweise"]:
            zeilen.append(f"   • {h}")

    return "\n".join(zeilen)


def verfuegbarkeit_pruefen(datum: str = "") -> str:
    """
    Prüft ob an einem bestimmten Datum geöffnet/verfügbar ist.
    datum: TT.MM.JJJJ (Standard: heute)
    Nutze diesen Skill wenn Kunden für ein konkretes Datum fragen ob du verfügbar bist.
    Gibt Öffnungszeiten oder den genauen Schließungsgrund zurück.
    """
    inhalt = _lade_datei()
    if not inhalt:
        return "❌ Keine Verfügbarkeitsdaten vorhanden."

    daten = _parse_datei(inhalt)
    try:
        ziel = datetime.strptime(datum.strip(), "%d.%m.%Y").date() if datum else date.today()
    except ValueError:
        return f"❌ Ungültiges Datum '{datum}' – bitte Format TT.MM.JJJJ verwenden."

    tag_lang  = WOCHENTAG_LANG[WOCHENTAG_KÜRZEL[ziel.weekday()]]
    ist_offen, info = _ist_verfuegbar(ziel, daten)

    if ist_offen:
        return (f"✅ {ziel.strftime('%d.%m.%Y')} ({tag_lang}): "
                f"Geöffnet / Verfügbar\n🕐 Zeiten: {info}")
    else:
        # Nächsten offenen Tag suchen (max. 30 Tage)
        nächster = None
        for i in range(1, 31):
            kandidat = ziel + timedelta(days=i)
            offen, zeiten = _ist_verfuegbar(kandidat, daten)
            if offen:
                nächster = (kandidat, zeiten)
                break

        antwort = (f"❌ {ziel.strftime('%d.%m.%Y')} ({tag_lang}): Nicht verfügbar\n"
                   f"   Grund: {info}")
        if nächster:
            nd, nz = nächster
            nd_lang = WOCHENTAG_LANG[WOCHENTAG_KÜRZEL[nd.weekday()]]
            antwort += (f"\n✅ Nächster verfügbarer Tag: "
                        f"{nd.strftime('%d.%m.%Y')} ({nd_lang}), {nz}")
        return antwort


AVAILABLE_SKILLS = [
    verfuegbarkeit_lesen,
    verfuegbarkeit_pruefen,
]
