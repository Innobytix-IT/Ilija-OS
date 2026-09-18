# tv_programm.py – TV-Programm Skill fuer Ilija Public Edition
#
# Datenquellen:
#   api.zapp.mediathekview.de  – oeffentlich-rechtliche Sender DE/AT/CH (kostenlos)
#   bibeltv.de                 – Bibel TV via Website-Scraping (Next.js RSC payload)
#
# Private Massensender (RTL, SAT.1 etc.) haben keine freie API.

import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

_API_BASE = "https://api.zapp.mediathekview.de/v1/shows"
_BIBELTV_URL = "https://www.bibeltv.de/programm/bibeltv?tag={datum}"
_CACHE: dict = {}
_CACHE_TTL = 10 * 60  # 10 Minuten

_SENDER_ID = {
    # ARD
    "das erste":    "das_erste",
    "ard":          "das_erste",
    "one":          "one",
    "ard alpha":    "ard_alpha",
    "tagesschau24": "tagesschau24",
    # ARD Dritte
    "br":           "br",
    "hr":           "hr",
    "mdr":          "mdr",
    "ndr":          "ndr",
    "swr":          "swr",
    "wdr":          "wdr",
    "rbb":          "rbb",
    # ZDF
    "zdf":          "zdf",
    "zdfinfo":      "zdfinfo",
    "zdfneo":       "zdfneo",
    # Weitere oeffentlich-rechtliche
    "arte":         "arte",
    "3sat":         "3sat",
    "phoenix":      "phoenix",
    "kika":         "kika",
    # Oesterreich
    "orf1":         "orf1",
    "orf 1":        "orf1",
    "orf2":         "orf2",
    "orf 2":        "orf2",
    # Schweiz
    "srf1":         "srf1",
    "srf 1":        "srf1",
    "srf2":         "srf2",
    "srf 2":        "srf2",
    "srf info":     "srfinfo",
    "srfinfo":      "srfinfo",
}

_BIBELTV_NAMEN = {"bibeltv", "bibel tv", "bibel-tv"}

_PRIVATSENDER = {
    "rtl", "sat1", "sat.1", "pro7", "prosieben", "vox", "rtl2", "kabel1",
    "kabel eins", "superrtl", "super rtl", "nitro", "sat1 gold", "pro7maxx",
    "ntv", "n-tv", "welt", "dmax", "tele5", "sixx", "sport1",
    "rtlup", "rtlplus", "toggo", "comedy central", "disney channel", "mtv",
    "servustv", "puls4", "atv",
}

_UNTERSTUETZTE_SENDER = sorted(_SENDER_ID.keys())

_CET = timezone(timedelta(hours=2))


# ── Cache ─────────────────────────────────────────────────────────────────────

def _cache_get(key):
    if key in _CACHE:
        ts, data = _CACHE[key]
        if (datetime.now() - ts).total_seconds() < _CACHE_TTL:
            return data
    return None


def _cache_set(key, data):
    _CACHE[key] = (datetime.now(), data)


# ── Zapp API (oeffentlich-rechtlich) ──────────────────────────────────────────

def _zapp_get(channel_id: str) -> list:
    cached = _cache_get(channel_id)
    if cached is not None:
        return cached
    try:
        url = f"{_API_BASE}/{channel_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "IlijaBot/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            shows = data.get("shows", [])
            _cache_set(channel_id, shows)
            return shows
    except Exception:
        return []


def _utc_to_local(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_CET).strftime("%H:%M")
    except Exception:
        return "??:??"


def _format_show(show: dict, sender_label: str = "") -> str:
    start = _utc_to_local(show.get("startTime", ""))
    end   = _utc_to_local(show.get("endTime", ""))
    titel = show.get("title", "Unbekannt")
    untertitel = show.get("subtitle", "")
    zeile = f"  {start}–{end}  "
    if sender_label:
        zeile += f"{sender_label:<16}"
    zeile += titel
    if untertitel:
        zeile += f"  [{untertitel}]"
    return zeile


# ── Bibel TV Scraper ──────────────────────────────────────────────────────────

def _bibeltv_items(datum: str) -> list:
    """Laedt Programm-Items von bibeltv.de fuer das angegebene Datum (YYYY-MM-DD)."""
    cache_key = f"bibeltv_{datum}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        url = _BIBELTV_URL.format(datum=datum)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "de-DE,de;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    # Next.js RSC Streaming-Chunks extrahieren
    pushes = re.findall(r'self\.__next_f\.push\(\[(.*?)\]\)', html, re.DOTALL)

    for raw_chunk in pushes:
        try:
            decoded = json.loads("[" + raw_chunk + "]")[1]
        except Exception:
            continue
        if not isinstance(decoded, str) or '"items":[' not in decoded:
            continue

        # items-Array per Bracket-Tracking extrahieren
        idx = decoded.find('"items":[')
        start = idx + len('"items":')
        depth = 0
        end = start
        for i, c in enumerate(decoded[start:], start):
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            items = json.loads(decoded[start:end])
            _cache_set(cache_key, items)
            return items
        except Exception:
            continue

    return []


def _bibeltv_aktuell(items: list) -> dict | None:
    """Gibt das gerade laufende Item zurueck, oder das naechste."""
    now_utc = datetime.now(timezone.utc)
    for item in items:
        try:
            s = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(item["ende"].replace("Z", "+00:00"))
            if s <= now_utc <= e:
                return item
        except Exception:
            continue
    # Kein laufendes Item → naechstes
    for item in items:
        try:
            s = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
            if s > now_utc:
                return item
        except Exception:
            continue
    return items[-1] if items else None


def _bibeltv_format(item: dict) -> str:
    """Formatiert ein Bibel-TV-Item als lesbaren String."""
    try:
        s = datetime.fromisoformat(item["start"].replace("Z", "+00:00")).astimezone(_CET)
        e = datetime.fromisoformat(item["ende"].replace("Z", "+00:00")).astimezone(_CET)
        start_str = s.strftime("%H:%M")
        end_str   = e.strftime("%H:%M")
    except Exception:
        start_str = end_str = "??:??"

    titel  = item.get("termin_titel", "Unbekannt")
    zusatz = item.get("titel_zusatz", "")
    folge  = item.get("episoden_text", "")
    genre  = item.get("hauptgenre", "")

    zeilen = [
        "JETZT AUF BIBEL TV",
        "=" * 35,
        f"⏱  {start_str} – {end_str} Uhr",
        f"\U0001f4fa  {titel}",
    ]
    if zusatz:
        zeilen.append(f"    {zusatz}")
    if folge:
        zeilen.append(f"    {folge}")
    if genre:
        zeilen.append(f"    Genre: {genre}")
    return "\n".join(zeilen)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _ist_privatsender(name: str) -> bool:
    return name.lower().strip() in _PRIVATSENDER


def _resolve_sender(name: str) -> str | None:
    return _SENDER_ID.get(name.lower().strip())


# ── Oeffentliche Skill-Funktionen ─────────────────────────────────────────────

def tv_jetzt() -> str:
    """
    Zeigt was gerade aktuell auf den wichtigsten oeffentlich-rechtlichen
    Sendern laeuft (ARD, ZDF, Arte, 3sat, Phoenix, WDR, HR, One u.a.).
    Beispiel: tv_jetzt()
    """
    haupt_sender = [
        ("Das Erste", "das_erste"),
        ("ZDF",       "zdf"),
        ("arte",      "arte"),
        ("3sat",      "3sat"),
        ("phoenix",   "phoenix"),
        ("One",       "one"),
        ("ZDFinfo",   "zdfinfo"),
        ("ZDFneo",    "zdfneo"),
        ("WDR",       "wdr"),
        ("HR",        "hr"),
        ("NDR",       "ndr"),
        ("BR",        "br"),
        ("SWR",       "swr"),
        ("MDR",       "mdr"),
        ("RBB",       "rbb"),
        ("Tagesschau24", "tagesschau24"),
        ("ARD alpha", "ard_alpha"),
        ("KiKA",      "kika"),
        ("ORF 1",     "orf1"),
        ("ORF 2",     "orf2"),
        ("SRF 1",     "srf1"),
        ("SRF 2",     "srf2"),
    ]

    jetzt_str = datetime.now().strftime("%H:%M Uhr, %d.%m.%Y")
    zeilen = [f"JETZT IM TV – {jetzt_str}", "=" * 45]
    gefunden = 0

    for label, cid in haupt_sender:
        shows = _zapp_get(cid)
        if shows:
            zeilen.append(_format_show(shows[0], label))
            gefunden += 1

    if gefunden == 0:
        return "Aktuell keine Programmdaten verfuegbar. Bitte spaeter erneut versuchen."

    zeilen.append("")
    zeilen.append("ℹ️  Nur oeffentlich-rechtliche Sender. Fuer Bibel TV: tv_sender(\"Bibel TV\")")
    return "\n".join(zeilen)


def tv_sender(sender: str) -> str:
    """
    Zeigt was gerade auf einem bestimmten Sender laeuft.
    Unterstuetzte Sender: ARD/Das Erste, ZDF, Arte, 3sat, Phoenix, One,
    ZDFinfo, ZDFneo, WDR, HR, NDR, BR, SWR, MDR, RBB, KiKA, Tagesschau24,
    ARD alpha, ORF 1, ORF 2, SRF 1, SRF 2, Bibel TV.
    Beispiel: tv_sender(sender="arte")
    Beispiel: tv_sender(sender="ZDF")
    Beispiel: tv_sender(sender="Bibel TV")
    """
    sender_clean = sender.strip()
    sender_lower = sender_clean.lower()

    # Bibel TV via Website-Scraping
    if sender_lower in _BIBELTV_NAMEN:
        datum = datetime.now().strftime("%Y-%m-%d")
        items = _bibeltv_items(datum)
        if not items:
            return "Aktuell keine Programmdaten fuer Bibel TV verfuegbar. Bitte spaeter erneut versuchen."
        item = _bibeltv_aktuell(items)
        if not item:
            return "Kein aktuelles Programm fuer Bibel TV gefunden."
        return _bibeltv_format(item)

    # Bekannte Privatsender
    if _ist_privatsender(sender_clean):
        return (
            f"❌ Kein Programm fuer '{sender_clean}' verfuegbar.\n"
            f"Privatsender (RTL, SAT.1 etc.) werden von keiner\n"
            f"kostenlosen API mit Echtzeitdaten beliefert.\n\n"
            f"Unterstuetzte Sender: {', '.join(sorted({v.replace('_',' ') for v in set(_SENDER_ID.values())}))}, Bibel TV"
        )

    # Zapp API (oeffentlich-rechtlich)
    cid = _resolve_sender(sender_clean)
    if not cid:
        return (
            f"❌ Sender '{sender_clean}' nicht gefunden.\n"
            f"Unterstuetzte Sender:\n  " +
            "\n  ".join(_UNTERSTUETZTE_SENDER) +
            "\n  bibel tv"
        )

    shows = _zapp_get(cid)
    if not shows:
        return (
            f"Aktuell keine Programmdaten fuer '{sender_clean}' verfuegbar.\n"
            f"(Sender ist unterstuetzt, aber gerade keine Daten in der API.)"
        )

    show = shows[0]
    start = _utc_to_local(show.get("startTime", ""))
    end   = _utc_to_local(show.get("endTime", ""))
    titel = show.get("title", "Unbekannt")
    untertitel = show.get("subtitle", "")
    beschr = show.get("description", "")

    zeilen = [
        f"JETZT AUF {sender_clean.upper()}",
        "=" * 35,
        f"⏱  {start} – {end} Uhr",
        f"\U0001f4fa  {titel}",
    ]
    if untertitel:
        zeilen.append(f"    {untertitel}")
    if beschr:
        beschr = re.sub(r"<[^>]+>", " ", beschr).strip()
        kurz = beschr[:200] + ("…" if len(beschr) > 200 else "")
        zeilen.append(f"\n{kurz}")

    return "\n".join(zeilen)


def tv_sender_liste() -> str:
    """
    Zeigt alle Sender fuer die TV-Programmdaten verfuegbar sind.
    Beispiel: tv_sender_liste()
    """
    zeilen = [
        "VERFUEGBARE SENDER",
        "=" * 50,
        "",
        "Oeffentlich-rechtlich DE/AT/CH (via Zapp-API):",
        "  ARD-Familie:  Das Erste, One, ARD alpha, Tagesschau24",
        "                BR, HR, MDR, NDR, RBB, SWR, WDR",
        "  ZDF-Familie:  ZDF, ZDFinfo, ZDFneo",
        "  Weitere:      arte, 3sat, phoenix, KiKA",
        "  Oesterreich:  ORF 1, ORF 2",
        "  Schweiz:      SRF 1, SRF 2, SRFinfo",
        "",
        "Christlich (via Website-Scraping):",
        "  Bibel TV",
        "",
        "❌ Nicht verfuegbar (keine freie API):",
        "  RTL, SAT.1, ProSieben, VOX, Kabel Eins,",
        "  n-tv, WELT und alle weiteren Privatsender",
    ]
    return "\n".join(zeilen)


AVAILABLE_SKILLS = [
    tv_jetzt,
    tv_sender,
    tv_sender_liste,
]