import os
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

PROFIL_PFAD = os.path.abspath(os.path.join("data", "outlook_profil"))

def _chrome_options(profil_pfad: str, headless: bool = False) -> "Options":
    """Erstellt Chrome-Optionen für Snap-Chromium auf Linux."""
    import os as _os
    if "DISPLAY" not in _os.environ:
        _os.environ["DISPLAY"] = ":0"
    opts = Options()
    opts.binary_location = "/usr/bin/google-chrome"
    opts.add_argument(f"user-data-dir={profil_pfad}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-debugging-port=9222")
    if headless:
        opts.add_argument("--headless=new")
    return opts


def _make_driver(options: "Options") -> "webdriver.Chrome":
    """Erstellt einen Chrome-WebDriver mit dem Snap-ChromeDriver."""
    return webdriver.Chrome(
        service=Service("/usr/local/bin/chromedriver"),
        options=options,
    )


_UI_FILTER = {
    "bearbeiten", "löschen", "serie", "antworten", "allen antworten",
    "weiterleiten", "öffnen", "mehr anzeigen", "ereignis öffnen",
    "edit", "delete", "respond", "reply all", "forward", "open",
}

def _popup_bereinigen(text: str) -> str:
    zeilen = []
    for z in text.splitlines():
        s = z.strip()
        if not s or len(s) <= 2 or s.lower() in _UI_FILTER:
            continue
        zeilen.append(s)
    return "\n".join(zeilen)

def outlook_kalender_lesen() -> str:
    """
    Liest alle Termine des heutigen Tages aus dem Outlook-Kalender.
    Beispiel: outlook_kalender_lesen()
    """
    os.makedirs(PROFIL_PFAD, exist_ok=True)
    options = _chrome_options(PROFIL_PFAD, headless=True)

    driver = None
    try:
        driver = _make_driver(options)
        driver.get("https://outlook.live.com/calendar/0/view/day")
        time.sleep(12)

        # JavaScript liest ALLE aria-labels direkt aus dem DOM –
        # zuverlässiger als Seleniums find_elements, fängt alle Event-Typen
        alle_labels = driver.execute_script("""
            var result = [];
            var seen = {};
            var els = document.querySelectorAll('[aria-label]');
            for (var i = 0; i < els.length; i++) {
                var label = els[i].getAttribute('aria-label');
                if (label && label.length > 5 && !seen[label]) {
                    seen[label] = true;
                    result.push(label);
                }
            }
            return result;
        """) or []

        # Nur Labels behalten die wie Kalendertermine aussehen:
        # → enthalten eine Uhrzeit (16:00) ODER bekannte Event-Keywords
        skip_worte = ["erstellen", "create", "navigation", "suchen", "search",
                      "kalender hinzufügen", "neues ereignis", "new event",
                      "monat", "woche", "arbeitswoche", "drucken", "filter",
                      "jetzt besprechen", "einstellungen",
                      "aktuelle zeit", "current time", "kalenderansicht",
                      "leerer", "zeitslot", "wiederholtes ereignis"]

        ergebnisse = []
        for label in alle_labels:
            lower = label.lower()
            if any(w in lower for w in skip_worte):
                continue
            # Labels die direkt mit einer Uhrzeit beginnen haben keinen Termintitel
            # → UI-Elemente wie "17:30 bis 18:00, Freitag..." überspringen
            if re.match(r'^\d{1,2}:\d{2}', label.strip()):
                continue
            # Muss Uhrzeit oder bekannte Event-Keywords enthalten
            hat_uhrzeit = bool(re.search(r'\d{1,2}:\d{2}', label))
            hat_keyword = any(w in lower for w in ["ereignis", "event", "aufgabe", "task"])
            if not (hat_uhrzeit or hat_keyword):
                continue
            sauber = _popup_bereinigen(label)
            if sauber and sauber not in ergebnisse:
                ergebnisse.append(sauber)

        driver.quit()

        if not ergebnisse:
            return "Keine Termine für heute im Outlook-Kalender gefunden."

        return "DEINE TERMINE FÜR HEUTE:\n" + "\n---\n".join(ergebnisse)

    except Exception as e:
        if driver: driver.quit()
        return f"❌ Fehler: {e}"

def _labels_fuer_datum(datum_url: str) -> list[str]:
    """Interne Hilfsfunktion: Gibt bereinigte Event-Labels für ein Datum zurück."""
    os.makedirs(PROFIL_PFAD, exist_ok=True)
    options = _chrome_options(PROFIL_PFAD, headless=True)
    driver = None
    try:
        driver = _make_driver(options)
        driver.get(f"https://outlook.live.com/calendar/0/view/day/{datum_url}")
        time.sleep(12)
        alle_labels = driver.execute_script("""
            var result = []; var seen = {};
            var els = document.querySelectorAll('[aria-label]');
            for (var i = 0; i < els.length; i++) {
                var label = els[i].getAttribute('aria-label');
                if (label && label.length > 5 && !seen[label]) { seen[label] = true; result.push(label); }
            }
            return result;
        """) or []
        driver.quit()
        return alle_labels
    except Exception:
        if driver:
            try: driver.quit()
            except Exception: pass
        return []

def _parse_belegte_zeiten(labels: list[str]) -> list[tuple]:
    """Extrahiert belegte (von, bis) Zeitpaare aus den aria-labels."""
    skip_worte = ["erstellen", "create", "navigation", "suchen", "kalender hinzufügen",
                  "neues ereignis", "monat", "woche", "arbeitswoche", "drucken", "filter",
                  "jetzt besprechen", "einstellungen", "aktuelle zeit", "current time",
                  "kalenderansicht", "leerer", "zeitslot", "wiederholtes ereignis"]
    belegte = []
    for label in labels:
        lower = label.lower()
        if any(w in lower for w in skip_worte): continue
        if re.match(r'^\d{1,2}:\d{2}', label.strip()): continue
        zeiten = re.findall(r'(\d{1,2}:\d{2})', label)
        if len(zeiten) >= 2:
            try:
                von = datetime.strptime(zeiten[0], "%H:%M")
                bis = datetime.strptime(zeiten[1], "%H:%M")
                if bis > von:
                    belegte.append((von, bis))
            except Exception:
                pass
    return sorted(belegte)


def outlook_freie_slots_finden(datum: str = "", dauer_minuten: int = 60,
                                arbeit_von: int = 8, arbeit_bis: int = 18) -> str:
    """
    Findet freie Zeitfenster im Outlook-Kalender für einen Tag.
    datum: TT.MM.JJJJ (Standard: heute)
    dauer_minuten: Mindestlänge des freien Slots (Standard: 60)
    arbeit_von/bis: Arbeitszeitrahmen in Stunden (Standard: 8–18 Uhr)
    Beispiel: outlook_freie_slots_finden()
    Beispiel: outlook_freie_slots_finden(datum="18.04.2026", dauer_minuten=30)
    """
    from datetime import datetime, timedelta
    try:
        if datum:
            url_datum = datetime.strptime(datum.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
            anzeige = datum
        else:
            url_datum = datetime.today().strftime("%Y-%m-%d")
            anzeige = datetime.today().strftime("%d.%m.%Y")

        labels = _labels_fuer_datum(url_datum)
        belegte = _parse_belegte_zeiten(labels)

        # Arbeitszeit-Rahmen
        tag = datetime.today().date()
        start = datetime.strptime(f"{arbeit_von}:00", "%H:%M")
        ende  = datetime.strptime(f"{arbeit_bis}:00", "%H:%M")
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

        if not freie_slots:
            return f"Keine freien Slots am {anzeige} (Mindestdauer: {dauer_minuten} Min.)."

        zeilen = [f"FREIE ZEITFENSTER AM {anzeige} (mind. {dauer_minuten} Min.):\n"]
        for i, (von, bis) in enumerate(freie_slots, 1):
            zeilen.append(f"{i}. {von.strftime('%H:%M')} – {bis.strftime('%H:%M')} "
                          f"({int((bis-von).total_seconds()//60)} Min. frei)")
        return "\n".join(zeilen)

    except Exception as e:
        return f"❌ Fehler: {e}"


def outlook_termin_eintragen(titel: str, datum: str, uhrzeit_von: str, uhrzeit_bis: str, kontaktinfos: str = "", beschreibung: str = "") -> str:
    """
    Trägt einen neuen Termin in den Outlook-Kalender ein.
    datum: TT.MM.JJJJ
    uhrzeit_von / uhrzeit_bis: HH:MM
    Beispiel: outlook_termin_eintragen(titel="Meeting mit Anna", datum="18.04.2026", uhrzeit_von="10:00", uhrzeit_bis="11:00")
    """
    from datetime import datetime
    try:
        dt = datetime.strptime(datum.strip(), "%d.%m.%Y")
        start_iso = f"{dt.strftime('%Y-%m-%d')}T{uhrzeit_von}:00"
        ende_iso  = f"{dt.strftime('%Y-%m-%d')}T{uhrzeit_bis}:00"
    except Exception as e:
        return f"❌ Ungültiges Datum/Uhrzeit-Format: {e}"

    import urllib.parse
    compose_url = (
        "https://outlook.live.com/calendar/0/deeplink/compose?"
        f"startdt={urllib.parse.quote(start_iso)}"
        f"&enddt={urllib.parse.quote(ende_iso)}"
        f"&subject={urllib.parse.quote(titel)}"
    )

    os.makedirs(PROFIL_PFAD, exist_ok=True)
    options = _chrome_options(PROFIL_PFAD, headless=True)
    driver = None
    try:
        driver = _make_driver(options)
        driver.get(compose_url)
        time.sleep(12)

        # Speichern-Button suchen – viele Varianten da Outlook UI sich ändert
        SPEICHERN_SELEKTOREN = [
            (By.XPATH,  "//button[@aria-label='Speichern']"),
            (By.XPATH,  "//button[@aria-label='Save']"),
            (By.XPATH,  "//button[contains(@aria-label,'speichern') or contains(@aria-label,'Speichern')]"),
            (By.XPATH,  "//button[contains(@aria-label,'Senden') or contains(@aria-label,'Send')]"),
            (By.XPATH,  "//button[contains(text(),'Speichern') or contains(text(),'Save')]"),
            (By.XPATH,  "//div[@role='button'][contains(@aria-label,'Speichern') or contains(@aria-label,'Save')]"),
            (By.XPATH,  "//button[@data-testid='compose-save-button']"),
            (By.XPATH,  "//button[@type='submit']"),
            # Neue Outlook-Toolbar: erster primärer Button im Compose-Bereich
            (By.XPATH,  "(//div[@role='toolbar']//button)[1]"),
            (By.CSS_SELECTOR, "button[aria-label*='ave'], button[aria-label*='peichern']"),
        ]
        speichern = None
        from selenium.webdriver.support.ui import WebDriverWait as _WDW
        from selenium.webdriver.support import expected_conditions as _EC
        for by, sel in SPEICHERN_SELEKTOREN:
            try:
                speichern = _WDW(driver, 4).until(_EC.element_to_be_clickable((by, sel)))
                if speichern:
                    break
            except Exception:
                continue

        if not speichern:
            # Letzter Versuch: JavaScript sucht alle Buttons und klickt den ersten sichtbaren
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var label = (b.getAttribute('aria-label') || b.textContent || '').toLowerCase();
                        if (label.includes('save') || label.includes('speichern') || label.includes('send')) {
                            b.click(); return true;
                        }
                    }
                    return false;
                """)
                time.sleep(4)
                driver.quit()
                return (f"✅ Termin eingetragen (JS-Fallback)!\n"
                        f"📅 {titel}\n🕐 {datum}, {uhrzeit_von} – {uhrzeit_bis} Uhr")
            except Exception:
                pass
            driver.quit()
            return "❌ Speichern-Button nicht gefunden. Ist der Login noch aktiv?"

        driver.execute_script("arguments[0].click();", speichern)
        time.sleep(4)
        driver.quit()

        return (f"✅ Termin eingetragen!\n"
                f"📅 {titel}\n"
                f"🕐 {datum}, {uhrzeit_von} – {uhrzeit_bis} Uhr")

    except Exception as e:
        if driver:
            try: driver.quit()
            except Exception: pass
        return f"❌ Fehler beim Eintragen: {e}"


def outlook_termin_loeschen(titel: str, datum: str) -> str:
    """
    Löscht einen Termin aus dem Outlook-Kalender.
    datum: TT.MM.JJJJ
    titel: Titel des Termins (Teilübereinstimmung reicht)
    Beispiel: outlook_termin_loeschen(titel="Besprechung Camino", datum="20.04.2026")
    """
    from datetime import datetime
    try:
        dt = datetime.strptime(datum.strip(), "%d.%m.%Y")
        url_datum = dt.strftime("%Y-%m-%d")
    except Exception as e:
        return f"❌ Ungültiges Datum: {e}"

    os.makedirs(PROFIL_PFAD, exist_ok=True)
    options = _chrome_options(PROFIL_PFAD, headless=True)
    driver = None
    try:
        driver = _make_driver(options)
        driver.get(f"https://outlook.live.com/calendar/0/view/day/{url_datum}")
        time.sleep(12)

        titel_lower = titel.lower()

        # Event per JS suchen und klicken
        geklickt = driver.execute_script(f"""
            var els = document.querySelectorAll('[aria-label]');
            for (var i = 0; i < els.length; i++) {{
                var label = (els[i].getAttribute('aria-label') || '').toLowerCase();
                if (label.includes(arguments[0])) {{
                    els[i].click();
                    return els[i].getAttribute('aria-label');
                }}
            }}
            return null;
        """, titel_lower)

        if not geklickt:
            driver.quit()
            return f"❌ Termin '{titel}' am {datum} nicht gefunden."

        time.sleep(2)

        from selenium.webdriver.common.action_chains import ActionChains as _AC
        from selenium.webdriver.support.ui import WebDriverWait as _WDW2
        from selenium.webdriver.support import expected_conditions as _EC2

        # Löschen-Button im Popover finden – echter Mausklick via ActionChains
        # JS-click() triggert in React-Apps oft nicht alle Event-Handler → Server-Request bleibt aus
        LOESCHEN_SELEKTOREN = [
            (By.XPATH, "//button[@aria-label='Löschen']"),
            (By.XPATH, "//button[@aria-label='Delete']"),
            (By.XPATH, "//button[contains(@aria-label,'öschen')]"),
            (By.XPATH, "//button[contains(@aria-label,'elete')]"),
            (By.XPATH, "//div[@role='button'][contains(@aria-label,'öschen')]"),
        ]
        geloescht = False
        for by, sel in LOESCHEN_SELEKTOREN:
            try:
                btn = _WDW2(driver, 5).until(_EC2.element_to_be_clickable((by, sel)))
                # Echter Mausklick statt JS-click – triggert React Event-Handler korrekt
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                _AC(driver).move_to_element(btn).click().perform()
                geloescht = True
                break
            except Exception:
                continue

        if not geloescht:
            # Fallback: Selenium nativer click() nach scroll
            for by, sel in LOESCHEN_SELEKTOREN:
                try:
                    btn = driver.find_element(by, sel)
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(0.3)
                    btn.click()
                    geloescht = True
                    break
                except Exception:
                    continue

        time.sleep(3)  # Warten ob ein Bestätigungs-Dialog erscheint

        # ── Bestätigungs-Dialog abfangen – NUR wenn wirklich ein Dialog sichtbar ist ──
        # WICHTIG: Erst prüfen ob überhaupt ein Dialog da ist.
        # Bei einfachen Terminen löscht Outlook sofort (Toast "Ereignis gelöscht" + "Rückgängig").
        # Das "Rückgängig"-Button hat evtl. aria-label mit "löschen" → darf NICHT geklickt werden!
        from selenium.webdriver.support.ui import WebDriverWait as _W
        from selenium.webdriver.support import expected_conditions as _EC

        dialog_vorhanden = driver.execute_script("""
            return !!(document.querySelector('[role="dialog"]') ||
                      document.querySelector('[role="alertdialog"]'));
        """)

        bestaetigt = not dialog_vorhanden  # Kein Dialog = keine Bestätigung nötig, Löschung direkt

        if dialog_vorhanden:
            # Nur wenn Dialog sichtbar: Bestätigungs-Button suchen
            # contains(., ...) matched auch Kind-Elemente wie <span>Löschen</span>
            BESTAETIGUNG_SELEKTOREN = [
                (By.XPATH, "//div[@role='dialog']//button[contains(.,'Löschen') or contains(.,'Delete')]"),
                (By.XPATH, "//div[@role='alertdialog']//button[contains(.,'Löschen') or contains(.,'Delete')]"),
                (By.XPATH, "//button[@data-testid='confirm-delete']"),
                # Wiederkehrende Termine: "Dieses Ereignis" Option
                (By.XPATH, "//div[@role='dialog']//button[contains(.,'Dieses Ereignis')]"),
            ]
            for by, sel in BESTAETIGUNG_SELEKTOREN:
                try:
                    bestaetigen = _W(driver, 4).until(_EC.element_to_be_clickable((by, sel)))
                    driver.execute_script("arguments[0].click();", bestaetigen)
                    bestaetigt = True
                    break
                except Exception:
                    continue

            if not bestaetigt:
                # JS-Fallback NUR innerhalb des Dialog-Containers
                bestaetigt = driver.execute_script("""
                    var dialog = document.querySelector('[role="dialog"], [role="alertdialog"]');
                    if (!dialog) return false;
                    var btns = dialog.querySelectorAll('button, [role="button"]');
                    for (var b of btns) {
                        var txt = (b.textContent || '').trim().toLowerCase();
                        // Nur exakter Text "löschen"/"delete" oder "dieses ereignis"
                        if (txt === 'löschen' || txt === 'delete' || txt === 'dieses ereignis') {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                """)

        # 10 Sekunden auf der GLEICHEN Seite warten bis der "Rückgängig"-Toast
        # von selbst verschwindet. Navigation weg während Toast aktiv ist könnte
        # Undo auslösen. Erst nach Toast-Ablauf ist die Löschung server-seitig committed.
        time.sleep(10)

        driver.quit()

        if geloescht and bestaetigt:
            return f"✅ Termin '{titel}' am {datum} gelöscht."
        elif geloescht and not bestaetigt:
            return f"⚠️ Termin geklickt und Löschen ausgelöst, aber Dialog-Bestätigung fehlgeschlagen."
        return f"❌ Löschen-Button nicht gefunden für '{titel}' am {datum}."

    except Exception as e:
        if driver:
            try: driver.quit()
            except Exception: pass
        return f"❌ Fehler beim Löschen: {e}"


def outlook_login_einrichten() -> str:
    """
    Einmalige Einrichtung: Öffnet Outlook zum Einloggen.
    Beispiel: outlook_login_einrichten()
    """
    os.makedirs(PROFIL_PFAD, exist_ok=True)
    options = _chrome_options(PROFIL_PFAD, headless=False)
    options.add_experimental_option("detach", True)
    driver = _make_driver(options)
    driver.get("https://outlook.live.com/calendar/")
    return "Browser offen für Login."

AVAILABLE_SKILLS = [
    outlook_login_einrichten,
    outlook_kalender_lesen,
    outlook_freie_slots_finden,
    outlook_termin_loeschen,
    outlook_termin_eintragen,
]
