"""
phone_dialog.py – Enterprise-Voice-Dialog (strikte Python-State-Machine)
========================================================================
Architektur (nach Vapi/Retell/Pipecat-Flows Best Practice):
  - Python steuert ALLE Übergänge im Termin-Flow (kein LLM-Dialog-Routing)
  - Templated Responses für Buchung/Stornierung/Identifikation
  - Konkrete 60-Minuten-Slots werden in Python generiert (nicht freie Intervalle)
  - LLM kommt NUR zum Einsatz für:
       * Intent-Erkennung am Gespräch-Start (mit Pattern-Fallback)
       * Allgemeine Fragen (Öffnungszeiten etc.) mit Knowledge-Base
  - Spelling-Mode komplett in Python
  - Robust gegen STT-Fehler (mehrere Match-Heuristiken pro Eingabe)
"""

import re
import sys
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════
# KONSTANTEN
# ════════════════════════════════════════════════════════════════════

MAX_HISTORY_TURNS  = 10
MAX_NAME_RETRIES    = 2    # nach 2 Namen-Fehlern → Buchstabieren
MAX_OTHER_RETRIES   = 3    # nach 3 Fehlern in einem Slot → Eskalation
MAX_CONFIRM_RETRIES = 5    # Bestätigungs-States bekommen mehr Versuche (Spracherkennung braucht manchmal mehrere Anläufe)
MAX_REPEATS         = 3    # nach 3 identischen Antworten in Folge → Eskalation
MAX_USER_REPEATS    = 4    # nach 4 identischen User-Eingaben in Folge → Eskalation
MAX_SPELLING_FAILS  = 2    # nach 2 leeren Buchstabier-Versuchen → Eskalation
SLOT_DAUER_MIN     = 60   # Fallback falls verfuegbarkeit.txt keinen [SLOT_DAUER]-Eintrag hat
ARBEITSBEGINN_H    = 8
ARBEITSENDE_H      = 18
SUCHE_VOR_TAGEN    = 60    # max. Tage in die Zukunft für Slot-Suche

ESKALATIONS_NACHRICHT = (
    "Es tut mir leid, wir verstehen uns gerade leider nicht ganz richtig. "
    "Damit Sie Ihr Anliegen sicher klären können, würde ich Sie bitten, "
    "es kurz später noch einmal zu versuchen oder uns direkt zurückzurufen. "
    "Vielen Dank für Ihren Anruf und auf Wiederhören."
)

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]
MONATE     = ["Januar", "Februar", "März", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]

WOCHENTAG_NUM = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6,
}

MONAT_NUM = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

ORDINAL_NUM = {
    "ersten": 1, "erster": 1, "zweiten": 2, "zweiter": 2, "dritten": 3, "dritter": 3,
    "vierten": 4, "vierter": 4, "fünften": 5, "fünfter": 5, "sechsten": 6, "sechster": 6,
    "siebten": 7, "siebter": 7, "siebenten": 7, "achten": 8, "achter": 8,
    "neunten": 9, "neunter": 9, "zehnten": 10, "zehnter": 10,
    "elften": 11, "elfter": 11, "zwölften": 12, "zwölfter": 12,
    "dreizehnten": 13, "vierzehnten": 14, "fünfzehnten": 15, "sechzehnten": 16,
    "siebzehnten": 17, "achtzehnten": 18, "neunzehnten": 19, "zwanzigsten": 20,
    "einundzwanzigsten": 21, "zweiundzwanzigsten": 22, "dreiundzwanzigsten": 23,
    "vierundzwanzigsten": 24, "fünfundzwanzigsten": 25, "sechsundzwanzigsten": 26,
    "siebenundzwanzigsten": 27, "achtundzwanzigsten": 28, "neunundzwanzigsten": 29,
    "dreißigsten": 30, "einunddreißigsten": 31,
}

UHRZEIT_WORTE = {
    "halb eins": "12:30", "halb zwei": "13:30", "halb drei": "14:30",
    "halb vier": "15:30", "halb fünf": "16:30", "halb sechs": "17:30",
    "halb sieben": "06:30", "halb acht": "07:30", "halb neun": "08:30",
    "halb zehn": "09:30", "halb elf": "10:30", "halb zwölf": "11:30",
    "ein uhr": "13:00", "zwei uhr": "14:00", "drei uhr": "15:00",
    "vier uhr": "16:00", "fünf uhr": "17:00",
    "acht uhr": "08:00", "neun uhr": "09:00", "zehn uhr": "10:00",
    "elf uhr": "11:00", "zwölf uhr": "12:00",
    "dreizehn uhr": "13:00", "vierzehn uhr": "14:00",
    "fünfzehn uhr": "15:00", "sechzehn uhr": "16:00",
    "siebzehn uhr": "17:00", "achtzehn uhr": "18:00",
}

H_WORT = {
    0:"null",1:"ein",2:"zwei",3:"drei",4:"vier",5:"fünf",6:"sechs",7:"sieben",
    8:"acht",9:"neun",10:"zehn",11:"elf",12:"zwölf",13:"dreizehn",14:"vierzehn",
    15:"fünfzehn",16:"sechzehn",17:"siebzehn",18:"achtzehn",19:"neunzehn",
    20:"zwanzig",21:"einundzwanzig",22:"zweiundzwanzig",23:"dreiundzwanzig",
}

ZAHL_WORTE = {
    "null": 0, "eins": 1, "ein": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7,
    "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "dreizehn": 13, "vierzehn": 14,
    "fünfzehn": 15, "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19, "zwanzig": 20,
    "fünfundzwanzig": 25, "dreißig": 30, "fünfunddreißig": 35, "vierzig": 40, "fünfundvierzig": 45,
    "fünfzig": 50, "fünfundfünfzig": 55,
}

PHONETIC = {
    "anton":"A","ärger":"Ä","berta":"B","cäsar":"C","caesar":"C","dora":"D",
    "emil":"E","friedrich":"F","gustav":"G","heinrich":"H","ida":"I",
    "julius":"J","kaufmann":"K","ludwig":"L","martha":"M","nordpol":"N",
    "ökonom":"Ö","otto":"O","paula":"P","quelle":"Q","richard":"R",
    "samuel":"S","siegfried":"S","theodor":"T","übermut":"Ü","ulrich":"U",
    "viktor":"V","wilhelm":"W","xanthippe":"X","ypsilon":"Y","zacharias":"Z",
    "eszett":"ß","scharf-s":"ß","scharfes-s":"ß",
    "alpha":"A","bravo":"B","charlie":"C","delta":"D","echo":"E","foxtrot":"F",
    "golf":"G","hotel":"H","india":"I","juliet":"J","juliett":"J","kilo":"K",
    "lima":"L","mike":"M","november":"N","oscar":"O","papa":"P","quebec":"Q",
    "romeo":"R","sierra":"S","tango":"T","uniform":"U","victor":"V","whiskey":"W",
    "whisky":"W","x-ray":"X","xray":"X","yankee":"Y","zulu":"Z",
}

FERTIG_WORTE = frozenset((
    "fertig","ende","schluss","stop","stopp","das war's","das wars",
    "das war alles","das ist alles","abschluss","ok das wars","ok fertig",
))

JA_WORTE = ("ja","jaa","jaaa","jo","joa","jep","jepp","yep","yes","yeah",
            "genau","richtig","stimmt","korrekt","gerne","gern","okay","ok",
            "jawohl","natürlich","sicher","passt","super","wunderbar",
            "bitte","gut so","perfekt","klingt gut","stimmt so","passt so",
            "richtig so","mhm","mhmm")
NEIN_WORTE = ("nein","nö","noe","nee","ne","falsch","doch nicht",
              "anders","stimmt nicht","nicht richtig","passt nicht",
              "ne danke","nein danke","auf keinen fall","lieber nicht","nope")
ABSCHIEDS_WORTE = ("auf wiederhören","wiederhören","auf wiederhoeren","wiederhoeren",
                   "wiederschauen","wiederschau'n","tschüss","tschuess","tschuess",
                   "ciao","bye","ade","schönen tag","schoenen tag",
                   "schönes wochenende","schoenes wochenende",
                   "danke und tschüss","das wars dann","mehr brauche ich nicht",
                   "danke das war alles","reicht mir so")

# ════════════════════════════════════════════════════════════════════
# HELFER
# ════════════════════════════════════════════════════════════════════

def datum_de(datum_str: str) -> str:
    """TT.MM.JJJJ → 'Montag, siebenundzwanzigster April'."""
    try:
        dt = datetime.strptime(datum_str, "%d.%m.%Y")
        tag = dt.day
        ordinal = next((w for w, n in ORDINAL_NUM.items() if n == tag), str(tag))
        ordinal_er = ordinal.replace("ten", "ter") if ordinal.endswith("ten") else ordinal
        return f"{WOCHENTAGE[dt.weekday()]}, {ordinal_er} {MONATE[dt.month-1]}"
    except Exception:
        return datum_str


def datum_kurz_de(datum_str: str) -> str:
    """TT.MM.JJJJ → 'siebenundzwanzigster April'."""
    try:
        dt = datetime.strptime(datum_str, "%d.%m.%Y")
        tag = dt.day
        ordinal = next((w for w, n in ORDINAL_NUM.items() if n == tag), str(tag))
        ordinal_er = ordinal.replace("ten", "ter") if ordinal.endswith("ten") else ordinal
        return f"{ordinal_er} {MONATE[dt.month-1]}"
    except Exception:
        return datum_str


def uhrzeit_de(hhmm: str) -> str:
    """HH:MM → 'zehn Uhr' / 'halb elf' (vormittag) / 'vierzehn Uhr dreißig' (24h ab nachmittag)."""
    try:
        h, m = map(int, hhmm.split(":"))
        if m == 0:
            return f"{H_WORT.get(h, str(h))} Uhr"
        if m == 30 and h < 12:
            return f"halb {H_WORT.get(h+1, str(h+1))}"
        return f"{H_WORT.get(h, str(h))} Uhr {m}"
    except Exception:
        return hhmm


def ist_telefonnummer(wert: str) -> bool:
    return len(re.sub(r'[^\d]', '', wert or "")) >= 5


def normalisiere_namen(s: str) -> str:
    return " ".join(w.capitalize() for w in (s or "").strip().split())


# ════════════════════════════════════════════════════════════════════
# PARSER
# ════════════════════════════════════════════════════════════════════

def naechster_wochentag(ziel_wt: int, ab: Optional[date] = None) -> date:
    ab = ab or datetime.now().date()
    diff = (ziel_wt - ab.weekday()) % 7
    if diff == 0:
        diff = 7
    return ab + timedelta(days=diff)


def parse_datum(text: str) -> Optional[str]:
    """Single-Day-Parser. Rückgabe TT.MM.JJJJ oder None."""
    if not text:
        return None
    t     = text.lower().strip()
    heute = datetime.now().date()

    # Relativbegriffe
    if re.search(r'\büber\s?morgen\b', t) or re.search(r'\buebermorgen\b', t):
        return (heute + timedelta(days=2)).strftime("%d.%m.%Y")
    if re.search(r'\bmorgen\b', t):
        return (heute + timedelta(days=1)).strftime("%d.%m.%Y")
    if re.search(r'\bheute\b', t):
        return heute.strftime("%d.%m.%Y")

    m = re.search(r'in\s+(\d+|einer|eine|zwei|drei|vier|fünf)\s+(tag|tagen|woche|wochen)', t)
    if m:
        zahl_map = {"einer":1,"eine":1,"zwei":2,"drei":3,"vier":4,"fünf":5}
        wert = m.group(1)
        n = int(wert) if wert.isdigit() else zahl_map.get(wert, 0)
        if "woche" in m.group(2):
            n *= 7
        if n > 0:
            return (heute + timedelta(days=n)).strftime("%d.%m.%Y")

    # Zahl + Monatsname ZUERST (spezifischer als Wochentag)
    # z.B. "28 Mai", "28. Mai", "Donnerstag 28. Mai", "Freitag 2. Juni"
    _monat_pattern = '|'.join(MONAT_NUM.keys())
    _m_early = re.search(rf'(\d{{1,2}})\.?\s+({_monat_pattern})\b', t)
    if _m_early:
        try:
            tag_z = int(_m_early.group(1))
            mon_z = MONAT_NUM[_m_early.group(2)]
            dt = date(heute.year, mon_z, tag_z)
            if dt < heute:
                dt = date(heute.year + 1, mon_z, tag_z)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            pass

    # Wochentage
    for wort, wt in WOCHENTAG_NUM.items():
        if re.search(rf'\b{wort}\b', t):
            return naechster_wochentag(wt, heute).strftime("%d.%m.%Y")

    # Ordinal + Monat / Ordinal allein
    for ord_wort, tag in ORDINAL_NUM.items():
        if re.search(rf'\b{ord_wort}\b', t):
            for mo_wort, mon in MONAT_NUM.items():
                if re.search(rf'\b{mo_wort}\b', t):
                    try:
                        dt = date(heute.year, mon, tag)
                        if dt < heute:
                            dt = date(heute.year + 1, mon, tag)
                        return dt.strftime("%d.%m.%Y")
                    except ValueError:
                        pass
            try:
                dt = date(heute.year, heute.month, tag)
                if dt < heute:
                    nm = heute.month + 1
                    ny = heute.year + (1 if nm > 12 else 0)
                    nm = nm if nm <= 12 else 1
                    dt = date(ny, nm, tag)
                return dt.strftime("%d.%m.%Y")
            except ValueError:
                pass

    # Numerisch mit Punkt/Schrägstrich (z.B. "28.05", "28.05.2026")
    m = re.search(r'(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?', text)
    if m:
        tag, mon = int(m.group(1)), int(m.group(2))
        jahr = int(m.group(3)) if m.group(3) else heute.year
        if len(str(jahr)) == 2:
            jahr += 2000
        try:
            dt = date(jahr, mon, tag)
            if dt < heute:
                dt = date(dt.year + 1, dt.month, dt.day)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            pass
    return None


def parse_zeitraum(text: str) -> Optional[Tuple[date, date]]:
    """Erkennt Zeitspannen wie 'nächste Woche', 'übernächste Woche',
    'in der ersten Mai-Woche'. Rückgabe (start_date, end_date) oder None."""
    if not text:
        return None
    t = text.lower().strip()
    heute = datetime.now().date()

    # Anfang nächster Woche = nächster Montag
    naechster_mo = naechster_wochentag(0, heute)
    naechster_fr = naechster_mo + timedelta(days=4)

    if re.search(r'\bnächste\w*\s+woche\b', t) or re.search(r'\bnaechste\w*\s+woche\b', t):
        return (naechster_mo, naechster_fr)
    if re.search(r'\büber\s?nächste\w*\s+woche\b', t) or re.search(r'\buebernaechste\w*\s+woche\b', t):
        return (naechster_mo + timedelta(days=7), naechster_fr + timedelta(days=7))
    if re.search(r'\bdiese\w*\s+woche\b', t):
        # Diese Woche = von heute bis Freitag (falls heute < Fr) sonst nächste Woche
        return (heute, heute + timedelta(days=(4 - heute.weekday()) % 7))
    if re.search(r'\bnächste\w*\s+monat\b', t) or re.search(r'\bnaechste\w*\s+monat\b', t):
        nm = heute.month + 1
        ny = heute.year + (1 if nm > 12 else 0)
        nm = nm if nm <= 12 else 1
        try:
            start = date(ny, nm, 1)
            # Ende = letzter Tag des Monats
            if nm == 12:
                end = date(ny + 1, 1, 1) - timedelta(days=1)
            else:
                end = date(ny, nm + 1, 1) - timedelta(days=1)
            return (start, end)
        except ValueError:
            pass
    return None


def parse_uhrzeit(text: str) -> Optional[str]:
    """Toleranter Uhrzeit-Parser für STT-typische Eingaben."""
    if not text:
        return None
    t = text.lower()

    # 1. Wortformen ("halb zehn", "zehn uhr") — sortiert nach Länge absteigend
    for wort, zeit in sorted(UHRZEIT_WORTE.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf'\b{re.escape(wort)}\b', t):
            return zeit

    # 1b. "halb X" mit Ziffer ("halb 10" = 09:30)
    m = re.search(r'\bhalb\s+(\d{1,2})\b', t)
    if m:
        h = int(m.group(1)) - 1
        if h < 0:
            h = 23
        return f"{h:02d}:30"

    # 2. Numerisch: "10:30", "10.30", "10,30"
    m = re.search(r'\b(\d{1,2})\s*[:.,]\s*(\d{2})\b', t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    # 3. "10 uhr 30" / "10 uhr"
    m = re.search(r'\b(\d{1,2})\s*uhr(?:\s*(\d{1,2}))?\b', t)
    if m:
        h  = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    # 3b. "vierzehn uhr dreißig" (Wörter)
    wort_pattern = "|".join(ZAHL_WORTE.keys())
    m = re.search(rf'\b({wort_pattern})\s+uhr\s+({wort_pattern})\b', t)
    if m:
        h = ZAHL_WORTE.get(m.group(1))
        mi = ZAHL_WORTE.get(m.group(2))
        if h is not None and mi is not None and 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    # 4. Stunden-Wörter ALLEIN ohne "uhr" (häufig bei STT-Fehlern: "neun" statt "neun uhr")
    NUR_STUNDE = {
        "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12,
        "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "sechzehn": 16,
        "siebzehn": 17, "achtzehn": 18,
    }
    for wort, h in NUR_STUNDE.items():
        if re.search(rf'\b{wort}\b', t):
            return f"{h:02d}:00"

    # 5. "um 10" / "gegen 10" / "für 14"
    m = re.search(r'\b(?:um|gegen|für|fuer)\s+(\d{1,2})\b', t)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return f"{h:02d}:00"

    return None


def parse_yesno(text: str) -> Optional[bool]:
    """Robust gegen Satzzeichen, Mehrfachvokale, STT-Varianten und DTMF (1/2)."""
    if not text:
        return None
    # DTMF-Tasten (vom FritzBox-Skill als reine Ziffer-Strings übergeben)
    s = text.strip()
    if s == "1":
        return True
    if s == "2":
        return False
    # Satzzeichen entfernen, lowercase, mehrfache Spaces normalisieren
    t = re.sub(r'[^\w\säöüß]', ' ', text.lower())
    t = re.sub(r'\s+', ' ', t).strip()
    if not t:
        return None
    t_padded = " " + t + " "
    # Nein zuerst (sonst würde "ne" in "gerne" matchen)
    for w in NEIN_WORTE:
        if f" {w} " in t_padded:
            return False
    for w in JA_WORTE:
        if f" {w} " in t_padded:
            return True
    return None


def parse_telefon(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'[\d][\d\s\+\-/()]{4,}', text)
    if m:
        kandidat = m.group(0).strip()
        if ist_telefonnummer(kandidat):
            return kandidat
    return None


def ist_abschied(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    return any(w in t for w in ABSCHIEDS_WORTE)


def ist_spelling_input(text: str) -> bool:
    if not text:
        return False
    tokens = re.findall(r'\b\w+\b', text.lower())
    if not tokens:
        return False
    treffer = sum(1 for tok in tokens
                  if tok in PHONETIC or tok in FERTIG_WORTE
                  or (len(tok) == 1 and tok.isalpha()))
    return treffer >= max(2, len(tokens) // 2)


def extract_letters(text: str) -> Tuple[List[str], bool]:
    t = text.lower()
    is_done = any(w in t for w in FERTIG_WORTE)
    letters: List[str] = []
    for tok in re.findall(r'\b\w+\b', t):
        if tok in FERTIG_WORTE:
            continue
        if tok in PHONETIC:
            letters.append(PHONETIC[tok])
        elif len(tok) == 1 and tok.isalpha():
            letters.append(tok.upper())
    return letters, is_done


# ════════════════════════════════════════════════════════════════════
# INTENT-ERKENNUNG (Pattern-First, kein LLM nötig im Normalfall)
# ════════════════════════════════════════════════════════════════════

class Intent(Enum):
    BUCHEN     = "buchen"
    ABFRAGEN   = "abfragen"
    STORNIEREN = "stornieren"
    INFO       = "info"
    NOTIZ      = "notiz"
    ABSCHIED   = "abschied"
    UNKLAR     = "unklar"


def erkenne_intent(text: str) -> Intent:
    """Pattern-basierte Intent-Erkennung. Robust ohne LLM."""
    if not text:
        return Intent.UNKLAR
    t = text.lower()

    if ist_abschied(t):
        return Intent.ABSCHIED

    # Stornieren — höchste Priorität (sonst würde "termin" "buchen" matchen)
    if any(w in t for w in ("stornier", "absag", "absagen", "cancel",
                            "abmeld", "löschen", "löschen sie", "nicht mehr",
                            "doch nicht", "wieder absagen")):
        return Intent.STORNIEREN

    # Abfragen
    if any(w in t for w in ("welche termin", "meine termin", "habe ich",
                            "wann bin ich", "wann habe ich", "übersicht",
                            "was steht an", "was hab ich")):
        return Intent.ABFRAGEN

    # Notiz hinterlassen — vor BUCHEN prüfen, da "möchte" sonst BUCHEN auslöst
    if any(w in t for w in ("nachricht", "notiz", "ausrichten", "bescheid",
                            "hinterlassen", "hinterlass", "ich wollte nur",
                            "bitte sagen sie", "bitte richten sie")):
        return Intent.NOTIZ

    # Info / allgemeine Fragen
    if any(w in t for w in ("öffnungszeit", "sprechzeit", "geöffnet",
                            "wann sind sie", "wann habt ihr", "wann öffnet",
                            "haben sie auf", "wie lange", "adresse",
                            "wo befindet", "wo finde ich", "wie komme ich",
                            "preis", "kostet", "was kostet")):
        return Intent.INFO

    # Buchen — "möchte"/"hätte gerne" entfernt (zu unspezifisch, matcht alles)
    if any(w in t for w in ("termin", "vereinbar", "buchen", "anlegen",
                            "anmelden", "buchung", "neuer termin",
                            "neuen termin", "einen termin")):
        return Intent.BUCHEN

    return Intent.UNKLAR


# ════════════════════════════════════════════════════════════════════
# KALENDER-WRAPPER + KONKRETE SLOT-GENERIERUNG
# ════════════════════════════════════════════════════════════════════

def _kalender_funk(name: str):
    try:
        import skills.lokaler_kalender_skill as ks
    except ImportError:
        sd = str(Path(__file__).resolve().parent / "skills")
        if sd not in sys.path:
            sys.path.insert(0, sd)
        import lokaler_kalender_skill as ks  # type: ignore
    return getattr(ks, name)


def _freie_intervalle(datum: str) -> List[Tuple[str, str]]:
    """Holt freie Intervalle vom Kalender-Skill (Format: [(von, bis), ...])."""
    try:
        roh = _kalender_funk("lokaler_kalender_freie_slots_finden")(
            datum=datum,
            dauer_minuten=_lese_slot_dauer(),
            arbeit_von=ARBEITSBEGINN_H,
            arbeit_bis=ARBEITSENDE_H,
        )
        return re.findall(r'(\d{2}:\d{2})\s*[–\-]\s*(\d{2}:\d{2})', roh)
    except Exception as e:
        logger.error(f"[PhoneDialog] _freie_intervalle: {e}")
        return []


def konkrete_slots(datum: str, dauer_min: int = 0) -> List[Tuple[str, str]]:
    """Aus den freien Intervallen konkrete dauer_min-Slots machen.
    Beispiel: Intervall 08:00–18:00 (10h frei) → [(08:00,09:00), (09:00,10:00), ...]
    Filtert fehlerhafte Kalender-Einträge (Endzeit <= Startzeit) und dedupliziert."""
    if dauer_min <= 0:
        dauer_min = _lese_slot_dauer()
    intervalle = _freie_intervalle(datum)
    konkret: List[Tuple[str, str]] = []
    for von, bis in intervalle:
        try:
            v_h, v_m = map(int, von.split(":"))
            b_h, b_m = map(int, bis.split(":"))
            startmin = v_h * 60 + v_m
            endmin   = b_h * 60 + b_m
            # Fehlerhafter Eintrag: Endzeit vor oder gleich Startzeit → überspringen
            if endmin <= startmin:
                logger.warning(f"[konkrete_slots] Interval ignoriert (Ende<=Start): {von}–{bis}")
                continue
            # Auf nächste volle Stunde aufrunden
            if v_m != 0:
                startmin = ((startmin + 59) // 60) * 60
            cur = startmin
            while cur + dauer_min <= endmin:
                sh, sm = divmod(cur, 60)
                eh, em = divmod(cur + dauer_min, 60)
                # Mittagspause 12:00–13:00 generell überspringen
                if not (sh == 12 and sm == 0):
                    slot = (f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}")
                    if slot not in konkret:
                        konkret.append(slot)
                cur += dauer_min
        except Exception:
            continue
    return konkret


def naechster_freier_tag(ab_datum: str, max_tage: int = SUCHE_VOR_TAGEN) -> Optional[str]:
    """Findet den nächsten Werktag mit mindestens einem konkreten freien Slot."""
    try:
        ab = datetime.strptime(ab_datum, "%d.%m.%Y").date()
    except Exception:
        return None
    for i in range(1, max_tage + 1):
        kand = ab + timedelta(days=i)
        if kand.weekday() >= 5:
            continue
        if konkrete_slots(kand.strftime("%d.%m.%Y")):
            return kand.strftime("%d.%m.%Y")
    return None


def freier_tag_in_zeitraum(start: date, end: date) -> Optional[str]:
    """Findet den ersten Werktag im Zeitraum mit freien Slots."""
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            datum = cur.strftime("%d.%m.%Y")
            if konkrete_slots(datum):
                return datum
        cur += timedelta(days=1)
    return None

def naechste_n_slots(ab_datum: str, n: int = 3, max_tage: int = SUCHE_VOR_TAGEN):
    """Sammelt die n naechsten freien Slots tagesubergreifend.
    Rueckgabe: (slots, datums) parallel indiziert.
    Beispiel: slots[0]=("09:00","10:00"), datums[0]="28.04.2026"
    """
    try:
        ab = datetime.strptime(ab_datum, "%d.%m.%Y").date()
    except Exception:
        return [], []
    slots_gesamt = []
    datums_gesamt = []
    cur = ab
    for _ in range(max_tage):
        if len(slots_gesamt) >= n:
            break
        if cur.weekday() >= 5:          # Wochenende ueberspringen
            cur += timedelta(days=1)
            continue
        datum_str = cur.strftime("%d.%m.%Y")
        tages_slots = konkrete_slots(datum_str)
        noch_benoetigt = n - len(slots_gesamt)
        if len(tages_slots) <= noch_benoetigt:
            auswahl = tages_slots
        else:
            if noch_benoetigt > 1:
                idxs = [int(i * (len(tages_slots) - 1) / (noch_benoetigt - 1))
                        for i in range(noch_benoetigt)]
            else:
                idxs = [0]
            auswahl = [tages_slots[i] for i in idxs]
        for s in auswahl:
            slots_gesamt.append(s)
            datums_gesamt.append(datum_str)
        cur += timedelta(days=1)
    return slots_gesamt, datums_gesamt


# ════════════════════════════════════════════════════════════════════
# SLOT-AUSWAHL (welcher Slot meint der Anrufer?)
# ════════════════════════════════════════════════════════════════════

def waehle_slot(text: str, slots: List[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    """Versucht aus Anrufer-Eingabe einen der angebotenen Slots zu identifizieren.
    Robust gegen STT-Variationen: Uhrzeit, Ordinal, Tageszeit, DTMF-Ziffer."""
    if not slots:
        return None
    t = text.lower()

    # 1. Konkrete Uhrzeit
    z = parse_uhrzeit(text)
    if z:
        for von, bis in slots:
            if von == z:
                return (von, bis)
        # Toleranz: nur Stunde matchen
        z_h = z[:2]
        for von, bis in slots:
            if von[:2] == z_h:
                return (von, bis)

    # 2. Ordinal ("die zweite", "den dritten")
    for wort, idx in [("erst", 0), ("zweit", 1), ("dritt", 2), ("viert", 3),
                      ("fünft", 4), ("letzt", -1)]:
        if re.search(rf'\b{wort}\w*\b', t) and (idx == -1 or idx < len(slots)):
            return slots[idx]

    # 3. DTMF-Ziffer (reine "1", "2", ...) als Slot-Index
    nur_ziffer = text.strip()
    if nur_ziffer.isdigit():
        idx = int(nur_ziffer) - 1
        if 0 <= idx < len(slots):
            return slots[idx]

    # 4. Tageszeit-Hinweise
    if any(w in t for w in ("vormittag", "morgens", "frueh", "früh", "zeitig")):
        vormittag = [s for s in slots if int(s[0][:2]) < 12]
        if vormittag:
            return vormittag[0]
        return slots[0]
    if any(w in t for w in ("nachmittag", "abends", "spät", "spaet", "später", "spaeter")):
        nachmittag = [s for s in slots if int(s[0][:2]) >= 13]
        if nachmittag:
            return nachmittag[0]
        return slots[-1]
    if "mittag" in t:
        mittag = [s for s in slots if 11 <= int(s[0][:2]) <= 14]
        if mittag:
            return mittag[0]

    # 5. Bloße Ziffer im Satz ("ich nehme die 2")
    for i, slot in enumerate(slots, 1):
        if re.search(rf'\b{i}\b', t):
            return slot

    # 6. Wenn nur ein Slot da ist → automatisch wählen
    if len(slots) == 1:
        return slots[0]

    return None


# ════════════════════════════════════════════════════════════════════
# VERFÜGBARKEIT → LESBARER TEXT (für Telefon-Auskunft)
# ════════════════════════════════════════════════════════════════════

_TAGE_LANG = {
    "MO": "Montag", "DI": "Dienstag", "MI": "Mittwoch",
    "DO": "Donnerstag", "FR": "Freitag", "SA": "Samstag", "SO": "Sonntag",
}
_WOCHENTAG_ORDER = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def _lese_verfuegbarkeit() -> str:
    """
    Liest data/verfuegbarkeit.txt und gibt einen menschenlesbaren Text zurück,
    den der Telefon-Assistent als Kontext für Öffnungszeiten-Auskünfte benutzt.
    Fehlende Wochentage erhalten die Standard-Arbeitszeiten aus den Konstanten.
    """
    pfad = Path(__file__).resolve().parent / "data" / "verfuegbarkeit.txt"
    if not pfad.exists():
        return ""

    try:
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""

    tage: dict = {}       # "MO" → "09:00 - 17:00" oder "Geschlossen"
    urlaub: list = []
    feiertage: list = []
    hinweise: list = []

    for zeile in zeilen:
        z = zeile.strip()
        if not z or z.startswith("#"):
            continue

        # Wochentag: [MO] 09:00 - 17:00  oder  [SA] Geschlossen
        m = re.match(r'\[(MO|DI|MI|DO|FR|SA|SO)\]\s+(.*)', z, re.IGNORECASE)
        if m:
            kuerzel = m.group(1).upper()
            wert = m.group(2).strip()
            tage[kuerzel] = wert
            continue

        # Urlaub: [URLAUB] 2026-08-03 - 2026-08-14 Sommerurlaub
        m = re.match(r'\[URLAUB\]\s+(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})\s*(.*)',
                     z, re.IGNORECASE)
        if m:
            von_str, bis_str, name = m.group(1), m.group(2), m.group(3).strip()
            # Nur zukünftige/laufende Urlaube zeigen
            try:
                bis_dt = datetime.strptime(bis_str, "%Y-%m-%d").date()
                if bis_dt >= date.today():
                    von_de = datetime.strptime(von_str, "%Y-%m-%d").strftime("%-d. %B %Y") if hasattr(datetime, 'strptime') else von_str
                    bis_de = datetime.strptime(bis_str, "%Y-%m-%d").strftime("%-d. %B %Y")
                    # Windows-kompatibles Format (kein %-d)
                    von_de = datetime.strptime(von_str, "%Y-%m-%d").strftime("%d.%m.%Y").lstrip("0")
                    bis_de = datetime.strptime(bis_str, "%Y-%m-%d").strftime("%d.%m.%Y").lstrip("0")
                    eintrag = f"{name}: {von_de} bis {bis_de}" if name else f"{von_de} bis {bis_de}"
                    urlaub.append(eintrag)
            except Exception:
                pass
            continue

        # Feiertag: [FEIERTAG] 2026-04-03 Karfreitag
        m = re.match(r'\[FEIERTAG\]\s+(\d{4}-\d{2}-\d{2})\s+(.*)', z, re.IGNORECASE)
        if m:
            datum_str, name = m.group(1), m.group(2).strip()
            try:
                dt = datetime.strptime(datum_str, "%Y-%m-%d").date()
                # Nur kommende 60 Tage zeigen
                delta = (dt - date.today()).days
                if 0 <= delta <= 60:
                    datum_de = dt.strftime("%d.%m.%Y").lstrip("0")
                    feiertage.append(f"{name} ({datum_de})")
            except Exception:
                pass
            continue

        # Hinweis: [HINWEIS] Text
        m = re.match(r'\[HINWEIS\]\s+(.*)', z, re.IGNORECASE)
        if m:
            hinweise.append(m.group(1).strip())

    # Ausgabe aufbauen
    zeilen_out = ["ÖFFNUNGSZEITEN:"]
    standard = f"{ARBEITSBEGINN_H:02d}:00 - {ARBEITSENDE_H:02d}:00"
    for kuerzel in _WOCHENTAG_ORDER:
        lang = _TAGE_LANG[kuerzel]
        wert = tage.get(kuerzel, standard)
        zeilen_out.append(f"  {lang}: {wert}")

    if urlaub:
        zeilen_out.append("\nBETRIEBSFERIEN / URLAUB:")
        for u in urlaub:
            zeilen_out.append(f"  {u}")

    if feiertage:
        zeilen_out.append("\nKOMMENDE FEIERTAGE (geschlossen):")
        for f in feiertage:
            zeilen_out.append(f"  {f}")

    if hinweise:
        zeilen_out.append("\nHINWEISE:")
        for h in hinweise:
            zeilen_out.append(f"  {h}")

    return "\n".join(zeilen_out)


def _lese_slot_dauer() -> int:
    """Liest [SLOT_DAUER] aus verfuegbarkeit.txt. Fallback: SLOT_DAUER_MIN."""
    pfad = Path(__file__).resolve().parent / "data" / "verfuegbarkeit.txt"
    if not pfad.exists():
        return SLOT_DAUER_MIN
    try:
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            m = re.match(r'\[SLOT_DAUER\]\s+(\d+)', zeile.strip(), re.IGNORECASE)
            if m:
                dauer = int(m.group(1))
                return dauer if dauer >= 5 else SLOT_DAUER_MIN
    except Exception:
        pass
    return SLOT_DAUER_MIN


# ════════════════════════════════════════════════════════════════════
# STATE MACHINE
# ════════════════════════════════════════════════════════════════════

class State(Enum):
    INIT             = "init"
    INTENT           = "intent"
    BOOK_TOPIC       = "book_topic"
    BOOK_DATE        = "book_date"
    BOOK_SLOT        = "book_slot"
    BOOK_FIRSTNAME   = "book_firstname"
    BOOK_LASTNAME    = "book_lastname"
    BOOK_PHONE       = "book_phone"
    BOOK_NOTES       = "book_notes"
    BOOK_CONFIRM     = "book_confirm"
    BOOK_DONE        = "book_done"
    IDENT_FIRSTNAME  = "ident_firstname"
    IDENT_LASTNAME   = "ident_lastname"
    IDENT_PHONE      = "ident_phone"
    QUERY_RESULT     = "query_result"
    CANCEL_LIST      = "cancel_list"
    CANCEL_CONFIRM   = "cancel_confirm"
    CANCEL_DONE      = "cancel_done"
    GENERAL          = "general"
    NOTIZ            = "notiz"
    END              = "end"


@dataclass
class Slots:
    # Identifikation (wird für Abfrage/Stornierung Pflicht)
    caller_id:    str = ""
    vorname:      str = ""
    nachname:     str = ""
    # Buchung
    intent:       Intent = Intent.UNKLAR
    intent_nach_ident: Intent = Intent.UNKLAR  # was nach Ident ausgeführt wird
    topic:        str = ""
    datum:        str = ""
    angebotene_slots: list = field(default_factory=list)
    angebotene_slots_datums: list = field(default_factory=list)  # Datum je Slot
    chosen_von:   str = ""
    chosen_bis:   str = ""
    notes:        str = ""
    # Stornierung
    cancel_termine: list = field(default_factory=list)  # [(datum, von, titel), ...]
    cancel_datum:   str = ""
    cancel_uhrzeit: str = ""
    # Spelling
    spelling_active: bool = False
    spelling_for:    str  = ""  # 'vorname' | 'nachname'
    spelling_buffer: list = field(default_factory=list)
    # Retries
    retries:      dict = field(default_factory=dict)


class PhoneDialog:
    """Strikte Python-State-Machine für den Telefon-Dialog."""

    def __init__(self, provider, config: dict,
                 info_reader=None, caller_id: str = ""):
        self.provider    = provider
        self.config      = config
        self.info_reader = info_reader
        self.state       = State.INIT
        self.slots       = Slots(caller_id=(caller_id or "").strip())
        self._history: List[dict] = []          # NUR für GENERAL-Modus
        # Loop-Detection
        self._last_response: str = ""
        self._repeat_count: int  = 0
        self._last_user_input: str = ""
        self._user_repeat_count: int = 0

    # ── Öffentliche API ──────────────────────────────────────────────

    def set_caller_id(self, caller_id: str):
        self.slots.caller_id = (caller_id or "").strip()

    def reset(self):
        self.state = State.INIT
        self.slots = Slots()
        self._history = []
        self._last_response = ""
        self._repeat_count = 0
        self._last_user_input = ""
        self._user_repeat_count = 0

    def process(self, user_input: str) -> str:
        """Hauptmethode: Verarbeitet einen User-Turn."""
        if user_input is None:
            return ""
        text = user_input.strip()
        if not text:
            return ""

        # ── User-Wiederholung erkennen ───────────────────────────────
        if text.lower() == self._last_user_input.lower():
            self._user_repeat_count += 1
            if self._user_repeat_count >= MAX_USER_REPEATS:
                logger.warning(f"[PhoneDialog] User-Loop ({MAX_USER_REPEATS}× '{text[:40]}') → Eskalation")
                return self._eskaliere()
        else:
            self._user_repeat_count = 1
        self._last_user_input = text


        # Spelling-Mode hat Vorrang
        if self.slots.spelling_active:
            antwort = self._handle_spelling(text)
            return self._mit_loop_check(antwort)

        # Verabschiedung jederzeit
        if ist_abschied(text) and self.state not in (State.BOOK_TOPIC,):
            self.state = State.END
            return self.config.get("abschluss", "Auf Wiederhören!")

        # Dispatch nach State
        try:
            antwort = self._dispatch(text)
        except Exception as e:
            logger.exception(f"[PhoneDialog] Dispatch-Fehler: {e}")
            antwort = ("Entschuldigung, da ist mir gerade ein Fehler unterlaufen. "
                       "Können Sie Ihr Anliegen kurz wiederholen?")
        return self._mit_loop_check(antwort)

    def _mit_loop_check(self, antwort: str) -> str:
        """Globale Wiederholungs-Erkennung: identische Antworten N× → Eskalation."""
        if not antwort:
            return antwort
        # Spelling-Stille (leere Antwort) zählt nicht
        if antwort == self._last_response:
            self._repeat_count += 1
            if self._repeat_count >= MAX_REPEATS:
                logger.warning(f"[PhoneDialog] Antwort-Loop ({MAX_REPEATS}×) → Eskalation")
                return self._eskaliere()
        else:
            self._repeat_count = 1
        self._last_response = antwort
        return antwort

    def _eskaliere(self) -> str:
        """Bricht den Dialog kontrolliert ab und gibt die Eskalations-Nachricht zurück."""
        self.state = State.END
        self._repeat_count = 0
        self._user_repeat_count = 0
        self._last_response = ""
        self._last_user_input = ""
        return ESKALATIONS_NACHRICHT

    # ── Dispatcher ──────────────────────────────────────────────────

    def _dispatch(self, text: str) -> str:
        handler = {
            State.INIT:            self._s_init,
            State.INTENT:          self._s_intent,
            State.BOOK_TOPIC:      self._s_book_topic,
            State.BOOK_DATE:       self._s_book_date,
            State.BOOK_SLOT:       self._s_book_slot,
            State.BOOK_FIRSTNAME:  self._s_book_firstname,
            State.BOOK_LASTNAME:   self._s_book_lastname,
            State.BOOK_PHONE:      self._s_book_phone,
            State.BOOK_NOTES:      self._s_book_notes,
            State.BOOK_CONFIRM:    self._s_book_confirm,
            State.BOOK_DONE:       self._s_done,
            State.IDENT_FIRSTNAME: self._s_ident_firstname,
            State.IDENT_LASTNAME:  self._s_ident_lastname,
            State.IDENT_PHONE:     self._s_ident_phone,
            State.QUERY_RESULT:    self._s_query_result,
            State.CANCEL_LIST:     self._s_cancel_list,
            State.CANCEL_CONFIRM:  self._s_cancel_confirm,
            State.CANCEL_DONE:     self._s_done,
            State.GENERAL:         self._s_general,
            State.NOTIZ:           self._s_notiz,
            State.END:             self._s_end,
        }.get(self.state, self._s_init)
        return handler(text)

    # ── State: INIT / INTENT ────────────────────────────────────────

    def _s_init(self, text: str) -> str:
        return self._s_intent(text)

    def _s_intent(self, text: str) -> str:
        intent = erkenne_intent(text)
        self.slots.intent = intent

        if intent == Intent.BUCHEN:
            self.state = State.BOOK_TOPIC
            return "Gerne. Worum geht es bei dem Termin?"

        if intent in (Intent.ABFRAGEN, Intent.STORNIEREN):
            self.slots.intent_nach_ident = intent
            return self._start_identifikation()

        if intent == Intent.INFO:
            return self._s_general(text)

        if intent == Intent.NOTIZ:
            self.state = State.NOTIZ
            return "Gerne. Bitte sprechen Sie Ihre Nachricht, ich leite sie weiter."

        if intent == Intent.ABSCHIED:
            self.state = State.END
            return self.config.get("abschluss", "Auf Wiederhören!")

        # "Nein danke" / "Das war alles" im INTENT-State → Verabschiedung
        t = text.lower()
        if any(w in t for w in ("nein danke", "ne danke", "nö danke", "nein, danke",
                                 "nö, danke", "ne, danke",
                                 "das war alles", "das war's", "das wars",
                                 "danke, das war", "mehr brauche ich nicht",
                                 "reicht mir", "passt so", "sonst nichts")):
            self.state = State.END
            return self.config.get("abschluss", "Auf Wiederhören!")

        # "Ja" / "Jaaa" / "Ja bitte" ohne konkreten Intent → nach Anliegen fragen
        if t.strip().startswith("ja"):
            return ("Was kann ich für Sie tun? "
                    "Ich kann Ihnen unsere Öffnungszeiten nennen, "
                    "einen Termin vereinbaren, "
                    "oder eine Nachricht für den Inhaber entgegennehmen.")

        # Unklar → dieselben 3 Dienste wie in der Begrüßung nennen
        return ("Das habe ich leider nicht verstanden. "
                "Ich kann Ihnen unsere Öffnungszeiten nennen, "
                "einen Termin vereinbaren, "
                "oder eine Nachricht für den Inhaber entgegennehmen.")

    # ── BOOK Flow ───────────────────────────────────────────────────

    def _s_book_topic(self, text: str) -> str:
        # Sehr kurze Antworten ablehnen
        if len(text) < 2:
            return self._retry_or_clarify(
                "book_topic",
                "Worum geht es bei dem Termin?",
                "Können Sie mir kurz sagen, weswegen Sie kommen möchten?")
        self.slots.topic = text.strip()
        self.slots.retries.pop("book_topic", None)

        # Sofort die 3 naechsten freien Slots anbieten — kein "fuer wann?"-Umweg.
        # Falls Anrufer beim Thema schon ein Datum nannte ("am Montag"), nutzen wir es.
        datum_aus_topic = parse_datum(text)
        heute = datetime.now().strftime("%d.%m.%Y")
        ab = datum_aus_topic if datum_aus_topic else heute

        slots, datums = naechste_n_slots(ab, n=3)
        if slots:
            self.slots.angebotene_slots = slots
            self.slots.angebotene_slots_datums = datums
            self.slots.datum = datums[0]
            self.state = State.BOOK_SLOT
            # Liegt der erste freie Slot mehr als 3 Tage in der Zukunft?
            # → Hinweis "erst wieder ab" vor den Terminvorschlägen
            try:
                tage_bis = (datetime.strptime(datums[0], "%d.%m.%Y").date()
                            - datetime.now().date()).days
            except Exception:
                tage_bis = 0
            if tage_bis > 3:
                prefix = (f"Leider kann ich Ihnen Termine erst wieder ab dem "
                          f"{datum_de(datums[0])} anbieten.")
            else:
                prefix = "Ich habe folgende freie Termine für Sie:"
            return self._formatiere_slot_angebot_multi(prefix)

        # Wirklich nichts in SUCHE_VOR_TAGEN Tagen gefunden
        erste_chance = (datetime.now() + timedelta(days=SUCHE_VOR_TAGEN)).strftime("%d.%m.%Y")
        self.state = State.BOOK_DATE
        return (f"Leider kann ich Ihnen im Moment Termine erst wieder ab dem "
                f"{datum_de(erste_chance)} anbieten. "
                f"Für welchen Tag darf ich es dann suchen?")

    def _s_book_date(self, text: str) -> str:
        # Erst Single-Day-Datum
        datum = parse_datum(text)

        # Dann Zeitraum (falls kein konkretes Datum)
        if not datum:
            zr = parse_zeitraum(text)
            if zr:
                start, end = zr
                gefunden = freier_tag_in_zeitraum(start, end)
                if gefunden:
                    return self._biete_slots_an(gefunden, prefix=
                        f"In diesem Zeitraum hätte ich am {datum_de(gefunden)} "
                        f"freie Termine.")
                return ("In diesem Zeitraum habe ich leider keine freien Termine. "
                        "Möchten Sie einen anderen Zeitraum nennen?")

        if not datum:
            return self._retry_or_clarify(
                "book_date",
                "Ich habe das Datum leider nicht verstanden. "
                "Bitte nennen Sie mir Tag und Monat — zum Beispiel 'achtundzwanzigster Mai' oder 'Montag'.",
                "Entschuldigung, das Datum war nicht klar. "
                "Bitte sagen Sie zum Beispiel 'fünfter Juni' oder 'nächsten Dienstag'.")

        # Zu weit in der Zukunft?
        try:
            dt = datetime.strptime(datum, "%d.%m.%Y").date()
            tage_entfernt = (dt - datetime.now().date()).days
            if tage_entfernt > SUCHE_VOR_TAGEN:
                max_datum = (datetime.now().date() + timedelta(days=SUCHE_VOR_TAGEN))
                return (f"So weit im Voraus kann ich leider keine Termine planen. "
                        f"Ich kann Termine bis maximal {datum_de(max_datum.strftime('%d.%m.%Y'))} "
                        f"vergeben. Welches Datum in diesem Zeitraum würde Ihnen passen?")
            # Wochenende prüfen
            if dt.weekday() >= 5:
                ersatz = naechster_freier_tag(datum)
                hinweis = (f" Der nächste verfügbare Werktag wäre {datum_de(ersatz)}."
                           if ersatz else "")
                return (f"Am Wochenende sind wir leider geschlossen.{hinweis} "
                        "Welcher Werktag würde Ihnen passen?")
        except Exception:
            pass

        # Slots generieren
        return self._biete_slots_an(datum)

    def _biete_slots_an(self, datum: str, prefix: str = "") -> str:
        """Präsentiert konkrete freie Slots für ein Datum."""
        slots = konkrete_slots(datum)
        if not slots:
            ersatz = naechster_freier_tag(datum)
            self.slots.angebotene_slots = []
            self.slots.datum = ""
            if ersatz:
                # Slots des Ersatztags vorbereiten
                self.slots.datum = ersatz
                self.slots.angebotene_slots = konkrete_slots(ersatz)
                self.state = State.BOOK_SLOT
                return self._formatiere_slot_angebot(
                    f"Leider kann ich Ihnen Termine erst wieder ab dem "
                    f"{datum_de(ersatz)} anbieten.")
            # Kein freier Tag innerhalb von SUCHE_VOR_TAGEN gefunden
            # → konkretes Enddatum nennen, damit der Anrufer weiß, ab wann er zurückrufen kann
            from datetime import datetime as _dt, timedelta as _td
            ab_heute = _dt.now().date()
            erste_chance = ab_heute + _td(days=SUCHE_VOR_TAGEN)
            return (f"Leider habe ich in den nächsten {SUCHE_VOR_TAGEN} Tagen keine freien Termine. "
                    f"Bitte versuchen Sie es ab {datum_de(erste_chance.strftime('%d.%m.%Y'))} wieder "
                    f"oder hinterlassen Sie uns eine Nachricht.")

        self.slots.datum = datum
        self.slots.angebotene_slots = slots
        self.slots.retries.pop("book_date", None)
        self.state = State.BOOK_SLOT
        return self._formatiere_slot_angebot(prefix or
                                             f"Am {datum_de(datum)} habe ich folgende Zeiten frei.")

    def _formatiere_slot_angebot(self, prefix: str) -> str:
        """Bietet bis zu 3 konkrete Zeiten an, gleichmäßig über den Tag verteilt."""
        slots = self.slots.angebotene_slots
        if not slots:
            return prefix + " Leider sind alle Zeiten ausgebucht."

        # Wenn 1 Slot → einfach nennen
        if len(slots) == 1:
            return f"{prefix} {uhrzeit_de(slots[0][0])}. Passt Ihnen das?"

        # Wenn 2-3 Slots → alle nennen
        if len(slots) <= 3:
            zeiten = ", ".join(uhrzeit_de(v) for v, _ in slots[:-1])
            zeiten += f" oder {uhrzeit_de(slots[-1][0])}"
            return f"{prefix} {zeiten}. Welche Zeit passt Ihnen?"

        # >3: gleichmäßig 3 wählen (früh / mittag / spät)
        n = len(slots)
        idx = [0, n // 2, n - 1]
        ausgewaehlt = [slots[i] for i in idx]
        zeiten = ", ".join(uhrzeit_de(v) for v, _ in ausgewaehlt[:-1])
        zeiten += f" oder {uhrzeit_de(ausgewaehlt[-1][0])}"
        return (f"{prefix} Zum Beispiel {zeiten}. "
                "Welche Zeit passt Ihnen — oder soll ich eine andere Zeit suchen?")

    def _formatiere_slot_angebot_multi(self, prefix: str) -> str:
        """Bietet Slots mit vollstaendigem Datum an.
        Immer: 'Montag, den 4. Mai 2026 um 9 Uhr'
        """
        slots  = self.slots.angebotene_slots
        datums = self.slots.angebotene_slots_datums
        if not slots:
            return prefix + " Leider sind im naechsten Zeitraum keine Termine frei."

        WOCHENTAGE = ["Montag","Dienstag","Mittwoch","Donnerstag",
                      "Freitag","Samstag","Sonntag"]
        MONATE_LANG = ["Januar","Februar","März","April","Mai","Juni",
                       "Juli","August","September","Oktober","November","Dezember"]

        def slot_text(i):
            uhr = uhrzeit_de(slots[i][0])
            try:
                dt = datetime.strptime(datums[i], "%d.%m.%Y")
                wt  = WOCHENTAGE[dt.weekday()]
                tag = dt.day
                mon = MONATE_LANG[dt.month - 1]
                jahr = dt.year
                return f"{wt}, den {tag}. {mon} {jahr} um {uhr}"
            except Exception:
                return uhr

        if len(slots) == 1:
            return f"{prefix} {slot_text(0)}. Passt Ihnen das?"

        teile = [slot_text(i) for i in range(len(slots))]
        zeiten = ", ".join(teile[:-1]) + f" oder {teile[-1]}"
        return f"{prefix} {zeiten}. Welche Zeit passt Ihnen?"

    def _s_book_slot(self, text: str) -> str:
        # Lehnt der Anrufer die Vorschläge ab, ohne ein konkretes Datum zu nennen?
        # Beispiele: "keiner passt", "lieber einen anderen Tag", "nein danke"
        text_l = text.lower()
        ablehnung_ohne_datum = (
            parse_yesno(text) is False or
            any(w in text_l for w in (
                "anderer tag", "anderen tag", "andere zeit", "anderen termin",
                "nichts dabei", "keiner passt", "kein termin", "nicht dabei",
                "lieber", "anders", "andere option", "sonstiger",
            ))
        )
        if ablehnung_ohne_datum and not parse_datum(text) and not parse_uhrzeit(text):
            self.state = State.BOOK_DATE
            return ("Gerne, wir suchen Ihnen einen anderen Termin. "
                    "Welches Datum schwebt Ihnen vor? "
                    "Bitte nennen Sie mir ein konkretes Datum.")

        # Moechte der Anrufer einen anderen Tag?
        anderes_datum = parse_datum(text)
        if anderes_datum and anderes_datum != self.slots.datum:
            # Pruefen ob das genannte Datum zu einem angebotenen Slot-Tag gehoert.
            # parse_datum liefert bei "Montag" immer den *naechsten* Montag —
            # aber wir haben vielleicht den uebernaechsten angeboten.
            angebotene_datums = getattr(self.slots, "angebotene_slots_datums", [])
            ist_angebotener_tag = anderes_datum in angebotene_datums
            if not ist_angebotener_tag:
                # Wochentag-Toleranz: gleicher Wochentag wie ein angebotener Slot?
                try:
                    wt_genannt = datetime.strptime(anderes_datum, "%d.%m.%Y").weekday()
                    ist_angebotener_tag = any(
                        datetime.strptime(d, "%d.%m.%Y").weekday() == wt_genannt
                        for d in angebotene_datums
                    )
                except Exception:
                    pass
            if not ist_angebotener_tag:
                # Wirklich ein anderer, nicht angebotener Tag → neu suchen
                self.state = State.BOOK_DATE
                return self._s_book_date(text)

        chosen = waehle_slot(text, self.slots.angebotene_slots)
        if not chosen:
            # Hat der Anrufer eine Uhrzeit genannt, die nicht angeboten wurde?
            z = parse_uhrzeit(text)
            if z:
                logger.warning(f"[PhoneDialog] Gewünschter Slot {z} nicht verfügbar. input={text!r}")
                return self._retry_or_clarify(
                    "book_slot",
                    self._formatiere_slot_angebot(f"Um {uhrzeit_de(z)} habe ich leider keinen Termin frei. "),
                    self._formatiere_slot_angebot(f"Um {uhrzeit_de(z)} ist leider kein Termin möglich. Bitte wählen Sie aus diesen Zeiten: ")
                )

            # Detailliertes Logging — hilft Debug bei STT-Problemen
            logger.warning(f"[PhoneDialog] Slot nicht erkannt: input={text!r}, "
                           f"slots={self.slots.angebotene_slots}")
            # Konkrete Beispiele aus den verfügbaren Slots bauen
            if self.slots.angebotene_slots:
                bsp = uhrzeit_de(self.slots.angebotene_slots[0][0])
                klare_frage = (
                    f"Ich habe Ihre Wahl nicht verstanden. Bitte nennen Sie eine "
                    f"konkrete Uhrzeit — zum Beispiel '{bsp}' — oder sagen Sie "
                    f"'erste', 'zweite' oder 'dritte'."
                )
            else:
                klare_frage = "Ich habe Ihre Wahl nicht verstanden."
            return self._retry_or_clarify(
                "book_slot",
                self._formatiere_slot_angebot(
                    f"Welche Zeit passt Ihnen am {datum_de(self.slots.datum)}?"),
                klare_frage)
        self.slots.chosen_von, self.slots.chosen_bis = chosen
        # Datum des gewahlten Slots nachfuehren (wichtig bei tagesubergreifenden Angeboten)
        if self.slots.angebotene_slots_datums:
            try:
                idx = self.slots.angebotene_slots.index(chosen)
                self.slots.datum = self.slots.angebotene_slots_datums[idx]
            except (ValueError, IndexError):
                pass
        self.slots.retries.pop("book_slot", None)
        return self._frage_nachname()

    def _frage_nachname(self) -> str:
        # Nachname schon bekannt? → direkt zum Telefon
        if self.slots.nachname:
            return self._frage_telefon()
        self.state = State.BOOK_LASTNAME
        return "Auf welchen Namen darf ich den Termin buchen?"

    def _s_book_firstname(self, text: str) -> str:
        # Legacy-State (wird nicht mehr aktiv betreten, fallback auf Nachname)
        return self._s_book_lastname(text)

    def _s_book_lastname(self, text: str) -> str:
        name = self._extrahiere_namen(text)
        if not name:
            return self._name_retry("book_lastname", "nachname",
                                    "Auf welchen Namen darf ich den Termin buchen?")
        # Wenn 2+ Wörter: ersten als Vorname, letzten als Nachname
        teile = name.split()
        if len(teile) >= 2:
            self.slots.vorname  = normalisiere_namen(" ".join(teile[:-1]))
            self.slots.nachname = normalisiere_namen(teile[-1])
        else:
            self.slots.nachname = normalisiere_namen(name)
        self.slots.retries.pop("book_lastname", None)
        return self._frage_telefon()

    def _handle_dtmf_phone_komplett(self, nummer: str) -> str:
        """Nicht mehr aktiv — DTMF wurde zugunsten reiner Spracheingabe deaktiviert."""
        return ""

    def _handle_dtmf_phone_komplett_legacy(self, nummer: str) -> str:
        """[LEGACY — nicht mehr verwendet] DTMF-Rufnummern-Bestätigung."""
        nummer = nummer.strip()

        # "1#" → Bestätigung der bereits übermittelten Rufnummer
        if nummer == "1" and ist_telefonnummer(self.slots.caller_id):
            logger.info(f"[PhoneDialog] DTMF '1' = Ja-Bestätigung für {self.slots.caller_id!r}")
            self.slots.retries.pop("book_phone", None)
            self.state = State.BOOK_NOTES
            return "Vielen Dank. Möchten Sie noch etwas zur Vorbereitung des Termins anmerken?"

        gueltig = ist_telefonnummer(nummer)
        logger.info(f"[PhoneDialog] DTMF-Rufnummer: {nummer!r} gueltig={gueltig}")
        if gueltig:
            self.slots.caller_id = nummer
            self.slots.retries.pop("book_phone", None)
            self.state = State.BOOK_NOTES
            return (f"Vielen Dank. Ich habe die Nummer {nummer} notiert. "
                    "Möchten Sie noch etwas zur Vorbereitung des Termins anmerken?")
        # Nummer ungültig → Retry (Sprache)
        return self._retry_or_clarify(
            "book_phone",
            "Die Nummer scheint unvollständig. Bitte sprechen Sie Ihre Rufnummer erneut laut aus.",
            "Ich konnte die Nummer leider nicht erfassen. Bitte sprechen Sie sie noch einmal deutlich aus.")

    def _frage_telefon(self) -> str:
        """Fragt nach der Rufnummer — ausschließlich per Sprache."""
        self.state = State.BOOK_PHONE
        if ist_telefonnummer(self.slots.caller_id):
            return (f"Darf ich Ihre Rufnummer {self.slots.caller_id} für den Termin notieren? "
                    f"Sagen Sie einfach Ja, oder nennen Sie mir eine andere Nummer.")
        return ("Unter welcher Rufnummer können wir Sie für Rückfragen zum Termin erreichen? "
                "Bitte sprechen Sie Ihre Telefonnummer laut aus.")

    def _s_book_phone(self, text: str) -> str:
        """Verarbeitet die gesprochene Rufnummer."""
        # Ja-Bestätigung der übermittelten Nummer
        ja = parse_yesno(text)
        if ja is True and ist_telefonnummer(self.slots.caller_id):
            self.slots.retries.pop("book_phone", None)
            self.state = State.BOOK_NOTES
            return "Vielen Dank. Möchten Sie noch etwas zur Vorbereitung des Termins anmerken?"

        # Nein → Anrufer möchte andere Nummer angeben, caller_id zurücksetzen
        if ja is False:
            self.slots.caller_id = ""
            return self._retry_or_clarify(
                "book_phone",
                "Kein Problem. Unter welcher Rufnummer können wir Sie erreichen? "
                "Bitte sprechen Sie Ihre Telefonnummer laut aus.",
                "Bitte nennen Sie mir Ihre Telefonnummer Ziffer für Ziffer.")

        # Gesprochene Nummer erkennen
        tel = parse_telefon(text)
        if tel:
            self.slots.caller_id = tel
            self.slots.retries.pop("book_phone", None)
            self.state = State.BOOK_NOTES
            return f"Vielen Dank. Ich habe {tel} notiert. Möchten Sie noch etwas zur Vorbereitung anmerken?"

        # Nichts erkannt → Retry
        return self._retry_or_clarify(
            "book_phone",
            "Ich habe die Nummer leider nicht verstanden. Bitte sprechen Sie Ihre Rufnummer noch einmal laut aus.",
            "Entschuldigung, ich kann die Nummer nicht erkennen. Bitte nennen Sie mir Ihre Telefonnummer Ziffer für Ziffer.")

    def _s_book_notes(self, text: str) -> str:
        # Negativwörter → keine Anmerkung
        ja = parse_yesno(text)
        if ja is False or any(w in text.lower() for w in ("nein", "nichts", "keine", "nö")):
            self.slots.notes = ""
        else:
            self.slots.notes = text.strip()
        self.state = State.BOOK_CONFIRM
        return self._zusammenfassung()

    def _zusammenfassung(self) -> str:
        anm = f" Ihre Anmerkung lautet: {self.slots.notes}." if self.slots.notes else ""
        # Name: bei "Anrufer +XX..."-Platzhalter NICHT laut vorlesen
        if self.slots.nachname.startswith("Anrufer "):
            name_text = "unter Ihrer Rufnummer"
        elif self.slots.vorname:
            name_text = f"für {self.slots.vorname} {self.slots.nachname}"
        else:
            name_text = f"für {self.slots.nachname}"
        return (
            f"Ich fasse zusammen: Termin {name_text} "
            f"am {datum_de(self.slots.datum)} um {uhrzeit_de(self.slots.chosen_von)}, "
            f"Anlass: {self.slots.topic}.{anm} "
            f"Soll ich den Termin so eintragen?"
        )

    def _s_book_confirm(self, text: str) -> str:
        ja = parse_yesno(text)
        if ja is True:
            return self._buche_termin()
        if ja is False:
            # Komplett von vorne (Identifikation behalten)
            v, n, t = self.slots.vorname, self.slots.nachname, self.slots.caller_id
            self.slots = Slots(vorname=v, nachname=n, caller_id=t,
                               intent=Intent.BUCHEN)
            self.state = State.BOOK_TOPIC
            return "Kein Problem. Worum geht es bei dem Termin?"
        return self._retry_or_clarify(
            "book_confirm",
            "Bitte bestätigen Sie mit 'Ja' oder sagen Sie 'Nein' für eine Korrektur.",
            ("Ich habe Sie nicht verstanden. Bitte sagen Sie 'Ja' oder 'Nein' — "
             "oder drücken Sie auf Ihrem Telefon die 1 für Ja und die 2 für Nein."))

    def _buche_termin(self) -> str:
        try:
            # Kontakt zusammenstellen: Vorname optional, Telefon Pflicht
            name_parts = []
            if self.slots.vorname:
                name_parts.append(self.slots.vorname)
            if self.slots.nachname:
                name_parts.append(self.slots.nachname)
            name_str = " ".join(name_parts) if name_parts else "Anrufer"
            kontakt = f"{name_str}, {self.slots.caller_id}"
            fn = _kalender_funk("lokaler_kalender_termin_eintragen")
            erg = fn(titel=self.slots.topic,
                     datum=self.slots.datum,
                     uhrzeit_von=self.slots.chosen_von,
                     uhrzeit_bis=self.slots.chosen_bis,
                     kontaktinfos=kontakt,
                     beschreibung=self.slots.notes,
                     caller_id=self.slots.caller_id)
            if "✅" in erg:
                self.state = State.BOOK_DONE
                # Buchungsdetails für Post-Call-Sync (Push nach Gesprächsende) merken
                try:
                    from skills.fritzbox_skill import registriere_post_call_push
                    registriere_post_call_push(
                        self.slots.topic, self.slots.datum,
                        self.slots.chosen_von, self.slots.chosen_bis,
                        kontakt, self.slots.notes or "",
                    )
                except Exception:
                    pass
                anm = " Ihre Anmerkung haben wir notiert." if self.slots.notes else ""
                return (f"Ihr Termin am {datum_de(self.slots.datum)} um "
                        f"{uhrzeit_de(self.slots.chosen_von)} ist eingetragen.{anm} "
                        f"Wir freuen uns auf Sie. Kann ich Ihnen sonst noch helfen?")
            logger.warning(f"[PhoneDialog] Buchung fehlgeschlagen: {erg}")
            return ("Leider konnte der Termin nicht eingetragen werden. "
                    "Bitte versuchen Sie es noch einmal oder rufen Sie uns direkt an.")
        except Exception as e:
            logger.exception(f"[PhoneDialog] Buchungs-Exception: {e}")
            return ("Ein technischer Fehler ist aufgetreten. "
                    "Bitte rufen Sie uns direkt an.")

    # ── IDENTIFIKATION ──────────────────────────────────────────────

    def _start_identifikation(self) -> str:
        # Wenn schon vollständig identifiziert → direkt weiter
        if self._ist_voll_identifiziert():
            return self._nach_identifikation()
        # Direkt nach Nachname fragen (Vorname optional)
        self.state = State.IDENT_LASTNAME
        return ("Gerne. Damit ich Ihre Termine sicher zuordnen kann, "
                "darf ich Ihren Namen erfragen?")

    def _s_ident_firstname(self, text: str) -> str:
        # Legacy-State — fallback auf Nachname-Logik
        return self._s_ident_lastname(text)

    def _s_ident_lastname(self, text: str) -> str:
        name = self._extrahiere_namen(text)
        if not name:
            return self._name_retry("ident_lastname", "nachname",
                                    "Wie lautet Ihr Name?")
        teile = name.split()
        if len(teile) >= 2:
            self.slots.vorname  = normalisiere_namen(" ".join(teile[:-1]))
            self.slots.nachname = normalisiere_namen(teile[-1])
        else:
            self.slots.nachname = normalisiere_namen(name)
        self.slots.retries.pop("ident_lastname", None)
        # Telefon prüfen
        if ist_telefonnummer(self.slots.caller_id):
            return self._nach_identifikation()
        self.state = State.IDENT_PHONE
        return "Unter welcher Rufnummer haben Sie den Termin vereinbart?"

    def _s_ident_phone(self, text: str) -> str:
        tel = parse_telefon(text)
        if not tel:
            return self._retry_or_clarify(
                "ident_phone",
                "Unter welcher Rufnummer haben Sie den Termin vereinbart?",
                ("Ich habe die Nummer leider nicht verstanden. "
                 "Bitte nennen Sie sie noch einmal."))
        self.slots.caller_id = tel
        self.slots.retries.pop("ident_phone", None)
        return self._nach_identifikation()

    def _nach_identifikation(self) -> str:
        if self.slots.intent_nach_ident == Intent.STORNIEREN:
            return self._lade_termine_zur_stornierung()
        # Default: ABFRAGEN
        return self._zeige_termine()

    def _zeige_termine(self) -> str:
        try:
            fn = _kalender_funk("kunde_termine_abfragen")
            roh = fn(caller_id=self.slots.caller_id,
                     vorname=self.slots.vorname,
                     nachname=self.slots.nachname)
            self.state = State.QUERY_RESULT
            anrede = (self.slots.vorname or self.slots.nachname or "").strip()
            anrede_text = f", {anrede}" if anrede and not anrede.startswith("Anrufer ") else ""
            if "keine bevorstehenden" in roh.lower():
                return (f"Vielen Dank{anrede_text}. "
                        "Sie haben aktuell keine bevorstehenden Termine bei uns. "
                        "Möchten Sie einen vereinbaren?")
            # Termine extrahieren und natürlich vorlesen
            return self._termine_zu_sprache(roh)
        except Exception as e:
            logger.exception(f"[PhoneDialog] Termine abfragen Fehler: {e}")
            return ("Ich konnte Ihre Termine leider gerade nicht abrufen. "
                    "Bitte versuchen Sie es später noch einmal.")

    def _lade_termine_zur_stornierung(self) -> str:
        try:
            fn = _kalender_funk("kunde_termine_abfragen")
            roh = fn(caller_id=self.slots.caller_id,
                     vorname=self.slots.vorname,
                     nachname=self.slots.nachname)
            if "keine bevorstehenden" in roh.lower():
                return ("Sie haben aktuell keine Termine, die storniert werden könnten. "
                        "Kann ich sonst etwas für Sie tun?")
            # Parse: "📅 27.04.2026, 10:00–11:00 Uhr: Beratung"
            self.slots.cancel_termine = []
            for line in roh.splitlines():
                m = re.search(r'(\d{2}\.\d{2}\.\d{4}),\s*(\d{2}:\d{2})[–\-]\d{2}:\d{2}\s*Uhr:\s*(.+)$', line)
                if m:
                    self.slots.cancel_termine.append((m.group(1), m.group(2), m.group(3).strip()))

            if not self.slots.cancel_termine:
                return ("Ich konnte Ihre Termine nicht erkennen. "
                        "Bitte rufen Sie zur Stornierung direkt unsere Praxis an.")

            self.state = State.CANCEL_LIST
            if len(self.slots.cancel_termine) == 1:
                d, u, t = self.slots.cancel_termine[0]
                return (f"Ich sehe einen Termin für Sie: {datum_de(d)} um {uhrzeit_de(u)}, "
                        f"Anlass {t}. Soll ich diesen stornieren?")
            zeilen = []
            for i, (d, u, t) in enumerate(self.slots.cancel_termine[:5], 1):
                zeilen.append(f"{i}. {datum_de(d)} um {uhrzeit_de(u)}, {t}")
            return ("Ich sehe folgende Termine für Sie: " + "; ".join(zeilen) +
                    ". Welchen möchten Sie stornieren? Sagen Sie zum Beispiel 'den ersten'.")
        except Exception as e:
            logger.exception(f"[PhoneDialog] Stornier-Liste: {e}")
            return "Ich konnte Ihre Termine leider nicht abrufen."

    def _termine_zu_sprache(self, roh: str) -> str:
        eintraege = []
        for line in roh.splitlines():
            m = re.search(r'(\d{2}\.\d{2}\.\d{4}),\s*(\d{2}:\d{2}).*?:\s*(.+)$', line)
            if m:
                d, u, t = m.group(1), m.group(2), m.group(3).strip()
                eintraege.append(f"am {datum_de(d)} um {uhrzeit_de(u)}, Anlass {t}")
        if not eintraege:
            return ("Sie haben Termine bei uns, aber ich konnte das Format nicht "
                    "richtig vorlesen. Bitte rufen Sie zur genauen Auskunft direkt an.")
        if len(eintraege) == 1:
            return f"Sie haben einen Termin: {eintraege[0]}. Kann ich Ihnen sonst noch helfen?"
        zeilen = "; ".join(eintraege[:5])
        return f"Sie haben folgende Termine: {zeilen}. Kann ich Ihnen sonst noch helfen?"

    def _s_query_result(self, text: str) -> str:
        intent = erkenne_intent(text)
        if intent == Intent.STORNIEREN:
            self.slots.intent_nach_ident = Intent.STORNIEREN
            return self._lade_termine_zur_stornierung()
        if intent == Intent.BUCHEN:
            self.slots.intent = Intent.BUCHEN
            self.state = State.BOOK_TOPIC
            return "Gerne. Worum geht es beim neuen Termin?"
        # Sonst → INTENT
        self.state = State.INTENT
        return self._s_intent(text)

    # ── STORNIERUNG ─────────────────────────────────────────────────

    def _s_cancel_list(self, text: str) -> str:
        # Bei nur einem Termin: ja/nein-Bestätigung
        if len(self.slots.cancel_termine) == 1:
            ja = parse_yesno(text)
            if ja is True:
                self.slots.cancel_datum, self.slots.cancel_uhrzeit, _ = self.slots.cancel_termine[0]
                return self._stornierung_durchfuehren()
            if ja is False:
                self.state = State.QUERY_RESULT
                return "In Ordnung, der Termin bleibt bestehen. Kann ich sonst etwas tun?"
            return self._retry_or_clarify(
                "cancel_single",
                "Bitte sagen Sie 'Ja' für die Stornierung oder 'Nein' zum Behalten.",
                ("Bitte sagen Sie 'Ja' oder 'Nein' — "
                 "oder drücken Sie die 1 für Ja, die 2 für Nein."))

        # Mehrere Termine: Auswahl per Ordinal/Datum/Uhrzeit
        idx = None
        for wort, i in [("erst", 0), ("zweit", 1), ("dritt", 2),
                        ("viert", 3), ("fünft", 4), ("letzt", -1)]:
            if wort in text.lower():
                idx = i if i != -1 else len(self.slots.cancel_termine) - 1
                break
        if idx is None:
            for i in range(1, len(self.slots.cancel_termine) + 1):
                if re.search(rf'\b{i}\b', text):
                    idx = i - 1
                    break
        # Per Datum
        if idx is None:
            d = parse_datum(text)
            if d:
                for i, (dat, _, _) in enumerate(self.slots.cancel_termine):
                    if dat == d:
                        idx = i
                        break

        if idx is None or idx >= len(self.slots.cancel_termine):
            return self._retry_or_clarify(
                "cancel_list",
                ("Welchen Termin möchten Sie stornieren? Sagen Sie zum Beispiel "
                 "'den ersten' oder nennen Sie das Datum."),
                ("Ich habe Sie nicht verstanden. Bitte sagen Sie zum Beispiel 'den ersten' "
                 "oder nennen Sie das genaue Datum des Termins."))

        d, u, t = self.slots.cancel_termine[idx]
        self.slots.cancel_datum   = d
        self.slots.cancel_uhrzeit = u
        self.state = State.CANCEL_CONFIRM
        return (f"Soll ich Ihren Termin am {datum_de(d)} um {uhrzeit_de(u)} "
                f"({t}) wirklich stornieren?")

    def _s_cancel_confirm(self, text: str) -> str:
        ja = parse_yesno(text)
        if ja is True:
            return self._stornierung_durchfuehren()
        if ja is False:
            self.state = State.QUERY_RESULT
            return "In Ordnung, der Termin bleibt bestehen. Kann ich sonst etwas tun?"
        return self._retry_or_clarify(
            "cancel_confirm",
            "Bitte bestätigen Sie mit 'Ja' oder sagen Sie 'Nein'.",
            ("Ich habe Sie nicht verstanden. Bitte sagen Sie 'Ja' oder 'Nein' — "
             "oder drücken Sie die 1 für Ja, die 2 für Nein."))

    def _stornierung_durchfuehren(self) -> str:
        try:
            fn = _kalender_funk("kunde_termin_stornieren")
            erg = fn(caller_id=self.slots.caller_id,
                     datum=self.slots.cancel_datum,
                     uhrzeit_von=self.slots.cancel_uhrzeit,
                     vorname=self.slots.vorname,
                     nachname=self.slots.nachname)
            if "✅" in erg:
                self.state = State.CANCEL_DONE
                return ("Ihr Termin wurde erfolgreich storniert. "
                        "Kann ich Ihnen sonst noch helfen?")
            self.state = State.CANCEL_LIST
            return ("Ich konnte den Termin leider nicht stornieren. "
                    "Möchten Sie es noch einmal versuchen?")
        except Exception as e:
            logger.exception(f"[PhoneDialog] Stornierungs-Exception: {e}")
            return "Ein technischer Fehler ist aufgetreten. Bitte rufen Sie uns direkt an."

    # ── DONE / END / GENERAL ────────────────────────────────────────

    def _s_done(self, text: str) -> str:
        # Nach erfolgreichem Eintrag/Stornierung: neuer Wunsch?
        if parse_yesno(text) is False or ist_abschied(text):
            self.state = State.END
            return self.config.get("abschluss", "Auf Wiederhören!")
        intent = erkenne_intent(text)
        if intent == Intent.BUCHEN:
            v, n, t = self.slots.vorname, self.slots.nachname, self.slots.caller_id
            self.slots = Slots(vorname=v, nachname=n, caller_id=t,
                               intent=Intent.BUCHEN)
            self.state = State.BOOK_TOPIC
            return "Gerne. Worum geht es beim nächsten Termin?"
        if intent in (Intent.ABFRAGEN, Intent.STORNIEREN):
            self.slots.intent_nach_ident = intent
            return self._start_identifikation()
        if intent == Intent.INFO:
            return self._s_general(text)
        # Default: höflich verabschieden
        self.state = State.END
        return self.config.get("abschluss", "Vielen Dank für Ihren Anruf. Auf Wiederhören!")

    def _s_notiz(self, text: str) -> str:
        """Anrufer spricht seine Nachricht — direkt speichern, kein LLM."""
        nachricht = text.strip()[:500]
        nachricht = re.sub(r'[\x00-\x1f\x7f]', ' ', nachricht).strip()
        anrufer = self.slots.caller_id or "unbekannt"
        try:
            from pathlib import Path as _Path
            import sys as _sys
            skills_dir = str(_Path(__file__).resolve().parent / "skills")
            if skills_dir not in _sys.path:
                _sys.path.insert(0, skills_dir)
            from basis_tools import notiz_speichern
            eintrag = f"[Telefonnotiz] Von: {anrufer} — {nachricht}"
            notiz_speichern(eintrag, datei="telefon_notizen.txt")
            logger.info(f"[PhoneDialog] Notiz gespeichert: {eintrag[:80]}")
        except Exception as e:
            logger.error(f"[PhoneDialog] Notiz-Fehler: {e}")
        self.state = State.END
        return "Vielen Dank. Ihre Nachricht wurde notiert, ich leite sie weiter. " + self.config.get("abschluss", "Auf Wiederhören!")

    def _s_end(self, text: str) -> str:
        # Anrufer spricht weiter nach Verabschiedung — kurze freundliche Antwort
        return ("Vielen Dank, einen schönen Tag noch. Auf Wiederhören!")

    def _s_general(self, text: str) -> str:
        """Allgemeine Frage (Öffnungszeiten etc.) — LLM mit Knowledge-Base."""
        # Öffnungszeiten direkt aus verfuegbarkeit.txt (einzige Wahrheitsquelle)
        verfuegbarkeit = _lese_verfuegbarkeit()

        # Weitere Infos (Adresse, Kontakt etc.) aus public_info-Ordner
        zusatz = ""
        if self.info_reader and self.info_reader.hat_dokumente:
            zusatz = self.info_reader.als_kontext_text(text) or ""

        kontext_teile = []
        if verfuegbarkeit:
            kontext_teile.append(verfuegbarkeit)
        if zusatz:
            kontext_teile.append(zusatz)
        kontext = "\n\n".join(kontext_teile)

        system = (
            f"Du bist {self.config.get('ki_rolle', 'Ilija')}.\n"
            "Du beantwortest die Frage des Anrufers KURZ und KLAR auf Deutsch "
            "(maximal zwei Sätze).\n"
            "Nutze AUSSCHLIESSLICH die unten gelisteten Informationen. "
            "Wenn dort nichts passendes steht, sage: "
            "'Dazu habe ich leider keine Information. Möchten Sie einen "
            "Termin vereinbaren oder sonst etwas wissen?'"
            + (f"\n\n{kontext}" if kontext else "")
        )
        try:
            self._history.append({"role": "user", "content": text})
            if len(self._history) > MAX_HISTORY_TURNS * 2:
                self._history = self._history[-(MAX_HISTORY_TURNS * 2):]
            antwort = self.provider.chat(messages=self._history, system=system).strip()
            self._history.append({"role": "assistant", "content": antwort})
            self.state = State.INTENT
            if not antwort.endswith("?"):
                antwort += " Kann ich Ihnen sonst noch helfen?"
            return antwort
        except Exception as e:
            logger.error(f"[PhoneDialog] _s_general LLM-Fehler: {e}")
            self.state = State.INTENT
            return ("Dazu habe ich leider keine Information. "
                    "Möchten Sie einen Termin vereinbaren?")

    # ── SPELLING ────────────────────────────────────────────────────

    def _enter_spelling(self, field_: str) -> str:
        self.slots.spelling_active  = True
        self.slots.spelling_for     = field_
        self.slots.spelling_buffer  = []
        return ("Ich habe den Namen leider nicht verstanden. "
                "Dürften Sie ihn bitte langsam Buchstabe für Buchstabe nennen? "
                "Sagen Sie nach dem letzten Buchstaben bitte 'fertig'.")

    def _handle_spelling(self, text: str) -> str:
        letters, is_done = extract_letters(text)
        self.slots.spelling_buffer.extend(letters)
        logger.info(f"[PhoneDialog] Spelling: input={text!r}, letters={letters}, "
                    f"done={is_done}, buffer={self.slots.spelling_buffer}")
        if not is_done:
            return ""  # Schweigen — kein TTS
        name = "".join(self.slots.spelling_buffer)

        if not name:
            # Buffer leer + Abschluss-Signal → Fehlversuch
            n = self.slots.retries.get("spelling_fail", 0) + 1
            self.slots.retries["spelling_fail"] = n
            if n >= MAX_SPELLING_FAILS:
                # Letzte Rückfall-Option: Termin-Flow trotzdem fortsetzen,
                # mit Telefonnummer als Kontakt-Identifier
                logger.warning(f"[PhoneDialog] Spelling {n}× leer → "
                               f"Fallback auf Telefonnummer als Identifier")
                self.slots.spelling_active  = False
                self.slots.spelling_for     = ""
                self.slots.spelling_buffer  = []
                self.slots.retries.pop("spelling_fail", None)
                return self._spelling_fallback_zu_telefon()
            # Im Spelling-Mode bleiben — nur Buffer leeren
            self.slots.spelling_buffer = []
            return ("Ich habe leider keine Buchstaben erkannt. "
                    "Dürften Sie es bitte noch einmal langsam versuchen? "
                    "Sagen Sie nach dem letzten Buchstaben 'fertig'.")

        # Erfolgreiches Spelling
        field_ = self.slots.spelling_for
        self.slots.spelling_active  = False
        self.slots.spelling_for     = ""
        self.slots.spelling_buffer  = []
        self.slots.retries.pop("spelling_fail", None)
        name_norm = normalisiere_namen(name.lower())
        if field_ == "vorname":
            self.slots.vorname = name_norm
            # Nachname fragen falls noch nicht da
            if not self.slots.nachname:
                # Welcher State? → Bestimmen wo wir herkamen
                if self.state in (State.IDENT_FIRSTNAME, State.IDENT_LASTNAME):
                    self.state = State.IDENT_LASTNAME
                else:
                    self.state = State.BOOK_LASTNAME
                return f"Vielen Dank — Vorname {name_norm}. Und Ihr Nachname?"
            return f"Vielen Dank — '{name_norm}' notiert."
        if field_ == "nachname":
            self.slots.nachname = name_norm
            if self.state in (State.IDENT_LASTNAME,):
                if ist_telefonnummer(self.slots.caller_id):
                    return self._nach_identifikation()
                self.state = State.IDENT_PHONE
                return (f"Vielen Dank — Nachname {name_norm}. "
                        f"Unter welcher Rufnummer haben Sie den Termin vereinbart?")
            # Buchungs-Flow
            return self._frage_telefon()
        return f"Vielen Dank — '{name_norm}' ist notiert."

    # ── HELPER: Namen extrahieren / Retry-Logik ─────────────────────

    def _extrahiere_namen(self, text: str) -> Optional[str]:
        """Extrahiert plausiblen Namen — strenge Validierung gegen STT-Garbage."""
        text = text.strip()
        if len(text) < 2 or len(text) > 50:
            return None
        # Häufige Einleitungs-Muster
        m = re.search(r'(?:mein\s+name\s+ist|ich\s+heiße|ich\s+bin|name|nachname|vorname)\s+(.+)',
                      text, re.IGNORECASE)
        kandidat = m.group(1).strip() if m else text

        # Satzzeichen entfernen (STT macht oft "Müller." oder "Meier!")
        kandidat = re.sub(r'[^\w\säöüÄÖÜß\-]', '', kandidat)

        # Stoppwörter und Füllwörter entfernen (Nicht-Namen-Tokens)
        STOPP = {"ähm", "äh", "halt", "also", "naja", "und", "ja", "nein",
                 "bitte", "danke", "eigentlich", "hm", "hmm", "mhm", "ist", "mein", "name"}
        woerter = [w for w in kandidat.split()
                   if w.lower() not in STOPP]

        # Plausibilitätsprüfung: 1-3 Wörter
        if not (1 <= len(woerter) <= 3):
            return None

        for w in woerter:
            # Nur Buchstaben (inkl. Umlaute, Bindestrich für Doppelnamen)
            if not re.match(r'^[a-zA-ZÄÖÜäöüß\-]+$', w):
                return None
            # Mindestlänge 2 Zeichen pro Wort (Ausnahme: einbuchstabige Initialen sind selten)
            if len(w) < 2:
                return None
            # Mindestens 1 Vokal — STT-Garbage wie "grrhgg" oder "xyzz" rejecten
            if not re.search(r'[aeiouäöüAEIOUÄÖÜ]', w):
                return None
            # Maximal 4 gleiche Buchstaben in Folge → "yyyy" ablehnen
            if re.search(r'(.)\1{3,}', w):
                return None

        return " ".join(woerter)

    def _retry_or_clarify(self, key: str, frage_1: str, frage_2: str) -> str:
        n = self.slots.retries.get(key, 0) + 1
        self.slots.retries[key] = n
        # Confirm-States bekommen mehr Versuche — DTMF braucht manchmal mehrere Anlaeufe
        limit = MAX_CONFIRM_RETRIES if "confirm" in key else MAX_OTHER_RETRIES
        if n > limit:
            logger.warning(f"[PhoneDialog] {key}: {n} Fehlversuche → Eskalation")
            return self._eskaliere()
        return frage_2 if n >= 2 else frage_1

    def _name_retry(self, key: str, field_: str, frage: str) -> str:
        n = self.slots.retries.get(key, 0) + 1
        self.slots.retries[key] = n
        if n >= MAX_NAME_RETRIES:
            self.slots.retries[key] = 0
            return self._enter_spelling(field_)
        return frage

    def _ist_voll_identifiziert(self) -> bool:
        # Nachname + Telefonnummer reichen — Vorname ist optional.
        return (bool(self.slots.nachname.strip())
                and ist_telefonnummer(self.slots.caller_id))

    # ── Spelling-Fallback: Telefonnummer als Identifier ─────────────

    def _spelling_fallback_zu_telefon(self) -> str:
        """Letzte Rückfall-Option: Name nicht ermittelbar → Telefonnummer als Identifier.
        Funktioniert nur wenn eine valide Telefonnummer vorliegt."""
        if not ist_telefonnummer(self.slots.caller_id):
            # Keine Telefonnummer da → wirkliche Eskalation
            logger.warning("[PhoneDialog] Spelling-Fallback ohne Telefonnummer → Eskalation")
            return self._eskaliere()

        # Setze einen Platzhalter-Nachnamen, der die Telefonnummer enthält
        platzhalter = f"Anrufer {self.slots.caller_id}"
        self.slots.nachname = platzhalter
        self.slots.vorname  = ""
        logger.info(f"[PhoneDialog] Fallback: nachname='{platzhalter}'")

        # Wo waren wir? Flow fortsetzen
        if self.state in (State.BOOK_LASTNAME, State.BOOK_FIRSTNAME):
            # Direkt zur Telefon-Bestätigung (oder zum nächsten Schritt)
            return self._frage_telefon()
        if self.state in (State.IDENT_LASTNAME, State.IDENT_FIRSTNAME, State.IDENT_PHONE):
            return self._nach_identifikation()
        # Sonst: Termin-Notes-Schritt
        self.state = State.BOOK_NOTES
        return ("In Ordnung, ich notiere den Termin unter Ihrer Rufnummer. "
                "Möchten Sie noch etwas zur Vorbereitung anmerken?")