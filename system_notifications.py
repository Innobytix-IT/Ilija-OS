"""
system_notifications.py – persistente System-Hinweise fuer Ilija OS.

Fuer Dinge die der User sehen MUSS bis er sich kuemmert: Update
zurueckgerollt, Platte voll, AHPT-Agent down, neue Updates verfuegbar.
Nicht fuer einmalige Chat-Toasts – dafuer gibt es data/notifications.json
(Fax/Fristen).

Jede Nachricht hat:
  id, level (kritisch|warnung|info), titel, text, erstellt, meta,
  typ (fuer Auto-Resolve-Lookup), bedingung (optional)

Auto-Resolve: beim GET prueft register_check(typ, func) ob die Bedingung
noch zutrifft. Wenn func() == False, wird die Notification entfernt.
Nachrichten vom Typ "update_rollback" haben keinen Check – sie bleiben
bis der User manuell auf "Erledigt" klickt.
"""
import json
import os
import threading
import uuid
from datetime import datetime
from typing import Callable, Optional

_BASE  = os.path.dirname(os.path.abspath(__file__))
_STORE = os.path.join(_BASE, "data", "system_notifications.json")
_lock  = threading.Lock()

# Registry: typ -> Funktion die True zurueckgibt wenn Bedingung noch
# existiert (also Notification NICHT aufgeloest werden darf).
_resolve_checks: dict[str, Callable[[dict], bool]] = {}

LEVEL_KRITISCH = "kritisch"
LEVEL_WARNUNG  = "warnung"
LEVEL_INFO     = "info"


def _load() -> list:
    try:
        with open(_STORE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list) -> None:
    os.makedirs(os.path.dirname(_STORE), exist_ok=True)
    tmp = _STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STORE)


def register_check(typ: str, func: Callable[[dict], bool]) -> None:
    """Registriert einen Auto-Resolve-Check. func(meta) muss True
    zurueckgeben wenn die Bedingung noch besteht, False wenn geloest."""
    _resolve_checks[typ] = func


def notify(level: str, titel: str, text: str,
           typ: str = "allgemein", meta: Optional[dict] = None,
           dedupe_key: Optional[str] = None) -> str:
    """
    Legt eine neue Nachricht ab. Gibt die ID zurueck.

    dedupe_key: wenn gesetzt, wird eine bestehende offene Nachricht mit
    gleichem key ueberschrieben statt eine neue anzulegen. Verhindert
    dass z.B. ein Hintergrund-Check 'platte voll' alle 10min stapelt.
    """
    if level not in (LEVEL_KRITISCH, LEVEL_WARNUNG, LEVEL_INFO):
        raise ValueError(f"Ungueltiger Level: {level}")
    with _lock:
        items = _load()
        if dedupe_key:
            # Alte Eintraege mit gleichem Key entfernen
            items = [n for n in items if n.get("dedupe_key") != dedupe_key]
        eintrag = {
            "id":         str(uuid.uuid4()),
            "level":      level,
            "titel":      titel,
            "text":       text,
            "typ":        typ,
            "meta":       meta or {},
            "dedupe_key": dedupe_key,
            "erstellt":   datetime.now().isoformat(timespec="seconds"),
        }
        items.append(eintrag)
        _save(items)
        return eintrag["id"]


def get_offene(mit_auto_resolve: bool = True) -> list:
    """Liefert alle offenen Nachrichten. Prueft optional Auto-Resolve."""
    with _lock:
        items = _load()
        if not mit_auto_resolve:
            return items
        geblieben: list = []
        for n in items:
            check = _resolve_checks.get(n.get("typ", ""))
            if check is None:
                geblieben.append(n)
                continue
            try:
                if check(n.get("meta") or {}):
                    geblieben.append(n)
                # else: Bedingung geloest -> Notification faellt raus
            except Exception:
                # Check-Fehler: lieber Notification zeigen als unterdruecken
                geblieben.append(n)
        if len(geblieben) != len(items):
            _save(geblieben)
        # neueste zuerst
        geblieben.sort(key=lambda n: n.get("erstellt", ""), reverse=True)
        return geblieben


def resolve_by_id(nid: str) -> bool:
    """Markiert Nachricht als vom User erledigt. True wenn gefunden."""
    with _lock:
        items = _load()
        neu = [n for n in items if n.get("id") != nid]
        if len(neu) == len(items):
            return False
        _save(neu)
        return True


def resolve_by_type(typ: str) -> int:
    """Entfernt alle Nachrichten eines Typs. Fuer Code-Pfade die wissen
    dass ein Problem geloest ist (z.B. 'update erfolgreich eingespielt'
    loescht 'updates_verfuegbar')."""
    with _lock:
        items = _load()
        neu = [n for n in items if n.get("typ") != typ]
        geloescht = len(items) - len(neu)
        if geloescht:
            _save(neu)
        return geloescht
