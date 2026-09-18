import os
import re
import json
import uuid
from datetime import datetime, timedelta, time as dtime

CALENDAR_FILE = os.path.join("data", "local_calendar_events.json")

def _load_events():
    if not os.path.exists(CALENDAR_FILE):
        return []
    try:
        with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_events(events):
    os.makedirs(os.path.dirname(CALENDAR_FILE), exist_ok=True)
    with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

def _parse_iso(iso_str):
    """Parst ISO-Datum/Zeit-String und gibt immer ein timezone-NAHES (naive) datetime zurück."""
    if not iso_str: return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        # Timezone-aware → in lokale Zeit konvertieren und tzinfo entfernen
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except ValueError:
        try:
            return datetime.strptime(iso_str.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None

def _get_events_for_date(ziel_datum):
    events = _load_events()
    belegte = []
    termine_mit_zeit = []  # (start_time, eintrag) – für sortierte Ausgabe

    js_weekday = (ziel_datum.weekday() + 1) % 7

    for ev in events:
        is_match = False
        ev_start_time = None
        ev_end_time = None

        try:
            recurrence = ev.get("recurrence", "none")

            if recurrence != "none":
                start_recur_raw = ev.get("startRecur")
                if not start_recur_raw:
                    continue
                start_recur_dt = datetime.strptime(start_recur_raw, "%Y-%m-%d").date()

                # endRecur berücksichtigen (optional)
                end_recur_raw = ev.get("endRecur")
                end_recur_dt = datetime.strptime(end_recur_raw, "%Y-%m-%d").date() if end_recur_raw else None

                in_zeitraum = ziel_datum >= start_recur_dt
                if end_recur_dt:
                    in_zeitraum = in_zeitraum and ziel_datum < end_recur_dt

                if in_zeitraum:
                    if recurrence == "daily":
                        is_match = True
                    elif recurrence == "weekly":
                        if js_weekday in ev.get("daysOfWeek", []):
                            is_match = True
                    elif recurrence == "monthly":
                        if ziel_datum.day == start_recur_dt.day:
                            is_match = True
                    elif recurrence == "yearly":
                        if ziel_datum.month == start_recur_dt.month and ziel_datum.day == start_recur_dt.day:
                            is_match = True

                if is_match:
                    start_time_raw = ev.get("startTime")
                    end_time_raw   = ev.get("endTime")
                    if not start_time_raw or not end_time_raw:
                        continue
                    ev_start_time = datetime.strptime(start_time_raw, "%H:%M").time()
                    ev_end_time   = datetime.strptime(end_time_raw,   "%H:%M").time()
            else:
                start_dt = _parse_iso(ev.get("start"))
                if start_dt:
                    end_dt_parsed = _parse_iso(ev.get("end"))
                    event_start_date = start_dt.date()
                    event_end_date = end_dt_parsed.date() if end_dt_parsed else event_start_date

                    # Mehrtagestermine: alle Tage im Zeitraum blockieren, nicht nur den Starttag
                    if event_start_date <= ziel_datum <= event_end_date:
                        is_match = True
                        if event_start_date == event_end_date:
                            # Eintägiger Termin — exakte Start- und Endzeit
                            ev_start_time = start_dt.time()
                            ev_end_time   = end_dt_parsed.time() if end_dt_parsed else (
                                datetime.combine(event_start_date, start_dt.time()) + timedelta(hours=1)
                            ).time()
                        elif ziel_datum == event_start_date:
                            # Erster Tag: ab Startzeit bis Mitternacht
                            ev_start_time = start_dt.time()
                            ev_end_time   = dtime(23, 59)
                        elif ziel_datum == event_end_date:
                            # Letzter Tag: von Mitternacht bis Endzeit
                            ev_start_time = dtime(0, 0)
                            ev_end_time   = end_dt_parsed.time() if end_dt_parsed else dtime(23, 59)
                            if ev_end_time == dtime(0, 0):
                                ev_end_time = dtime(23, 59)
                        else:
                            # Mittlerer Tag: ganztägig blockieren
                            ev_start_time = dtime(0, 0)
                            ev_end_time   = dtime(23, 59)

            if is_match:
                start_comb = datetime.combine(ziel_datum, ev_start_time)
                end_comb   = datetime.combine(ziel_datum, ev_end_time)
                # Cross-Midnight-Blocker (z.B. startTime=16:30, endTime=06:00):
                # Endzeit liegt vor Startzeit → Blocker geht über Mitternacht
                if end_comb <= start_comb:
                    end_comb += timedelta(days=1)
                belegte.append((start_comb, end_comb))

                cat = ev.get("category", "standard")
                kat_prefix = ""
                if cat == "blocker": kat_prefix = "⛔ [BLOCKER] "
                elif cat == "wichtig": kat_prefix = "🔴 [WICHTIG] "
                elif cat == "privat": kat_prefix = "🔵 [PRIVAT] "

                titel   = ev.get("title", "Ohne Titel")
                desc    = ev.get("description", "")
                contact = ev.get("contactInfo", "")
                zeit_str = f"{ev_start_time.strftime('%H:%M')} - {ev_end_time.strftime('%H:%M')}"

                eintrag = f"[{zeit_str}] {kat_prefix}{titel}"
                if contact: eintrag += f"\n  👤 Kontakt: {contact}"
                if desc:    eintrag += f"\n  📝 Details: {desc}"
                termine_mit_zeit.append((start_comb, eintrag))

        except Exception:
            continue  # Kaputtes Event überspringen, nicht abstürzen

    termine_mit_zeit.sort(key=lambda x: x[0])
    tages_termine = [e for _, e in termine_mit_zeit]
    return sorted(belegte), tages_termine


def lokaler_kalender_lesen(datum: str = "") -> str:
    """Liest alle Termine und Serientermine eines bestimmten Tages. datum: TT.MM.JJJJ (Standard: heute)"""
    try:
        if datum:
            ziel_datum = datetime.strptime(datum.strip(), "%d.%m.%Y").date()
        else:
            ziel_datum = datetime.now().date()

        _, tages_termine = _get_events_for_date(ziel_datum)
        anzeige = ziel_datum.strftime("%d.%m.%Y")

        if not tages_termine:
            return f"Keine Termine am {anzeige} gefunden."

        return f"TERMINE AM {anzeige}:\n" + "\n---\n".join(tages_termine)
    except Exception as e:
        return f"❌ Fehler beim Lesen: {e}"


def lokaler_kalender_freie_slots_finden(datum: str = "", dauer_minuten: int = 60, arbeit_von: int = 8, arbeit_bis: int = 18) -> str:
    """Findet freie Zeitfenster. Berücksichtigt Blockereinträge und Serientermine.
    Nur Arbeitstage (Mo-Fr) haben freie Slots."""
    try:
        if datum:
            ziel_datum = datetime.strptime(datum.strip(), "%d.%m.%Y").date()
        else:
            ziel_datum = datetime.now().date()

        # Kein Arbeitstag (Samstag=5, Sonntag=6)
        if ziel_datum.weekday() >= 5:
            wochentag = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"][ziel_datum.weekday()]
            return f"❌ {wochentag} ist kein Arbeitstag. Bitte einen Werktag (Mo–Fr) wählen."

        belegte, _ = _get_events_for_date(ziel_datum)

        start = datetime.combine(ziel_datum, datetime.strptime(f"{arbeit_von}:00", "%H:%M").time())
        ende = datetime.combine(ziel_datum, datetime.strptime(f"{arbeit_bis}:00", "%H:%M").time())

        # Wenn heute: frühestens ab jetzt suchen (vergangene Slots ignorieren)
        if ziel_datum == datetime.now().date():
            jetzt = datetime.now().replace(second=0, microsecond=0)
            if jetzt > start:
                start = jetzt
        dauer = timedelta(minutes=dauer_minuten)

        freie_slots = []
        zeiger = start

        for (ev_von, ev_bis) in belegte:
            if zeiger + dauer <= ev_von:
                freie_slots.append((zeiger, ev_von))
            if ev_bis > zeiger:
                zeiger = ev_bis

        if zeiger + dauer <= ende:
            freie_slots.append((zeiger, ende))

        anzeige = ziel_datum.strftime("%d.%m.%Y")
        if not freie_slots:
            return f"Keine freien Slots am {anzeige} (Mindestdauer: {dauer_minuten} Min.)."

        zeilen = [f"FREIE ZEITFENSTER AM {anzeige} (mind. {dauer_minuten} Min.):\n"]
        for i, (v, b) in enumerate(freie_slots, 1):
            zeilen.append(f"{i}. {v.strftime('%H:%M')} – {b.strftime('%H:%M')} "
                          f"({int((b-v).total_seconds()//60)} Min. frei)")
        return "\n".join(zeilen)
    except Exception as e:
        return f"❌ Fehler bei der Slot-Suche: {e}"


def naechste_n_slots(n: int = 3, ab_datum=None, dauer_minuten: int = 60, arbeit_von: int = 8, arbeit_bis: int = 18) -> list:
    """Gibt die nächsten n freien Einzelslots zurück als Liste von (datum_str, uhrzeit_str).
    Sucht maximal 60 Werktage in die Zukunft."""
    from datetime import date as date_cls
    if ab_datum is None:
        ab_datum = date_cls.today()
    ergebnis = []
    pruef_datum = ab_datum
    max_tage = 60
    gezaehlt = 0
    while len(ergebnis) < n and gezaehlt < max_tage:
        if pruef_datum.weekday() < 5:  # nur Werktage
            datum_str = pruef_datum.strftime("%d.%m.%Y")
            slots_text = lokaler_kalender_freie_slots_finden(datum_str, dauer_minuten, arbeit_von, arbeit_bis)
            # Slots parsen: "1. 09:00 – 10:00 (60 Min. frei)"
            for zeile in slots_text.splitlines():
                m = re.match(r'\d+\.\s+(\d{2}:\d{2})', zeile)
                if m and len(ergebnis) < n:
                    ergebnis.append((datum_str, m.group(1)))
        pruef_datum += timedelta(days=1)
        gezaehlt += 1
    return ergebnis


def lokaler_kalender_termin_eintragen(titel: str, datum: str, uhrzeit_von: str, uhrzeit_bis: str, kontaktinfos: str = "", beschreibung: str = "", caller_id: str = "") -> str:
    """
    Trägt einen Termin in den Kalender ein.
    kontaktinfos: Name, Nummer oder E-Mail des Kunden.
    caller_id: Telefon-/WhatsApp-Nummer des Buchenden (für Datenisolation).
    """
    try:
        start_dt = datetime.strptime(f"{datum.strip()} {uhrzeit_von.strip()}", "%d.%m.%Y %H:%M")
        end_dt = datetime.strptime(f"{datum.strip()} {uhrzeit_bis.strip()}", "%d.%m.%Y %H:%M")

        # caller_id in kontaktinfos einbetten falls vorhanden und noch nicht drin
        if caller_id and caller_id not in kontaktinfos:
            kontaktinfos = f"{kontaktinfos} [{caller_id}]".strip() if kontaktinfos else caller_id

        events = _load_events()
        new_event = {
            "id": str(uuid.uuid4()),
            "title": titel,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "description": beschreibung,
            "contactInfo": kontaktinfos,
            "caller_id": caller_id,          # für Datenisolation
            "category": "standard",
            "recurrence": "none",
            "backgroundColor": "var(--g)",
            "borderColor": "var(--g2)"
        }
        events.append(new_event)
        _save_events(events)

        ausgabe = f"✅ Termin eingetragen!\n📅 {titel}\n🕐 {datum}, {uhrzeit_von} – {uhrzeit_bis} Uhr"
        if kontaktinfos:
            ausgabe += f"\n👤 Teilnehmer/Kontakt: {kontaktinfos}"
        if beschreibung:
            ausgabe += f"\n📝 Info: {beschreibung}"
        return ausgabe
    except Exception as e:
        return f"❌ Fehler beim Eintragen: {e}"


def lokaler_kalender_termin_loeschen(titel: str, datum: str) -> str:
    """Löscht einen Termin nach Titel und Datum (nur für den Haupt-Kernel / Telegram).
    Für Kundenstornierungen: kunde_termin_stornieren() verwenden."""
    try:
        ziel_datum = datetime.strptime(datum.strip(), "%d.%m.%Y").date()
        titel_lower = titel.lower()

        events = _load_events()
        behalten = []
        geloescht = None

        js_weekday = (ziel_datum.weekday() + 1) % 7

        for ev in events:
            is_match = False
            if ev.get("recurrence", "none") != "none":
                start_recur_dt = datetime.strptime(ev.get("startRecur"), "%Y-%m-%d").date()
                if ziel_datum >= start_recur_dt:
                    if ev.get("recurrence") == "daily" or (ev.get("recurrence") == "weekly" and js_weekday in ev.get("daysOfWeek", [])):
                        is_match = True
            else:
                start_dt = _parse_iso(ev.get("start"))
                if start_dt and start_dt.date() == ziel_datum:
                    is_match = True

            if is_match and titel_lower in ev.get("title", "").lower():
                if not geloescht:
                    geloescht = ev
                    continue

            behalten.append(ev)

        if geloescht:
            _save_events(behalten)
            info = " (Ganze Serie)" if geloescht.get("recurrence") != "none" else ""
            return f"✅ Termin '{geloescht.get('title')}' am {datum} wurde erfolgreich gelöscht{info}."
        else:
            return f"❌ Keinen passenden Termin für '{titel}' am {datum} gefunden."
    except Exception as e:
        return f"❌ Fehler beim Löschen: {e}"


# ── Kundensichere Kalender-Funktionen (für Phone/WhatsApp) ────────────────────

def kunde_termine_abfragen(caller_id: str, vorname: str = "", nachname: str = "") -> str:
    """
    Gibt NUR die Termine zurück die zu dieser caller_id gehören.
    Mit vorname + nachname wird zusätzlich gegen contactInfo gefiltert
    (3-Faktor-Identifikation: Rufnummer + Vorname + Nachname müssen passen).
    Niemals Termine anderer Personen. Für Phone/WhatsApp-Kanal.
    """
    if not caller_id or not caller_id.strip():
        return "❌ Keine verifizierte Rufnummer vorhanden — Termine können nicht abgerufen werden."

    caller_id  = caller_id.strip()
    vorname_l  = vorname.strip().lower()
    nachname_l = nachname.strip().lower()
    events = _load_events()
    jetzt = datetime.now()
    eigene = []

    for ev in events:
        # Faktor 1: Rufnummer muss übereinstimmen
        ist_eigene_nummer = (
            caller_id in ev.get("caller_id", "") or
            caller_id in ev.get("contactInfo", "")
        )
        if not ist_eigene_nummer:
            continue

        # Faktor 2+3: Vorname und Nachname müssen in contactInfo erscheinen
        if vorname_l or nachname_l:
            contact_lower = ev.get("contactInfo", "").lower()
            if vorname_l and vorname_l not in contact_lower:
                continue
            if nachname_l and nachname_l not in contact_lower:
                continue

        start_dt = _parse_iso(ev.get("start"))
        if not start_dt or start_dt < jetzt:
            continue

        datum_str = start_dt.strftime("%d.%m.%Y")
        zeit_str  = start_dt.strftime("%H:%M")
        end_dt    = _parse_iso(ev.get("end"))
        bis_str   = end_dt.strftime("%H:%M") if end_dt else ""
        titel     = ev.get("title", "Termin")
        eigene.append((start_dt, f"📅 {datum_str}, {zeit_str}–{bis_str} Uhr: {titel}"))

    if not eigene:
        return "Sie haben aktuell keine bevorstehenden Termine bei uns eingetragen."

    eigene.sort(key=lambda x: x[0])
    zeilen = ["Ihre bevorstehenden Termine:"] + [e for _, e in eigene]
    return "\n".join(zeilen)


def kunde_termin_stornieren(caller_id: str, datum: str, uhrzeit_von: str,
                            vorname: str = "", nachname: str = "") -> str:
    """
    Storniert einen Termin — NUR wenn caller_id + Name übereinstimmen.
    3-Faktor-Sicherheit: Rufnummer + Vorname + Nachname müssen passen.
    Datum: TT.MM.JJJJ, uhrzeit_von: HH:MM
    Niemals Termine anderer Personen löschbar. Für Phone/WhatsApp-Kanal.
    """
    if not caller_id or not caller_id.strip():
        return "❌ Keine verifizierte Rufnummer vorhanden — Stornierung nicht möglich."

    caller_id  = caller_id.strip()
    vorname_l  = vorname.strip().lower()
    nachname_l = nachname.strip().lower()

    try:
        ziel_datum   = datetime.strptime(datum.strip(), "%d.%m.%Y").date()
        ziel_uhrzeit = uhrzeit_von.strip()
    except ValueError:
        return "❌ Ungültiges Datum oder Uhrzeit. Bitte Format TT.MM.JJJJ und HH:MM verwenden."

    events  = _load_events()
    behalten = []
    geloescht = None

    for ev in events:
        # Faktor 1: Rufnummer
        ist_eigen = (
            caller_id in ev.get("caller_id", "") or
            caller_id in ev.get("contactInfo", "")
        )
        if not ist_eigen:
            behalten.append(ev)
            continue

        # Faktor 2+3: Name
        if vorname_l or nachname_l:
            contact_lower = ev.get("contactInfo", "").lower()
            name_stimmt = True
            if vorname_l and vorname_l not in contact_lower:
                name_stimmt = False
            if nachname_l and nachname_l not in contact_lower:
                name_stimmt = False
            if not name_stimmt:
                behalten.append(ev)
                continue

        start_dt = _parse_iso(ev.get("start"))
        if start_dt and start_dt.date() == ziel_datum and start_dt.strftime("%H:%M") == ziel_uhrzeit:
            if not geloescht:
                geloescht = ev
                continue  # nicht in behalten = löschen

        behalten.append(ev)

    if geloescht:
        _save_events(behalten)
        return (f"✅ Ihr Termin '{geloescht.get('title')}' am {datum} um {uhrzeit_von} Uhr "
                f"wurde erfolgreich storniert.")
    else:
        return (f"❌ Ich konnte keinen Termin von Ihnen am {datum} um {uhrzeit_von} Uhr finden. "
                f"Bitte prüfen Sie Datum und Uhrzeit oder fragen Sie nach Ihren Terminen.")


AVAILABLE_SKILLS = [
    lokaler_kalender_lesen,
    lokaler_kalender_freie_slots_finden,
    lokaler_kalender_termin_eintragen,
    lokaler_kalender_termin_loeschen,
    kunde_termine_abfragen,
    kunde_termin_stornieren,
]
