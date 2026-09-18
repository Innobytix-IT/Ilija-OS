import os
from datetime import datetime, timedelta

SCOPES           = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_PATH = os.path.join("data", "google_kalender", "credentials.json")
TOKEN_PATH       = os.path.join("data", "google_kalender", "token.json")
ZEITZONE         = "Europe/Berlin"


# ── Interne Hilfsfunktionen ────────────────────────────────────────────────────

def _get_service(credentials_pfad: str = ""):
    """
    Lädt OAuth2-Credentials und gibt einen Google Calendar API Service zurück.
    Beim ersten Aufruf öffnet sich einmalig ein Browser-Fenster zur Autorisierung.
    """
    try:
        from google.oauth2.credentials      import Credentials
        from google_auth_oauthlib.flow      import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery      import build
    except ImportError:
        raise ImportError(
            "Google-Bibliotheken fehlen. Bitte installieren:\n"
            "pip install google-api-python-client google-auth-httplib2 "
            "google-auth-oauthlib"
        )

    creds_pfad = credentials_pfad.strip() or CREDENTIALS_PATH

    if not os.path.exists(creds_pfad):
        raise FileNotFoundError(
            f"credentials.json nicht gefunden: {creds_pfad}\n"
            "Bitte aus der Google Cloud Console herunterladen:\n"
            "APIs & Dienste → Anmeldedaten → OAuth-Client → JSON herunterladen"
        )

    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            # Einmalig: Browser öffnet sich, User klickt "Zulassen"
            flow  = InstalledAppFlow.from_client_secrets_file(creds_pfad, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_datum(datum: str):
    """TT.MM.JJJJ oder '' (heute) → date-Objekt"""
    if datum and datum.strip():
        return datetime.strptime(datum.strip(), "%d.%m.%Y").date()
    return datetime.now().date()


def _rfc3339(dt: datetime) -> str:
    """naive datetime → RFC3339-String (als UTC-naive behandelt, Zeitzone über ZEITZONE)"""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_gev_dt(ev_time_dict: dict):
    """Google-Event start/end-Dict → naive datetime"""
    if "dateTime" in ev_time_dict:
        return datetime.fromisoformat(ev_time_dict["dateTime"][:19])
    if "date" in ev_time_dict:
        return datetime.fromisoformat(ev_time_dict["date"])
    return None


def _belegte_slots(svc, datum_dt: datetime):
    """Gibt sortierte Liste belegter (start, end) Intervalle für einen Tag zurück."""
    tag_start = datum_dt.replace(hour=0,  minute=0,  second=0)
    tag_ende  = datum_dt.replace(hour=23, minute=59, second=59)

    result = svc.events().list(
        calendarId  = "primary",
        timeMin     = _rfc3339(tag_start) + "Z",
        timeMax     = _rfc3339(tag_ende)  + "Z",
        singleEvents= True,
        orderBy     = "startTime",
    ).execute()

    belegte = []
    for ev in result.get("items", []):
        vs = _parse_gev_dt(ev.get("start", {}))
        ve = _parse_gev_dt(ev.get("end",   {}))
        if vs and ve:
            belegte.append((vs, ve))
    return sorted(belegte)


# ── Öffentliche Skill-Funktionen ───────────────────────────────────────────────

def google_kalender_lesen(datum: str = "") -> str:
    """
    Liest alle Termine aus dem Google-Kalender für einen bestimmten Tag.
    datum: TT.MM.JJJJ (Standard: heute)
    """
    try:
        ziel_datum = _parse_datum(datum)
        datum_dt   = datetime.combine(ziel_datum, datetime.min.time())
        svc        = _get_service()

        tag_start = datum_dt.replace(hour=0,  minute=0,  second=0)
        tag_ende  = datum_dt.replace(hour=23, minute=59, second=59)

        result = svc.events().list(
            calendarId  = "primary",
            timeMin     = _rfc3339(tag_start) + "Z",
            timeMax     = _rfc3339(tag_ende)  + "Z",
            singleEvents= True,
            orderBy     = "startTime",
        ).execute()

        items = result.get("items", [])
        anzeige = ziel_datum.strftime("%d.%m.%Y")

        if not items:
            return f"Keine Termine am {anzeige} gefunden."

        eintraege = []
        for ev in items:
            titel = ev.get("summary", "Ohne Titel")
            desc  = ev.get("description", "")
            vs    = _parse_gev_dt(ev.get("start", {}))
            ve    = _parse_gev_dt(ev.get("end",   {}))
            if vs and ve:
                zeit_str = f"{vs.strftime('%H:%M')} - {ve.strftime('%H:%M')}"
            else:
                zeit_str = "Ganztägig"
            eintrag = f"[{zeit_str}] {titel}"
            if desc:
                eintrag += f"\n  📝 Details: {desc}"
            eintraege.append(eintrag)

        return f"TERMINE AM {anzeige} (Google Kalender):\n" + "\n---\n".join(eintraege)

    except Exception as e:
        return f"❌ Fehler beim Lesen: {e}"


def google_freie_slots_finden(datum: str = "", dauer_minuten: int = 60,
                               arbeit_von: int = 8, arbeit_bis: int = 18) -> str:
    """
    Findet freie Zeitfenster im Google-Kalender für einen Tag.
    datum: TT.MM.JJJJ (Standard: heute)
    dauer_minuten: Mindestlänge des gesuchten Slots (Standard: 60)
    arbeit_von / arbeit_bis: Arbeitszeit in vollen Stunden (Standard: 8–18)
    """
    try:
        ziel_datum = _parse_datum(datum)
        datum_dt   = datetime.combine(ziel_datum, datetime.min.time())
        svc        = _get_service()

        belegte      = _belegte_slots(svc, datum_dt)
        arbeit_start = datum_dt.replace(hour=arbeit_von, minute=0, second=0)
        arbeit_end   = datum_dt.replace(hour=arbeit_bis, minute=0, second=0)
        dauer        = timedelta(minutes=dauer_minuten)

        freie_slots = []
        zeiger      = arbeit_start
        for ev_von, ev_bis in belegte:
            if zeiger + dauer <= ev_von:
                freie_slots.append((zeiger, ev_von))
            if ev_bis > zeiger:
                zeiger = ev_bis
        if zeiger + dauer <= arbeit_end:
            freie_slots.append((zeiger, arbeit_end))

        anzeige = ziel_datum.strftime("%d.%m.%Y")
        if not freie_slots:
            return f"Keine freien Slots am {anzeige} (Mindestdauer: {dauer_minuten} Min.)."

        zeilen = [f"FREIE ZEITFENSTER AM {anzeige} (mind. {dauer_minuten} Min.):\n"]
        for i, (von, bis) in enumerate(freie_slots, 1):
            diff = int((bis - von).total_seconds() // 60)
            zeilen.append(f"{i}. {von.strftime('%H:%M')} – {bis.strftime('%H:%M')} ({diff} Min. frei)")
        return "\n".join(zeilen)

    except Exception as e:
        return f"❌ Fehler bei der Slot-Suche: {e}"


def google_termin_eintragen(titel: str, datum: str, uhrzeit_von: str, uhrzeit_bis: str,
                             kontaktinfos: str = "", beschreibung: str = "") -> str:
    """
    Trägt einen neuen Termin in den Google-Kalender (primary) ein.
    titel: Terminbezeichnung
    datum: TT.MM.JJJJ
    uhrzeit_von / uhrzeit_bis: HH:MM
    kontaktinfos: Name, Telefon oder E-Mail des Kontakts (Optional)
    beschreibung: Weitere Details (Optional)
    Beispiel: google_termin_eintragen(titel="Beratung", datum="18.04.2026", uhrzeit_von="10:00", uhrzeit_bis="11:00", kontaktinfos="Max Müller, 0151-123456")
    """
    try:
        ziel_datum = _parse_datum(datum)
        datum_dt   = datetime.combine(ziel_datum, datetime.min.time())

        h_von, m_von = map(int, uhrzeit_von.strip().split(":"))
        h_bis, m_bis = map(int, uhrzeit_bis.strip().split(":"))

        start_dt = datum_dt.replace(hour=h_von, minute=m_von, second=0)
        end_dt   = datum_dt.replace(hour=h_bis, minute=m_bis, second=0)

        # Beschreibung zusammenbauen (Kontaktinfos + optionaler Freitext)
        desc_teile = []
        if kontaktinfos:
            desc_teile.append(f"👤 Kontakt: {kontaktinfos}")
        if beschreibung:
            desc_teile.append(beschreibung)
        volle_beschreibung = "\n".join(desc_teile)

        ev_body = {
            "summary": titel,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": ZEITZONE},
            "end":   {"dateTime": end_dt.isoformat(),   "timeZone": ZEITZONE},
        }
        if volle_beschreibung:
            ev_body["description"] = volle_beschreibung

        svc     = _get_service()
        created = svc.events().insert(calendarId="primary", body=ev_body).execute()

        ausgabe = (f"✅ Termin eingetragen!\n"
                   f"📅 {titel}\n"
                   f"🕐 {datum}, {uhrzeit_von} – {uhrzeit_bis} Uhr\n"
                   f"🔗 {created.get('htmlLink', '')}")
        if kontaktinfos:
            ausgabe += f"\n👤 Kontakt: {kontaktinfos}"
        return ausgabe

    except Exception as e:
        return f"❌ Fehler beim Eintragen: {e}"


def google_termin_loeschen(titel: str, datum: str) -> str:
    """
    Löscht einen Termin aus dem Google-Kalender (Teilübereinstimmung beim Titel reicht).
    titel: Suchbegriff (Groß-/Kleinschreibung egal)
    datum: TT.MM.JJJJ
    """
    try:
        ziel_datum = _parse_datum(datum)
        datum_dt   = datetime.combine(ziel_datum, datetime.min.time())
        svc        = _get_service()

        tag_start = datum_dt.replace(hour=0,  minute=0,  second=0)
        tag_ende  = datum_dt.replace(hour=23, minute=59, second=59)

        result = svc.events().list(
            calendarId  = "primary",
            timeMin     = _rfc3339(tag_start) + "Z",
            timeMax     = _rfc3339(tag_ende)  + "Z",
            singleEvents= True,
        ).execute()

        titel_lower = titel.lower()
        for ev in result.get("items", []):
            summary = ev.get("summary", "")
            if titel_lower in summary.lower():
                svc.events().delete(calendarId="primary", eventId=ev["id"]).execute()
                return f"✅ Termin '{summary}' am {datum} wurde gelöscht."

        return f"❌ Kein Termin mit '{titel}' am {datum} gefunden."

    except Exception as e:
        return f"❌ Fehler beim Löschen: {e}"


AVAILABLE_SKILLS = [
    google_kalender_lesen,
    google_freie_slots_finden,
    google_termin_eintragen,
    google_termin_loeschen,
]
