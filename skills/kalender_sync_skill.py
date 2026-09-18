"""
kalender_sync_skill.py – Synchronisiert den lokalen Kalender mit Google oder Outlook.

Lokaler Kalender = Single Source of Truth.
Sync-Richtungen:
  Push (Lokal → Provider): wird nach jeder neuen Buchung im Hintergrund aufgerufen.
  Pull (Provider → Lokal):  konfigurierbar (3x täglich / stündlich / manuell).

Config: data/kalender_sync.json
  {
    "provider":        "keiner" | "google" | "outlook",
    "pull_intervall":  "manuell" | "3x_taeglich" | "stuendlich",
    "auto_push":       true | false,
    "letzte_sync":     "2026-01-01T10:00:00"
  }
"""

import os
import json
import threading
from datetime import datetime

_BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_BASE_DIR, "data", "kalender_sync.json")

_DEFAULTS = {
    "provider":       "keiner",
    "pull_intervall": "3x_taeglich",
    "auto_push":      True,
    "letzte_sync":    "",
}


# ── Config I/O ────────────────────────────────────────────────────────────────

def _lade_config() -> dict:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {**_DEFAULTS, **cfg}
        except Exception:
            pass
    return dict(_DEFAULTS)


def _speichere_config(cfg: dict):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── Lokale Events lesen ───────────────────────────────────────────────────────

def _lokale_events() -> list:
    pfad = os.path.join(_BASE_DIR, "data", "local_calendar_events.json")
    if not os.path.exists(pfad):
        return []
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _speichere_lokale_events(events: list):
    pfad = os.path.join(_BASE_DIR, "data", "local_calendar_events.json")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _iso_zu_datum_zeit(iso_str: str):
    """ISO-String → (datum 'TT.MM.JJJJ', von 'HH:MM', bis 'HH:MM')"""
    if not iso_str:
        return None, None, None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime("%d.%m.%Y"), dt.strftime("%H:%M"), dt
    except Exception:
        return None, None, None


# ── Push: Lokal → Provider ────────────────────────────────────────────────────

def push_termin_zu_provider(titel: str, datum: str, uhrzeit_von: str, uhrzeit_bis: str,
                              kontaktinfos: str = "", beschreibung: str = "") -> str:
    """
    Trägt einen einzelnen Termin direkt beim konfigurierten Provider ein.
    Wird nach jeder neuen lokalen Buchung aufgerufen.

    Workaround-Hinweis für Outlook:
    Microsoft bietet keine kostenfreie offene API für den Outlook-Kalender an.
    Als Workaround steuert Ilija Outlook über Browser-Automatisierung (Selenium/Chrome):
    Nach dem Anruf öffnet sich kurz ein Chrome-Fenster, trägt den Termin ein und schließt
    sich wieder. Das ist kein Fehler — das ist das erwartete Verhalten.
    Voraussetzung: Chrome ist installiert und das Outlook-Profil wurde einmalig über
    'outlook_login_einrichten()' eingerichtet (einmaliges Anmelden im Browser).
    """
    cfg = _lade_config()
    provider = cfg.get("provider", "keiner").lower()

    if provider == "keiner":
        return "Kein externer Kalender konfiguriert — Push übersprungen."

    if not cfg.get("auto_push", True):
        return "Auto-Push deaktiviert — Push übersprungen."

    try:
        if provider == "google":
            from skills.google_kalender import google_termin_eintragen
            return google_termin_eintragen(titel, datum, uhrzeit_von, uhrzeit_bis,
                                           kontaktinfos, beschreibung)

        if provider == "outlook":
            # Öffnet kurz ein Chrome-Fenster (Selenium-Workaround, da Microsoft
            # keine kostenfreie Kalender-API anbietet). Läuft nach Gesprächsende
            # im Hintergrund — ein kurz aufpoppendes Fenster ist normal.
            from skills.outlook_kalender import outlook_termin_eintragen
            return outlook_termin_eintragen(titel, datum, uhrzeit_von, uhrzeit_bis,
                                            kontaktinfos, beschreibung)

        return f"Unbekannter Provider: {provider}"

    except Exception as e:
        return f"Push-Fehler ({provider}): {e}"


def push_termin_im_hintergrund(titel: str, datum: str, uhrzeit_von: str, uhrzeit_bis: str,
                                kontaktinfos: str = "", beschreibung: str = ""):
    """Startet den Push in einem Daemon-Thread (non-blocking für Aufrufer)."""
    def _run():
        ergebnis = push_termin_zu_provider(titel, datum, uhrzeit_von, uhrzeit_bis,
                                           kontaktinfos, beschreibung)
        print(f"[KalenderSync] Push-Ergebnis: {ergebnis}")

    threading.Thread(target=_run, daemon=True).start()


# ── Pull: Provider → Lokal ────────────────────────────────────────────────────

def _google_events_zu_lokal(tage_voraus: int = 90) -> list:
    """Liest Google-Events der nächsten N Tage und gibt sie als lokale Dicts zurück."""
    from skills.google_kalender import _get_service, _parse_gev_dt, _rfc3339
    import uuid as _uuid

    svc = _get_service()
    jetzt  = datetime.now()
    bis_dt = jetzt.replace(hour=23, minute=59)
    from datetime import timedelta
    bis_dt = jetzt + timedelta(days=tage_voraus)

    result = svc.events().list(
        calendarId  = "primary",
        timeMin     = _rfc3339(jetzt) + "Z",
        timeMax     = _rfc3339(bis_dt) + "Z",
        singleEvents= True,
        orderBy     = "startTime",
        maxResults  = 250,
    ).execute()

    events = []
    for ev in result.get("items", []):
        titel = ev.get("summary", "Ohne Titel")
        desc  = ev.get("description", "")
        start = _parse_gev_dt(ev.get("start", {}))
        ende  = _parse_gev_dt(ev.get("end",   {}))
        if not start:
            continue
        g_id = ev.get("id", "")
        events.append({
            "id":          f"google_{g_id}" if g_id else str(_uuid.uuid4()),
            "title":       titel,
            "start":       start.isoformat(),
            "end":         ende.isoformat() if ende else start.isoformat(),
            "description": desc,
            "contactInfo": ev.get("attendees", [{}])[0].get("email", "") if ev.get("attendees") else "",
            "caller_id":   "",
            "category":    "standard",
            "recurrence":  "none",
            "backgroundColor": "var(--g)",
            "borderColor":     "var(--g2)",
            "_sync_quelle":    "google",
        })
    return events


def pull_extern_zu_lokal() -> str:
    """
    Zieht alle bevorstehenden Termine vom konfigurierten Provider
    und fügt neue Einträge in den lokalen Kalender ein.
    Bereits vorhandene Einträge (anhand ID oder Titel+Zeit) werden nicht dupliziert.
    """
    cfg = _lade_config()
    provider = cfg.get("provider", "keiner").lower()

    if provider == "keiner":
        return "Kein externer Kalender konfiguriert."

    try:
        if provider == "google":
            neue = _google_events_zu_lokal()
        elif provider == "outlook":
            # Outlook-Pull ist technisch nicht umsetzbar:
            # Die Selenium-Automatisierung liefert nur formatierten Anzeigetext für
            # den heutigen Tag — keine strukturierten Daten für mehrere Tage.
            # Push (Lokal → Outlook) funktioniert jedoch über den Compose-Deeplink.
            return (
                "Outlook-Pull nicht unterstützt.\n"
                "Hintergrund: Microsoft bietet keine kostenfreie offene API an. "
                "Ilija steuert Outlook über Browser-Automatisierung (Selenium), "
                "die nur den Tagestext ausliest — kein strukturierter Import möglich.\n"
                "Workaround: Tragen Sie externe Outlook-Termine manuell im lokalen "
                "Kalender nach, oder verwenden Sie Google Kalender für automatischen Pull.\n"
                "Push (Lokal → Outlook) funktioniert weiterhin automatisch nach jedem Anruf."
            )
        else:
            return f"Unbekannter Provider: {provider}"

        lokale = _lokale_events()
        bekannte_ids  = {e.get("id") for e in lokale}
        # Fallback-Duplikatprüfung: Titel + Startzeit
        bekannte_keys = {(e.get("title", ""), e.get("start", "")) for e in lokale}

        hinzugefuegt = 0
        for ev in neue:
            key = (ev.get("title", ""), ev.get("start", ""))
            if ev["id"] in bekannte_ids or key in bekannte_keys:
                continue
            lokale.append(ev)
            bekannte_ids.add(ev["id"])
            bekannte_keys.add(key)
            hinzugefuegt += 1

        _speichere_lokale_events(lokale)

        cfg["letzte_sync"] = datetime.now().isoformat(timespec="seconds")
        _speichere_config(cfg)

        return (f"Pull abgeschlossen: {hinzugefuegt} neue Termin(e) von {provider} übernommen. "
                f"Gesamt lokal: {len(lokale)}.")

    except Exception as e:
        return f"Pull-Fehler ({provider}): {e}"


# ── Status ────────────────────────────────────────────────────────────────────

def kalender_sync_status() -> str:
    cfg = _lade_config()
    provider   = cfg.get("provider", "keiner")
    intervall  = cfg.get("pull_intervall", "3x_taeglich")
    auto_push  = cfg.get("auto_push", True)
    letzte     = cfg.get("letzte_sync", "")

    intervall_text = {
        "manuell":      "Manuell",
        "3x_taeglich":  "3× täglich",
        "stuendlich":   "Stündlich",
    }.get(intervall, intervall)

    zeilen = [
        f"Kalender-Synchronisation:",
        f"  Provider:       {provider}",
        f"  Pull-Intervall: {intervall_text}",
        f"  Auto-Push:      {'Ja' if auto_push else 'Nein'}",
        f"  Letzte Sync:    {letzte or '—'}",
    ]
    return "\n".join(zeilen)


# ── Scheduler-Logik (wird von web_server.py genutzt) ─────────────────────────

def soll_pull_jetzt(letzte_sync_str: str, intervall: str) -> bool:
    """Gibt True zurück wenn ein Pull fällig ist."""
    if intervall == "manuell":
        return False
    if not letzte_sync_str:
        return True
    try:
        letzte = datetime.fromisoformat(letzte_sync_str)
    except Exception:
        return True

    from datetime import timedelta
    delta = datetime.now() - letzte

    if intervall == "stuendlich":
        return delta.total_seconds() >= 3600
    if intervall == "3x_taeglich":
        return delta.total_seconds() >= 28800  # 8 Stunden
    return False


AVAILABLE_SKILLS = [
    kalender_sync_status,
    pull_extern_zu_lokal,
]
