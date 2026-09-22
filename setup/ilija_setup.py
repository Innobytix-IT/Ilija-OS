#!/usr/bin/env python3
"""Ilija OS – Einrichtungs-Assistent (Qt/PySide6).

Grafischer Assistent, der beim Setup / ersten Start die Bausteine (Ilija,
OpenPhönix, AHPT), die KI (lokal/Cloud/keine) und die gemeinsame Ablage
konfiguriert. Dieselbe Logik ist später als Calamares-Modul (im ISO) und im
Systemeinstellungs-Eintrag wiederverwendbar.

Diese Fassung: Willkommen · Hardware-Prüfung · KI-Auswahl · Zusammenfassung.
Weitere Seiten (Firmendaten, Bausteine, Ablage) folgen.
"""
from __future__ import annotations
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QLabel, QVBoxLayout, QHBoxLayout,
    QRadioButton, QLineEdit, QGridLayout, QFrame, QButtonGroup, QWidget,
    QComboBox, QCheckBox, QFormLayout, QMessageBox, QGroupBox, QScrollArea,
)

import apply

# Cloud-Anbieter: (Anzeige, Kennung, Placeholder, env-Variable)
CLOUD_ANBIETER = [
    ("Google Gemini — günstig, empfohlen", "gemini", "Gemini-Schlüssel (z. B. AQ.…)", "GOOGLE_API_KEY"),
    ("Anthropic Claude — beste Qualität", "claude", "Claude-Schlüssel (sk-ant-…)", "ANTHROPIC_API_KEY"),
    ("OpenAI ChatGPT", "openai", "OpenAI-Schlüssel (sk-…)", "OPENAI_API_KEY"),
]

import hardware

def _finde_logo() -> str:
    for p in ("/usr/share/ilija-os/branding/assets/ilija-logo.png",
              os.path.expanduser("~/.local/share/ilija-os/ilija-logo.png")):
        if os.path.exists(p):
            return p
    return ""

ASSET_LOGO = _finde_logo()
MARKER = os.path.expanduser("~/.config/ilija-os/setup-done")
GOLD = "#E8C15A"
BLUE = "#28B6F6"

STYLE = f"""
QWizard, QWizardPage, QWidget {{ background: #0d0f12; color: #EFE6CF;
    font-family: 'Ubuntu','Noto Sans',sans-serif; font-size: 14px; }}
QLabel#h1 {{ color: {GOLD}; font-size: 22px; font-weight: 600; }}
QLabel#h2 {{ color: {GOLD}; font-size: 16px; font-weight: 600; }}
QLabel#dim {{ color: #9a8f77; }}
QLabel#warn {{ color: #E8A05A; }}
QLabel#ok {{ color: {BLUE}; }}
QFrame#card {{ background: #16191e; border: 1px solid #262b33; border-radius: 10px; }}
QRadioButton {{ padding: 8px; font-size: 15px; }}
QRadioButton:disabled {{ color: #55606e; }}
QLineEdit {{ background: #10131a; border: 1px solid #2a303a;
    border-radius: 6px; padding: 8px; color: #EFE6CF; }}
QPushButton {{ background: #1d222b; border: 1px solid #2a303a; border-radius: 6px;
    padding: 8px 16px; color: #EFE6CF; }}
QPushButton:hover {{ border-color: {BLUE}; }}
QWizard QPushButton {{ min-width: 90px; }}
"""


def _logo(max_w=360) -> QLabel:
    lab = QLabel()
    lab.setAlignment(Qt.AlignCenter)
    if os.path.exists(ASSET_LOGO):
        pm = QPixmap(ASSET_LOGO)
        if not pm.isNull():
            lab.setPixmap(pm.scaledToWidth(max_w, Qt.SmoothTransformation))
    else:
        lab.setText("ILIJA OS")
        lab.setObjectName("h1")
    return lab


# --------------------------------------------------------------------------- #
class WillkommenPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(" ")
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        lay.addWidget(_logo(380))
        lay.addSpacing(18)
        t = QLabel("Willkommen bei Ilija OS")
        t.setObjectName("h1"); t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        u = QLabel("Dieser Assistent richtet deine Bausteine ein: den Ilija-KI-"
                   "Assistenten, das OpenPhönix-ERP und den AHPT-Fernzugriff — "
                   "inklusive KI-Auswahl und gemeinsamer Ablage.")
        u.setObjectName("dim"); u.setWordWrap(True); u.setAlignment(Qt.AlignCenter)
        u.setMaximumWidth(560)
        wrap = QHBoxLayout(); wrap.addStretch(1); wrap.addWidget(u); wrap.addStretch(1)
        lay.addSpacing(8); lay.addLayout(wrap)
        lay.addStretch(2)


# --------------------------------------------------------------------------- #
class HardwarePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Hardware-Prüfung")
        self.setSubTitle("Ich prüfe, ob ein lokales KI-Modell auf diesem Gerät läuft.")
        self._lay = QVBoxLayout(self)
        self.card = QFrame(); self.card.setObjectName("card")
        self.grid = QGridLayout(self.card); self.grid.setContentsMargins(18, 18, 18, 18)
        self.grid.setHorizontalSpacing(24); self.grid.setVerticalSpacing(10)
        self._lay.addWidget(self.card)
        self.verdict = QLabel(); self.verdict.setWordWrap(True)
        self._lay.addSpacing(10); self._lay.addWidget(self.verdict)
        self._lay.addStretch(1)

    def _row(self, r, key, val, good=None):
        k = QLabel(key); k.setObjectName("dim")
        v = QLabel(val)
        if good is True: v.setObjectName("ok")
        elif good is False: v.setObjectName("warn")
        self.grid.addWidget(k, r, 0); self.grid.addWidget(v, r, 1)

    def initializePage(self):
        hw = self.wizard().hw
        for i in reversed(range(self.grid.count())):
            self.grid.itemAt(i).widget().deleteLater()
        self._row(0, "Prozessor", f"{hw['cpu_model'] or 'unbekannt'} · {hw['cores']} Kerne")
        self._row(1, "AVX2 (für lokale KI nötig)", "vorhanden" if hw["avx2"] else "fehlt", hw["avx2"])
        self._row(2, "Arbeitsspeicher", f"{hw['ram_gb']:g} GB",
                  hw["ram_gb"] >= hardware.MIN_RAM_GB)
        gpu = hw["gpu_name"] and f"{hw['gpu_name']} ({hw['vram_gb']:g} GB)" or "keine dedizierte GPU"
        self._row(3, "Grafikkarte", gpu, bool(hw["gpu_name"]))
        self._row(4, "Freier Speicher", f"{hw['disk_free_gb']:g} GB",
                  hw["disk_free_gb"] >= hardware.MIN_DISK_GB)
        if hw["lokal_moeglich"]:
            q = "schnell (GPU)" if hw["qualitaet"] == "gpu" else "möglich (CPU, etwas langsamer)"
            self.verdict.setObjectName("ok")
            self.verdict.setText(f"✓ Lokales KI-Modell (Qwen2.5-7B) ist {q}. "
                                 "Du kannst im nächsten Schritt die lokale KI wählen.")
        else:
            grund = ", ".join(hw["gruende"]) or "Hardware nicht ausreichend"
            self.verdict.setObjectName("warn")
            self.verdict.setText(f"⚠ Lokales KI-Modell nicht möglich: {grund}.\n"
                                 "Im nächsten Schritt sind daher nur Cloud-KI (Gemini) "
                                 "oder 'ohne KI' wählbar.")
        self.verdict.style().unpolish(self.verdict); self.verdict.style().polish(self.verdict)


# --------------------------------------------------------------------------- #
class KiPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Künstliche Intelligenz")
        self.setSubTitle("Womit soll Ilija denken?")
        lay = QVBoxLayout(self)
        self.grp = QButtonGroup(self)

        # Lokal
        self.r_local = QRadioButton("Lokales KI-Modell — Qwen2.5-7B (privat, offline, mitgeliefert)")
        self.local_hint = QLabel(); self.local_hint.setObjectName("dim"); self.local_hint.setWordWrap(True)
        # Cloud
        self.r_api = QRadioButton("Cloud-KI — Online-Anbieter (schnell, benötigt API-Schlüssel)")
        self.provider = QComboBox()
        for anzeige, kennung, _ph, _env in CLOUD_ANBIETER:
            self.provider.addItem(anzeige, kennung)
        self.provider.currentIndexChanged.connect(self._provider_gewechselt)
        self.api_key = QLineEdit(); self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText(CLOUD_ANBIETER[0][2])
        self.api_key.textChanged.connect(self.completeChanged)
        self.provider_hint = QLabel(
            "Welches Modell Sie mit Ihrem API-Schlüssel ansprechen können, "
            "entnehmen Sie bitte der Dokumentation Ihres KI-Anbieters. Ilija nutzt "
            "zunächst das Standardmodell des Anbieters (später in den "
            "Systemeinstellungen änderbar).")
        self.provider_hint.setObjectName("dim"); self.provider_hint.setWordWrap(True)
        # Ohne KI
        self.r_none = QRadioButton("Ohne KI fortfahren")
        self.none_expl = QLabel(
            "Ohne KI bleibt Ilija OS voll nutzbar für DMS, OpenPhönix-ERP und die "
            "gemeinsame Ablage. Es entfällt: der Chat-Assistent, die automatische "
            "Dokument-Auswertung (OCR-Inhalte verstehen, Einsortieren), Telefon- und "
            "Text-Assistenz sowie die Web-Recherche. Du kannst die KI später jederzeit "
            "in den Systemeinstellungen aktivieren.")
        self.none_expl.setObjectName("dim"); self.none_expl.setWordWrap(True)

        for w in (self.r_local, self.local_hint, self.r_api, self.provider,
                  self.api_key, self.provider_hint, self.r_none, self.none_expl):
            lay.addWidget(w)
            if isinstance(w, (QLabel, QLineEdit, QComboBox)):
                w.setContentsMargins(30, 0, 0, 8)
        lay.addStretch(1)
        for r in (self.r_local, self.r_api, self.r_none):
            self.grp.addButton(r)
            r.toggled.connect(self._refresh)

    def initializePage(self):
        hw = self.wizard().hw
        if hw["lokal_moeglich"]:
            self.r_local.setEnabled(True)
            self.local_hint.setText("")
            self.r_local.setChecked(True)
        else:
            self.r_local.setEnabled(False)
            grund = ", ".join(hw["gruende"]) or "Hardware nicht ausreichend"
            self.local_hint.setObjectName("warn")
            self.local_hint.setText(f"⚠ Auf diesem Gerät nicht möglich: {grund}.")
            self.r_api.setChecked(True)
        self._refresh()

    def _refresh(self):
        an = self.r_api.isChecked()
        self.provider.setVisible(an); self.provider.setEnabled(an)
        self.api_key.setVisible(an); self.api_key.setEnabled(an)
        self.provider_hint.setVisible(an)
        self.none_expl.setVisible(self.r_none.isChecked())
        self.completeChanged.emit()

    def _provider_gewechselt(self, _i):
        self.api_key.setPlaceholderText(CLOUD_ANBIETER[self.provider.currentIndex()][2])
        self.api_key.clear()
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        if self.r_api.isChecked():
            return len(self.api_key.text().strip()) >= 8
        return self.r_local.isChecked() or self.r_none.isChecked()

    def validatePage(self) -> bool:
        w = self.wizard()
        if self.r_local.isChecked():
            w.ergebnis["ki_modus"] = "lokal"
            w.ergebnis["modell"] = w.hw["modell"]
        elif self.r_api.isChecked():
            i = self.provider.currentIndex()
            w.ergebnis["ki_modus"] = "cloud"
            w.ergebnis["provider"] = CLOUD_ANBIETER[i][1]
            w.ergebnis["provider_name"] = CLOUD_ANBIETER[i][0].split(" — ")[0]
            w.ergebnis["env_var"] = CLOUD_ANBIETER[i][3]
            w.ergebnis["api_key"] = self.api_key.text().strip()
        else:
            w.ergebnis["ki_modus"] = "keine"
        return True


# --------------------------------------------------------------------------- #
class ZusammenfassungPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Zusammenfassung")
        self.setSubTitle("Diese Einstellungen werden übernommen.")
        self._lay = QVBoxLayout(self)
        self.card = QFrame(); self.card.setObjectName("card")
        self.box = QVBoxLayout(self.card); self.box.setContentsMargins(18, 18, 18, 18)
        self._lay.addWidget(self.card)
        self.rest = QLabel("Mit 'Übernehmen' werden diese Einstellungen geschrieben. "
                           "Übersprungene Integrationen und die AHPT-Kopplung kannst du "
                           "jederzeit in den Systemeinstellungen nachholen.")
        self.rest.setObjectName("dim"); self.rest.setWordWrap(True)
        self._lay.addSpacing(10); self._lay.addWidget(self.rest); self._lay.addStretch(1)

    def initializePage(self):
        for i in reversed(range(self.box.count())):
            self.box.itemAt(i).widget().deleteLater()
        e = self.wizard().ergebnis

        def kopf(txt):
            l = QLabel(txt); l.setObjectName("h2"); self.box.addWidget(l)

        def zeile(txt):
            self.box.addWidget(QLabel(txt))

        b = e.get("bausteine", {})
        aktiv = [n for n, on in [("Ilija", b.get("ilija")),
                 ("OpenPhönix", b.get("erp")), ("AHPT", b.get("ahpt"))] if on]
        kopf("Bausteine"); zeile("• " + (", ".join(aktiv) or "—"))

        modus = {"lokal": f"Lokales Modell ({e.get('modell','?')})",
                 "cloud": f"Cloud-KI ({e.get('provider_name','?')})",
                 "keine": "Ohne KI"}.get(e.get("ki_modus"), "—")
        kopf("KI"); zeile("• " + modus)
        if e.get("ki_modus") == "cloud":
            zeile(f"• {e.get('provider_name','')}-Schlüssel: hinterlegt")

        f = e.get("firma", {})
        if f.get("name"):
            kopf("Firma"); zeile("• " + f["name"])
        kopf("Ablage"); zeile("• " + e.get("ablage_wurzel", "—"))

        kopf("Web-Login")
        zeile("• " + ("Passwort gesetzt" if e.get("web_passwort")
                      else "offen (kein Passwort)"))

        integ = e.get("integrationen", {})
        namen = {"fritzbox": "FritzBox", "telegram": "Telegram",
                 "websuche": "Web-Suche", "kalender": "Google-Kalender",
                 "whatsapp": "WhatsApp/Outlook"}
        an = [namen[k] for k, c in integ.items() if c.get("an")]
        kopf("Integrationen"); zeile("• " + (", ".join(an) or "keine (später nachholbar)"))


class BausteinePage(QWizardPage):
    PAGE_ID = 10  # feste ID fuer nextId()-Steuerung

    def __init__(self):
        super().__init__()
        self.setTitle("Bausteine")
        self.setSubTitle("Welche Teile von Ilija OS möchtest du nutzen? (später änderbar)")
        lay = QVBoxLayout(self)
        self.cb_ilija = QCheckBox("Ilija — KI-Assistent (Chat, DMS-Auswertung, Kalender, Web)")
        self.cb_erp = QCheckBox("OpenPhönix — ERP (Kunden, Rechnungen, XRechnung, DATEV)")
        self.cb_ahpt = QCheckBox("AHPT — sicherer Fernzugriff auf die Ablage")
        for c in (self.cb_ilija, self.cb_erp, self.cb_ahpt):
            c.setChecked(True); lay.addWidget(c)
        lay.addStretch(1)

    def validatePage(self):
        self.wizard().ergebnis["bausteine"] = {
            "ilija": self.cb_ilija.isChecked(),
            "erp": self.cb_erp.isChecked(),
            "ahpt": self.cb_ahpt.isChecked(),
        }
        return True

    def nextId(self):
        if self.cb_ahpt.isChecked():
            return AhptKonfigPage.PAGE_ID
        return AhptKonfigPage.PAGE_ID + 1  # HardwarePage überspringt AHPT


class AhptKonfigPage(QWizardPage):
    PAGE_ID = 11  # direkt nach BausteinePage (ID 10)

    def __init__(self):
        super().__init__()
        self.setTitle("AHPT — Fernzugriff konfigurieren")
        self.setSubTitle(
            "Richte den sicheren Tunnel ein. Alle Werte sind später in den "
            "Systemeinstellungen änderbar."
        )
        lay = QVBoxLayout(self)

        info = QLabel(
            "AHPT (Asymmetric HTTP Polling Tunnel) ermöglicht sicheren Zugriff auf\n"
            "deine Ilija-OS-Ablage von überall — ohne offene Ports oder statische IP.\n"
            "Du benötigst einen AHPT-Relay-Server (z. B. bplaced oder eigener Server)."
        )
        info.setObjectName("dim")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addSpacing(10)

        form = QFormLayout()
        self.relay_url = QLineEdit()
        self.relay_url.setPlaceholderText("https://deinserver.example.com/ahpt/")
        form.addRow("Relay-URL:", self.relay_url)

        self.client_key = QLineEdit()
        self.client_key.setPlaceholderText("32-stelliger Hex-Schlüssel (leer = automatisch generieren)")
        form.addRow("Client-Schlüssel:", self.client_key)

        self.device_name = QLineEdit()
        self.device_name.setPlaceholderText("z. B. Büro-PC oder Laptop-Manuel")
        form.addRow("Gerätename:", self.device_name)

        lay.addLayout(form)

        hint = QLabel(
            "Tipp: Lasse den Client-Schlüssel leer — Ilija OS generiert ihn\n"
            "automatisch beim ersten Start und zeigt dir den QR-Code zum Koppeln."
        )
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        lay.addSpacing(8)
        lay.addWidget(hint)
        lay.addStretch(1)

    def validatePage(self):
        self.wizard().ergebnis["ahpt_konfig"] = {
            "relay_url": self.relay_url.text().strip(),
            "client_key": self.client_key.text().strip(),
            "device_name": self.device_name.text().strip(),
        }
        return True


class FirmendatenPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Firmendaten")
        self.setSubTitle("Für Rechnungen und XRechnung in OpenPhönix (kann leer bleiben).")
        form = QFormLayout(self)
        self.felder = {}
        for schluessel, label in [
            ("name", "Firmenname"), ("strasse", "Straße & Nr."),
            ("plz", "PLZ"), ("ort", "Ort"), ("ustid", "USt-IdNr."),
            ("telefon", "Telefon"), ("email", "E-Mail"),
            ("iban", "IBAN"), ("bic", "BIC"), ("leitweg", "Leitweg-ID (XRechnung)"),
        ]:
            e = QLineEdit(); self.felder[schluessel] = e
            form.addRow(label + ":", e)

    def validatePage(self):
        self.wizard().ergebnis["firma"] = {k: e.text().strip() for k, e in self.felder.items()}
        return True


class AblagePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Gemeinsame Ablage")
        self.setSubTitle("Ein zentraler Ort für alle Dateien – ERP und DMS getrennt.")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Wurzel-Ordner:"))
        self.pfad = QLineEdit(os.path.expanduser("~/Ilija-Ablage"))
        lay.addWidget(self.pfad)
        info = QLabel("Darunter wird angelegt:\n"
                      "  ERP/   – Kunden-/Geschäftsdaten (OpenPhönix)\n"
                      "  DMS/   – persönliche/interne Dateien (Ilija)\n"
                      "So bleiben Kundendaten und interne Dateien getrennt.")
        info.setObjectName("dim"); lay.addSpacing(8); lay.addWidget(info)
        lay.addStretch(1)

    def validatePage(self):
        self.wizard().ergebnis["ablage_wurzel"] = \
            self.pfad.text().strip() or os.path.expanduser("~/Ilija-Ablage")
        return True


class IntegrationenPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Integrationen (optional)")
        self.setSubTitle("Freiwillig – jederzeit später in den Systemeinstellungen nachholbar.")
        aussen = QVBoxLayout(self)
        hinweis = QLabel("Wähle nur, was du jetzt einrichten willst. Übersprungenes "
                         "holst du später mit einem Klick nach.")
        hinweis.setObjectName("dim"); hinweis.setWordWrap(True)
        aussen.addWidget(hinweis)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget(); box = QVBoxLayout(inner)
        aussen.addWidget(scroll, 1); scroll.setWidget(inner)

        self.g_fritz = QGroupBox("FritzBox-Telefonassistent einrichten")
        self.g_fritz.setCheckable(True); self.g_fritz.setChecked(False)
        ff = QFormLayout(self.g_fritz)
        self.sip_server = QLineEdit(); self.sip_user = QLineEdit()
        self.sip_pw = QLineEdit(); self.sip_pw.setEchoMode(QLineEdit.Password)
        ff.addRow("SIP-Server (FritzBox-IP):", self.sip_server)
        ff.addRow("SIP-Benutzer:", self.sip_user)
        ff.addRow("SIP-Passwort:", self.sip_pw)
        box.addWidget(self.g_fritz)

        self.g_tg = QGroupBox("Telegram-Bot einrichten")
        self.g_tg.setCheckable(True); self.g_tg.setChecked(False)
        tf = QFormLayout(self.g_tg)
        self.tg_token = QLineEdit(); self.tg_token.setEchoMode(QLineEdit.Password)
        self.tg_users = QLineEdit()
        tf.addRow("Bot-Token (@BotFather):", self.tg_token)
        tf.addRow("Erlaubte User-IDs:", self.tg_users)
        box.addWidget(self.g_tg)

        self.g_such = QGroupBox("Google-Web-Suche einrichten")
        self.g_such.setCheckable(True); self.g_such.setChecked(False)
        sf = QFormLayout(self.g_such)
        self.such_key = QLineEdit(); self.such_key.setEchoMode(QLineEdit.Password)
        self.such_cx = QLineEdit()
        sf.addRow("Such-API-Schlüssel:", self.such_key)
        sf.addRow("Such-ID (CX):", self.such_cx)
        box.addWidget(self.g_such)

        self.g_cal = QGroupBox("Google-Kalender verbinden")
        self.g_cal.setCheckable(True); self.g_cal.setChecked(False)
        QVBoxLayout(self.g_cal).addWidget(QLabel(
            "Anmeldung beim ersten Start per Google-Login im Browser "
            "(kein Schlüssel hier nötig)."))
        box.addWidget(self.g_cal)

        self.g_wa = QGroupBox("WhatsApp / Outlook verbinden")
        self.g_wa.setCheckable(True); self.g_wa.setChecked(False)
        QVBoxLayout(self.g_wa).addWidget(QLabel(
            "Anmeldung beim ersten Start per Login im Browser-Fenster."))
        box.addWidget(self.g_wa)
        box.addStretch(1)

    def validatePage(self):
        self.wizard().ergebnis["integrationen"] = {
            "fritzbox": {"an": self.g_fritz.isChecked(),
                         "SIP_SERVER": self.sip_server.text().strip(),
                         "SIP_USER": self.sip_user.text().strip(),
                         "SIP_PASSWORD": self.sip_pw.text().strip()},
            "telegram": {"an": self.g_tg.isChecked(),
                         "TELEGRAM_BOT_TOKEN": self.tg_token.text().strip(),
                         "TELEGRAM_ALLOWED_USERS": self.tg_users.text().strip()},
            "websuche": {"an": self.g_such.isChecked(),
                         "GOOGLE_SEARCH_API_KEY": self.such_key.text().strip(),
                         "GOOGLE_SEARCH_CX": self.such_cx.text().strip()},
            "kalender": {"an": self.g_cal.isChecked(), "erststart": True},
            "whatsapp": {"an": self.g_wa.isChecked(), "erststart": True},
        }
        return True


class AnmeldungPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Anmeldung für die Weboberfläche")
        self.setSubTitle("Optionales Passwort für den Zugang zur Ilija-Weboberfläche.")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.pw1 = QLineEdit(); self.pw1.setEchoMode(QLineEdit.Password)
        self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.Password)
        self.pw1.textChanged.connect(self.completeChanged)
        self.pw2.textChanged.connect(self.completeChanged)
        form.addRow("Passwort:", self.pw1)
        form.addRow("Wiederholen:", self.pw2)
        lay.addLayout(form)
        self.hint = QLabel("Leer lassen = ohne Login (nur im vertrauenswürdigen "
                           "Heimnetz empfohlen). Das separate DMS-Passwort (schützt "
                           "Löschen und Pfad-Änderungen) setzt du bei Bedarf in Ilijas "
                           "Einstellungen. Jederzeit später änderbar.")
        self.hint.setObjectName("dim"); self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.err = QLabel(); self.err.setObjectName("warn"); lay.addWidget(self.err)
        lay.addStretch(1)

    def isComplete(self):
        a, b = self.pw1.text(), self.pw2.text()
        if a or b:
            ok = (a == b and len(a) >= 4)
            self.err.setText("" if ok else "Passwörter müssen übereinstimmen (mind. 4 Zeichen).")
            return ok
        self.err.setText("")
        return True

    def validatePage(self):
        self.wizard().ergebnis["web_passwort"] = self.pw1.text()
        return True


class IlijaSetup(QWizard):
    def __init__(self):
        super().__init__()
        self.ergebnis: dict = {}
        self.hw: dict = hardware.erkenne()
        self.setWindowTitle("Ilija OS – Einrichtung")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.setButtonText(QWizard.NextButton, "Weiter")
        self.setButtonText(QWizard.BackButton, "Zurück")
        self.setButtonText(QWizard.FinishButton, "Übernehmen")
        self.setButtonText(QWizard.CancelButton, "Abbrechen")
        self.resize(720, 560)
        self.addPage(WillkommenPage())
        self.setPage(BausteinePage.PAGE_ID, BausteinePage())
        self.setPage(AhptKonfigPage.PAGE_ID, AhptKonfigPage())
        self.addPage(HardwarePage())
        self.addPage(KiPage())
        self.addPage(FirmendatenPage())
        self.addPage(AblagePage())
        self.addPage(AnmeldungPage())
        self.addPage(IntegrationenPage())
        self.addPage(AutoUpdatePage())
        self.addPage(ZusammenfassungPage())
        _start = os.environ.get("ILIJA_SETUP_START")  # nur zum Testen einzelner Seiten
        if _start and _start.isdigit():
            self.setStartId(int(_start))

    def accept(self):
        dry = os.environ.get("ILIJA_SETUP_DRY") == "1"
        zeilen: list[str] = []
        try:
            apply.anwenden(self.ergebnis, dry=dry, log=zeilen.append)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Fehler bei der Einrichtung", str(ex))
            return
        kopf = "Testlauf – es wurde nichts geschrieben.\n\n" if dry \
            else "Ilija OS ist eingerichtet.\n\n"
        QMessageBox.information(self, "Ilija OS", kopf + "\n".join(zeilen[-14:]))
        if not dry:
            try:
                os.makedirs(os.path.dirname(MARKER), exist_ok=True)
                with open(MARKER, "w", encoding="utf-8") as f:
                    f.write("eingerichtet\n")
            except OSError:
                pass
        super().accept()


def main():
    # Autostart-Modus: nur zeigen, wenn noch nicht eingerichtet
    if "--wenn-noetig" in sys.argv and os.path.exists(MARKER):
        return
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = IlijaSetup()
    w.show()
    rc = app.exec()
    if w.result() == QWizard.Accepted:
        print("ERGEBNIS:", w.ergebnis)
    sys.exit(rc)


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------- #
class AutoUpdatePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Automatische Updates")
        self.setSubTitle("Ilija OS kann sich nachts selbst aktualisieren.")
        lay = QVBoxLayout(self)

        info = QLabel(
            "Wenn aktiviert, holt Ilija OS jede Nacht automatisch System- und "
            "Software-Updates. Das System bleibt dabei stets aktuell, "
            "ohne dass du etwas tun musst."
        )
        info.setObjectName("dim"); info.setWordWrap(True)
        lay.addWidget(info)
        lay.addSpacing(16)

        self.cb_enabled = QCheckBox("Automatische Updates aktivieren (empfohlen)")
        self.cb_enabled.setChecked(True)
        self.cb_enabled.toggled.connect(self._refresh)
        lay.addWidget(self.cb_enabled)

        lay.addSpacing(10)
        self.time_row = QWidget()
        tlay = QHBoxLayout(self.time_row); tlay.setContentsMargins(30, 0, 0, 0)
        tlay.addWidget(QLabel("Update-Uhrzeit:"))
        self.combo_time = QComboBox()
        for h in [1, 2, 3, 4, 5]:
            self.combo_time.addItem(f"{h:02d}:00 Uhr", f"{h:02d}:00")
        self.combo_time.setCurrentIndex(2)  # 03:00 als Standard
        tlay.addWidget(self.combo_time)
        tlay.addStretch(1)
        lay.addWidget(self.time_row)

        hint2 = QLabel(
            "Das Update läuft im Hintergrund während du schläfst. "
            "Diese Einstellung kannst du jederzeit unter Einstellungen → Auto-Update ändern."
        )
        hint2.setObjectName("dim"); hint2.setWordWrap(True)
        lay.addSpacing(12); lay.addWidget(hint2)
        lay.addStretch(1)
        self._refresh()

    def _refresh(self):
        self.time_row.setVisible(self.cb_enabled.isChecked())

    def validatePage(self):
        self.wizard().ergebnis["auto_update"] = {
            "enabled": self.cb_enabled.isChecked(),
            "time": self.combo_time.currentData() if self.cb_enabled.isChecked() else "03:00",
        }
        return True
