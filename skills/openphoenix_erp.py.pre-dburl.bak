"""
openphoenix_erp.py – OpenPhoenix ERP Skill für Ilija v2.2
==========================================================
Verbindet Ilija mit OpenPhoenix ERP v2 und v3.
V3 erweitert V2 um: Angebote, Eingangsbelege, DATEV-Export, Backup.

SETUP:
  Einmalig: erp_pfad_setzen(pfad="C:/Pfad/zu/OpenPhoenixERP_V2")
       oder: erp_pfad_setzen(pfad="C:/Pfad/zu/OpenPhoenixERP_V3")
"""

import os
import sys
import json
import smtplib
import logging
import functools
from pathlib import Path
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# KONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "openphoenix_config.json"
)

def _config_laden() -> dict:
    try:
        if os.path.exists(_CONFIG_FILE):
            return json.loads(Path(_CONFIG_FILE).read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"erp_pfad": ""}

def _config_speichern(cfg: dict):
    os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
    Path(_CONFIG_FILE).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def _erp_pfad() -> str:
    return _config_laden().get("erp_pfad", "")

def _erp_verfuegbar() -> bool:
    pfad = _erp_pfad()
    return bool(pfad) and os.path.exists(os.path.join(pfad, "main.py"))

def _erp_einbinden() -> bool:
    """Bindet OpenPhoenix in sys.path ein, damit Imports funktionieren."""
    pfad = _erp_pfad()
    if pfad and pfad not in sys.path:
        sys.path.insert(0, pfad)
    return _erp_verfuegbar()

def _db_url() -> str:
    """Liefert die korrekte SQLAlchemy-URL für OpenPhoenix."""
    # config.get_database_url() löst relativen DB-Pfad relativ zu config.toml auf
    from core.config import config
    return config.get_database_url()

# ══════════════════════════════════════════════════════════════════════════
# DECORATOR – Session-Management (Gemini-Tipp 1)
# ══════════════════════════════════════════════════════════════════════════

def erp_skill(func):
    """
    Decorator für alle ERP-Skill-Funktionen.
    Übernimmt: Verfügbarkeitsprüfung, db.initialize(), Session-Lifecycle,
    commit/rollback, close – auch bei Exceptions.
    Injiziert 'session' als ersten Parameter.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not _erp_einbinden():
            return (
                "❌ OpenPhoenix ERP ist nicht konfiguriert.\n"
                "Bitte zuerst ausführen: erp_pfad_setzen(pfad=\"C:/Pfad/zu/OpenPhoenixERP_V2\") "
                "oder erp_pfad_setzen(pfad=\"C:/Pfad/zu/OpenPhoenixERP_V3\")"
            )
        try:
            from core.db.engine import db
            db.initialize(_db_url())
            session = db.get_session()
            try:
                result = func(session, *args, **kwargs)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            logger.error(f"ERP-Skill '{func.__name__}': {e}", exc_info=True)
            return f"❌ Fehler in {func.__name__}: {e}"
    return wrapper

# ══════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════

def _fmt_euro(betrag) -> str:
    try:
        return f"{float(betrag):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"{betrag} €"

def _fmt_datum(d) -> str:
    if d is None:
        return "–"
    try:
        if isinstance(d, str):
            d = datetime.fromisoformat(d).date()
        return d.strftime("%d.%m.%Y")
    except Exception:
        return str(d)

def _tage_ueberfaellig(faellig) -> int:
    try:
        if isinstance(faellig, str):
            faellig = datetime.fromisoformat(faellig).date()
        return (date.today() - faellig).days
    except Exception:
        return 0

def _smtp_senden(empfaenger_email: str, betreff: str,
                 text: str, anhang_pfad: str = "") -> tuple:
    """Versendet eine E-Mail über die OpenPhoenix SMTP-Konfiguration."""
    try:
        from core.config import config
        from core.services.credential_service import passwort_laden

        smtp_server = config.get("smtp", "server", "")
        smtp_port   = int(config.get("smtp", "port", 587))
        smtp_user   = config.get("smtp", "user", "")
        smtp_pw     = passwort_laden()
        smtp_enc    = config.get("smtp", "encryption", "STARTTLS")

        if not smtp_server or not smtp_user:
            return False, "SMTP nicht konfiguriert (Einstellungen → SMTP)."

        msg = MIMEMultipart()
        msg["From"]    = smtp_user
        msg["To"]      = empfaenger_email
        msg["Subject"] = betreff
        msg.attach(MIMEText(text, "plain", "utf-8"))

        if anhang_pfad and os.path.exists(anhang_pfad):
            with open(anhang_pfad, "rb") as f:
                teil = MIMEBase("application", "octet-stream")
                teil.set_payload(f.read())
            encoders.encode_base64(teil)
            teil.add_header("Content-Disposition",
                            f"attachment; filename={os.path.basename(anhang_pfad)}")
            msg.attach(teil)

        if smtp_enc == "SSL/TLS":
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15) as s:
                s.login(smtp_user, smtp_pw)
                s.sendmail(smtp_user, [empfaenger_email], msg.as_bytes())
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as s:
                s.ehlo()
                if smtp_enc == "STARTTLS":
                    s.starttls()
                s.login(smtp_user, smtp_pw)
                s.sendmail(smtp_user, [empfaenger_email], msg.as_bytes())

        return True, f"E-Mail an {empfaenger_email} gesendet."
    except Exception as e:
        return False, f"SMTP-Fehler: {e}"

# ══════════════════════════════════════════════════════════════════════════
# ÖFFENTLICHE SKILL-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════

def erp_pfad_setzen(pfad: str) -> str:
    """
    Verbindet Ilija mit OpenPhoenix ERP (V2 oder V3). Einmalig ausführen.
    Beispiel V2: erp_pfad_setzen(pfad="C:/Users/manue/OpenPhoenixERP_V2")
    Beispiel V3: erp_pfad_setzen(pfad="C:/Users/manue/OpenPhoenixERP_V3")
    """
    pfad = pfad.strip().strip('"').strip("'")
    if not os.path.exists(pfad):
        return f"❌ Pfad nicht gefunden: {pfad}"
    if not os.path.exists(os.path.join(pfad, "main.py")):
        return f"❌ Kein OpenPhoenix ERP unter: {pfad}"

    cfg = _config_laden()
    cfg["erp_pfad"] = pfad
    _config_speichern(cfg)
    sys.path.insert(0, pfad)

    try:
        from core.db.engine import db
        from core.config import config
        db.initialize(config.get_database_url())
        firma = config.get("company", "name", "–")
        return f"✅ OpenPhoenix ERP verbunden!\n📂 Pfad: {pfad}\n🏢 Firma: {firma}"
    except Exception as e:
        return f"⚠️ Pfad gespeichert, Verbindungstest fehlgeschlagen: {e}"


@erp_skill
def erp_status(session) -> str:
    """
    Vollständige Geschäftsübersicht: offene Rechnungen, überfällige
    Forderungen, Gesamtumsatz und kritischer Lagerbestand.
    Beispiel: erp_status()
    """
    from core.services.rechnungen_service import RechnungsService
    from core.services.lager_service import LagerService
    from core.config import config

    firma  = config.get("company", "name", "Unbekannt")
    alle_r = RechnungsService().alle(session)           # ← alle(), nicht liste()
    lager  = LagerService().alle_artikel(session)       # ← alle_artikel()

    offen = [r for r in alle_r if r.status in [
        "Offen", "Steht zur Erinnerung an",
        "Steht zur Mahnung an", "Steht zur Mahnung 2 an",
        "Bitte an Inkasso weiterleiten"
    ]]
    ueberfaellig = [r for r in offen if r.status != "Offen"]
    inkasso      = [r for r in alle_r if r.status == "Bitte an Inkasso weiterleiten"]
    umsatz       = sum(float(r.summe_brutto or 0)
                       for r in alle_r if r.status not in ["Entwurf", "Storniert"])
    kritisch     = [a for a in lager if float(a.verfuegbar or 0) < 5]

    zeilen = [
        f"📊 OpenPhoenix ERP – Übersicht ({firma})",
        f"Stand: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        "── Rechnungen ──────────────────────────",
        f"  💰 Offene Forderungen:  {len(offen)} / {_fmt_euro(sum(float(r.summe_brutto or 0) for r in offen))}",
        f"  ⚠️  Überfällig:          {len(ueberfaellig)} / {_fmt_euro(sum(float(r.summe_brutto or 0) for r in ueberfaellig))}",
        f"  🔴 Inkasso-Stufe:       {len(inkasso)}",
        f"  📈 Gesamtumsatz:        {_fmt_euro(umsatz)}",
    ]

    if kritisch:
        zeilen += ["", "── Lager – Kritisch ──────────────────────"]
        for a in kritisch[:5]:
            zeilen.append(f"  🔴 [{a.artikelnummer}] {a.beschreibung}: {a.verfuegbar} {a.einheit}")
        if len(kritisch) > 5:
            zeilen.append(f"  ... und {len(kritisch)-5} weitere")
    else:
        zeilen.append("\n  ✅ Lager: kein kritischer Bestand")

    return "\n".join(zeilen)


@erp_skill
def erp_offene_rechnungen(session) -> str:
    """
    Listet alle offenen Rechnungen mit Fälligkeit, Betrag und Status.
    Beispiel: erp_offene_rechnungen()
    """
    from core.services.rechnungen_service import RechnungsService

    alle  = RechnungsService().alle(session)            # ← alle()
    offen = [r for r in alle if r.status in [
        "Offen", "Steht zur Erinnerung an",
        "Steht zur Mahnung an", "Steht zur Mahnung 2 an",
        "Bitte an Inkasso weiterleiten"
    ]]

    if not offen:
        return "✅ Keine offenen Rechnungen."

    offen.sort(key=lambda r: str(r.faelligkeitsdatum or ""))
    zeilen = [f"📋 {len(offen)} offene Rechnung(en):\n"]
    for r in offen:
        tage  = _tage_ueberfaellig(r.faelligkeitsdatum)
        ueber = f" ⚠️ {tage}d überfällig" if tage > 0 else ""
        zeilen.append(
            f"  [{r.rechnungsnummer}] {r.kunde_display} – "
            f"{_fmt_euro(r.summe_brutto)} – "
            f"fällig {_fmt_datum(r.faelligkeitsdatum)}{ueber}\n"
            f"    Status: {r.status}"
        )
    return "\n".join(zeilen)


@erp_skill
def erp_ueberfaellige_pruefen(session) -> str:
    """
    Prüft alle überfälligen Rechnungen und eskaliert automatisch auf
    die nächste Mahnstufe (Erinnerung → Mahnung 1 → Mahnung 2 → Inkasso).
    Beispiel: erp_ueberfaellige_pruefen()
    """
    from core.services.mahnwesen_service import MahnwesenService

    eskaliert = MahnwesenService().pruefe_und_eskaliere(session)

    if not eskaliert:
        return "✅ Keine Eskalationen notwendig."

    zeilen = [f"📬 {len(eskaliert)} Rechnung(en) eskaliert:\n"]
    for r in eskaliert:
        zeilen.append(f"  [{r.rechnungsnummer}] → {r.status}")
    return "\n".join(zeilen)


@erp_skill
def erp_rechnung_status_setzen(session, rechnungsnummer: str, status: str) -> str:
    """
    Ändert den Status einer Rechnung manuell.
    Gültige Status: Bezahlt, Offen, Steht zur Erinnerung an,
                    Steht zur Mahnung an, Steht zur Mahnung 2 an,
                    Bitte an Inkasso weiterleiten
    Beispiel: erp_rechnung_status_setzen(rechnungsnummer="2026-0018", status="Bezahlt")
    """
    from core.services.rechnungen_service import RechnungsService, RechnungStatus
    from core.models import Rechnung

    rechnung = session.query(Rechnung)\
        .filter(Rechnung.rechnungsnummer == rechnungsnummer).first()
    if not rechnung:
        return f"❌ Rechnung {rechnungsnummer} nicht gefunden."

    if status not in RechnungStatus.MANUELL_SETZBAR:
        return (f"❌ Ungültiger Status: '{status}'\n"
                f"Erlaubt: {', '.join(RechnungStatus.MANUELL_SETZBAR)}")

    alter_status = rechnung.status
    ergebnis = RechnungsService().status_aendern(   # ← status_aendern(), nicht status_setzen()
        session, rechnung.id, status,
        bemerkung_zusatz="Von Ilija gesetzt"
    )
    if not ergebnis.success:
        return f"❌ {ergebnis.message}"

    return (f"✅ Rechnung {rechnungsnummer}:\n"
            f"  {alter_status} → {status}\n"
            f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")


@erp_skill
def erp_zahlung_buchen(session, rechnungsnummer: str, betrag: str = "",
                       referenz: str = "") -> str:
    """
    Markiert eine Rechnung als bezahlt (voll oder Teilzahlung).
    Referenz optional – verhindert Doppelbuchungen (z.B. beim Bankimport).
    Beispiel: erp_zahlung_buchen(rechnungsnummer="2026-0018")
    Beispiel: erp_zahlung_buchen(rechnungsnummer="2026-0018", betrag="50.00", referenz="SEPA-2026-03-08")
    """
    from core.models import Rechnung, AuditLog
    from core.services.rechnungen_service import RechnungsService
    from decimal import Decimal

    rechnung = session.query(Rechnung)\
        .filter(Rechnung.rechnungsnummer == rechnungsnummer).first()
    if not rechnung:
        return f"❌ Rechnung {rechnungsnummer} nicht gefunden."

    # Duplikat-Prüfung (Gemini-Tipp 3)
    if referenz:
        duplikat = session.query(AuditLog).filter(
            AuditLog.details.ilike(f"%{referenz}%"),
            AuditLog.entity_id == rechnung.id
        ).first()
        if duplikat:
            return (f"⚠️ Duplikat erkannt! Referenz '{referenz}' wurde bereits gebucht.\n"
                    f"  Buchung vom: {_fmt_datum(duplikat.timestamp)}\n"
                    f"  Keine erneute Buchung vorgenommen.")

    rs        = RechnungsService()
    bemerkung = f"Referenz: {referenz}" if referenz else ""

    if betrag:
        teil = Decimal(betrag.replace(",", "."))
        ergebnis = rs.teilzahlung_buchen(session, rechnung.id, teil, bemerkung=bemerkung)
        if not ergebnis.success:
            return f"❌ {ergebnis.message}"
        bisher = Decimal(str(rechnung.gezahlter_betrag or 0)) + teil
        offen  = Decimal(str(rechnung.summe_brutto)) - bisher
        if offen <= 0:
            return f"✅ {rechnungsnummer} vollständig bezahlt ({_fmt_euro(bisher)})"
        return (f"✅ Teilzahlung {_fmt_euro(teil)} gebucht.\n"
                f"  Gesamt bezahlt: {_fmt_euro(bisher)}\n"
                f"  Noch offen:     {_fmt_euro(offen)}")
    else:
        ergebnis = rs.status_aendern(               # ← status_aendern()
            session, rechnung.id, "Bezahlt",
            bemerkung_zusatz=bemerkung or "Vollständig bezahlt – Von Ilija"
        )
        if not ergebnis.success:
            return f"❌ {ergebnis.message}"
        return f"✅ Rechnung {rechnungsnummer} als bezahlt markiert."


@erp_skill
def erp_mahnung_erstellen_und_senden(session, rechnungsnummer: str) -> str:
    """
    Erstellt das passende Mahnschreiben als PDF und versendet es per E-Mail.
    Beispiel: erp_mahnung_erstellen_und_senden(rechnungsnummer="2026-0018")
    """
    from core.models import Rechnung, Kunde
    from core.services.mahnwesen_service import MahnwesenService, MahnKonfig
    from core.services.pdf_service import pdf_service
    from core.config import config

    rechnung = session.query(Rechnung)\
        .filter(Rechnung.rechnungsnummer == rechnungsnummer).first()
    if not rechnung:
        return f"❌ Rechnung {rechnungsnummer} nicht gefunden."

    kunde = session.get(Kunde, rechnung.kunde_id)
    if not kunde or not kunde.email:
        return "❌ Keine E-Mail-Adresse für Kund:in hinterlegt."

    # UeberfaelligeDTO über uebersicht() holen –
    # mahnung_als_pdf_bytes() erwartet genau diesen Typ
    konfig   = MahnKonfig.aus_config()              # ← MahnKonfig.aus_config(), nicht get_konfig()
    ueb      = MahnwesenService().uebersicht(session, konfig=konfig)
    dto      = next((d for d in ueb.alle if d.rechnungsnummer == rechnungsnummer), None)

    if dto is None:
        return (f"⚠️ Rechnung {rechnungsnummer} ist nicht im Mahnwesen-Status "
                f"(aktuell: {rechnung.status}). Bitte zuerst Mahnlauf ausführen.")

    pdf_bytes = pdf_service.mahnung_als_pdf_bytes(dto, konfig=konfig)

    tmp_dir  = os.path.join(_erp_pfad(), "tmp_ilija")
    os.makedirs(tmp_dir, exist_ok=True)
    pdf_pfad = os.path.join(tmp_dir, f"Mahnung_{rechnungsnummer.replace('/', '-')}.pdf")
    with open(pdf_pfad, "wb") as f:
        f.write(pdf_bytes)

    status_label = {
        "Steht zur Erinnerung an":       "Zahlungserinnerung",
        "Steht zur Mahnung an":          "1. Mahnung",
        "Steht zur Mahnung 2 an":        "2. Mahnung",
        "Bitte an Inkasso weiterleiten": "Letzte Mahnung",
    }.get(rechnung.status, "Zahlungserinnerung")

    firma   = config.get("company", "name", "")
    betreff = f"{status_label} zur Rechnung Nr. {rechnungsnummer}"
    text    = (f"Sehr geehrte/r {kunde.vorname} {kunde.name},\n\n"
               f"anbei erhalten Sie unsere {status_label} "
               f"zur Rechnung Nr. {rechnungsnummer}.\n\n"
               f"Mit freundlichen Grüßen\n{firma}")

    ok, meldung = _smtp_senden(kunde.email, betreff, text, pdf_pfad)
    try:
        os.remove(pdf_pfad)
    except Exception:
        pass

    if ok:
        return (f"✅ {status_label} für {rechnungsnummer} erstellt und gesendet!\n"
                f"  Empfänger: {kunde.vorname} {kunde.name} <{kunde.email}>")
    return f"⚠️ PDF erstellt, E-Mail fehlgeschlagen: {meldung}"


def erp_mahnlauf_komplett() -> str:
    """
    Vollautomatischer Mahnlauf:
    1. Eskaliert alle überfälligen Rechnungen auf die nächste Stufe
    2. Erstellt und versendet alle fälligen Mahnschreiben per E-Mail
    Beispiel: erp_mahnlauf_komplett()
    """
    erg = erp_ueberfaellige_pruefen()

    if not _erp_einbinden():
        return erg

    try:
        from core.db.engine import db
        from core.models import Rechnung

        db.initialize(_db_url())
        with db.session() as session:
            nummern = [
                r.rechnungsnummer for r in
                session.query(Rechnung).filter(Rechnung.status.in_([
                    "Steht zur Erinnerung an", "Steht zur Mahnung an",
                    "Steht zur Mahnung 2 an",  "Bitte an Inkasso weiterleiten"
                ])).all()
            ]

        if not nummern:
            return f"{erg}\n\n✅ Keine Mahnschreiben zu versenden."

        bericht = [erg, "", f"📧 Versende {len(nummern)} Mahnschreiben:"]
        for nr in nummern:
            ergebnis = erp_mahnung_erstellen_und_senden(rechnungsnummer=nr)
            symbol   = "✅" if "✅" in ergebnis else "❌"
            bericht.append(f"  {symbol} {nr}")

        return "\n".join(bericht)

    except Exception as e:
        return f"❌ Mahnlauf-Fehler: {e}"


@erp_skill
def erp_lager_status(session) -> str:
    """
    Zeigt den aktuellen Lagerbestand, kritische Artikel hervorgehoben.
    Beispiel: erp_lager_status()
    """
    from core.services.lager_service import LagerService

    alle     = LagerService().alle_artikel(session)    # ← alle_artikel()
    if not alle:
        return "📦 Keine Artikel im Lager."

    kritisch = [a for a in alle if float(a.verfuegbar or 0) < 5]
    normal   = [a for a in alle if float(a.verfuegbar or 0) >= 5]
    zeilen   = [f"📦 Lagerübersicht ({len(alle)} Artikel)\n"]

    if kritisch:
        zeilen.append("🔴 KRITISCH (Bestand < 5):")
        for a in sorted(kritisch, key=lambda x: x.verfuegbar):
            zeilen.append(
                f"  [{a.artikelnummer}] {a.beschreibung}: "
                f"{a.verfuegbar} {a.einheit} – {_fmt_euro(a.einzelpreis_netto)} netto"
            )

    if normal:
        zeilen.append("\n✅ Ausreichend vorhanden:")
        for a in sorted(normal, key=lambda x: x.artikelnummer):
            zeilen.append(
                f"  [{a.artikelnummer}] {a.beschreibung}: {a.verfuegbar} {a.einheit}"
            )
    return "\n".join(zeilen)


@erp_skill
def erp_kpi_bericht(session) -> str:
    """
    Vollständiger Wirtschaftsbericht: Umsatz, Forderungen, Zahlungsquote,
    Mahnstatistik.
    Beispiel: erp_kpi_bericht()
    """
    from core.services.rechnungen_service import RechnungsService
    from core.services.kunden_service import KundenService
    from core.config import config

    alle    = RechnungsService().alle(session)          # ← alle()
    kunden  = KundenService().alle(session)             # ← alle()
    heute   = date.today()

    umsatz   = sum(float(r.summe_brutto or 0)
                   for r in alle if r.status not in ["Entwurf", "Storniert", "Gutschrift"])
    umsatz_m = sum(float(r.summe_brutto or 0)
                   for r in alle
                   if r.status not in ["Entwurf", "Storniert", "Gutschrift"]
                   and str(r.rechnungsdatum or "")[:7] == heute.strftime("%Y-%m"))
    forderungen = sum(float(r.summe_brutto or 0) for r in alle
                      if r.status in ["Offen", "Steht zur Erinnerung an",
                                       "Steht zur Mahnung an", "Steht zur Mahnung 2 an",
                                       "Bitte an Inkasso weiterleiten"])

    stufen = {"Erinnerung": 0, "Mahnung 1": 0, "Mahnung 2": 0, "Inkasso": 0}
    for r in alle:
        if   r.status == "Steht zur Erinnerung an":       stufen["Erinnerung"] += 1
        elif r.status == "Steht zur Mahnung an":           stufen["Mahnung 1"] += 1
        elif r.status == "Steht zur Mahnung 2 an":         stufen["Mahnung 2"] += 1
        elif r.status == "Bitte an Inkasso weiterleiten":  stufen["Inkasso"]   += 1

    bezahlt_q = (sum(1 for r in alle if r.status == "Bezahlt") / len(alle) * 100) if alle else 0

    return (
        f"📊 Wirtschaftsbericht – {heute.strftime('%d.%m.%Y')}\n"
        f"{'─'*42}\n"
        f"🏢 Kunden gesamt:          {len(kunden)}\n"
        f"📈 Umsatz gesamt:          {_fmt_euro(umsatz)}\n"
        f"📅 Umsatz {heute.strftime('%B %Y')}:  {_fmt_euro(umsatz_m)}\n"
        f"💳 Offene Forderungen:     {_fmt_euro(forderungen)}\n"
        f"✅ Zahlungsquote:          {bezahlt_q:.1f}%\n"
        f"{'─'*42}\n"
        f"⚠️  Mahnstatus:\n"
        f"  Erinnerungen:  {stufen['Erinnerung']}\n"
        f"  1. Mahnungen:  {stufen['Mahnung 1']}\n"
        f"  2. Mahnungen:  {stufen['Mahnung 2']}\n"
        f"  Inkasso:       {stufen['Inkasso']}\n"
    )


@erp_skill
def erp_kunde_info(session, suchbegriff: str) -> str:
    """
    Sucht einen Kunden und zeigt Stammdaten, Rechnungshistorie und Notizen.
    Beispiel: erp_kunde_info(suchbegriff="Müller")
    """
    from core.models import Kunde, Rechnung, KundenNotiz
    from sqlalchemy import or_

    q      = f"%{suchbegriff}%"
    kunden = session.query(Kunde).filter(
        or_(Kunde.vorname.ilike(q), Kunde.name.ilike(q),
            Kunde.email.ilike(q), Kunde.zifferncode.ilike(q))
    ).all()

    if not kunden:
        return f"🔍 Kein Kunde gefunden für: '{suchbegriff}'"

    zeilen = []
    for k in kunden[:3]:
        rechnungen = session.query(Rechnung)\
            .filter(Rechnung.kunde_id == k.id)\
            .order_by(Rechnung.rechnungsdatum.desc()).limit(5).all()
        notizen = session.query(KundenNotiz)\
            .filter(KundenNotiz.kunde_id == k.id)\
            .order_by(KundenNotiz.erstellt_am.desc()).limit(3).all()

        zeilen.append(
            f"👤 {k.anrede or ''} {k.vorname} {k.name} "
            f"(Kd.-Nr. {k.zifferncode or k.id})\n"
            f"  📧 {k.email or '–'}  📞 {k.telefon or '–'}\n"
            f"  📍 {k.strasse or ''} {k.hausnummer or ''}, "
            f"{k.plz or ''} {k.ort or ''}"
        )
        if rechnungen:
            zeilen.append("  📋 Letzte Rechnungen:")
            for r in rechnungen:
                zeilen.append(
                    f"    [{r.rechnungsnummer}] {_fmt_datum(r.rechnungsdatum)} "
                    f"– {_fmt_euro(r.summe_brutto)} – {r.status}"
                )
        if notizen:
            zeilen.append("  📝 Notizen:")
            for n in notizen:
                zeilen.append(f"    • {n.inhalt[:80]}")
        zeilen.append("")

    return "\n".join(zeilen)


# ══════════════════════════════════════════════════════════════════════════
# V3-ERKENNUNG
# ══════════════════════════════════════════════════════════════════════════

def _is_v3() -> bool:
    """Gibt True zurück wenn der eingerichtete ERP-Pfad V3 ist."""
    pfad = _erp_pfad()
    return bool(pfad) and os.path.exists(
        os.path.join(pfad, "core", "services", "angebote_service.py")
    )


def erp_version_info() -> str:
    """
    Zeigt welche OpenPhoenix-Version verbunden ist (V2 oder V3).
    Beispiel: erp_version_info()
    """
    if not _erp_verfuegbar():
        return "❌ Kein ERP verbunden. Bitte erp_pfad_setzen() ausführen."
    version = "V3" if _is_v3() else "V2"
    pfad = _erp_pfad()
    v3_features = ""
    if version == "V3":
        v3_features = "\n\nV3-Features verfügbar:\n  • erp_angebote_liste()\n  • erp_belege_liste()\n  • erp_datev_exportieren()\n  • erp_backup_erstellen()"
    return f"✅ OpenPhoenix ERP {version} verbunden\n📂 Pfad: {pfad}{v3_features}"


# ══════════════════════════════════════════════════════════════════════════
# V3-EXKLUSIVE SKILL-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════

_V3_HINWEIS = "⚠️ Diese Funktion erfordert OpenPhoenix ERP V3. Aktuell ist V2 verbunden."


@erp_skill
def erp_angebote_liste(session, status: str = "") -> str:
    """
    Listet alle Angebote (nur OpenPhoenix V3).
    Status-Filter optional: Entwurf, Offen, Angenommen, Abgelehnt, Abgelaufen
    Beispiel: erp_angebote_liste()
    Beispiel: erp_angebote_liste(status="Offen")
    """
    if not _is_v3():
        return _V3_HINWEIS
    from core.services.angebote_service import AngebotsService

    status_filter = [status] if status else None
    alle = AngebotsService().alle(session, status_filter=status_filter)
    if not alle:
        return f"📋 Keine Angebote{' mit Status ' + status if status else ''} gefunden."

    zeilen = [f"📄 {len(alle)} Angebot(e):\n"]
    for a in alle:
        zeilen.append(
            f"  [{a.angebotsnummer}] {a.kunde_display} – "
            f"{_fmt_euro(a.summe_brutto)} – {a.status} – "
            f"gültig bis {_fmt_datum(a.gueltig_bis)}"
        )
    return "\n".join(zeilen)


@erp_skill
def erp_belege_liste(session, status: str = "") -> str:
    """
    Listet alle Eingangsrechnungen/Belege (nur OpenPhoenix V3).
    Status-Filter optional: Offen, Bezahlt, Überfällig
    Beispiel: erp_belege_liste()
    Beispiel: erp_belege_liste(status="Offen")
    """
    if not _is_v3():
        return _V3_HINWEIS
    from core.services.belege_service import BelegeService

    alle = BelegeService().alle_belege(session, zahlungsstatus=status)
    if not alle:
        return f"📋 Keine Belege{' mit Status ' + status if status else ''} gefunden."

    gesamt = sum(float(b.betrag_brutto or 0) for b in alle)
    zeilen = [f"🧾 {len(alle)} Beleg(e) – gesamt {_fmt_euro(gesamt)}:\n"]
    for b in alle[:20]:
        zeilen.append(
            f"  [{b.belegnummer}] {b.lieferant or '–'} – "
            f"{_fmt_euro(b.betrag_brutto)} – {b.zahlungsstatus} – "
            f"Datum {b.datum}"
        )
    if len(alle) > 20:
        zeilen.append(f"  ... und {len(alle)-20} weitere")
    return "\n".join(zeilen)


def erp_datev_exportieren(von: str = "", bis: str = "", ausgabe_pfad: str = "") -> str:
    """
    Exportiert Buchungen im DATEV-CSV-Format für den Steuerberater (nur V3).
    von/bis: Zeitraum als TT.MM.JJJJ – Standard: aktuelles Jahr
    ausgabe_pfad optional – Standard: ERP-Verzeichnis/datev_export/
    Beispiel: erp_datev_exportieren()
    Beispiel: erp_datev_exportieren(von="01.01.2026", bis="31.03.2026", ausgabe_pfad="C:/Steuerberater")
    """
    if not _erp_einbinden():
        return "❌ ERP nicht verbunden."
    if not _is_v3():
        return _V3_HINWEIS
    try:
        from core.db.engine import db
        from core.services.datev_service import DatevService

        heute = date.today()
        von  = von  or f"01.01.{heute.year}"
        bis  = bis  or f"31.12.{heute.year}"
        ziel = ausgabe_pfad or os.path.join(_erp_pfad(), "datev_export")
        os.makedirs(ziel, exist_ok=True)

        db.initialize(_db_url())
        with db.session() as session:
            ergebnis = DatevService().exportieren(session, von=von, bis=bis)
            csv_pfad = os.path.join(ziel, ergebnis.dateiname)
            with open(csv_pfad, "wb") as f:
                f.write(ergebnis.csv_bytes)
            return (f"✅ DATEV-Export erfolgreich!\n"
                    f"📂 Datei:    {csv_pfad}\n"
                    f"📅 Zeitraum: {von} – {bis}\n"
                    f"📄 Buchungen: {ergebnis.anzahl_buchungen}\n"
                    f"💰 AR-Summe: {_fmt_euro(ergebnis.summe_ar)} | "
                    f"ER-Summe: {_fmt_euro(ergebnis.summe_er)}")
    except Exception as e:
        return f"❌ Fehler beim DATEV-Export: {e}"


def erp_backup_erstellen(ausgabe_pfad: str = "") -> str:
    """
    Erstellt ein vollständiges Backup (Datenbank + Konfiguration) als ZIP (nur V3).
    ausgabe_pfad optional – Standard: ERP-Verzeichnis/backups/
    Beispiel: erp_backup_erstellen()
    Beispiel: erp_backup_erstellen(ausgabe_pfad="G:/Backups/ERP")
    """
    if not _erp_einbinden():
        return "❌ ERP nicht verbunden."
    if not _is_v3():
        return _V3_HINWEIS
    try:
        from core.services.backup_service import erstelle_backup, vorgeschlagener_dateiname

        ziel_dir = ausgabe_pfad or os.path.join(_erp_pfad(), "backups")
        os.makedirs(ziel_dir, exist_ok=True)
        ziel_datei = os.path.join(ziel_dir, vorgeschlagener_dateiname())
        pfad = erstelle_backup(ziel_datei)
        groesse = os.path.getsize(pfad) / 1024
        return (f"✅ Backup erstellt!\n"
                f"📦 Datei: {pfad}\n"
                f"📊 Größe: {groesse:.1f} KB")
    except Exception as e:
        return f"❌ Backup fehlgeschlagen: {e}"


# ══════════════════════════════════════════════════════════════════════════
# SKILL-REGISTRIERUNG
# ══════════════════════════════════════════════════════════════════════════

AVAILABLE_SKILLS = [
    erp_pfad_setzen,
    erp_version_info,
    erp_status,
    erp_offene_rechnungen,
    erp_ueberfaellige_pruefen,
    erp_rechnung_status_setzen,
    erp_zahlung_buchen,
    erp_mahnung_erstellen_und_senden,
    erp_mahnlauf_komplett,
    erp_lager_status,
    erp_kpi_bericht,
    erp_kunde_info,
    # V3-exklusiv
    erp_angebote_liste,
    erp_belege_liste,
    erp_datev_exportieren,
    erp_backup_erstellen,
]
