# senderliste_tool.py -- XML-Senderlisten-Skill (Public Edition)

import xml.etree.ElementTree as ET
import os

_XML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "senderliste.xml")


def _lade_sender(xml_pfad=_XML_PATH):
    tree = ET.parse(xml_pfad)
    root = tree.getroot()
    gesehen = set()
    sender = []
    for kanal in root.findall("channel"):
        cid = kanal.get("id", "")
        if cid in gesehen:
            continue
        gesehen.add(cid)
        name_el = kanal.find("display-name")
        sender.append({
            "id": cid,
            "name": name_el.text.strip() if name_el is not None else "",
            "kategorie": kanal.get("kategorie", "unbekannt"),
            "land": kanal.get("land", "?"),
        })
    return sender


def alle_sender_auflisten():
    """Gibt alle Sender als formatierte Liste zurueck.
    Beispiel: alle_sender_auflisten()
    """
    sender = _lade_sender()
    zeilen = ["Senderliste ({} Sender):".format(len(sender))]
    for s in sender:
        zeilen.append("  TV {}  [{}]  ({})".format(s["name"], s["id"], s["land"]))
    return "\n".join(zeilen)


def sender_suchen(suchbegriff):
    """Sucht Sender nach Name oder ID (case-insensitive).
    Beispiel: sender_suchen('ZDF')
    """
    sl = suchbegriff.lower()
    treffer = [s for s in _lade_sender() if sl in s["name"].lower() or sl in s["id"].lower()]
    if not treffer:
        return "Kein Sender gefunden fuer: {}".format(suchbegriff)
    zeilen = ["Treffer fuer '{}' ({}):".format(suchbegriff, len(treffer))]
    for s in treffer:
        zeilen.append("  OK {}  [{}]  {} | {}".format(s["name"], s["id"], s["kategorie"], s["land"]))
    return "\n".join(zeilen)


def sender_nach_kategorie(kategorie):
    """Filtert Sender nach Kategorie.
    Werte: oeffentlich-rechtlich, drittes-programm, privat, news-doku, christlich
    Beispiel: sender_nach_kategorie('christlich')
    """
    kat = kategorie.lower()
    treffer = [s for s in _lade_sender() if kat in s["kategorie"].lower()]
    if not treffer:
        return "Keine Sender in Kategorie: {}".format(kategorie)
    zeilen = ["Kategorie '{}' ({} Sender):".format(kategorie, len(treffer))]
    for s in treffer:
        zeilen.append("  TV {}  [{}]  ({})".format(s["name"], s["id"], s["land"]))
    return "\n".join(zeilen)


def sender_nach_land(land):
    """Filtert Sender nach Laenderkuerzel DE, AT oder CH.
    Beispiel: sender_nach_land('AT')
    """
    lu = land.upper()
    treffer = [s for s in _lade_sender() if s["land"].upper() == lu]
    if not treffer:
        return "Keine Sender fuer Land: {}".format(land)
    zeilen = ["Sender aus {} ({}):".format(lu, len(treffer))]
    for s in treffer:
        zeilen.append("  TV {}  [{}]  {}".format(s["name"], s["id"], s["kategorie"]))
    return "\n".join(zeilen)


def sender_statistik():
    """Statistik: Sender pro Kategorie und Land.
    Beispiel: sender_statistik()
    """
    sender = _lade_sender()
    kat = {}
    land = {}
    for s in sender:
        kat[s["kategorie"]] = kat.get(s["kategorie"], 0) + 1
        land[s["land"]] = land.get(s["land"], 0) + 1
    lines = ["Senderlisten-Statistik ({} Sender)".format(len(sender)), "", "Nach Kategorie:"]
    for k, v in sorted(kat.items()):
        lines.append("  {}: {}".format(k, v))
    lines.append("\nNach Land:")
    for l, v in sorted(land.items()):
        lines.append("  {}: {}".format(l, v))
    return "\n".join(lines)


AVAILABLE_SKILLS = [alle_sender_auflisten, sender_suchen, sender_nach_kategorie, sender_nach_land, sender_statistik]


if __name__ == "__main__":
    import sys
    cmds = {
        "alle": lambda: alle_sender_auflisten(),
        "suchen": lambda: sender_suchen(sys.argv[2]) if len(sys.argv) > 2 else "Fehler: Suchbegriff fehlt",
        "kategorie": lambda: sender_nach_kategorie(sys.argv[2]) if len(sys.argv) > 2 else "Fehler: Kategorie fehlt",
        "land": lambda: sender_nach_land(sys.argv[2]) if len(sys.argv) > 2 else "Fehler: Laenderkuerzel fehlt",
        "statistik": lambda: sender_statistik(),
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print("Verwendung: python senderliste_tool.py [alle|suchen|kategorie|land|statistik] [Argument]")
    else:
        print(cmds[sys.argv[1]]())
