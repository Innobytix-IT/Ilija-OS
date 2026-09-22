"""
fristen_routes.py – Fristen & Vorlagen Modul
Verwaltet Frist-Vorlagen, Empfänger, Brief-Generierung und Kontaktdaten-Suche.
"""

import os
import json
import uuid
import re
import base64
import tempfile
import shutil
import threading
from datetime import datetime
from flask import request, jsonify, render_template
from werkzeug.utils import secure_filename

_BASE      = os.path.dirname(os.path.abspath(__file__))
_DATA      = os.path.join(_BASE, "data", "fristen")
_INDEX     = os.path.join(_DATA, "vorlagen.json")
_FILES     = os.path.join(_DATA, "dateien")
_ABSENDER          = os.path.join(_DATA, "absender.json")
_EMAIL_CONFIG      = os.path.join(_BASE, "data", "email", "email_config.json")
_NOTIF_LOG         = os.path.join(_DATA, "notif_log.json")
_TG_CONFIG         = os.path.join(_BASE, "data", "telegram", "telegram_config.json")
_PENDING_STICHTAG  = os.path.join(_DATA, "pending_stichtag.json")
_UNTERSCHRIFT_BASE = os.path.join(_DATA, "unterschrift")
_UNTERSCHRIFT_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]

os.makedirs(_FILES, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(_INDEX):
        return []
    try:
        with open(_INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(data: list):
    os.makedirs(_DATA, exist_ok=True)
    with open(_INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find(vorlagen: list, vid: str):
    return next((v for v in vorlagen if v["id"] == vid), None)


def _load_absender() -> dict:
    if not os.path.exists(_ABSENDER):
        return {"name": "", "adresse": "", "email": ""}
    try:
        with open(_ABSENDER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"name": "", "adresse": "", "email": ""}


def _save_absender(data: dict):
    os.makedirs(_DATA, exist_ok=True)
    with open(_ABSENDER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tage_bis(datum_str: str) -> int:
    try:
        d = datetime.strptime(datum_str, "%Y-%m-%d").date()
        return (d - datetime.today().date()).days
    except Exception:
        return 9999


def _find_unterschrift() -> str | None:
    """Gibt den Pfad zur hinterlegten Unterschrift zurück, oder None."""
    for ext in _UNTERSCHRIFT_EXTS:
        p = _UNTERSCHRIFT_BASE + ext
        if os.path.exists(p):
            return p
    return None


def _delete_unterschrift():
    """Löscht alle hinterlegten Unterschrift-Dateien."""
    for ext in _UNTERSCHRIFT_EXTS:
        p = _UNTERSCHRIFT_BASE + ext
        if os.path.exists(p):
            os.remove(p)


_EMAIL_DEFAULTS = {"smtp_server": "", "smtp_port": 587, "smtp_user": "",
                   "smtp_password": "", "use_ssl": False, "notif_email": ""}

def _load_email_config() -> dict:
    if not os.path.exists(_EMAIL_CONFIG):
        return dict(_EMAIL_DEFAULTS)
    try:
        with open(_EMAIL_CONFIG, encoding="utf-8") as f:
            return {**_EMAIL_DEFAULTS, **json.load(f)}
    except Exception:
        return dict(_EMAIL_DEFAULTS)

def _save_email_config(data: dict):
    os.makedirs(_DATA, exist_ok=True)
    with open(_EMAIL_CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Benachrichtigungs-Hilfsfunktionen ─────────────────────────────────────────

def _load_notif_log() -> dict:
    if not os.path.exists(_NOTIF_LOG):
        return {}
    try:
        with open(_NOTIF_LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_notif_log(log: dict):
    os.makedirs(_DATA, exist_ok=True)
    with open(_NOTIF_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def _notif_bereits_gesendet(log: dict, vid: str, kanal: str, heute: str) -> bool:
    return log.get(f"{vid}__{kanal}__{heute}", False)

def _notif_markieren(log: dict, vid: str, kanal: str, heute: str):
    log[f"{vid}__{kanal}__{heute}"] = True
    # Log-Einträge älter als 90 Tage bereinigen
    try:
        cutoff = (datetime.today().date().toordinal() - 90)
        log = {k: v for k, v in log.items()
               if datetime.strptime(k.split("__")[-1], "%Y-%m-%d").date().toordinal() >= cutoff}
    except Exception:
        pass
    return log


def _telegram_senden(text: str) -> bool:
    """Sendet Text an den konfigurierten Telegram-Chat. Gibt True bei Erfolg zurück."""
    try:
        import requests as _req
        if not os.path.exists(_TG_CONFIG):
            return False
        with open(_TG_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        token = cfg.get("token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()
        if not token or not chat_id:
            return False
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.ok
    except Exception as e:
        print(f"[FristenNotif] Telegram-Fehler: {e}")
        return False


def _telegram_datei_senden(pfad: str, caption: str = "") -> bool:
    """Sendet eine Datei (PDF) via Telegram sendDocument."""
    try:
        import requests as _req
        if not os.path.exists(_TG_CONFIG):
            return False
        with open(_TG_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        token   = cfg.get("token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()
        if not token or not chat_id:
            return False
        with open(pfad, "rb") as df:
            r = _req.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"document": (os.path.basename(pfad), df, "application/pdf")},
                timeout=30,
            )
        return r.ok
    except Exception as e:
        print(f"[FristenNotif] Telegram-Datei-Fehler: {e}")
        return False


def _ilija_basis_url() -> str:
    return os.getenv("ILIJA_BASE_URL", "http://localhost:5001")


def _load_pending_stichtag() -> list:
    if not os.path.exists(_PENDING_STICHTAG):
        return []
    try:
        with open(_PENDING_STICHTAG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_pending_stichtag(pending: list):
    os.makedirs(_DATA, exist_ok=True)
    with open(_PENDING_STICHTAG, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def _stichtag_notify_review(v: dict, out_path: str):
    """Benachrichtigt den User: Stichtag erreicht, Dokument bereit zur Prüfung (ki_pruefen-Modus)."""
    absender = _load_absender()
    vorname  = (absender.get("name", "") or "").split()[0] or "Hallo"
    name     = v.get("name", "Formular")
    vid      = v["id"]
    base_url = _ilija_basis_url()
    link     = f"{base_url}/fristen/formular-ausfuellen/{vid}"

    # Pending-Stichtag speichern (für Chat-Anzeige & Telegram-Bestätigung)
    pending = _load_pending_stichtag()
    pending = [p for p in pending if p.get("vid") != vid]
    pending.append({
        "vid": vid, "name": name, "link": link,
        "out_datei": os.path.basename(out_path),
        "vorbereitet": datetime.now().isoformat(),
        "typ": "review"
    })
    _save_pending_stichtag(pending)

    # E-Mail an Absender
    empf_email = absender.get("email", "").strip()
    betreff = f"Ilija: Dokument bereit zur Pruefung - {name}"
    body = (
        f"Hallo {vorname},\n\n"
        f"der Stichtag zum Versenden des Dokuments '{name}' wurde erreicht.\n"
        f"Wie von dir gewuenscht habe ich alles vorbereitet.\n\n"
        f"Du kannst es jetzt ueber diesen Link pruefen und gegebenenfalls Aenderungen vornehmen:\n"
        f"{link}\n\n"
        f"Wenn alles passt, klicke auf 'Speichern & Senden', um das Dokument abzusenden.\n\n"
        f"Viele Gruesse,\nIlija"
    )
    if empf_email:
        import smtplib, ssl as _ssl2
        from email.mime.multipart import MIMEMultipart as _MM
        from email.mime.text      import MIMEText as _MT
        try:
            cfg = _load_email_config()
            if cfg.get("smtp_server") and cfg.get("smtp_user") and cfg.get("smtp_password"):
                msg = _MM("alternative")
                msg["From"]    = cfg["smtp_user"]
                msg["To"]      = empf_email
                msg["Subject"] = betreff
                msg.attach(_MT(body, "plain", "utf-8"))
                ctx = _ssl2.create_default_context()
                if cfg.get("use_ssl"):
                    with smtplib.SMTP_SSL(cfg["smtp_server"], int(cfg["smtp_port"]), context=ctx) as srv:
                        srv.login(cfg["smtp_user"], cfg["smtp_password"])
                        srv.sendmail(cfg["smtp_user"], [empf_email], msg.as_bytes())
                else:
                    with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as srv:
                        srv.ehlo(); srv.starttls(context=ctx)
                        srv.login(cfg["smtp_user"], cfg["smtp_password"])
                        srv.sendmail(cfg["smtp_user"], [empf_email], msg.as_bytes())
        except Exception as e:
            print(f"[AutoLauf] Review-E-Mail-Fehler: {e}")
    else:
        _email_notif_senden(betreff, body)

    # Telegram: PDF-Anhang + Text
    tg_caption = (
        f"<b>Ilija · Stichtag erreicht 📋</b>\n\n"
        f"Hallo {vorname},\n\n"
        f"Das Dokument <b>{name}</b> wurde von mir vorbereitet.\n"
        f"Bitte prüfe es und gib mir Bescheid:\n\n"
        f"✅ Schreib <b>Dokument versenden</b> – ich versende es sofort.\n"
        f"📝 Oder passe es online an: {link}"
    )
    if os.path.exists(out_path):
        _telegram_datei_senden(out_path, caption=tg_caption)
    else:
        _telegram_senden(tg_caption)


def _stichtag_notify_bestaetigung(v: dict):
    """Benachrichtigt den User: Dokument wurde autonom ausgefüllt und versendet."""
    absender   = _load_absender()
    vorname    = (absender.get("name", "") or "").split()[0] or "Hallo"
    name       = v.get("name", "Formular")
    empfaenger = v.get("zeitplan", {}).get("empfaenger", "—")

    body = (
        f"Hallo {vorname},\n\n"
        f"Das Dokument '{name}' wurde automatisch ausgefuellt und erfolgreich "
        f"an {empfaenger} versendet.\n\n"
        f"Du musst nichts weiter unternehmen.\n\nViele Gruesse,\nIlija"
    )
    _email_notif_senden(f"Ilija: Dokument versendet - {name}", body)
    _telegram_senden(
        f"<b>Ilija · Dokument versendet ✅</b>\n\n"
        f"Hallo {vorname},\n\n"
        f"📄 <b>{name}</b> wurde automatisch ausgefüllt und an "
        f"<b>{empfaenger}</b> versendet.\n\n"
        f"Du musst nichts weiter unternehmen."
    )


def _email_notif_senden(subject: str, body: str) -> bool:
    """Sendet eine Benachrichtigungs-E-Mail an die konfigurierte Adresse."""
    import smtplib, ssl as _ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText
    try:
        cfg = _load_email_config()
        if not cfg.get("smtp_server") or not cfg.get("smtp_user") or not cfg.get("smtp_password"):
            return False
        empfaenger = cfg.get("notif_email", "").strip() or cfg["smtp_user"]
        msg = MIMEMultipart("alternative")
        msg["From"]    = cfg["smtp_user"]
        msg["To"]      = empfaenger
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        ctx = _ssl.create_default_context()
        if cfg.get("use_ssl"):
            with smtplib.SMTP_SSL(cfg["smtp_server"], int(cfg["smtp_port"]), context=ctx) as srv:
                srv.login(cfg["smtp_user"], cfg["smtp_password"])
                srv.sendmail(cfg["smtp_user"], [empfaenger], msg.as_bytes())
        else:
            with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as srv:
                srv.ehlo(); srv.starttls(context=ctx)
                srv.login(cfg["smtp_user"], cfg["smtp_password"])
                srv.sendmail(cfg["smtp_user"], [empfaenger], msg.as_bytes())
        return True
    except Exception as e:
        print(f"[FristenNotif] E-Mail-Fehler: {e}")
        return False


def _sende_fristen_benachrichtigungen() -> dict:
    """Prüft alle Vorlagen und sendet fällige Benachrichtigungen. Gibt Zusammenfassung zurück."""
    heute   = datetime.today().date()
    heute_s = heute.isoformat()
    vorlagen = _load()
    log      = _load_notif_log()
    gesendet = []
    fehler   = []

    for v in vorlagen:
        try:
            fd   = datetime.strptime(v["frist_datum"], "%Y-%m-%d").date()
            tage = (fd - heute).days
        except Exception:
            continue

        # Fällige Erinnerungsstufen für diese Vorlage berechnen
        erinn_wochen = v.get("erinnerung_wochen", [4, 2, 1])
        trigger_tage = set()
        for w in erinn_wochen:
            t = round(float(w) * 7)
            trigger_tage.add(t)
        # Immer am Fristtag selbst und bei Überfälligkeit (Tag 0 und -1)
        trigger_tage.update({0, -1})

        if tage not in trigger_tage:
            continue

        # Benachrichtigungstext aufbauen
        if tage < 0:
            dring = f"⚠️ ÜBERFÄLLIG (seit {abs(tage)} Tag{'en' if abs(tage)!=1 else ''})"
        elif tage == 0:
            dring = "🚨 HEUTE fällig"
        elif tage <= 3:
            dring = f"⚡ {tage} Tag{'e' if tage!=1 else ''} verbleibend"
        elif tage <= 7:
            dring = f"⏰ {tage} Tage verbleibend"
        else:
            wochen = tage // 7
            dring  = f"📋 {wochen} Woche{'n' if wochen!=1 else ''} verbleibend"

        name     = v.get("name", "Unbekannt")
        datum_de = _fmt_datum(v["frist_datum"])
        kanäle   = v.get("benachrichtigung", ["chat"])

        for kanal in kanäle:
            if kanal == "chat":
                continue  # Chat-Benachrichtigung läuft client-seitig
            if _notif_bereits_gesendet(log, v["id"], kanal, heute_s):
                continue

            ok = False
            if kanal == "telegram":
                text = (
                    f"<b>Ilija · Fristen-Erinnerung</b>\n\n"
                    f"{dring}\n"
                    f"📄 <b>{name}</b>\n"
                    f"📅 Frist: {datum_de}"
                )
                ok = _telegram_senden(text)

            elif kanal == "email":
                betreff = f"Ilija Frist-Erinnerung: {name} — {datum_de}"
                inhalt  = (
                    f"Ilija · Fristen-Erinnerung\n"
                    f"{'─'*40}\n\n"
                    f"{dring}\n\n"
                    f"Vorlage:  {name}\n"
                    f"Frist:    {datum_de}\n"
                )
                if v.get("beschreibung"):
                    inhalt += f"Hinweis:  {v['beschreibung']}\n"
                inhalt += f"\n→ Jetzt öffnen: http://localhost:5001/fristen\n"
                ok = _email_notif_senden(betreff, inhalt)

            if ok:
                log = _notif_markieren(log, v["id"], kanal, heute_s)
                gesendet.append({"vid": v["id"], "name": name, "kanal": kanal})
            else:
                fehler.append({"vid": v["id"], "name": name, "kanal": kanal})

    _save_notif_log(log)
    return {"gesendet": gesendet, "fehler": fehler}


# ── Autonome KI-Ausführung (Variante 2 + 3) ──────────────────────────────────

def _ki_alle_felder_befuellen(v: dict, felder_alle: list) -> tuple:
    """KI befüllt alle Felder in einem einzigen Call.
    Gibt (True, vorschlaege_dict) oder (False, fehlermeldung) zurück."""
    from providers import select_provider
    absender   = _load_absender()
    feld_namen = {f["name"] for f in felder_alle}
    feld_liste = "\n".join(
        "- " + f["name"] + ' ("' + f.get("label", f["name"]) + '", ' + f.get("type", "Text") + ")"
        + (" [Optionen: " + ", ".join(f["choices"][:6]) + "]" if f.get("choices") else "")
        for f in felder_alle
    )
    kontext      = v.get("ki_kontext", "").strip()
    adresse_einz = absender.get("adresse", "").replace("\n", ", ").strip()
    kontext_block  = f"\nZusatzinfos:\n{kontext}\n" if kontext else ""
    referenz_block = (
        f"\nReferenzdokument \"{v.get('referenz_name', '')}\" (Auszug):\n"
        + v["referenz_text"][:3000] + "\n"
    ) if v.get("referenz_text") else ""
    prompt = (
        "Du befüllst ein deutsches PDF-Formular. Antworte NUR mit einem JSON-Objekt "
        "(kein Markdown, keine Erklärungen, nur roher JSON-Text).\n\n"
        "=== PFLICHTREGELN ===\n"
        "1. JEDES Feld im JSON zurückgeben — auch wenn der Wert leer ist.\n"
        "2. CheckBox: IMMER 'true' oder 'false' — nie leer lassen.\n"
        "3. RadioButton: IMMER genau einen der [Optionen]-Werte wählen — nie leer lassen.\n"
        "4. Gekoppelte Felder: Wenn ein 'numf'-Betrag eingetragen wird, "
        "MUSS die gleichnamige 'chbx'-Checkbox (selbes Suffix) auf 'true' gesetzt werden.\n"
        "   Beispiel: numfBedarfGrundmiete='620' → chbxBedarfGrundmiete='true'\n"
        "5. Felder die du nicht kennst: '' (leerer String), aber CheckBox/Radio trotzdem befüllen.\n"
        "6. Zeilen-Felder mit Z1/Z2/Z3 im Namen: Z1 = erste Person der BG, "
        "Z2 = zweite Person der BG, Z3 = dritte Person usw.\n\n"
        "=== NUTZERDATEN ===\n"
        f"- Name: {absender.get('name', '')}\n"
        f"- Adresse: {adresse_einz}\n"
        f"- E-Mail: {absender.get('email', '')}\n"
        f"- Formulartitel: {v.get('name', '')}\n"
        f"{kontext_block}"
        f"{referenz_block}\n"
        "=== FELDER (Feldname, Bezeichnung, Typ, [Optionen]) ===\n"
        f"{feld_liste}\n\n"
        'Antworte nur mit: {"Feldname": "Wert", ...}'
    )
    try:
        _, _prov = select_provider()
        raw = _prov.chat(
            messages=[{"role": "user", "content": prompt}],
            system="Du bist ein Formular-Ausfüllassistent. Antworte IMMER und NUR mit reinem JSON — kein Text davor oder danach."
        )
    except Exception as e:
        return False, f"KI-Provider Fehler: {e}"
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        return False, "KI-Antwort nicht parsbar"
    try:
        vorschlaege = json.loads(match.group())
    except Exception:
        return False, "JSON-Fehler in KI-Antwort"
    for name, val in list(vorschlaege.items()):
        if name.lower().startswith("numf") and val:
            chbx = "chbx" + name[4:]
            if chbx in feld_namen and vorschlaege.get(chbx, "false") != "true":
                vorschlaege[chbx] = "true"
    return True, vorschlaege


def _felder_aus_pdf(datei_pfad: str) -> list:
    """Liest alle AcroForm-Felder aus einem PDF (für den autonomen Lauf)."""
    try:
        import fitz
        doc = fitz.open(datei_pfad)
        felder, seen_radio = [], {}
        for page_num, page in enumerate(doc):
            for widget in page.widgets():
                ft   = widget.field_type_string
                name = widget.field_name
                if not name:
                    continue
                choices = list(widget.choice_values or [])
                val_str = str(widget.field_value or "")
                if val_str == "Off":
                    val_str = ""
                w_rect = [widget.rect.x0, widget.rect.y0,
                          widget.rect.x1, widget.rect.y1]
                if ft == "RadioButton":
                    if name in seen_radio:
                        ex = felder[seen_radio[name]]
                        for c in choices:
                            if c not in ex["choices"]:
                                ex["choices"].append(c)
                        ex["choice_rects"].append(w_rect)
                        if val_str and val_str != "Off":
                            ex["value"] = val_str
                        continue
                    seen_radio[name] = len(felder)
                entry = {
                    "name": name, "label": widget.field_label or name,
                    "type": ft, "value": val_str, "choices": choices,
                    "page": page_num, "rect": w_rect
                }
                if ft == "RadioButton":
                    entry["choice_rects"] = [w_rect]
                felder.append(entry)
        doc.close()
        return felder
    except Exception:
        return []


def _pdf_ausfuellen(src_path: str, out_path: str, werte: dict) -> bool:
    """Füllt ein PDF-Formular mit den gegebenen Werten und speichert es."""
    tmp_path = None
    try:
        import fitz
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False,
                                         dir=os.path.dirname(out_path)) as tmp:
            tmp_path = tmp.name
        doc = fitz.open(src_path)
        for page in doc:
            for widget in page.widgets():
                name = widget.field_name
                if name not in werte:
                    continue
                val = werte[name]
                if widget.field_type_string == "CheckBox":
                    is_on = str(val).lower() in ("true", "1", "yes", "ja", "an")
                    widget.field_value = widget.on_state() if is_on else "Off"
                else:
                    widget.field_value = str(val)
                widget.update()
        doc.save(tmp_path, incremental=False)
        doc.close()
        shutil.move(tmp_path, out_path)
        return True
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _berechne_naechste_ausfuehrung(zeitplan: dict) -> str:
    """Berechnet das nächste Ausführungsdatum aus dem Zeitplan-Objekt."""
    from datetime import date, timedelta
    import calendar
    today     = date.today()
    intervall = zeitplan.get("intervall", "monatlich")
    tag       = max(1, min(28, int(zeitplan.get("stichtag_tag", today.day))))
    monat     = max(1, min(12, int(zeitplan.get("stichtag_monat", today.month))))
    if intervall == "taeglich":
        return (today + timedelta(days=1)).isoformat()
    if intervall == "woechentlich":
        return (today + timedelta(weeks=1)).isoformat()
    if intervall == "monatlich":
        nm = today.month % 12 + 1
        ny = today.year + (1 if today.month == 12 else 0)
        return date(ny, nm, min(tag, calendar.monthrange(ny, nm)[1])).isoformat()
    if intervall == "jaehrlich":
        ny = today.year + 1
        return date(ny, monat, min(tag, calendar.monthrange(ny, monat)[1])).isoformat()
    return (today + timedelta(days=30)).isoformat()


def _update_zeitplan_status(vorlagen: list, v: dict, status: str, fehler):
    from datetime import date
    zp = v.setdefault("zeitplan", {})
    zp["letzter_lauf"]   = date.today().isoformat()
    zp["letzter_status"] = status
    zp["letzter_fehler"] = fehler
    _save(vorlagen)


def _autonomer_lauf(vid: str):
    """Stichtag-Ablauf für eine Vorlage. Verhält sich je nach ki_modus:
    ki_pruefen → KI bereitet PDF vor, benachrichtigt User zur Prüfung.
    autonom    → KI befüllt + signiert + sendet an Empfänger + bestätigt User."""
    import smtplib, ssl as _ssl, mimetypes
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText
    from email.mime.base      import MIMEBase
    from email                import encoders as _enc
    print(f"[AutoLauf] Starte für Vorlage {vid}")
    vorlagen = _load()
    v = _find(vorlagen, vid)
    if not v:
        return
    ki_modus = v.get("ki_modus", "autonom")
    zeitplan = v.get("zeitplan", {})
    basis    = v.get("basis_datei") or v.get("datei", "")
    src_path = os.path.join(_FILES, basis)
    if not basis or not os.path.exists(src_path):
        _update_zeitplan_status(vorlagen, v, "fehler", "Basis-PDF nicht gefunden")
        return
    felder_alle = _felder_aus_pdf(src_path)
    if not felder_alle:
        _update_zeitplan_status(vorlagen, v, "fehler", "Keine PDF-Felder gefunden")
        return
    ok, result = _ki_alle_felder_befuellen(v, felder_alle)
    if not ok:
        _update_zeitplan_status(vorlagen, v, "fehler", result)
        return
    out_name = f"{vid}_ausgefuellt.pdf"
    out_path = os.path.join(_FILES, out_name)
    if not _pdf_ausfuellen(src_path, out_path, result):
        _update_zeitplan_status(vorlagen, v, "fehler", "PDF-Speichern fehlgeschlagen")
        return
    v["datei"] = out_name

    # ── Modus: ki_pruefen → User benachrichtigen, KEIN Versand ────────────────
    if ki_modus == "ki_pruefen":
        _save(vorlagen)
        try:
            _stichtag_notify_review(v, out_path)
        except Exception as e:
            print(f"[AutoLauf] Review-Notify-Fehler: {e}")
        if zeitplan.get("intervall") == "einmalig":
            zeitplan["aktiv"] = False
        else:
            zeitplan["naechste_ausfuehrung"] = _berechne_naechste_ausfuehrung(zeitplan)
        _update_zeitplan_status(vorlagen, v, "ok", None)
        print(f"[AutoLauf] ki_pruefen: Vorlage {vid} vorbereitet, User benachrichtigt")
        return

    # ── Modus: autonom → Unterschrift + E-Mail an Empfänger ───────────────────
    upos = v.get("unterschrift_position")
    if upos:
        u_pfad = _find_unterschrift()
        if u_pfad:
            s_name = f"{vid}_signed.pdf"
            s_path = os.path.join(_FILES, s_name)
            s_tmp  = None
            try:
                import fitz
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False,
                                                  dir=_FILES) as sf:
                    s_tmp = sf.name
                sdoc = fitz.open(out_path)
                pn   = min(int(upos.get("page", 0)), len(sdoc) - 1)
                sr   = fitz.Rect(upos["x"], upos["y"],
                                 upos["x"] + upos["width"], upos["y"] + upos["height"])
                sdoc[pn].insert_image(sr, filename=u_pfad, keep_proportion=True)
                sdoc.save(s_tmp); sdoc.close()
                shutil.move(s_tmp, s_path)
                s_tmp = None
                v["datei"] = s_name
                out_path   = s_path
            except Exception as e:
                print(f"[AutoLauf] Unterschrift-Fehler (nicht fatal): {e}")
                if s_tmp and os.path.exists(s_tmp):
                    os.remove(s_tmp)
    empfaenger = zeitplan.get("empfaenger", "").strip()
    if empfaenger:
        cfg = _load_email_config()
        if cfg.get("smtp_server") and cfg.get("smtp_user") and cfg.get("smtp_password"):
            try:
                msg = MIMEMultipart("mixed")
                msg["From"]    = cfg["smtp_user"]
                msg["To"]      = empfaenger
                cc = zeitplan.get("empfaenger_cc", "").strip()
                if cc:
                    msg["Cc"] = cc
                msg["Subject"] = zeitplan.get("betreff") or v.get("name", "Formular")
                body_text = (zeitplan.get("text") or "").strip() \
                    or "Anbei das automatisch ausgefüllte Formular."
                msg.attach(MIMEText(body_text, "plain", "utf-8"))
                if os.path.exists(out_path):
                    mt, _ = mimetypes.guess_type(out_path)
                    main, sub = (mt or "application/pdf").split("/", 1)
                    with open(out_path, "rb") as af:
                        part = MIMEBase(main, sub)
                        part.set_payload(af.read())
                    _enc.encode_base64(part)
                    part.add_header("Content-Disposition",
                                    f'attachment; filename="{os.path.basename(out_path)}"')
                    msg.attach(part)
                rcpts = [empfaenger] + \
                    ([e.strip() for e in cc.split(",") if e.strip()] if cc else [])
                ctx = _ssl.create_default_context()
                if cfg.get("use_ssl"):
                    with smtplib.SMTP_SSL(cfg["smtp_server"],
                                          int(cfg["smtp_port"]), context=ctx) as srv:
                        srv.login(cfg["smtp_user"], cfg["smtp_password"])
                        srv.sendmail(cfg["smtp_user"], rcpts, msg.as_bytes())
                else:
                    with smtplib.SMTP(cfg["smtp_server"],
                                      int(cfg["smtp_port"])) as srv:
                        srv.ehlo(); srv.starttls(context=ctx)
                        srv.login(cfg["smtp_user"], cfg["smtp_password"])
                        srv.sendmail(cfg["smtp_user"], rcpts, msg.as_bytes())
                print(f"[AutoLauf] E-Mail an {empfaenger} gesendet")
            except Exception as e:
                print(f"[AutoLauf] E-Mail-Fehler: {e}")
                _update_zeitplan_status(vorlagen, v, "fehler", f"E-Mail-Fehler: {e}")
                return
    if zeitplan.get("intervall") == "einmalig":
        zeitplan["aktiv"] = False
    else:
        zeitplan["naechste_ausfuehrung"] = _berechne_naechste_ausfuehrung(zeitplan)
    _update_zeitplan_status(vorlagen, v, "ok", None)
    # Bestätigung an User senden
    try:
        _stichtag_notify_bestaetigung(v)
    except Exception as e:
        print(f"[AutoLauf] Bestätigungs-Notify-Fehler: {e}")
    print(f"[AutoLauf] autonom: Vorlage {vid} erfolgreich abgeschlossen")


def _start_autonom_scheduler():
    """Hintergrund-Thread: prüft alle 15 Minuten auf fällige Stichtag-Abläufe (autonom + ki_pruefen)."""
    import time as _time
    from datetime import date
    while True:
        _time.sleep(900)
        try:
            today    = date.today().isoformat()
            vorlagen = _load()
            for v in vorlagen:
                ki_modus = v.get("ki_modus", "manuell")
                if ki_modus not in ("autonom", "ki_pruefen"):
                    continue
                zp = v.get("zeitplan", {})
                if not zp.get("aktiv"):
                    continue
                naechste = zp.get("naechste_ausfuehrung", "")
                if naechste and naechste <= today:
                    try:
                        _autonomer_lauf(v["id"])
                    except Exception as e:
                        print(f"[AutoLauf] Fehler für {v.get('id')}: {e}")
        except Exception as e:
            print(f"[AutoSched] Fehler: {e}")


def _start_fristen_notif_scheduler():
    """Hintergrund-Thread: prüft täglich zwischen 7–9 Uhr auf fällige Benachrichtigungen."""
    import time as _time
    while True:
        _time.sleep(1800)  # alle 30 Minuten prüfen
        try:
            stunde = datetime.now().hour
            if 7 <= stunde < 9:
                _sende_fristen_benachrichtigungen()
        except Exception as e:
            print(f"[FristenNotif] Scheduler-Fehler: {e}")


# ── Registrierung ─────────────────────────────────────────────────────────────

def register_fristen_routes(app, get_kernel_func=None, kernel_lock=None):

    # Scheduler einmalig starten
    threading.Thread(target=_start_fristen_notif_scheduler,
                     daemon=True, name="fristen-notif").start()
    threading.Thread(target=_start_autonom_scheduler,
                     daemon=True, name="fristen-autonom").start()

    # ── Seite ─────────────────────────────────────────────────────────────────

    @app.route("/fristen")
    def fristen_page():
        return render_template("fristen.html")

    # ── Vorlagen-API ──────────────────────────────────────────────────────────

    @app.route("/api/fristen", methods=["GET"])
    def fristen_list():
        vorlagen = _load()
        heute = datetime.today().date()
        for v in vorlagen:
            try:
                fd = datetime.strptime(v["frist_datum"], "%Y-%m-%d").date()
                v["_tage_bis_frist"] = (fd - heute).days
            except Exception:
                v["_tage_bis_frist"] = 9999
        vorlagen.sort(key=lambda v: v["_tage_bis_frist"])
        return jsonify(vorlagen)

    @app.route("/api/fristen/chat-notification", methods=["GET"])
    def fristen_chat_notification():
        """Gibt Fristen zurück, die ≤7 Tage entfernt oder überfällig sind."""
        vorlagen = _load()
        heute = datetime.today().date()
        urgent = []
        for v in vorlagen:
            try:
                fd = datetime.strptime(v["frist_datum"], "%Y-%m-%d").date()
                tage = (fd - heute).days
                if tage <= 7:
                    urgent.append({
                        "id":          v["id"],
                        "name":        v["name"],
                        "typ":         v.get("typ", ""),
                        "frist_datum": v["frist_datum"],
                        "tage":        tage,
                    })
            except Exception:
                pass
        urgent.sort(key=lambda x: x["tage"])
        return jsonify(urgent)

    @app.route("/api/fristen/benachrichtigungen-jetzt", methods=["POST"])
    def fristen_benachrichtigungen_jetzt():
        """Manueller Trigger — sendet alle heute fälligen Benachrichtigungen."""
        try:
            result = _sende_fristen_benachrichtigungen()
            return jsonify({"ok": True, **result})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/fristen/benachrichtigungen-log", methods=["GET"])
    def fristen_benachrichtigungen_log():
        log = _load_notif_log()
        heute_s = datetime.today().date().isoformat()
        heute_log = {k: v for k, v in log.items() if k.endswith(f"__{heute_s}")}
        return jsonify({"heute": heute_log, "gesamt": len(log)})

    @app.route("/api/fristen", methods=["POST"])
    def fristen_create():
        d = request.get_json(force=True) or {}
        vorlage = {
            "id":                   str(uuid.uuid4()),
            "typ":                  d.get("typ", "antrag"),
            "name":                 d.get("name", "").strip(),
            "beschreibung":         d.get("beschreibung", "").strip(),
            "datei":                "",
            "frist_datum":          d.get("frist_datum", ""),
            "wiederholung":         d.get("wiederholung", None),
            "erinnerung_wochen":    d.get("erinnerung_wochen", [4, 2, 1]),
            # Kündigung-spezifisch
            "vertragsbeginn":       d.get("vertragsbeginn", ""),
            "laufzeit_monate":      d.get("laufzeit_monate", 24),
            "kuendigungsfrist_wochen": d.get("kuendigungsfrist_wochen", 4),
            "kundennummer":         d.get("kundennummer", "").strip(),
            # Empfänger
            "empfaenger": {
                "name":    d.get("empf_name", "").strip(),
                "adresse": d.get("empf_adresse", "").strip(),
                "email":   d.get("empf_email", "").strip(),
                "fax":     d.get("empf_fax", "").strip(),
            },
            "benachrichtigung":     d.get("benachrichtigung", ["chat"]),
            "erstellt":             datetime.now().isoformat(),
            "zuletzt_gesendet":     None,
        }
        if not vorlage["name"]:
            return jsonify({"ok": False, "error": "Name fehlt"}), 400
        vorlagen = _load()
        vorlagen.append(vorlage)
        _save(vorlagen)
        return jsonify({"ok": True, "id": vorlage["id"]})

    @app.route("/api/fristen/<vid>", methods=["PUT"])
    def fristen_update(vid):
        d = request.get_json(force=True) or {}
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        v["typ"]              = d.get("typ", v.get("typ", "antrag"))
        v["name"]             = d.get("name", v["name"]).strip()
        v["beschreibung"]     = d.get("beschreibung", v.get("beschreibung", "")).strip()
        v["frist_datum"]      = d.get("frist_datum", v["frist_datum"])
        v["wiederholung"]     = d.get("wiederholung", v.get("wiederholung"))
        v["erinnerung_wochen"] = d.get("erinnerung_wochen", v["erinnerung_wochen"])
        v["vertragsbeginn"]   = d.get("vertragsbeginn", v.get("vertragsbeginn", ""))
        v["laufzeit_monate"]  = d.get("laufzeit_monate", v.get("laufzeit_monate", 24))
        v["kuendigungsfrist_wochen"] = d.get("kuendigungsfrist_wochen", v.get("kuendigungsfrist_wochen", 4))
        v["kundennummer"]     = d.get("kundennummer", v.get("kundennummer", "")).strip()
        v["empfaenger"]["name"]    = d.get("empf_name",    v["empfaenger"]["name"]).strip()
        v["empfaenger"]["adresse"] = d.get("empf_adresse", v["empfaenger"].get("adresse", "")).strip()
        v["empfaenger"]["email"]   = d.get("empf_email",   v["empfaenger"]["email"]).strip()
        v["empfaenger"]["fax"]     = d.get("empf_fax",     v["empfaenger"]["fax"]).strip()
        v["benachrichtigung"]      = d.get("benachrichtigung", v["benachrichtigung"])
        _save(vorlagen)
        return jsonify({"ok": True})

    @app.route("/api/fristen/<vid>", methods=["DELETE"])
    def fristen_delete(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        if v.get("datei"):
            fp = os.path.join(_FILES, v["datei"])
            if os.path.exists(fp):
                os.remove(fp)
        vorlagen = [x for x in vorlagen if x["id"] != vid]
        _save(vorlagen)
        return jsonify({"ok": True})

    @app.route("/api/fristen/<vid>/upload", methods=["POST"])
    def fristen_upload(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Vorlage nicht gefunden"}), 404
        if "datei" not in request.files:
            return jsonify({"ok": False, "error": "Keine Datei"}), 400
        f = request.files["datei"]
        if not f.filename:
            return jsonify({"ok": False, "error": "Kein Dateiname"}), 400
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".pdf", ".docx", ".doc", ".odt"):
            return jsonify({"ok": False, "error": "Nur PDF, DOCX, ODT erlaubt"}), 400
        filename = secure_filename(f"{vid}{ext}")
        if v.get("datei"):
            old = os.path.join(_FILES, v["datei"])
            if os.path.exists(old):
                os.remove(old)
        f.save(os.path.join(_FILES, filename))
        v["datei"] = filename
        _save(vorlagen)
        return jsonify({"ok": True, "datei": filename})

    # ── Absender-Profil ───────────────────────────────────────────────────────

    @app.route("/api/fristen/absender", methods=["GET"])
    def fristen_absender_get():
        return jsonify(_load_absender())

    @app.route("/api/fristen/absender", methods=["POST"])
    def fristen_absender_post():
        d = request.get_json(force=True) or {}
        data = {
            "name":    d.get("name", "").strip(),
            "adresse": d.get("adresse", "").strip(),
            "email":   d.get("email", "").strip(),
        }
        _save_absender(data)
        return jsonify({"ok": True})

    # ── Brief-Generierung ─────────────────────────────────────────────────────

    @app.route("/api/fristen/<vid>/brief", methods=["POST"])
    def fristen_brief(vid):
        if get_kernel_func is None:
            return jsonify({"ok": False, "error": "KI nicht verfügbar"}), 503

        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Vorlage nicht gefunden"}), 404

        absender  = _load_absender()
        typ       = v.get("typ", "antrag")
        empf      = v["empfaenger"]

        if typ == "kuendigung":
            betreff   = "Kündigung meines Vertrages"
            if v.get("kundennummer"):
                betreff += f"\nIhre Kundennummer: {v['kundennummer']}"
            kontext   = (
                f"Fristgemäße Kündigung zum {_fmt_datum(v.get('frist_datum',''))}."
                + (f"\nVertrag/Beschreibung: {v['beschreibung']}" if v.get("beschreibung") else "")
                + (f"\nKundennummer: {v['kundennummer']}" if v.get("kundennummer") else "")
            )
            typ_text  = "Kündigung"
        else:
            betreff   = v["name"]
            kontext   = v.get("beschreibung") or f"Antrag/Schreiben betreffend: {v['name']}"
            typ_text  = "Schreiben" if typ == "sonstiges" else "Antrag"

        prompt = f"""Schreibe den Briefkörper für ein formelles deutsches {typ_text}-Schreiben.

Empfänger: {empf.get('name') or 'die zuständige Stelle'}
Betreff: {betreff.splitlines()[0]}
Kontext: {kontext}

Schreibe NUR: Anrede → Briefinhalt → Schlussformel ("Mit freundlichen Grüßen").
NICHT: Datum, Adressen, Unterschrift — die werden automatisch hinzugefügt.
Kein Markdown, kein Fettdruck, keine Überschriften."""

        try:
            lock = kernel_lock
            if lock:
                with lock:
                    k = get_kernel_func()
                    koerper = k.chat(prompt)
            else:
                k = get_kernel_func()
                koerper = k.chat(prompt)

            # DIN-5008-Dokument bauen und als Datei speichern
            html = _baue_brief_html(v, absender, betreff, koerper)
            filename = f"{vid}.html"
            with open(os.path.join(_FILES, filename), "w", encoding="utf-8") as f:
                f.write(html)

            # Alte Datei löschen falls eine andere vorhanden war
            if v.get("datei") and v["datei"] != filename:
                old = os.path.join(_FILES, v["datei"])
                if os.path.exists(old):
                    os.remove(old)

            v["datei"] = filename
            _save(vorlagen)

            return jsonify({"ok": True, "doc_url": f"/fristen/dokument/{vid}"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Brief-Dokument anzeigen ───────────────────────────────────────────────

    @app.route("/fristen/dokument/<vid>")
    def fristen_dokument(vid):
        from flask import send_from_directory, abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei", "").endswith(".html"):
            abort(404)
        return send_from_directory(_FILES, v["datei"])

    # ── Kontaktdaten-Suche ────────────────────────────────────────────────────

    @app.route("/api/fristen/kontakt-suchen", methods=["POST"])
    def fristen_kontakt_suchen():
        if get_kernel_func is None:
            return jsonify({"ok": False, "error": "KI nicht verfügbar"}), 503

        d = request.get_json(force=True) or {}
        anbieter = d.get("anbieter", "").strip()
        typ = d.get("typ", "antrag")
        if not anbieter:
            return jsonify({"ok": False, "error": "Kein Anbieter angegeben"}), 400

        zweck = "Kündigung" if typ == "kuendigung" else "Antrag/Schreiben"
        prompt = f"""Suche die offiziellen Kontaktdaten für ein {zweck}-Schreiben an: "{anbieter}"

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne jeden weiteren Text davor oder danach:
{{"adresse": "Straße Hausnummer, PLZ Ort", "email": "...", "fax": "..."}}

Wenn du eine Information nicht kennst oder nicht sicher bist, setze den Wert auf "".
Wichtig: Nur echte, offizielle Adressen. Keine erfundenen Daten."""

        try:
            lock = kernel_lock
            if lock:
                with lock:
                    k = get_kernel_func()
                    antwort = k.chat(prompt)
            else:
                k = get_kernel_func()
                antwort = k.chat(prompt)

            # JSON aus der Antwort extrahieren
            match = re.search(r'\{[^{}]+\}', antwort, re.DOTALL)
            if match:
                kontakt = json.loads(match.group())
                return jsonify({"ok": True, "kontakt": kontakt, "rohantwort": antwort})
            else:
                return jsonify({"ok": True, "kontakt": {"adresse": "", "email": "", "fax": ""}, "rohantwort": antwort})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Unterschrift API ──────────────────────────────────────────────────────

    @app.route("/api/fristen/unterschrift", methods=["GET"])
    def fristen_unterschrift_get():
        pfad = _find_unterschrift()
        if not pfad:
            return jsonify({"ok": True, "exists": False})
        ext  = os.path.splitext(pfad)[1].lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        with open(pfad, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return jsonify({"ok": True, "exists": True, "data": f"data:{mime};base64,{data}"})

    @app.route("/api/fristen/unterschrift", methods=["POST"])
    def fristen_unterschrift_post():
        if "datei" in request.files:
            f   = request.files["datei"]
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                return jsonify({"ok": False, "error": "Nur PNG, JPG, GIF, WebP erlaubt"}), 400
            _delete_unterschrift()
            os.makedirs(_DATA, exist_ok=True)
            f.save(_UNTERSCHRIFT_BASE + ext)
            return jsonify({"ok": True})
        d        = request.get_json(force=True) or {}
        data_url = d.get("data", "")
        m = re.match(r"data:image/([^;]+);base64,(.+)", data_url, re.DOTALL)
        if not m:
            return jsonify({"ok": False, "error": "Ungültiges Format"}), 400
        subtype = m.group(1).lower().replace("jpeg", "jpg")
        ext     = "." + (subtype if subtype in ("png", "jpg", "gif", "webp") else "png")
        raw     = base64.b64decode(m.group(2))
        _delete_unterschrift()
        os.makedirs(_DATA, exist_ok=True)
        with open(_UNTERSCHRIFT_BASE + ext, "wb") as f:
            f.write(raw)
        return jsonify({"ok": True})

    @app.route("/api/fristen/unterschrift", methods=["DELETE"])
    def fristen_unterschrift_delete():
        _delete_unterschrift()
        return jsonify({"ok": True})

    # ── PDF-Datei ausliefern (für PDF.js) ────────────────────────────────────

    @app.route("/fristen/datei/<vid>")
    def fristen_datei_raw(vid):
        from flask import send_from_directory, abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei"):
            abort(404)
        return send_from_directory(_FILES, v["datei"])

    # ── Unterschrift-Platzierung (Seite) ──────────────────────────────────────

    @app.route("/fristen/unterschrift-setzen/<vid>")
    def fristen_unterschrift_setzen_page(vid):
        from flask import abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei") or v["datei"].endswith(".html"):
            abort(404)
        return render_template("unterschrift_setzen.html", vid=vid, name=v.get("name", "Dokument"))

    # ── Unterschrift einbetten (PyMuPDF) ──────────────────────────────────────

    @app.route("/api/fristen/<vid>/unterschrift-einbetten", methods=["POST"])
    def fristen_unterschrift_einbetten(vid):
        try:
            import fitz
        except ImportError:
            return jsonify({"ok": False,
                            "error": "PyMuPDF nicht installiert. Bitte: pip install pymupdf"}), 503

        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei"):
            return jsonify({"ok": False, "error": "Keine Datei vorhanden"}), 404
        if not v["datei"].lower().endswith(".pdf"):
            return jsonify({"ok": False,
                            "error": "Unterschrift-Einbettung ist nur für PDF-Dateien möglich"}), 400

        unterschrift_pfad = _find_unterschrift()
        if not unterschrift_pfad:
            return jsonify({"ok": False, "error": "Keine Unterschrift hinterlegt"}), 404

        d        = request.get_json(force=True) or {}
        page_num = max(0, int(d.get("page", 0)))
        x        = float(d.get("x", 0))
        y        = float(d.get("y", 0))
        width    = max(10.0, float(d.get("width", 150)))
        height   = max(5.0,  float(d.get("height", 50)))

        src_path = os.path.join(_FILES, v["datei"])
        out_name = f"{vid}_signed.pdf"
        out_path = os.path.join(_FILES, out_name)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=_FILES) as tmp:
                tmp_path = tmp.name
            doc  = fitz.open(src_path)
            if page_num >= len(doc):
                page_num = len(doc) - 1
            page = doc[page_num]
            rect = fitz.Rect(x, y, x + width, y + height)
            page.insert_image(rect, filename=unterschrift_pfad, keep_proportion=True)
            doc.save(tmp_path)
            doc.close()
            shutil.move(tmp_path, out_path)
            tmp_path = None
            v["datei"] = out_name
            v["unterschrift_position"] = {
                "page": page_num, "x": x, "y": y,
                "width": width, "height": height
            }
            _save(vorlagen)
            return jsonify({"ok": True})
        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── E-Mail-Konfiguration ──────────────────────────────────────────────────

    @app.route("/api/fristen/email-config", methods=["GET"])
    def fristen_email_config_get():
        cfg  = _load_email_config()
        safe = {k: v for k, v in cfg.items() if k != "smtp_password"}
        safe["hat_passwort"] = bool(cfg.get("smtp_password"))
        return jsonify(safe)

    @app.route("/api/fristen/email-config", methods=["POST"])
    def fristen_email_config_post():
        d   = request.get_json(force=True) or {}
        cfg = _load_email_config()
        if "smtp_server"  in d: cfg["smtp_server"]  = d["smtp_server"].strip()
        if "smtp_port"    in d: cfg["smtp_port"]    = int(d["smtp_port"])
        if "smtp_user"    in d: cfg["smtp_user"]    = d["smtp_user"].strip()
        if "use_ssl"      in d: cfg["use_ssl"]      = bool(d["use_ssl"])
        if "notif_email"  in d: cfg["notif_email"]  = d["notif_email"].strip()
        if d.get("smtp_password"):
            cfg["smtp_password"] = d["smtp_password"]
        _save_email_config(cfg)
        return jsonify({"ok": True})

    # ── E-Mail senden ─────────────────────────────────────────────────────────

    @app.route("/api/fristen/<vid>/email-senden", methods=["POST"])
    def fristen_email_senden(vid):
        import smtplib, ssl as _ssl
        from email.mime.multipart import MIMEMultipart
        from email.mime.text      import MIMEText
        from email.mime.base      import MIMEBase
        from email                import encoders as _enc
        import mimetypes

        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404

        cfg = _load_email_config()
        if not cfg.get("smtp_server") or not cfg.get("smtp_user") or not cfg.get("smtp_password"):
            return jsonify({"ok": False, "error": "SMTP nicht konfiguriert. Bitte unter 👤 Meine Daten einrichten."}), 400

        d       = request.get_json(force=True) or {}
        to      = d.get("to", "").strip()
        cc      = d.get("cc", "").strip()
        subject = d.get("subject", v.get("name", "")).strip()
        body    = d.get("body", "").strip()

        if not to:
            return jsonify({"ok": False, "error": "Kein Empfänger angegeben"}), 400

        msg           = MIMEMultipart("mixed")
        msg["From"]   = cfg["smtp_user"]
        msg["To"]     = to
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject

        msg.attach(MIMEText(body or " ", "plain", "utf-8"))

        # Datei anhängen (wenn vorhanden)
        datei = v.get("datei", "")
        if datei:
            datei_pfad = os.path.join(_FILES, datei)
            if os.path.exists(datei_pfad):
                mime_type, _ = mimetypes.guess_type(datei_pfad)
                maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
                with open(datei_pfad, "rb") as af:
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(af.read())
                _enc.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{datei}"')
                msg.attach(part)

        recipients = [to] + ([e.strip() for e in cc.split(",") if e.strip()] if cc else [])

        try:
            ctx = _ssl.create_default_context()
            if cfg.get("use_ssl"):
                with smtplib.SMTP_SSL(cfg["smtp_server"], int(cfg["smtp_port"]), context=ctx) as srv:
                    srv.login(cfg["smtp_user"], cfg["smtp_password"])
                    srv.sendmail(cfg["smtp_user"], recipients, msg.as_bytes())
            else:
                with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as srv:
                    srv.ehlo()
                    srv.starttls(context=ctx)
                    srv.login(cfg["smtp_user"], cfg["smtp_password"])
                    srv.sendmail(cfg["smtp_user"], recipients, msg.as_bytes())
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Fax senden (Mail2Fax via simple-fax.de) ──────────────────────────────

    @app.route("/api/fristen/<vid>/fax-senden", methods=["POST"])
    def fristen_fax_senden(vid):
        import smtplib, ssl as _ssl
        from email.mime.multipart import MIMEMultipart
        from email.mime.text      import MIMEText
        from email.mime.base      import MIMEBase
        from email                import encoders as _enc
        import mimetypes, re as _re

        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404

        datei = v.get("datei", "")
        if not datei or not datei.lower().endswith(".pdf"):
            return jsonify({"ok": False,
                            "error": "Fax-Versand erfordert eine PDF-Datei."}), 400

        cfg = _load_email_config()
        if not cfg.get("smtp_server") or not cfg.get("smtp_user") or not cfg.get("smtp_password"):
            return jsonify({"ok": False,
                            "error": "SMTP nicht konfiguriert. Bitte unter 👤 Meine Daten einrichten."}), 400

        d = request.get_json(force=True) or {}
        fax_nummer = d.get("fax_nummer", "").strip()
        if not fax_nummer:
            return jsonify({"ok": False, "error": "Keine Faxnummer angegeben"}), 400

        # Normalisieren: nur Ziffern, +, führende Leerzeichen/Sonderzeichen entfernen
        fax_clean = _re.sub(r"[\s\-\(\)/]", "", fax_nummer)
        if not _re.match(r"^\+?[\d]{5,}$", fax_clean):
            return jsonify({"ok": False, "error": "Ungültige Faxnummer"}), 400

        fax_to = f"{fax_clean}@simple-fax.de"
        subject = d.get("subject", v.get("name", "Fax")).strip() or "Fax"
        body    = d.get("body", "").strip()

        msg           = MIMEMultipart("mixed")
        msg["From"]   = cfg["smtp_user"]
        msg["To"]     = fax_to
        msg["Subject"] = subject

        msg.attach(MIMEText(body or " ", "plain", "utf-8"))

        datei_pfad = os.path.join(_FILES, datei)
        if os.path.exists(datei_pfad):
            mime_type, _ = mimetypes.guess_type(datei_pfad)
            maintype, subtype = (mime_type or "application/pdf").split("/", 1)
            with open(datei_pfad, "rb") as af:
                part = MIMEBase(maintype, subtype)
                part.set_payload(af.read())
            _enc.encode_base64(part)
            part.add_header("Content-Disposition",
                            f'attachment; filename="{datei}"')
            msg.attach(part)

        try:
            ctx = _ssl.create_default_context()
            if cfg.get("use_ssl"):
                with smtplib.SMTP_SSL(cfg["smtp_server"], int(cfg["smtp_port"]), context=ctx) as srv:
                    srv.login(cfg["smtp_user"], cfg["smtp_password"])
                    srv.sendmail(cfg["smtp_user"], [fax_to], msg.as_bytes())
            else:
                with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as srv:
                    srv.ehlo()
                    srv.starttls(context=ctx)
                    srv.login(cfg["smtp_user"], cfg["smtp_password"])
                    srv.sendmail(cfg["smtp_user"], [fax_to], msg.as_bytes())
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Formular ausfüllen ────────────────────────────────────────────────────

    @app.route("/fristen/formular-ausfuellen/<vid>")
    def fristen_formular_page(vid):
        from flask import abort
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei", "").lower().endswith(".pdf"):
            abort(404)
        return render_template("formular_ausfuellen.html", vid=vid, name=v.get("name", "Dokument"))

    def _camel_to_label(name):
        import re
        clean = re.sub(r'^(txtf?|date|chk|cmb|rb|lbl|btn)', '', name, flags=re.IGNORECASE)
        spaced = re.sub(r'([A-Z])', r' \1', clean).strip()
        return spaced if spaced else name

    @app.route("/api/fristen/<vid>/formular-felder", methods=["GET"])
    def fristen_formular_felder(vid):
        try:
            import fitz
        except ImportError:
            return jsonify({"ok": False, "error": "PyMuPDF nicht installiert"}), 503
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei"):
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        src = os.path.join(_FILES, v["datei"])
        if not os.path.exists(src) or not v["datei"].lower().endswith(".pdf"):
            return jsonify({"ok": False, "error": "Keine PDF-Datei"}), 404
        felder = []
        doc = fitz.open(src)
        seen_radio = {}  # field_name → index in felder (for grouping radio choices)
        for page_num, page in enumerate(doc):
            for widget in page.widgets():
                ft = widget.field_type_string
                if ft in ("Button", "Signature", "Unknown"):
                    continue
                name = widget.field_name or f"Feld_{len(felder)+1}"
                val  = widget.field_value
                val_str = str(val) if val else ""
                choices = list(widget.choice_values or [])
                raw_label = getattr(widget, "field_label", None)
                display_label = (raw_label.strip() if raw_label and raw_label.strip() else None) or _camel_to_label(name)
                w_rect = [widget.rect.x0, widget.rect.y0,
                          widget.rect.x1, widget.rect.y1]
                if ft == "RadioButton":
                    if name in seen_radio:
                        existing = felder[seen_radio[name]]
                        existing["choices"].extend(
                            c for c in choices if c not in existing["choices"]
                        )
                        existing["choice_rects"].append(w_rect)
                        if val_str and val_str != "Off":
                            existing["value"] = val_str
                        continue
                    else:
                        seen_radio[name] = len(felder)
                entry = {
                    "name":    name,
                    "label":   display_label,
                    "type":    ft,
                    "value":   val_str if val_str != "Off" else "",
                    "choices": choices,
                    "page":    page_num,
                    "rect":    w_rect,
                }
                if ft == "RadioButton":
                    entry["choice_rects"] = [w_rect]
                felder.append(entry)
        total_pages = doc.page_count
        doc.close()
        return jsonify({"ok": True, "felder": felder, "total_pages": total_pages})

    @app.route("/api/fristen/<vid>/vorlage", methods=["GET"])
    def fristen_vorlage_get(vid):
        v = _find(_load(), vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        return jsonify({"ok": True, "ki_kontext": v.get("ki_kontext", ""),
                        "referenz_name": v.get("referenz_name", ""),
                        "ki_modus": v.get("ki_modus", "manuell")})

    @app.route("/api/fristen/<vid>/modus", methods=["POST"])
    def fristen_modus_post(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        modus = (request.get_json(force=True) or {}).get("modus", "manuell")
        if modus not in ("manuell", "ki_pruefen", "autonom"):
            return jsonify({"ok": False, "error": "Ungültiger Modus"}), 400
        v["ki_modus"] = modus
        _save(vorlagen)
        return jsonify({"ok": True})

    @app.route("/api/fristen/<vid>/ki-kontext", methods=["POST"])
    def fristen_ki_kontext_save(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        v["ki_kontext"] = (request.get_json(force=True) or {}).get("kontext", "").strip()
        _save(vorlagen)
        return jsonify({"ok": True})

    @app.route("/api/fristen/<vid>/referenz-upload", methods=["POST"])
    def fristen_referenz_upload(vid):
        _IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp"}
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "Keine Datei"}), 400
        ext = os.path.splitext(f.filename.lower())[1]
        if ext not in _IMG_EXTS and ext != ".pdf":
            return jsonify({"ok": False,
                            "error": "Nur PDF oder Bild (JPG, PNG, WEBP, TIFF) erlaubt"}), 400

        full_text = ""
        if ext == ".pdf":
            try:
                import fitz
            except ImportError:
                return jsonify({"ok": False, "error": "PyMuPDF nicht installiert"}), 503
            doc = fitz.open(stream=f.read(), filetype="pdf")
            parts = []
            for page in doc:
                # Digitaler Text aus AcroForm-PDFs
                t = page.get_text().strip()
                if t:
                    parts.append(t)
                else:
                    # Gescannte Seite → OCR via Pixmap
                    try:
                        import pytesseract
                        from PIL import Image
                        import io
                        pix = page.get_pixmap(dpi=150)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        parts.append(pytesseract.image_to_string(img, lang="deu+eng"))
                    except Exception:
                        pass
            doc.close()
            full_text = "\n".join(parts).strip()
        else:
            # Bild (Handy-Foto, Scan)
            try:
                import pytesseract
                from PIL import Image, ImageOps
                import io
                img = Image.open(io.BytesIO(f.read()))
                img = ImageOps.exif_transpose(img)  # EXIF-Rotation für Handyfotos
                full_text = pytesseract.image_to_string(img, lang="deu+eng").strip()
            except ImportError:
                return jsonify({"ok": False,
                                "error": "pytesseract/Pillow nicht installiert"}), 503
            except Exception as e:
                return jsonify({"ok": False, "error": f"OCR-Fehler: {e}"}), 500

        v["referenz_text"] = full_text[:4000]
        v["referenz_name"] = f.filename
        _save(vorlagen)
        return jsonify({"ok": True, "zeichen": len(v["referenz_text"]), "name": f.filename})

    @app.route("/api/fristen/<vid>/formular-ki-vorschlag", methods=["POST"])
    def fristen_formular_ki(vid):
        if not get_kernel_func or not kernel_lock:
            return jsonify({"ok": False, "error": "Kernel nicht verfügbar"}), 503
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        data     = request.get_json(force=True) or {}
        felder   = data.get("felder", [])
        kontext  = data.get("kontext", "").strip() or v.get("ki_kontext", "").strip()
        absender = _load_absender()

        # Feldnamen-Set für spätere Pairing-Prüfung
        feld_namen = {f["name"] for f in felder}

        # Feldliste mit Typ-Hinweisen aufbauen
        feld_liste = "\n".join(
            "- " + f["name"] + ' ("' + f.get("label", f["name"]) + '", ' + f.get("type", "Text") + ")"
            + (" [Optionen: " + ", ".join(f["choices"][:6]) + "]" if f.get("choices") else "")
            for f in felder
        )

        adresse_einz = absender.get("adresse", "").replace("\n", ", ").strip()
        kontext_block = f"\nZusatzinfos:\n{kontext}\n" if kontext else ""
        referenz_block = (
            f"\nReferenzdokument \"{v.get('referenz_name','')}\" (Auszug):\n"
            + v["referenz_text"][:3000] + "\n"
        ) if v.get("referenz_text") else ""

        prompt = (
            "Du befüllst ein deutsches PDF-Formular. Antworte NUR mit einem JSON-Objekt "
            "(kein Markdown, keine Erklärungen, nur roher JSON-Text).\n\n"
            "=== PFLICHTREGELN ===\n"
            "1. JEDES Feld im JSON zurückgeben — auch wenn der Wert leer ist.\n"
            "2. CheckBox: IMMER 'true' oder 'false' — nie leer lassen.\n"
            "3. RadioButton: IMMER genau einen der [Optionen]-Werte wählen — nie leer lassen.\n"
            "4. Gekoppelte Felder: Wenn ein 'numf'-Betrag eingetragen wird, "
            "MUSS die gleichnamige 'chbx'-Checkbox (selbes Suffix) auf 'true' gesetzt werden.\n"
            "   Beispiel: numfBedarfGrundmiete='620' → chbxBedarfGrundmiete='true'\n"
            "5. Felder die du nicht kennst: '' (leerer String), aber CheckBox/Radio trotzdem befüllen.\n"
            "6. Zeilen-Felder mit Z1/Z2/Z3 im Namen: Z1 = erste Person der BG (Antragsteller/in), "
            "Z2 = zweite Person der BG, Z3 = dritte Person usw. Nutze die Nutzerdaten/Zusatzinfos, "
            "um die richtigen Personen den richtigen Zeilen zuzuordnen.\n\n"
            "=== NUTZERDATEN ===\n"
            f"- Name: {absender.get('name', '')}\n"
            f"- Adresse: {adresse_einz}\n"
            f"- E-Mail: {absender.get('email', '')}\n"
            f"- Formulartitel: {v.get('name', '')}\n"
            f"{kontext_block}"
            f"{referenz_block}\n"
            "=== FELDER (Feldname, Bezeichnung, Typ, [Optionen]) ===\n"
            f"{feld_liste}\n\n"
            'Antworte nur mit: {"Feldname": "Wert", ...}'
        )
        # Fristen-KI braucht eine saubere, zustandslose Provider-Verbindung ohne
        # die globale Ilija-Chat-History und System-Prompt, da sonst die JSON-Antwort
        # durch die Ilija-Persoenlichkeit ueberschrieben wird.
        try:
            from providers import select_provider
            _, _prov = select_provider()
            raw = _prov.chat(
                messages=[{"role": "user", "content": prompt}],
                system="Du bist ein Formular-Ausfüllassistent. Antworte IMMER und NUR mit reinem JSON — kein Text davor oder danach."
            )
        except Exception as _e:
            return jsonify({"ok": False, "error": f"KI-Provider Fehler: {_e}"}), 503
        match = re.search(r'\{[\s\S]*\}', raw)
        if not match:
            return jsonify({"ok": False, "error": "KI-Antwort nicht parsbar", "raw": raw[:300]}), 500
        try:
            vorschlaege = json.loads(match.group())
        except Exception:
            return jsonify({"ok": False, "error": "JSON-Fehler", "raw": raw[:300]}), 500

        # ── Post-Processing: numf+chbx automatisch koppeln ──────────
        for name, val in list(vorschlaege.items()):
            if name.lower().startswith("numf") and val:
                chbx = "chbx" + name[4:]
                if chbx in feld_namen and vorschlaege.get(chbx, "false") != "true":
                    vorschlaege[chbx] = "true"

        return jsonify({"ok": True, "vorschlaege": vorschlaege})

    @app.route("/api/fristen/<vid>/ki-alle-seiten", methods=["POST"])
    def fristen_ki_alle_seiten(vid):
        """Variante 2/3: KI befüllt alle Felder aller Seiten in einem Call."""
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        data = request.get_json(force=True) or {}
        felder_alle = data.get("felder", [])
        if not felder_alle:
            return jsonify({"ok": False, "error": "Keine Felder übergeben"}), 400
        ok, result = _ki_alle_felder_befuellen(v, felder_alle)
        if not ok:
            return jsonify({"ok": False, "error": result}), 503
        return jsonify({"ok": True, "vorschlaege": result})

    @app.route("/api/fristen/<vid>/zeitplan", methods=["GET"])
    def fristen_zeitplan_get(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        return jsonify({"ok": True, "zeitplan": v.get("zeitplan", {})})

    @app.route("/api/fristen/<vid>/zeitplan", methods=["POST"])
    def fristen_zeitplan_post(vid):
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        d = request.get_json(force=True) or {}
        # Basis-Datei beim ersten Aktivieren festhalten
        if d.get("aktiv") and not v.get("basis_datei") and v.get("datei"):
            v["basis_datei"] = v["datei"]
        zp = v.setdefault("zeitplan", {})
        for key in ("aktiv", "intervall", "stichtag_tag", "stichtag_monat",
                    "empfaenger", "empfaenger_cc", "betreff", "text"):
            if key in d:
                zp[key] = d[key]
        if zp.get("aktiv") and not zp.get("naechste_ausfuehrung"):
            zp["naechste_ausfuehrung"] = _berechne_naechste_ausfuehrung(zp)
        _save(vorlagen)
        return jsonify({"ok": True, "zeitplan": zp})

    @app.route("/api/fristen/pending-stichtag", methods=["GET"])
    def fristen_pending_stichtag():
        """Gibt offene ki_pruefen-Stichtag-Einträge zurück (für Chat-Anzeige)."""
        return jsonify({"ok": True, "pending": _load_pending_stichtag()})

    @app.route("/api/fristen/<vid>/stichtag-senden", methods=["POST"])
    def fristen_stichtag_senden(vid):
        """Sendet das vorbereitete ki_pruefen-Dokument an den Empfänger und räumt den Pending-Eintrag ab."""
        import smtplib, ssl as _ssl2s, mimetypes as _mt2
        from email.mime.multipart import MIMEMultipart as _MM2
        from email.mime.text      import MIMEText as _MT2
        from email.mime.base      import MIMEBase as _MB2
        from email                import encoders as _enc2
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v:
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        zeitplan   = v.get("zeitplan", {})
        empfaenger = zeitplan.get("empfaenger", "").strip()
        out_name   = v.get("datei", "")
        out_path   = os.path.join(_FILES, out_name)
        if not out_name or not os.path.exists(out_path):
            return jsonify({"ok": False, "error": "Vorbereitetes Dokument nicht gefunden"}), 404
        if empfaenger:
            cfg = _load_email_config()
            if not cfg.get("smtp_server") or not cfg.get("smtp_user") or not cfg.get("smtp_password"):
                return jsonify({"ok": False, "error": "SMTP nicht konfiguriert"}), 503
            try:
                msg = _MM2("mixed")
                msg["From"]    = cfg["smtp_user"]
                msg["To"]      = empfaenger
                cc = zeitplan.get("empfaenger_cc", "").strip()
                if cc:
                    msg["Cc"] = cc
                msg["Subject"] = zeitplan.get("betreff") or v.get("name", "Formular")
                body_t = (zeitplan.get("text") or "").strip() or "Anbei das ausgefüllte Formular."
                msg.attach(_MT2(body_t, "plain", "utf-8"))
                mime_t, _ = _mt2.guess_type(out_path)
                main2, sub2 = (mime_t or "application/pdf").split("/", 1)
                with open(out_path, "rb") as af:
                    part = _MB2(main2, sub2)
                    part.set_payload(af.read())
                _enc2.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{os.path.basename(out_path)}"')
                msg.attach(part)
                rcpts = [empfaenger] + \
                    ([e.strip() for e in cc.split(",") if e.strip()] if cc else [])
                ctx2 = _ssl2s.create_default_context()
                if cfg.get("use_ssl"):
                    with smtplib.SMTP_SSL(cfg["smtp_server"], int(cfg["smtp_port"]), context=ctx2) as srv:
                        srv.login(cfg["smtp_user"], cfg["smtp_password"])
                        srv.sendmail(cfg["smtp_user"], rcpts, msg.as_bytes())
                else:
                    with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as srv:
                        srv.ehlo(); srv.starttls(context=ctx2)
                        srv.login(cfg["smtp_user"], cfg["smtp_password"])
                        srv.sendmail(cfg["smtp_user"], rcpts, msg.as_bytes())
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        # Pending-Eintrag entfernen
        pending = [p for p in _load_pending_stichtag() if p.get("vid") != vid]
        _save_pending_stichtag(pending)
        # nächste Ausführung berechnen
        if zeitplan.get("intervall") == "einmalig":
            zeitplan["aktiv"] = False
        else:
            zeitplan["naechste_ausfuehrung"] = _berechne_naechste_ausfuehrung(zeitplan)
        _update_zeitplan_status(vorlagen, v, "ok", None)
        try:
            _stichtag_notify_bestaetigung(v)
        except Exception:
            pass
        return jsonify({"ok": True, "empfaenger": empfaenger})

    @app.route("/api/fristen/<vid>/formular-ausfuellen", methods=["POST"])
    def fristen_formular_ausfuellen_post(vid):
        try:
            import fitz
        except ImportError:
            return jsonify({"ok": False, "error": "PyMuPDF nicht installiert"}), 503
        vorlagen = _load()
        v = _find(vorlagen, vid)
        if not v or not v.get("datei"):
            return jsonify({"ok": False, "error": "Nicht gefunden"}), 404
        src_path = os.path.join(_FILES, v["datei"])
        if not os.path.exists(src_path) or not v["datei"].lower().endswith(".pdf"):
            return jsonify({"ok": False, "error": "Keine PDF-Datei"}), 404
        data  = request.get_json(force=True) or {}
        werte = data.get("werte", {})
        out_name = f"{vid}_ausgefuellt.pdf"
        out_path = os.path.join(_FILES, out_name)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=_FILES) as tmp:
                tmp_path = tmp.name
            doc = fitz.open(src_path)
            for page in doc:
                for widget in page.widgets():
                    name = widget.field_name
                    if name not in werte:
                        continue
                    val = werte[name]
                    if widget.field_type_string == "CheckBox":
                        is_on = str(val).lower() in ("true", "1", "yes", "ja", "an")
                        widget.field_value = widget.on_state() if is_on else "Off"
                    else:
                        widget.field_value = str(val)
                    widget.update()
            doc.save(tmp_path, incremental=False)
            doc.close()
            shutil.move(tmp_path, out_path)
            tmp_path = None
            v["datei"] = out_name
            # Auto-Unterschrift wenn Position für diese Vorlage gespeichert ist
            upos = v.get("unterschrift_position")
            if upos:
                u_pfad = _find_unterschrift()
                if u_pfad:
                    s_out_name = f"{vid}_signed.pdf"
                    s_out_path = os.path.join(_FILES, s_out_name)
                    s_tmp = None
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=_FILES) as sf:
                            s_tmp = sf.name
                        sdoc = fitz.open(out_path)
                        pn = min(int(upos.get("page", 0)), len(sdoc) - 1)
                        srect = fitz.Rect(
                            upos["x"], upos["y"],
                            upos["x"] + upos["width"], upos["y"] + upos["height"]
                        )
                        sdoc[pn].insert_image(srect, filename=u_pfad, keep_proportion=True)
                        sdoc.save(s_tmp)
                        sdoc.close()
                        shutil.move(s_tmp, s_out_path)
                        s_tmp = None
                        v["datei"] = s_out_name
                        out_name = s_out_name
                    except Exception:
                        if s_tmp and os.path.exists(s_tmp):
                            os.remove(s_tmp)
            _save(vorlagen)
            return jsonify({"ok": True, "datei": out_name})
        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            return jsonify({"ok": False, "error": str(e)}), 500


def _fmt_datum(datum_str: str) -> str:
    try:
        return datetime.strptime(datum_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return datum_str


def _baue_brief_html(v: dict, absender: dict, betreff: str, briefkoerper: str) -> str:
    """Baut ein druckbares DIN-5008-konformes HTML-Dokument."""
    heute = datetime.today().strftime("%d.%m.%Y")

    # Hinterlegte Unterschrift laden
    unterschrift_pfad = _find_unterschrift()
    unterschrift_img_html = ""
    name_margin = "margin-top:16mm"  # Leerraum für manuelle Unterschrift
    if unterschrift_pfad:
        ext  = os.path.splitext(unterschrift_pfad)[1].lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        with open(unterschrift_pfad, "rb") as uf:
            udata = base64.b64encode(uf.read()).decode()
        unterschrift_img_html = (
            f'<img src="data:{mime};base64,{udata}" '
            f'style="max-height:55px;max-width:180px;display:block;'
            f'margin-top:12mm;margin-bottom:3mm">'
        )
        name_margin = "margin-top:0"

    def he(s: str) -> str:
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Absender-Kurzzeile (über dem Empfängerfenster — sichtbar im Fensterkuvert)
    abs_name    = absender.get("name", "")
    abs_adresse = absender.get("adresse", "")
    abs_kurz    = abs_name
    if abs_adresse:
        abs_kurz += " · " + abs_adresse.replace("\n", ", ").strip()

    # Ort aus letzter Zeile der Absenderadresse extrahieren
    ort = ""
    if abs_adresse:
        letzte = abs_adresse.strip().splitlines()[-1]
        m = re.match(r"^\d{5}\s+(.+)", letzte.strip())
        if m:
            ort = m.group(1)
    ort_datum = f"{ort + ', ' if ort else ''}{heute}"

    # Empfänger-Block
    empf       = v.get("empfaenger", {})
    empf_zeile = "\n".join(z for z in [empf.get("name", ""), empf.get("adresse", "")] if z)

    # Betreff (ggf. mehrzeilig — erste Zeile fett, Rest normal)
    betreff_zeilen = betreff.strip().splitlines()
    betreff_html   = "<strong>" + he(betreff_zeilen[0]) + "</strong>"
    if len(betreff_zeilen) > 1:
        betreff_html += "<br>" + "<br>".join(he(z) for z in betreff_zeilen[1:])

    # Briefkörper: Zeilenumbrüche → <br>-Paare für Absätze
    koerper_html = briefkoerper.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    abs_email_html = (
        f'<div style="font-size:9pt;color:#555;margin-top:2mm">{he(absender.get("email",""))}</div>'
        if absender.get("email") else ""
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>{he(v.get('name','Brief'))}</title>
<style>
@page {{ size: A4; margin: 10mm 20mm 19mm 25mm; }}
@media print {{
  .no-print {{ display: none !important; }}
  body {{ background: white !important; }}
  .page {{ box-shadow: none !important; margin: 0 !important; }}
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: Arial, Helvetica, sans-serif;
  font-size: 11pt;
  background: #dde3ea;
  color: #000;
}}
.page {{
  width: 210mm;
  min-height: 297mm;
  background: white;
  margin: 16px auto 40px;
  padding: 10mm 20mm 25mm 25mm;
  box-shadow: 0 3px 18px rgba(0,0,0,.18);
}}
/* Absender-Kurzzeile (DIN 5008: Angabe über dem Empfängerfenster) */
.abs-kurz {{
  font-size: 7.5pt;
  color: #555;
  border-bottom: 0.4pt solid #bbb;
  padding-bottom: 1.5mm;
  margin-bottom: 3mm;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
/* Empfänger-Block: 40mm Höhe passt ins Fensterkuvert */
.empf-block {{
  height: 40mm;
  font-size: 11pt;
  line-height: 1.45;
  white-space: pre-line;
  padding-top: 5mm;
}}
/* Datum rechtsbündig */
.datum {{
  text-align: right;
  margin-top: 8mm;
  margin-bottom: 12mm;
  font-size: 11pt;
}}
/* Betreff fett */
.betreff {{
  margin-bottom: 8mm;
  font-size: 11pt;
  line-height: 1.5;
}}
/* Brieftext — white-space:pre-wrap erhält Absätze */
.brieftext {{
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 11pt;
}}
/* Unterschrift-Block */
.unterschrift {{
  margin-top: 12mm;
  font-size: 11pt;
}}
.unterschrift .name {{
  font-weight: bold;
}}
/* Drucken-Leiste (nur am Bildschirm sichtbar) */
.print-bar {{
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 100;
  display: flex;
  gap: 8px;
  background: #10202D;
  border: 1px solid rgba(255,255,255,.12);
  padding: 10px 14px;
  border-radius: 9px;
  box-shadow: 0 4px 18px rgba(0,0,0,.5);
}}
.print-bar button {{
  padding: 7px 18px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}}
.btn-print {{ background: #E0A82E; color: #0B1520; }}
.btn-print:hover {{ background: #C8871B; }}
.btn-close {{ background: #1E3547; color: #E6EEF5; }}
.btn-close:hover {{ background: #274257; }}
@media (max-width: 680px) {{
  .page {{ width: 100%; margin: 0; padding: 8mm 6mm 15mm 8mm; box-shadow: none; }}
}}
</style>
</head>
<body>
<div class="print-bar no-print">
  <button class="btn-print" onclick="window.print()">🖨&nbsp;Drucken / Als PDF speichern</button>
  <button class="btn-close" onclick="window.close()">✕&nbsp;Schließen</button>
</div>

<div class="page">
  <div class="abs-kurz">{he(abs_kurz)}</div>
  <div class="empf-block">{he(empf_zeile)}</div>
  <div class="datum">{he(ort_datum)}</div>
  <div class="betreff">{betreff_html}</div>
  <div class="brieftext">{koerper_html}</div>
  <div class="unterschrift">
    {unterschrift_img_html}
    <div class="name" style="{name_margin}">{he(abs_name)}</div>
    {abs_email_html}
  </div>
</div>
</body>
</html>"""
