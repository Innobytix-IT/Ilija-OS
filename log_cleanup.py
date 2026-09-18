"""
log_cleanup.py – Automatische Bereinigung alter Log-Einträge
Wird beim Start von web_server.py aufgerufen.
Einträge älter als MAX_ALTER_WOCHEN werden entfernt.
"""

import os
import re
import glob
from datetime import datetime, timedelta

MAX_ALTER_WOCHEN = 12

_PATTERN_ISO   = re.compile(r'^\[(\d{4}-\d{2}-\d{2})[T ]')   # [YYYY-MM-DD ...]
_PATTERN_DE    = re.compile(r'^\[(\d{2})\.(\d{2})\.(\d{4})')  # [DD.MM.YYYY ...]

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _zeitstempel(zeile: str):
    m = _PATTERN_ISO.match(zeile)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            return None
    m = _PATTERN_DE.match(zeile)
    if m:
        try:
            return datetime.strptime(f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _bereinige_datei(pfad: str, grenze: datetime) -> int:
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            zeilen = f.readlines()
    except Exception:
        return 0

    gefiltert = []
    entfernt  = 0
    for z in zeilen:
        ts = _zeitstempel(z)
        if ts is None or ts >= grenze:
            gefiltert.append(z)
        else:
            entfernt += 1

    if entfernt > 0:
        try:
            with open(pfad, "w", encoding="utf-8") as f:
                f.writelines(gefiltert)
        except Exception:
            pass

    return entfernt


def bereinige_logs():
    grenze = datetime.now() - timedelta(weeks=MAX_ALTER_WOCHEN)
    gesamt = 0

    log_dateien = [
        os.path.join(_BASE_DIR, "data", "whatsapp_log.txt"),
    ]
    notizen_glob = os.path.join(_BASE_DIR, "data", "notizen", "*.txt")
    log_dateien += glob.glob(notizen_glob)

    for pfad in log_dateien:
        if os.path.exists(pfad):
            n = _bereinige_datei(pfad, grenze)
            if n:
                gesamt += n

    if gesamt:
        print(f"[log_cleanup] {gesamt} Einträge älter als {MAX_ALTER_WOCHEN} Wochen entfernt.")
