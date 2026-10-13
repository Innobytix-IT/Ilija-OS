#!/usr/bin/env python3
"""
update_history_eintrag.py – schreibt einen Eintrag in update_history.json
und erzeugt ggf. eine System-Notification.

Aufruf vom ilija-update.sh:
  python3 update_history_eintrag.py \
      --von <sha> --nach <sha> --status ok|rollback|fehler \
      [--grund "..."] [--changelog "..."]
"""
import argparse
import json
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(REPO, "data", "update_history.json")


def _load():
    try:
        with open(HIST, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items):
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--von",       required=True)
    ap.add_argument("--nach",      required=True)
    ap.add_argument("--status",    required=True,
                    choices=["ok", "rollback", "fehler"])
    ap.add_argument("--grund",     default="")
    ap.add_argument("--changelog", default="")
    args = ap.parse_args()

    items = _load()
    items.insert(0, {
        "zeit":      datetime.now().isoformat(timespec="seconds"),
        "von":       args.von,
        "nach":      args.nach,
        "status":    args.status,
        "grund":     args.grund,
        "changelog": args.changelog,
    })
    items = items[:20]  # nur die letzten 20 behalten
    _save(items)

    # Bei Rollback: Notification erzeugen
    if args.status == "rollback":
        sys.path.insert(0, REPO)
        try:
            import system_notifications as sn
            sn.notify(
                sn.LEVEL_KRITISCH,
                "Update automatisch zurueckgerollt",
                f"Das Update ({args.von[:7]} → {args.nach[:7]}) hat den "
                f"Selbsttest nicht bestanden. Grund:\n{args.grund}\n\n"
                "Ilija laeuft wieder auf der vorherigen Version. "
                "Unter Einstellungen → Auto-Update → Update-Verlauf "
                "kannst du nachsehen oder manuell auf eine andere "
                "Version wechseln.",
                typ="update_rollback",
                meta={"von": args.von, "nach": args.nach,
                      "grund": args.grund},
            )
        except Exception as e:
            print(f"Hinweis: Notification konnte nicht angelegt werden: {e}",
                  file=sys.stderr)

    # Bei Erfolg: evtl. offenen "updates_verfuegbar"-Hinweis loeschen
    if args.status == "ok" and args.von != args.nach:
        sys.path.insert(0, REPO)
        try:
            import system_notifications as sn
            sn.resolve_by_type("updates_verfuegbar")
        except Exception:
            pass


if __name__ == "__main__":
    main()
