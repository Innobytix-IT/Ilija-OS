"""
basis_tools.py – Grundlegende Werkzeuge für Ilija Public Edition
"""

import os
import json
from datetime import datetime


def uhrzeit_datum() -> str:
    """
    Gibt das aktuelle Datum und die Uhrzeit zurück.
    Beispiel: uhrzeit_datum()
    """
    jetzt = datetime.now()
    return (
        f"📅 {jetzt.strftime('%A, %d. %B %Y')}\n"
        f"🕐 {jetzt.strftime('%H:%M:%S Uhr')}"
    )


def notiz_speichern(text: str, datei: str = "notizen.txt") -> str:
    """
    Speichert eine Notiz in einer Textdatei.
    Beispiel: notiz_speichern(text="Wichtig: Meeting morgen um 10 Uhr")
    """
    # Nur Dateiname erlaubt — kein Verzeichnis-Traversal möglich
    datei    = os.path.basename(datei) or "notizen.txt"
    if not datei.endswith(".txt"):
        datei = datei + ".txt"
    os.makedirs("data/notizen", exist_ok=True)
    pfad     = os.path.join("data/notizen", datei)
    eintrag  = f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] {text}\n"
    try:
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(eintrag)
        return f"✅ Notiz gespeichert in {pfad}"
    except Exception as e:
        return f"❌ Fehler beim Speichern: {e}"


def notizen_lesen(datei: str = "notizen.txt") -> str:
    """
    Liest alle gespeicherten Notizen.
    Beispiel: notizen_lesen()
    """
    # Nur Dateiname erlaubt — kein Verzeichnis-Traversal möglich
    datei = os.path.basename(datei) or "notizen.txt"
    pfad  = os.path.join("data/notizen", datei)
    if not os.path.exists(pfad):
        return "📝 Keine Notizen vorhanden."
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            inhalt = f.read().strip()
        return f"📝 Notizen:\n{inhalt}" if inhalt else "📝 Notizbuch ist leer."
    except Exception as e:
        return f"❌ Fehler beim Lesen: {e}"


def taschenrechner(ausdruck: str) -> str:
    """
    Berechnet einen mathematischen Ausdruck sicher.
    Beispiel: taschenrechner(ausdruck="(1250 * 1.19) + 48.50")
    """
    import ast
    import operator

    erlaubte_ops = {
        ast.Add:  operator.add,
        ast.Sub:  operator.sub,
        ast.Mult: operator.mul,
        ast.Div:  operator.truediv,
        ast.Pow:  operator.pow,
        ast.Mod:  operator.mod,
        ast.USub: operator.neg,
    }

    def berechne(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            op = erlaubte_ops.get(type(node.op))
            if op is None:
                raise ValueError(f"Nicht erlaubte Operation: {type(node.op)}")
            return op(berechne(node.left), berechne(node.right))
        elif isinstance(node, ast.UnaryOp):
            op = erlaubte_ops.get(type(node.op))
            if op is None:
                raise ValueError(f"Nicht erlaubte Operation")
            return op(berechne(node.operand))
        else:
            raise ValueError(f"Nicht erlaubter Ausdruck")

    try:
        tree   = ast.parse(ausdruck.strip(), mode="eval")
        result = berechne(tree.body)
        return f"🧮 {ausdruck} = **{result}**"
    except ZeroDivisionError:
        return "❌ Division durch Null"
    except Exception as e:
        return f"❌ Berechnung fehlgeschlagen: {e}"


def einheit_umrechnen(wert: str, von: str, nach: str) -> str:
    """
    Rechnet gängige Einheiten um (Länge, Gewicht, Temperatur).
    Beispiel: einheit_umrechnen(wert="100", von="km", nach="meilen")
    """
    try:
        v = float(wert)
    except ValueError:
        return f"❌ Ungültiger Wert: {wert}"

    umrechnungen = {
        ("km",     "meilen"):   v * 0.621371,
        ("meilen", "km"):       v * 1.60934,
        ("m",      "ft"):       v * 3.28084,
        ("ft",     "m"):        v * 0.3048,
        ("cm",     "zoll"):     v * 0.393701,
        ("zoll",   "cm"):       v * 2.54,
        ("kg",     "pfund"):    v * 2.20462,
        ("pfund",  "kg"):       v * 0.453592,
        ("kg",     "gramm"):    v * 1000,
        ("gramm",  "kg"):       v / 1000,
        ("liter",  "gallonen"): v * 0.264172,
        ("gallonen","liter"):   v * 3.78541,
        ("celsius","fahrenheit"): v * 9/5 + 32,
        ("fahrenheit","celsius"): (v - 32) * 5/9,
        ("celsius","kelvin"):   v + 273.15,
        ("kelvin","celsius"):   v - 273.15,
        ("euro",   "dollar"):   v * 1.09,
        ("dollar", "euro"):     v / 1.09,
    }

    key    = (von.lower().strip(), nach.lower().strip())
    result = umrechnungen.get(key)

    if result is None:
        return f"❌ Umrechnung von '{von}' nach '{nach}' nicht bekannt."

    return f"🔢 {v} {von} = **{round(result, 4)} {nach}**"


AVAILABLE_SKILLS = [
    uhrzeit_datum,
    notiz_speichern,
    notizen_lesen,
    taschenrechner,
    einheit_umrechnen,
]
