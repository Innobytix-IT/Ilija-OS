"""
Wetter-Skill fuer Ilija.

Fragt aktuelles Wetter oder Vorhersage (heute/morgen/uebermorgen) ueber
wttr.in ab. Stadt wird aus dem Absender-Profil (Fristen -> Meine Daten)
abgeleitet oder kann explizit uebergeben werden.
"""
import os
import json
import re
import requests


def _stadt_aus_absender() -> str | None:
    """Liest die Stadt aus dem Absender-Profil (data/fristen/absender.json).
    Erwartet eine Adresse der Form 'Strasse 12\\n12345 Stadt'. Gibt die
    Stadt zurueck, oder None wenn nichts Brauchbares drinsteht."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pfad = os.path.join(base, "data", "fristen", "absender.json")
        if not os.path.exists(pfad):
            return None
        with open(pfad, encoding="utf-8") as f:
            data = json.load(f)
        adresse = (data.get("adresse") or "").strip()
        if not adresse:
            return None
        # Letzte Zeile ist typischerweise "PLZ Stadt"
        letzte = adresse.splitlines()[-1].strip()
        m = re.match(r"^\s*\d{4,5}\s+(.+?)\s*$", letzte)
        if m:
            return m.group(1).strip()
        # Platzhalter-Namen ausschliessen
        if "muster" in letzte.lower():
            return None
        return letzte or None
    except Exception:
        return None


def wetter_abfragen(stadt: str = "", tag: str = "heute") -> str:
    """
    Ruft Wetter fuer eine Stadt ab.

    Parameter:
      stadt: Ortsname (z.B. "Berlin", "Offenburg"). Wenn leer, wird die
             Stadt aus dem Absender-Profil (Fristen -> Meine Daten) gelesen.
             Fallback: Berlin.
      tag:   "heute" (aktuelles Wetter), "morgen" oder "uebermorgen"
             (Tagesvorhersage mit Min-/Max-Temperatur, Bedingung,
             Regenwahrscheinlichkeit, Wind).

    Beispiele:
      wetter_abfragen()                       -> aktuelles Wetter User-Stadt
      wetter_abfragen(stadt="Berlin")         -> aktuelles Wetter Berlin
      wetter_abfragen(tag="morgen")           -> Vorhersage morgen User-Stadt
      wetter_abfragen(stadt="Hamburg", tag="uebermorgen")
    """
    if not stadt:
        stadt = _stadt_aus_absender() or "Berlin"

    tag_norm = (tag or "heute").strip().lower()
    tag_norm = tag_norm.replace("ü", "u").replace("ue", "u")
    tag_index = {"heute": 0, "morgen": 1, "ubermorgen": 2}.get(tag_norm)
    if tag_index is None:
        return (f"Ich kenne nur 'heute', 'morgen' oder 'uebermorgen' – "
                f"'{tag}' verstehe ich nicht.")

    try:
        if tag_index == 0:
            # Aktuelles Wetter als Kurzformat
            url = f"https://wttr.in/{stadt}?format=3&lang=de"
            r = requests.get(url, timeout=10)
            r.encoding = "utf-8"
            if r.status_code != 200:
                return f"Wetterdienst nicht erreichbar (Status {r.status_code})."
            return r.text.strip()

        # Vorhersage: wttr.in liefert mit ?format=j1 bis zu 3 Tage als JSON.
        url = f"https://wttr.in/{stadt}?format=j1&lang=de"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return f"Wetterdienst nicht erreichbar (Status {r.status_code})."
        data = r.json()
        tage = data.get("weather") or []
        if tag_index >= len(tage):
            return f"Keine Vorhersage fuer '{tag}' verfuegbar."
        t = tage[tag_index]
        datum   = t.get("date", "?")
        maxc    = t.get("maxtempC", "?")
        minc    = t.get("mintempC", "?")
        sonne   = t.get("sunHour", "?")
        regen   = t.get("totalSnow_cm", None)
        # Mittagsvorhersage (12:00) fuer Bedingung / Regenwkt / Wind
        hourly  = t.get("hourly") or []
        mittag  = next((h for h in hourly if h.get("time") in ("1200", "1300")),
                       (hourly[len(hourly)//2] if hourly else {}))
        bed     = ""
        desc    = mittag.get("lang_de") or mittag.get("weatherDesc") or []
        if isinstance(desc, list) and desc:
            bed = desc[0].get("value", "")
        regen_prob = mittag.get("chanceofrain", "?")
        wind       = mittag.get("windspeedKmph", "?")
        tag_label  = {0: "Heute", 1: "Morgen", 2: "Uebermorgen"}[tag_index]
        return (
            f"{tag_label} in {stadt} ({datum}): {bed}, "
            f"{minc}-{maxc}°C, {regen_prob}% Regenwahrscheinlichkeit, "
            f"Wind {wind} km/h, {sonne} Sonnenstunden."
        )
    except requests.Timeout:
        return "Der Wetterdienst antwortet nicht (Timeout)."
    except Exception as e:
        return f"Fehler beim Abrufen des Wetters: {e}"


AVAILABLE_SKILLS = [wetter_abfragen]
