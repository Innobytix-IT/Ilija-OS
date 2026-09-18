"""
buero_skills.py – Büro-/Dokument-Skills für Ilija (Ilija OS)
============================================================
Word, Excel, PowerPoint und PDF – die Dateien sind Standard-Office-Formate
(OOXML) und öffnen sich direkt in LibreOffice. Ausgabe standardmäßig nach
~/Ilija-Ablage/Dokumente.

Parameter sind einfache Strings (SKILL-kompatibel). Mehrzeilige Inhalte:
Zeilen mit "# " = Überschrift, "## " = Unterüberschrift, "- " = Aufzählung,
sonst normaler Absatz.
"""
import os
from datetime import datetime

AUSGABE = "/srv/ilija-ablage/Dokumente"


def _ziel(dateiname: str, endung: str) -> str:
    os.makedirs(AUSGABE, exist_ok=True)
    if not dateiname:
        dateiname = "ilija_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    pfad = dateiname if os.path.isabs(dateiname) else os.path.join(AUSGABE, dateiname)
    if not pfad.lower().endswith(endung):
        pfad += endung
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    return pfad


def _zeilen(text: str):
    return [z.rstrip() for z in (text or "").replace("\r\n", "\n").split("\n")]


def word_dokument_erstellen(titel: str = "", inhalt: str = "", dateiname: str = "") -> str:
    """
    Erstellt ein Word-Dokument (.docx, öffnet in LibreOffice/Word).
    inhalt: Zeilen mit '# '=Überschrift, '## '=Unterüberschrift, '- '=Aufzählung,
    sonst Absatz. Beispiel:
    word_dokument_erstellen(titel="Angebot", inhalt="# Angebot\n\nSehr geehrte Damen und Herren,\n\n- Position 1\n- Position 2")
    """
    from docx import Document
    doc = Document()
    if titel:
        doc.add_heading(titel, level=0)
    for z in _zeilen(inhalt):
        if not z.strip():
            continue
        if z.startswith("## "):
            doc.add_heading(z[3:], level=2)
        elif z.startswith("# "):
            doc.add_heading(z[2:], level=1)
        elif z.startswith("- ") or z.startswith("* "):
            doc.add_paragraph(z[2:], style="List Bullet")
        else:
            doc.add_paragraph(z)
    pfad = _ziel(dateiname, ".docx")
    doc.save(pfad)
    return f"✓ Word-Dokument erstellt: {pfad}"


def excel_tabelle_erstellen(titel: str = "", daten: str = "", dateiname: str = "") -> str:
    """
    Erstellt eine Excel-Tabelle (.xlsx, öffnet in LibreOffice Calc/Excel).
    daten: Zeilen durch Zeilenumbruch, Spalten durch ';' getrennt. Erste Zeile = Kopf.
    Beispiel:
    excel_tabelle_erstellen(titel="Umsatz", daten="Monat;Umsatz\nJan;1000\nFeb;1500")
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = (titel or "Tabelle")[:31]
    rows = [z for z in _zeilen(daten) if z.strip()]
    for i, row in enumerate(rows):
        cols = [c.strip() for c in row.split(";")]
        for j, val in enumerate(cols, 1):
            cell = ws.cell(row=i + 1, column=j, value=_zahl(val))
            if i == 0:
                cell.font = Font(bold=True)
    # Spaltenbreite grob
    for col in ws.columns:
        breite = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(breite + 2, 40)
    pfad = _ziel(dateiname, ".xlsx")
    wb.save(pfad)
    return f"✓ Excel-Tabelle erstellt ({len(rows)} Zeilen): {pfad}"


def _zahl(v: str):
    try:
        if v.strip() == "":
            return v
        f = float(v.replace(",", "."))
        return int(f) if f.is_integer() else f
    except Exception:
        return v


def powerpoint_erstellen(titel: str = "", folien: str = "", dateiname: str = "") -> str:
    """
    Erstellt eine PowerPoint-Präsentation (.pptx, öffnet in LibreOffice Impress).
    folien: Folien durch '---' trennen. In jeder Folie ist die erste Zeile der
    Folientitel, die weiteren Zeilen (mit '- ') die Stichpunkte. Beispiel:
    powerpoint_erstellen(titel="Quartalsbericht", folien="Umsatz\n- Q1 stark\n- Q2 stabil\n---\nAusblick\n- Wachstum geplant")
    """
    from pptx import Presentation
    from pptx.util import Pt
    prs = Presentation()
    # Titelfolie
    s0 = prs.slides.add_slide(prs.slide_layouts[0])
    s0.shapes.title.text = titel or "Präsentation"
    try:
        s0.placeholders[1].text = "Erstellt mit Ilija OS · " + datetime.now().strftime("%d.%m.%Y")
    except Exception:
        pass
    anzahl = 1
    for block in (folien or "").split("---"):
        block = block.strip()
        if not block:
            continue
        zeilen = [z for z in _zeilen(block) if z.strip()]
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = zeilen[0]
        body = slide.placeholders[1].text_frame
        body.clear()
        for k, z in enumerate(zeilen[1:]):
            txt = z[2:] if (z.startswith("- ") or z.startswith("* ")) else z
            p = body.paragraphs[0] if k == 0 else body.add_paragraph()
            p.text = txt
            p.font.size = Pt(20)
        anzahl += 1
    pfad = _ziel(dateiname, ".pptx")
    prs.save(pfad)
    return f"✓ PowerPoint erstellt ({anzahl} Folien): {pfad}"


def pdf_erstellen(titel: str = "", inhalt: str = "", dateiname: str = "") -> str:
    """
    Erstellt ein PDF-Dokument (.pdf). Formatierung wie bei word_dokument_erstellen
    ('# '=Überschrift, '## '=Unterüberschrift, '- '=Aufzählung, sonst Absatz).
    Beispiel: pdf_erstellen(titel="Rechnung", inhalt="# Rechnung Nr. 2026-001\n\nBetrag: 100 EUR")
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
    from xml.sax.saxutils import escape
    pfad = _ziel(dateiname, ".pdf")
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(pfad, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    flow = []
    if titel:
        flow.append(Paragraph(escape(titel), styles["Title"]))
        flow.append(Spacer(1, 0.4 * cm))
    puffer = []

    def _bullets():
        if puffer:
            flow.append(ListFlowable([ListItem(Paragraph(escape(b), styles["Normal"]))
                                      for b in puffer], bulletType="bullet"))
            puffer.clear()

    for z in _zeilen(inhalt):
        if z.startswith("- ") or z.startswith("* "):
            puffer.append(z[2:]); continue
        _bullets()
        if not z.strip():
            flow.append(Spacer(1, 0.3 * cm))
        elif z.startswith("## "):
            flow.append(Paragraph(escape(z[3:]), styles["Heading2"]))
        elif z.startswith("# "):
            flow.append(Paragraph(escape(z[2:]), styles["Heading1"]))
        else:
            flow.append(Paragraph(escape(z), styles["Normal"]))
    _bullets()
    doc.build(flow)
    return f"✓ PDF erstellt: {pfad}"


def pdf_zusammenfuehren(dateien: str = "", dateiname: str = "") -> str:
    """
    Führt mehrere PDFs zu einem zusammen. dateien: Pfade durch ';' getrennt.
    Beispiel: pdf_zusammenfuehren(dateien="/pfad/a.pdf;/pfad/b.pdf", dateiname="gesamt")
    """
    from PyPDF2 import PdfMerger
    pfade = [p.strip() for p in (dateien or "").replace(",", ";").split(";") if p.strip()]
    if len(pfade) < 2:
        return "❌ Bitte mindestens zwei PDF-Pfade angeben (durch ';' getrennt)."
    merger = PdfMerger()
    for p in pfade:
        p2 = os.path.expanduser(p)
        if not os.path.isfile(p2):
            return f"❌ Datei nicht gefunden: {p}"
        merger.append(p2)
    ziel = _ziel(dateiname or "zusammengefuehrt", ".pdf")
    merger.write(ziel); merger.close()
    return f"✓ {len(pfade)} PDFs zusammengeführt: {ziel}"


def pdf_text_lesen(datei: str = "", max_zeichen: str = "4000") -> str:
    """
    Liest den Text aus einem PDF aus. datei: Pfad zur PDF-Datei.
    Beispiel: pdf_text_lesen(datei="/home/innobytix/Ilija-Ablage/DMS/archiv/rechnung.pdf")
    """
    from PyPDF2 import PdfReader
    p = os.path.expanduser(datei or "")
    if not os.path.isfile(p):
        return f"❌ PDF nicht gefunden: {datei}"
    try:
        grenze = int(max_zeichen)
    except Exception:
        grenze = 4000
    reader = PdfReader(p)
    text = "\n".join((seite.extract_text() or "") for seite in reader.pages)
    if len(text) > grenze:
        text = text[:grenze] + f"\n… (gekürzt, {len(reader.pages)} Seiten)"
    return text.strip() or "(kein extrahierbarer Text – evtl. gescanntes PDF)"


AVAILABLE_SKILLS = [
    word_dokument_erstellen, excel_tabelle_erstellen, powerpoint_erstellen,
    pdf_erstellen, pdf_zusammenfuehren, pdf_text_lesen,
]
