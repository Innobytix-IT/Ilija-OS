"""
public_info_reader.py – Öffentliche Wissensbasis für Ilija
===========================================================
Liest Dokumente aus einem konfigurierten Ordner und sucht
relevante Textabschnitte für Kundenanfragen.

Unterstützte Formate: .txt, .md, .pdf
Kanal-agnostisch: funktioniert für Telefon, WhatsApp, E-Mail.

Verwendung:
    from public_info_reader import PublicInfoReader
    reader = PublicInfoReader("/pfad/zum/ordner")
    passagen = reader.suche("Was kosten eure Produkte?")
    # → Liste relevanter Textabschnitte
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Maximale Zeichen die pro Suchergebnis zurückgegeben werden
MAX_PASSAGE_CHARS = 600

# Maximale Gesamtzeichen die in den Kontext eingebunden werden
MAX_TOTAL_CHARS = 2400

# Mindest-Score damit ein Abschnitt als relevant gilt
MIN_SCORE = 1


class PublicInfoReader:
    """
    Liest alle Dokumente aus einem Ordner und ermöglicht
    Keyword-basierte Relevanzssuche für Kundenanfragen.
    """

    def __init__(self, ordner_pfad: str = ""):
        self.ordner = ordner_pfad.strip() if ordner_pfad else ""
        self._dokumente: List[Tuple[str, str]] = []  # [(dateiname, inhalt), ...]
        self._geladen = False

        if self.ordner:
            self._laden()

    def _laden(self):
        """Lädt alle unterstützten Dateien aus dem Ordner."""
        if not self.ordner or not os.path.isdir(self.ordner):
            logger.warning(f"[PublicInfo] Ordner nicht gefunden: '{self.ordner}'")
            return

        self._dokumente = []
        pfad = Path(self.ordner)

        # Dateien die nie als Wissensdokumente behandelt werden sollen
        _IGNORIEREN = {"lies_mich.txt", "readme.txt", "readme.md",
                       "_lies_mich.txt", "hinweis.txt"}

        for datei in sorted(pfad.iterdir()):
            if not datei.is_file():
                continue
            if datei.name.lower() in _IGNORIEREN or datei.name.startswith("_"):
                logger.debug(f"[PublicInfo] Übersprungen (README): {datei.name}")
                continue
            inhalt = self._datei_lesen(datei)
            if inhalt:
                self._dokumente.append((datei.name, inhalt))
                logger.info(f"[PublicInfo] Geladen: {datei.name} ({len(inhalt)} Zeichen)")

        self._geladen = True
        logger.info(f"[PublicInfo] {len(self._dokumente)} Dokumente geladen aus '{self.ordner}'")

    def _datei_lesen(self, pfad: Path) -> str:
        """Liest eine einzelne Datei je nach Format."""
        suffix = pfad.suffix.lower()

        # ── Textdateien ───────────────────────────────────────────────────────
        if suffix in (".txt", ".md", ".rst"):
            try:
                return pfad.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logger.warning(f"[PublicInfo] Lesefehler {pfad.name}: {e}")
                return ""

        # ── PDF ───────────────────────────────────────────────────────────────
        if suffix == ".pdf":
            return self._pdf_lesen(pfad)

        # Andere Formate ignorieren
        return ""

    def _pdf_lesen(self, pfad: Path) -> str:
        """Extrahiert Text aus einer PDF-Datei."""
        # Versuch 1: PyMuPDF (fitz)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(pfad))
            text = "\n".join(seite.get_text() for seite in doc)
            doc.close()
            if text.strip():
                return text
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[PublicInfo] PyMuPDF Fehler {pfad.name}: {e}")

        # Versuch 2: pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(str(pfad)) as pdf:
                text = "\n".join(
                    seite.extract_text() or "" for seite in pdf.pages
                )
            if text.strip():
                return text
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[PublicInfo] pdfplumber Fehler {pfad.name}: {e}")

        logger.warning(f"[PublicInfo] PDF konnte nicht gelesen werden: {pfad.name} "
                       f"(pip install pymupdf oder pdfplumber)")
        return ""

    def _in_abschnitte(self, text: str) -> List[str]:
        """Teilt Text in sinnvolle Abschnitte auf."""
        # Aufteilen nach Leerzeilen oder Überschriften
        abschnitte = re.split(r'\n\s*\n|\n#{1,3} ', text)
        result = []
        for a in abschnitte:
            a = a.strip()
            if len(a) > 30:  # Zu kurze Fragmente ignorieren
                # Lange Abschnitte weiter unterteilen
                if len(a) > MAX_PASSAGE_CHARS * 1.5:
                    saetze = re.split(r'(?<=[.!?])\s+', a)
                    chunk = ""
                    for satz in saetze:
                        if len(chunk) + len(satz) < MAX_PASSAGE_CHARS:
                            chunk += " " + satz
                        else:
                            if chunk.strip():
                                result.append(chunk.strip())
                            chunk = satz
                    if chunk.strip():
                        result.append(chunk.strip())
                else:
                    result.append(a)
        return result

    def _score(self, abschnitt: str, stichwoerter: List[str]) -> int:
        """Berechnet Relevanz-Score eines Abschnitts für die Stichworte."""
        text_lower = abschnitt.lower()
        score = 0
        for wort in stichwoerter:
            if len(wort) < 3:
                continue
            count = text_lower.count(wort.lower())
            score += count * (2 if len(wort) > 5 else 1)
        return score

    def suche(self, anfrage: str, max_ergebnisse: int = 3) -> List[str]:
        """
        Sucht relevante Textabschnitte für eine Kundenanfrage.

        Args:
            anfrage: Die Frage oder Nachricht des Kunden
            max_ergebnisse: Maximale Anzahl zurückgegebener Abschnitte

        Returns:
            Liste relevanter Textabschnitte (leer wenn nichts gefunden)
        """
        if not self._dokumente:
            return []

        # Stichworte aus Anfrage extrahieren (Stopwörter entfernen)
        stopwoerter = {
            "ich", "du", "er", "sie", "es", "wir", "ihr", "die", "der", "das",
            "ein", "eine", "und", "oder", "aber", "mit", "von", "für", "auf",
            "ist", "sind", "war", "was", "wie", "wann", "wo", "bitte", "kann",
            "können", "haben", "hat", "mir", "mich", "uns", "euch", "sich",
            "mal", "doch", "noch", "auch", "schon", "dann", "wenn", "dass",
        }
        woerter = re.findall(r'\b\w{3,}\b', anfrage.lower())
        stichwoerter = [w for w in woerter if w not in stopwoerter]

        if not stichwoerter:
            return []

        # Alle Abschnitte bewerten
        kandidaten: List[Tuple[int, str, str]] = []  # (score, datei, abschnitt)
        for dateiname, inhalt in self._dokumente:
            abschnitte = self._in_abschnitte(inhalt)
            for abschnitt in abschnitte:
                score = self._score(abschnitt, stichwoerter)
                if score >= MIN_SCORE:
                    kandidaten.append((score, dateiname, abschnitt))

        if not kandidaten:
            return []

        # Nach Score sortieren, beste nehmen
        kandidaten.sort(key=lambda x: x[0], reverse=True)
        ergebnisse = []
        gesamt_zeichen = 0

        for score, dateiname, abschnitt in kandidaten[:max_ergebnisse * 2]:
            if gesamt_zeichen >= MAX_TOTAL_CHARS:
                break
            gekuerzt = abschnitt[:MAX_PASSAGE_CHARS]
            if len(abschnitt) > MAX_PASSAGE_CHARS:
                gekuerzt += "…"
            ergebnisse.append(f"[{dateiname}]\n{gekuerzt}")
            gesamt_zeichen += len(gekuerzt)
            if len(ergebnisse) >= max_ergebnisse:
                break

        return ergebnisse

    def als_kontext_text(self, anfrage: str) -> str:
        """
        Gibt gefundene Infos als formatierten Kontext-String zurück,
        direkt einbindbar in einen System-Prompt.
        """
        passagen = self.suche(anfrage)
        if not passagen:
            return ""
        return (
            "\n\n════ VERFÜGBARE INFORMATIONEN (offizielle Dokumente) ════\n"
            + "\n\n".join(passagen)
            + "\n════════════════════════════════════════════════════════\n"
            + "Nutze NUR diese Informationen für deine Antwort. Erfinde NICHTS dazu."
        )

    def alle_dokumente_kurz(self) -> str:
        """Gibt eine kurze Übersicht aller geladenen Dokumente zurück."""
        if not self._dokumente:
            return "Keine Dokumente geladen."
        zeilen = [f"📄 {name} ({len(inhalt)} Zeichen)"
                  for name, inhalt in self._dokumente]
        return f"Geladene Dokumente ({len(self._dokumente)}):\n" + "\n".join(zeilen)

    def neu_laden(self):
        """Dokumente neu einlesen (nach Änderungen im Ordner)."""
        self._dokumente = []
        self._geladen = False
        self._laden()

    @property
    def hat_dokumente(self) -> bool:
        return bool(self._dokumente)


# ── Hilfsfunktion für einfachen Zugriff ──────────────────────────────────────

_reader_cache: dict = {}  # pfad → PublicInfoReader (pro Ordner gecacht)


def get_reader(ordner_pfad: str) -> PublicInfoReader:
    """
    Gibt einen gecachten PublicInfoReader für den Pfad zurück.
    Beim ersten Aufruf werden die Dokumente geladen.
    """
    global _reader_cache
    pfad = ordner_pfad.strip()
    if pfad not in _reader_cache:
        _reader_cache[pfad] = PublicInfoReader(pfad)
    return _reader_cache[pfad]


def cache_leeren():
    """Cache leeren (z.B. nach Änderungen an Dokumenten)."""
    global _reader_cache
    _reader_cache = {}
