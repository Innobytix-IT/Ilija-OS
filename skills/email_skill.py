"""
email_skill.py – E-Mail-Integration für Ilija Public Edition
=============================================================
Unterstützte Provider: Gmail, Outlook/Hotmail, GMX, Web.de, Yahoo, Eigener Server
Nutzt ausschließlich Python-Standardbibliothek (imaplib, smtplib) – keine externen Pakete nötig.

Workflow-Reihenfolge:
  1. email_konfigurieren()  →  Zugangsdaten einmalig speichern
  2. email_verbinden()      →  Verbindung prüfen
  3. emails_lesen()         →  Posteingang lesen
  4. email_senden() / email_beantworten()  →  Aktionen
"""

import os
import json
import imaplib
import smtplib
import email as email_lib
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header         import decode_header
from datetime             import datetime

# ── Konfigurationsdatei ──────────────────────────────────────
_CONFIG_DIR  = os.path.join("data", "email")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "email_config.json")

# ── Provider-Voreinstellungen ────────────────────────────────
_PROVIDER_PRESETS = {
    "gmail": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "hinweis":   "Gmail: App-Passwort unter myaccount.google.com/apppasswords erstellen!",
    },
    "outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "hinweis":   "Outlook/Hotmail: Normales Passwort oder App-Passwort verwenden.",
    },
    "gmx": {
        "imap_host": "imap.gmx.net",
        "imap_port": 993,
        "smtp_host": "mail.gmx.net",
        "smtp_port": 587,
        "hinweis":   "GMX: IMAP in den GMX-Einstellungen aktivieren.",
    },
    "webde": {
        "imap_host": "imap.web.de",
        "imap_port": 993,
        "smtp_host": "smtp.web.de",
        "smtp_port": 587,
        "hinweis":   "Web.de: IMAP in den Web.de-Einstellungen aktivieren.",
    },
    "yahoo": {
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 587,
        "hinweis":   "Yahoo: App-Passwort in den Yahoo-Sicherheitseinstellungen erstellen.",
    },
    "eigener": {
        "imap_host": "",
        "imap_port": 993,
        "smtp_host": "",
        "smtp_port": 587,
        "hinweis":   "Eigener Server: imap_host und smtp_host manuell angeben.",
    },
}


def _cfg_laden() -> dict:
    if not os.path.exists(_CONFIG_FILE):
        return {}
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cfg_speichern(cfg: dict):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _header_dekodieren(wert: str) -> str:
    """Dekodiert E-Mail-Header (z.B. UTF-8-kodierte Betreffzeilen)."""
    if not wert:
        return ""
    teile = decode_header(wert)
    ergebnis = []
    for teil, encoding in teile:
        if isinstance(teil, bytes):
            ergebnis.append(teil.decode(encoding or "utf-8", errors="replace"))
        else:
            ergebnis.append(str(teil))
    return " ".join(ergebnis)


# ═══════════════════════════════════════════════════════════════
#  SKILL 1 – Konfigurieren
# ═══════════════════════════════════════════════════════════════

def email_konfigurieren(
    provider:   str = "gmail",
    email_adresse: str = "",
    passwort:   str = "",
    imap_host:  str = "",
    smtp_host:  str = "",
) -> str:
    """
    E-Mail-Provider einrichten und Zugangsdaten speichern.
    Wird einmalig ausgeführt — danach nutzen alle anderen Email-Skills die gespeicherte Konfiguration.
    Beispiel: email_konfigurieren(provider="gmail", email_adresse="deine@gmail.com", passwort="app-passwort")
    Provider: gmail | outlook | gmx | webde | yahoo | eigener
    Für 'eigener': imap_host und smtp_host ebenfalls angeben.
    """
    provider = provider.lower().strip()
    if provider not in _PROVIDER_PRESETS:
        verfuegbar = ", ".join(_PROVIDER_PRESETS.keys())
        return f"❌ Unbekannter Provider '{provider}'. Verfügbar: {verfuegbar}"

    if not email_adresse or not passwort:
        return "❌ Bitte email_adresse und passwort angeben."

    preset = _PROVIDER_PRESETS[provider].copy()

    # Bei eigenem Server: manuelle Hosts überschreiben
    if provider == "eigener":
        if not imap_host or not smtp_host:
            return "❌ Für 'eigener' müssen imap_host und smtp_host angegeben werden."
        preset["imap_host"] = imap_host
        preset["smtp_host"] = smtp_host

    cfg = {
        "provider":       provider,
        "email_adresse":  email_adresse,
        "passwort":       passwort,
        "imap_host":      preset["imap_host"],
        "imap_port":      preset["imap_port"],
        "smtp_host":      preset["smtp_host"],
        "smtp_port":      preset["smtp_port"],
        "konfiguriert_am": datetime.now().isoformat(),
    }

    _cfg_speichern(cfg)

    hinweis = preset.get("hinweis", "")
    return (
        f"✅ E-Mail konfiguriert!\n"
        f"   Provider:  {provider}\n"
        f"   Adresse:   {email_adresse}\n"
        f"   IMAP:      {cfg['imap_host']}:{cfg['imap_port']}\n"
        f"   SMTP:      {cfg['smtp_host']}:{cfg['smtp_port']}\n"
        f"   💡 {hinweis}"
    )


# ═══════════════════════════════════════════════════════════════
#  SKILL 2 – Verbindung prüfen
# ═══════════════════════════════════════════════════════════════

def email_verbinden() -> str:
    """
    Prüft ob die gespeicherte E-Mail-Konfiguration funktioniert (Testverbindung).
    Vorher email_konfigurieren() ausführen.
    Beispiel: email_verbinden()
    """
    cfg = _cfg_laden()
    if not cfg:
        return "❌ Keine Konfiguration gefunden. Bitte zuerst email_konfigurieren() ausführen."

    try:
        imap = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
        imap.login(cfg["email_adresse"], cfg["passwort"])
        status, daten = imap.select("INBOX")
        anzahl = daten[0].decode() if daten and daten[0] else "?"
        imap.logout()
        return (
            f"✅ Verbindung erfolgreich!\n"
            f"   Provider:  {cfg['provider']}\n"
            f"   Adresse:   {cfg['email_adresse']}\n"
            f"   Posteingang: {anzahl} Nachrichten"
        )
    except imaplib.IMAP4.error as e:
        return f"❌ Login fehlgeschlagen: {e}\n💡 Tipp: App-Passwort prüfen oder IMAP-Zugang aktivieren."
    except Exception as e:
        return f"❌ Verbindungsfehler: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 3 – E-Mails lesen
# ═══════════════════════════════════════════════════════════════

def emails_lesen(
    anzahl:   int = 5,
    nur_ungelesen: str = "nein",
    ordner:   str = "INBOX",
) -> str:
    """
    Liest die neuesten E-Mails aus dem Posteingang.
    Beispiel: emails_lesen(anzahl=5, nur_ungelesen="ja")
    anzahl: Wie viele E-Mails anzeigen (Standard: 5)
    nur_ungelesen: 'ja' = nur ungelesene, 'nein' = alle (Standard: nein)
    ordner: Postfach-Ordner (Standard: INBOX)
    """
    cfg = _cfg_laden()
    if not cfg:
        return "❌ Keine Konfiguration. Bitte zuerst email_konfigurieren() ausführen."

    try:
        imap = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
        imap.login(cfg["email_adresse"], cfg["passwort"])
        imap.select(ordner)

        suchkriterium = "UNSEEN" if nur_ungelesen.lower() == "ja" else "ALL"
        status, nachrichten_ids = imap.search(None, suchkriterium)

        if status != "OK" or not nachrichten_ids[0]:
            imap.logout()
            return "📭 Keine E-Mails gefunden."

        ids = nachrichten_ids[0].split()
        # Neueste zuerst
        ids = ids[-anzahl:][::-1]

        ergebnis = []
        for i, msg_id in enumerate(ids, 1):
            status, daten = imap.fetch(msg_id, "(RFC822)")
            if status != "OK" or not daten:
                continue

            raw = daten[0][1]
            msg = email_lib.message_from_bytes(raw)

            absender = _header_dekodieren(msg.get("From", "Unbekannt"))
            betreff  = _header_dekodieren(msg.get("Subject", "(kein Betreff)"))
            datum    = msg.get("Date", "")
            msg_id_header = msg.get("Message-ID", "")

            # Text-Body extrahieren
            body = ""
            if msg.is_multipart():
                for teil in msg.walk():
                    if teil.get_content_type() == "text/plain":
                        charset = teil.get_content_charset() or "utf-8"
                        try:
                            body = teil.get_payload(decode=True).decode(charset, errors="replace")
                        except Exception:
                            body = "[Inhalt nicht lesbar]"
                        break
            else:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    body = msg.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    body = "[Inhalt nicht lesbar]"

            # Body kürzen für Übersicht
            body_kurz = body.strip()[:300].replace("\n", " ").replace("\r", "")
            if len(body.strip()) > 300:
                body_kurz += "…"

            ergebnis.append(
                f"── E-Mail {i} ──────────────────────\n"
                f"Von:      {absender}\n"
                f"Betreff:  {betreff}\n"
                f"Datum:    {datum}\n"
                f"ID:       {msg_id_header}\n"
                f"Inhalt:   {body_kurz}"
            )

        imap.logout()

        if not ergebnis:
            return "📭 Keine E-Mails zum Anzeigen."

        header = f"📬 {len(ergebnis)} E-Mail(s) aus '{ordner}' ({cfg['email_adresse']}):\n\n"
        return header + "\n\n".join(ergebnis)

    except imaplib.IMAP4.error as e:
        return f"❌ IMAP-Fehler: {e}"
    except Exception as e:
        return f"❌ Fehler beim Lesen: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 4 – E-Mail senden
# ═══════════════════════════════════════════════════════════════

def email_senden(
    an:       str = "",
    betreff:  str = "",
    text:     str = "",
) -> str:
    """
    Sendet eine E-Mail über den konfigurierten Provider.
    Beispiel: email_senden(an="empfaenger@example.com", betreff="Hallo", text="Nachrichtentext hier")
    Vorher email_konfigurieren() ausführen.
    """
    cfg = _cfg_laden()
    if not cfg:
        return "❌ Keine Konfiguration. Bitte zuerst email_konfigurieren() ausführen."

    if not an or not betreff or not text:
        return "❌ Bitte an, betreff und text angeben."

    try:
        msg = MIMEMultipart()
        msg["From"]    = cfg["email_adresse"]
        msg["To"]      = an
        msg["Subject"] = betreff
        msg.attach(MIMEText(text, "plain", "utf-8"))

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["email_adresse"], cfg["passwort"])
            server.sendmail(cfg["email_adresse"], an, msg.as_string())

        return (
            f"✅ E-Mail gesendet!\n"
            f"   An:       {an}\n"
            f"   Betreff:  {betreff}\n"
            f"   Von:      {cfg['email_adresse']}"
        )
    except smtplib.SMTPAuthenticationError:
        return "❌ Authentifizierungsfehler. App-Passwort prüfen."
    except smtplib.SMTPException as e:
        return f"❌ SMTP-Fehler: {e}"
    except Exception as e:
        return f"❌ Fehler beim Senden: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 5 – E-Mail beantworten
# ═══════════════════════════════════════════════════════════════

def email_beantworten(
    message_id: str = "",
    antwort_text: str = "",
    an:         str = "",
    betreff:    str = "",
) -> str:
    """
    Beantwortet eine E-Mail. Die Message-ID kommt aus emails_lesen().
    Wenn an und betreff direkt angegeben werden, werden diese verwendet (ohne Message-ID).
    Beispiel: email_beantworten(an="absender@example.com", betreff="Re: Original", antwort_text="Danke für deine Nachricht!")
    Vorher email_konfigurieren() ausführen.
    """
    if not antwort_text:
        return "❌ Bitte antwort_text angeben."

    # Wenn direkte Empfängerangabe: einfach senden
    if an and betreff:
        return email_senden(an=an, betreff=betreff, text=antwort_text)

    # Ohne Empfänger und ohne Message-ID: Fehler
    if not message_id:
        return "❌ Bitte entweder message_id (aus emails_lesen) oder an + betreff angeben."

    cfg = _cfg_laden()
    if not cfg:
        return "❌ Keine Konfiguration. Bitte zuerst email_konfigurieren() ausführen."

    try:
        # Original-E-Mail via IMAP suchen
        imap = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
        imap.login(cfg["email_adresse"], cfg["passwort"])
        imap.select("INBOX")

        status, ids = imap.search(None, f'HEADER Message-ID "{message_id}"')
        if status != "OK" or not ids[0]:
            imap.logout()
            return f"❌ E-Mail mit ID '{message_id}' nicht gefunden."

        msg_id = ids[0].split()[-1]
        status, daten = imap.fetch(msg_id, "(RFC822)")
        imap.logout()

        if status != "OK":
            return "❌ E-Mail konnte nicht geladen werden."

        original = email_lib.message_from_bytes(daten[0][1])
        absender  = original.get("From", "")
        orig_subj = _header_dekodieren(original.get("Subject", ""))
        reply_subj = orig_subj if orig_subj.startswith("Re:") else f"Re: {orig_subj}"

        return email_senden(an=absender, betreff=reply_subj, text=antwort_text)

    except Exception as e:
        return f"❌ Fehler beim Beantworten: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 6 – Status anzeigen
# ═══════════════════════════════════════════════════════════════

def email_status() -> str:
    """
    Zeigt die aktuelle E-Mail-Konfiguration an (ohne Passwort).
    Beispiel: email_status()
    """
    cfg = _cfg_laden()
    if not cfg:
        return (
            "📭 Noch kein E-Mail-Provider konfiguriert.\n"
            "Führe email_konfigurieren() aus um zu starten.\n"
            "Verfügbare Provider: gmail, outlook, gmx, webde, yahoo, eigener"
        )

    passwort_anzeige = "*" * min(len(cfg.get("passwort", "")), 8)
    return (
        f"📧 E-Mail-Konfiguration:\n"
        f"   Provider:   {cfg.get('provider', '?')}\n"
        f"   Adresse:    {cfg.get('email_adresse', '?')}\n"
        f"   IMAP:       {cfg.get('imap_host')}:{cfg.get('imap_port')}\n"
        f"   SMTP:       {cfg.get('smtp_host')}:{cfg.get('smtp_port')}\n"
        f"   Passwort:   {passwort_anzeige}\n"
        f"   Eingerichtet: {cfg.get('konfiguriert_am', '?')[:10]}"
    )


# ═══════════════════════════════════════════════════════════════
#  AVAILABLE_SKILLS – automatisch von SkillManager geladen
# ═══════════════════════════════════════════════════════════════

AVAILABLE_SKILLS = [
    email_konfigurieren,
    email_verbinden,
    emails_lesen,
    email_senden,
    email_beantworten,
    email_status,
]
