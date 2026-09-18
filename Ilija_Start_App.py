"""
Ilija AI – Setup Assistent & Control Center
Modernisierte GUI mit CustomTkinter (pip install customtkinter)
"""

import os
import sys
import json
import shutil
import hashlib
import threading
import webbrowser
import subprocess

# CustomTkinter – modernes, natives Dark-Mode UI
# Fallback auf TKinter falls customtkinter nicht installiert ist
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import customtkinter as ctk
    from customtkinter import CTkFont
    HAS_CTK = True
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
except ImportError:
    HAS_CTK = False
    print("HINWEIS: customtkinter nicht installiert. Bitte ausführen: pip install customtkinter")
    print("Starte mit Standard-TKinter als Fallback...")

if HAS_CTK:
    from tkinter import messagebox, filedialog


# ─────────────────────────────────────────────────────────────────────────────
# Pfad-Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_env_path():
    return os.path.join(get_base_dir(), '.env')

def _ensure_env_exists():
    env_path = get_env_path()
    if not os.path.exists(env_path):
        example = os.path.join(get_base_dir(), '.env.example')
        if os.path.exists(example):
            shutil.copy(example, env_path)

_ensure_env_exists()

def get_data_dir():
    d = os.path.join(get_base_dir(), 'data')
    os.makedirs(d, exist_ok=True)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Konfigurationen Laden/Speichern
# ─────────────────────────────────────────────────────────────────────────────
def load_env_dict():
    env_path = get_env_path()
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def save_env_dict(new_vars):
    env_path = get_env_path()
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    for key, value in new_vars.items():
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        if not found and value:
            lines.append(f"{key}={value}\n")
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    for k, v in new_vars.items():
        if v:
            os.environ[k] = v

def load_json_config(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_json_config(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_local_ollama_models():
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            ['ollama', 'list'], capture_output=True, text=True,
            timeout=5, startupinfo=startupinfo
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()[1:]
            return [line.split()[0] for line in lines if line.strip()]
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────────────────────────────────────
# IMAP/SMTP Provider-Tabelle
# ─────────────────────────────────────────────────────────────────────────────
EMAIL_PROVIDERS = {
    "gmail":   {"imap_host": "imap.gmail.com",   "imap_port": 993, "smtp_host": "smtp.gmail.com",        "smtp_port": 587},
    "outlook": {"imap_host": "outlook.office365.com", "imap_port": 993, "smtp_host": "smtp.office365.com", "smtp_port": 587},
    "gmx":     {"imap_host": "imap.gmx.net",     "imap_port": 993, "smtp_host": "mail.gmx.net",          "smtp_port": 587},
    "webde":   {"imap_host": "imap.web.de",      "imap_port": 993, "smtp_host": "smtp.web.de",           "smtp_port": 587},
    "yahoo":   {"imap_host": "imap.mail.yahoo.com","imap_port": 993,"smtp_host": "smtp.mail.yahoo.com",  "smtp_port": 587},
    "ionos":   {"imap_host": "imap.ionos.de",    "imap_port": 993, "smtp_host": "smtp.ionos.de",         "smtp_port": 587},
    "eigener": {"imap_host": "", "imap_port": 993, "smtp_host": "", "smtp_port": 587},
}


# ─────────────────────────────────────────────────────────────────────────────
# Farben & Fonts (CustomTkinter Design-System)
# ─────────────────────────────────────────────────────────────────────────────
C_BG        = "#1e1e2e"
C_BG2       = "#2a2a3e"
C_BG3       = "#16213e"
C_GREEN     = "#00D882"
C_BLUE      = "#4d9fff"
C_YELLOW    = "#f59e0b"
C_RED       = "#ef4444"
C_PURPLE    = "#a855f7"
C_TEAL      = "#29b6f6"
C_TEXT      = "#e2e2ee"
C_MUTED     = "#7878a0"


# ─────────────────────────────────────────────────────────────────────────────
# Haupt-Anwendungsklasse (CustomTkinter)
# ─────────────────────────────────────────────────────────────────────────────
class IlijaApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("⚡ Ilija AI – Setup & Control Center")
        self.geometry("1020x820")
        self.minsize(1020, 700)
        self.configure(fg_color=C_BG)

        self.server_thread   = None
        self.telegram_thread = None
        self._server_running   = False
        self._telegram_running = False

        self._build_header()
        self._build_tabs()
        self._build_status_bar()
        self._build_footer_buttons()

        self.load_all_settings()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=C_BG3, corner_radius=12)
        hdr.pack(fill="x", padx=20, pady=(15, 5))

        ctk.CTkLabel(hdr, text="⚡  Ilija Public Edition",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C_GREEN).pack(pady=(12, 2))
        ctk.CTkLabel(hdr, text="Dein privater KI-Agent für Automatisierung",
                     font=ctk.CTkFont(size=12), text_color=C_MUTED).pack(pady=(0, 12))

    # ── Tabs ──────────────────────────────────────────────────────────────────
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, fg_color=C_BG2, corner_radius=12,
                              segmented_button_fg_color=C_BG3,
                              segmented_button_selected_color=C_GREEN,
                              segmented_button_selected_hover_color="#00b86e")
        self.tabview.pack(fill="both", expand=True, padx=20, pady=5)

        for name in ["1. KI Modelle", "2. Telegram", "3. Google", "4. E-Mail", "5. DMS", "6. Server", "7. FritzBox", "8. Eingangskanäle", "9. Start"]:
            self.tabview.add(name)

        self._tab_ki()
        self._tab_telegram()
        self._tab_google()
        self._tab_email()
        self._tab_dms()
        self._tab_server()
        self._tab_fritzbox()
        self._tab_eingangskanale()
        self._tab_start()

    # ── Status-Bar ────────────────────────────────────────────────────────────
    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, fg_color=C_BG3, corner_radius=8, height=32)
        self.status_bar.pack(fill="x", padx=20, pady=(2, 0))
        self.status_bar.pack_propagate(False)

        self.lbl_srv_status = ctk.CTkLabel(self.status_bar, text="⚫ Server: gestoppt",
                                           font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self.lbl_srv_status.pack(side="left", padx=15)

        self.lbl_tg_status = ctk.CTkLabel(self.status_bar, text="⚫ Telegram: gestoppt",
                                          font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self.lbl_tg_status.pack(side="left", padx=15)

    # ── Footer Buttons (Beenden & Speichern) ─────────────────────────────────
    def _build_footer_buttons(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(6, 14))

        self.btn_save_all = ctk.CTkButton(
            footer, text="💾  Alle Einstellungen speichern",
            fg_color=C_BLUE, hover_color="#3a88ef",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42, corner_radius=8,
            command=self.save_all_settings)
        self.btn_save_all.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.btn_quit = ctk.CTkButton(
            footer, text="🛑  Alles beenden",
            fg_color=C_RED, hover_color="#c83232",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42, corner_radius=8, width=180,
            command=self._quit_all)
        self.btn_quit.pack(side="right")

    # ─────────────────────────────────────────────────────────────────────────
    # Hilfsmethoden für Widgets
    # ─────────────────────────────────────────────────────────────────────────
    def _section(self, parent, text, color=C_TEXT):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=color, anchor="w").pack(fill="x", padx=4, pady=(14, 2))

    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=11), text_color=C_MUTED, anchor="w").pack(fill="x", padx=4, pady=(6, 1))

    def _entry(self, parent, show=None, placeholder=""):
        e = ctk.CTkEntry(parent, show=show, placeholder_text=placeholder,
                         fg_color=C_BG3, border_color="#44445a", border_width=1,
                         text_color=C_TEXT, height=36)
        e.pack(fill="x", padx=4, pady=2)
        return e

    def _hint_box(self, parent, text):
        """Graue Hinweis-Box"""
        box = ctk.CTkTextbox(parent, height=80, fg_color=C_BG3,
                             text_color=C_MUTED, border_color="#44445a",
                             border_width=1, font=ctk.CTkFont(size=10),
                             wrap="word", activate_scrollbars=False)
        box.pack(fill="x", padx=4, pady=(4, 8))
        box.insert("1.0", text)
        box.configure(state="disabled")
        return box

    def _divider(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color="#44445a").pack(fill="x", padx=4, pady=10)

    def _scrollable(self, tab_name):
        """Gibt einen scrollbaren Frame im Tab zurück."""
        tab = self.tabview.tab(tab_name)
        sf = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        sf.pack(fill="both", expand=True)
        return sf

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: KI Modelle
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_ki(self):
        f = self._scrollable("1. KI Modelle")

        self._section(f, "☁️  Cloud-Modelle (API-Keys)", C_YELLOW)
        self._hint_box(f, "Trage mindestens einen API-Key ein. Empfohlen: Google Gemini (kostenlos). "
                          "Die Keys werden sicher in der .env-Datei gespeichert und niemals übertragen.")

        self._label(f, "Claude API Key (Anthropic) → console.anthropic.com")
        self.ent_anthropic = self._entry(f, show="*", placeholder="sk-ant-api03-...")

        self._label(f, "ChatGPT API Key (OpenAI) → platform.openai.com/api-keys")
        self.ent_openai = self._entry(f, show="*", placeholder="sk-proj-...")

        self._label(f, "Gemini API Key (Google – oft kostenlos!) → aistudio.google.com")
        self.ent_gemini = self._entry(f, show="*", placeholder="AIzaSy-...")

        self._divider(f)
        self._section(f, "🖥️  Lokale Modelle (Ollama – 100% privat)", C_BLUE)
        self._hint_box(f, "Lokale Modelle laufen vollständig auf deinem PC – kein Internet nötig.\n"
                          "1. Lade Ollama herunter: https://ollama.com\n"
                          "2. Öffne CMD und tippe: ollama run qwen2.5:7b  (ca. 4 GB Download)\n"
                          "3. Klicke 'Lokal suchen' – das Modell erscheint im Dropdown.")

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=4)
        self.cbo_ollama = ctk.CTkComboBox(row, values=["-- Klicke 'Lokal suchen' --"],
                                          fg_color=C_BG3, border_color="#44445a",
                                          button_color=C_BLUE, text_color=C_TEXT,
                                          dropdown_fg_color=C_BG2)
        self.cbo_ollama.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="🔄 Lokal suchen", fg_color=C_BLUE, hover_color="#3a88ef",
                      width=140, command=self._refresh_ollama).pack(side="right")

        self._label(f, "Ollama Server URL (Standard: http://localhost:11434)")
        self.ent_ollama_url = self._entry(f, placeholder="http://localhost:11434")

        self._divider(f)
        self._section(f, "🎙️  Spracheingabe (Whisper)", C_PURPLE)
        self._hint_box(f, "Whisper läuft entweder lokal (kein Key nötig, wird automatisch erkannt)\n"
                          "oder über die OpenAI API (selber Key wie ChatGPT).")
        self._label(f, "Bevorzugtes Whisper-Modell (lokal: tiny/base/small/medium/large)")
        self.ent_whisper_model = self._entry(f, placeholder="base")

        self._divider(f)
        self._section(f, "⚙️  Modell-Auswahl (optional)", C_MUTED)
        self._label(f, "Standard-Claude-Modell (leer = claude-opus-4-6)")
        self.ent_anthropic_model = self._entry(f, placeholder="claude-opus-4-6")
        self._label(f, "Standard-Gemini-Modell (leer = gemini-2.5-flash)")
        self.ent_gemini_model = self._entry(f, placeholder="gemini-2.5-flash")
        self._label(f, "Standard-OpenAI-Modell (leer = gpt-4o)")
        self.ent_openai_model = self._entry(f, placeholder="gpt-4o")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: Telegram
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_telegram(self):
        f = self._scrollable("2. Telegram")

        self._section(f, "📱  Telegram Bot – Fernsteuerung für Ilija", C_TEAL)
        self._hint_box(f,
            "Schritt 1 – Bot erstellen:\n"
            "  • Öffne Telegram, suche '@BotFather', schreibe /newbot\n"
            "  • Folge den Anweisungen → du erhältst einen Token (12345:ABC-DEF)\n\n"
            "Schritt 2 – Deine User-ID finden:\n"
            "  • Suche '@userinfobot' in Telegram, schreibe /start\n"
            "  • Er antwortet mit deiner ID – nur diese ID darf Ilija steuern!\n\n"
            "Schritt 3 – Bot-Berechtigungen:\n"
            "  • Optional: Gehe zu @BotFather → /setcommands und füge Befehle hinzu."
        )

        self._label(f, "Bot-Token (von @BotFather):")
        self.ent_tg_token = self._entry(f, show="*", placeholder="1234567890:AAH-...")

        self._label(f, "Erlaubte User-IDs (kommagetrennt, z.B. 123456789,987654321):")
        self.ent_tg_users = self._entry(f, placeholder="123456789")

        self._divider(f)
        self._section(f, "🔔  Benachrichtigungskanal (optional)", C_MUTED)
        self._hint_box(f, "Wenn Ilija selbstständig Nachrichten senden soll (z.B. bei Workflow-Abschluss),\n"
                          "trägst du hier die Chat-ID ein. Bei Privatnutzung = deine User-ID.")
        self._label(f, "Standard-Chat-ID für ausgehende Nachrichten:")
        self.ent_tg_chat_id = self._entry(f, placeholder="123456789 oder -100xxx (Gruppe)")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3: Google Dienste
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_google(self):
        f = self._scrollable("3. Google")

        self._section(f, "🔵  Google Workspace Integration", "#ea4335")
        self._hint_box(f,
            "Ilija Studio bietet Nodes für: Docs, Sheets, Drive, Kalender, Gmail & Forms.\n"
            "Einmalige Einrichtung:\n"
            "  1. console.cloud.google.com → Neues Projekt erstellen\n"
            "  2. APIs & Dienste → Bibliothek: benötigte APIs aktivieren\n"
            "  3. OAuth-Zustimmungsschirm → Extern → deine E-Mail eintragen\n"
            "  4. Anmeldedaten → OAuth-Client-ID → Desktop-App → JSON laden\n"
            "  5. Datei unten hochladen. Ilija erledigt den Rest!"
        )

        btn_up = ctk.CTkButton(f, text="📂  credentials.json auswählen & installieren",
                               fg_color=C_YELLOW, hover_color="#d98c00",
                               text_color="black", font=ctk.CTkFont(weight="bold"),
                               height=40, corner_radius=8,
                               command=self._upload_google_json)
        btn_up.pack(fill="x", padx=4, pady=10)

        self.lbl_google_status = ctk.CTkLabel(f, text="⚫  Status: Keine credentials.json gefunden.",
                                              text_color=C_MUTED, anchor="w")
        self.lbl_google_status.pack(fill="x", padx=4)

        self._divider(f)
        self._section(f, "🔄  Token-Verwaltung", C_MUTED)
        self._hint_box(f, "Wenn sich ein Google-Dienst nicht verbindet, könnte das Token abgelaufen sein.\n"
                          "Lösche die entsprechende token.json-Datei und starte den Server neu – Ilija\n"
                          "öffnet dann automatisch einen Browser zur erneuten Anmeldung.")

        services = [
            ("Gmail",          "gmail"),
            ("Google Drive",   "google_drive"),
            ("Google Docs",    "google_docs"),
            ("Google Kalender","google_kalender"),
        ]
        for label, folder in services:
            row = ctk.CTkFrame(f, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=3)
            token_path = os.path.join(get_data_dir(), folder, "token.json")
            exists = os.path.exists(token_path)
            icon = "✅" if exists else "⚫"
            color = C_GREEN if exists else C_MUTED
            ctk.CTkLabel(row, text=f"{icon}  {label}", text_color=color,
                         font=ctk.CTkFont(size=11), width=200, anchor="w").pack(side="left")
            ctk.CTkButton(row, text="🗑  Token löschen", width=140,
                          fg_color="#3a2020", hover_color="#5a2020",
                          command=lambda p=token_path: self._delete_token(p)).pack(side="right")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4: E-Mail
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_email(self):
        f = self._scrollable("4. E-Mail")

        self._section(f, "📧  Standard E-Mail Setup (IMAP/SMTP)", C_PURPLE)
        self._hint_box(f,
            "Wird für den 'E-Mail'-Node im Ilija Studio benötigt.\n\n"
            "WICHTIG – App-Passwörter:\n"
            "Die meisten Anbieter (Gmail, Outlook, GMX, Yahoo, Web.de, iCloud) erlauben\n"
            "aus Sicherheitsgründen KEIN normales Login-Passwort mehr. Du musst in den\n"
            "Sicherheitseinstellungen deines Anbieters ein 'App-Passwort' generieren!\n\n"
            "Gmail: myaccount.google.com → Sicherheit → App-Passwörter\n"
            "Outlook: account.microsoft.com → Sicherheit → App-Kennwörter"
        )

        self._label(f, "Provider:")
        providers = list(EMAIL_PROVIDERS.keys())
        self.cbo_em_prov = ctk.CTkComboBox(f, values=providers,
                                            fg_color=C_BG3, border_color="#44445a",
                                            button_color=C_PURPLE, text_color=C_TEXT,
                                            dropdown_fg_color=C_BG2,
                                            command=self._on_email_provider_change)
        self.cbo_em_prov.pack(fill="x", padx=4, pady=2)

        self._label(f, "E-Mail Adresse:")
        self.ent_em_addr = self._entry(f, placeholder="deine@email.de")

        self._label(f, "App-Passwort (KEIN Login-Passwort!):")
        self.ent_em_pw = self._entry(f, show="*", placeholder="xxxx xxxx xxxx xxxx")

        self._divider(f)
        self._section(f, "🔧  Erweiterte Servereinstellungen", C_MUTED)
        self._hint_box(f, "Wird bei Auswahl eines bekannten Providers automatisch ausgefüllt.\n"
                          "Nur bei 'eigener' Einstellung manuell anpassen.")

        row1 = ctk.CTkFrame(f, fg_color="transparent")
        row1.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(row1, text="IMAP Host:", text_color=C_MUTED, width=100, anchor="w").pack(side="left")
        self.ent_imap_host = ctk.CTkEntry(row1, placeholder_text="imap.gmail.com",
                                          fg_color=C_BG3, border_color="#44445a", text_color=C_TEXT)
        self.ent_imap_host.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ctk.CTkLabel(row1, text="Port:", text_color=C_MUTED, width=40, anchor="w").pack(side="left")
        self.ent_imap_port = ctk.CTkEntry(row1, placeholder_text="993", width=70,
                                          fg_color=C_BG3, border_color="#44445a", text_color=C_TEXT)
        self.ent_imap_port.pack(side="right")

        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(row2, text="SMTP Host:", text_color=C_MUTED, width=100, anchor="w").pack(side="left")
        self.ent_smtp_host = ctk.CTkEntry(row2, placeholder_text="smtp.gmail.com",
                                          fg_color=C_BG3, border_color="#44445a", text_color=C_TEXT)
        self.ent_smtp_host.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ctk.CTkLabel(row2, text="Port:", text_color=C_MUTED, width=40, anchor="w").pack(side="left")
        self.ent_smtp_port = ctk.CTkEntry(row2, placeholder_text="587", width=70,
                                          fg_color=C_BG3, border_color="#44445a", text_color=C_TEXT)
        self.ent_smtp_port.pack(side="right")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 5: DMS (Dokumenten-Management)
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_dms(self):
        f = self._scrollable("5. DMS")

        self._section(f, "📁  Dokumenten-Management System (DMS)", C_YELLOW)
        self._hint_box(f,
            "Das DMS speichert und verwaltet deine Dokumente lokal. Du kannst:\n"
            "  • Eigene Archiv- und Import-Pfade festlegen\n"
            "  • Ein Passwort für den DMS-Bereich setzen\n"
            "  • Dokumente per Scan (JPG/PDF) importieren\n\n"
            "Standard: data/dms/archiv und data/dms/import im Ilija-Verzeichnis."
        )

        self._label(f, "Archiv-Pfad (wo Dokumente dauerhaft gespeichert werden):")
        row_archiv = ctk.CTkFrame(f, fg_color="transparent")
        row_archiv.pack(fill="x", padx=4, pady=2)
        self.ent_dms_archiv = ctk.CTkEntry(row_archiv, fg_color=C_BG3, border_color="#44445a", text_color=C_TEXT)
        self.ent_dms_archiv.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row_archiv, text="📂 Auswählen", width=120, fg_color=C_YELLOW,
                      hover_color="#d98c00", text_color="black",
                      command=lambda: self._choose_dir(self.ent_dms_archiv)).pack(side="right")

        self._label(f, "Import-Pfad (wo Ilija neue Dokumente einliest):")
        row_import = ctk.CTkFrame(f, fg_color="transparent")
        row_import.pack(fill="x", padx=4, pady=2)
        self.ent_dms_import = ctk.CTkEntry(row_import, fg_color=C_BG3, border_color="#44445a", text_color=C_TEXT)
        self.ent_dms_import.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row_import, text="📂 Auswählen", width=120, fg_color=C_YELLOW,
                      hover_color="#d98c00", text_color="black",
                      command=lambda: self._choose_dir(self.ent_dms_import)).pack(side="right")

        self._divider(f)
        self._section(f, "🔒  DMS Passwortschutz", C_RED)
        self._hint_box(f, "Optional: Schütze den DMS-Bereich mit einem Passwort.\n"
                          "Leer lassen = kein Passwortschutz.\n"
                          "Das Passwort wird als SHA-256-Hash gespeichert (niemals im Klartext).")

        self._label(f, "Neues DMS-Passwort (leer = deaktivieren):")
        self.ent_dms_pw = self._entry(f, show="*", placeholder="Leer lassen für kein Passwort")
        self._label(f, "Passwort wiederholen:")
        self.ent_dms_pw2 = self._entry(f, show="*", placeholder="Passwort wiederholen")

        self.lbl_dms_status = ctk.CTkLabel(f, text="", text_color=C_MUTED, anchor="w")
        self.lbl_dms_status.pack(fill="x", padx=4, pady=4)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 6: Server-Einstellungen
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_server(self):
        f = self._scrollable("6. Server")

        self._section(f, "🖥️  Web-Server Konfiguration", C_BLUE)
        self._hint_box(f,
            "Standardmäßig läuft Ilija auf localhost:5000 (nur dein PC).\n"
            "Für Netzwerkzugriff (z.B. vom Handy im Heimnetz): Host auf 0.0.0.0 setzen.\n\n"
            "WARNUNG: Nie ohne Firewall/VPN ins öffentliche Internet exponieren!"
        )

        self._label(f, "Host (Standard: 0.0.0.0 = alle Netzwerkschnittstellen):")
        self.ent_host = self._entry(f, placeholder="0.0.0.0")

        self._label(f, "Port (Standard: 5000):")
        self.ent_port = self._entry(f, placeholder="5000")

        self._divider(f)
        self._section(f, "🔐  Ilija Web-UI Passwortschutz (optional)", C_RED)
        self._hint_box(f, "Schütze die Web-Oberfläche mit einem Login. Empfohlen bei Netzwerkzugang.\n"
                          "Leer lassen = kein Schutz (nur localhost).")
        self._label(f, "Web-UI Benutzername:")
        self.ent_web_user = self._entry(f, placeholder="admin")
        self._label(f, "Web-UI Passwort:")
        self.ent_web_pw = self._entry(f, show="*", placeholder="sicheres-passwort")

        self._divider(f)
        self._section(f, "🐛  Debug-Modus", C_MUTED)
        self._hint_box(f, "Im Debug-Modus werden mehr Logs ausgegeben. Nur für Entwicklung aktivieren.")
        self.var_debug = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(f, text="Debug-Modus aktivieren", variable=self.var_debug,
                        text_color=C_TEXT, fg_color=C_GREEN,
                        hover_color="#00b86e").pack(anchor="w", padx=4, pady=6)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 7: FritzBox (SIP-Verbindung & Audio)
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_fritzbox(self):
        f = self._scrollable("7. FritzBox")

        self._section(f, "☎️  FritzBox SIP-Verbindung", C_GREEN)
        self._hint_box(f,
            "Ilija nimmt Anrufe automatisch über deine FritzBox entgegen.\n\n"
            "Einrichtung in fritz.box:\n"
            "  1. Telefonie → Telefoniegeräte → Neues Gerät hinzufügen → IP-Telefon\n"
            "  2. Einen Benutzernamen vergeben (z.B. 'ilija2026') + Passwort setzen\n"
            "  3. Diese Zugangsdaten unten eintragen und speichern.\n\n"
            "Wichtig: Ilija und FritzBox müssen im selben Heimnetz sein!"
        )

        self._label(f, "FritzBox-Adresse (Standard: fritz.box oder 192.168.178.1):")
        self.ent_sip_server = self._entry(f, placeholder="fritz.box")

        self._label(f, "SIP-Port (Standard: 5060 — nicht ändern wenn unklar):")
        self.ent_sip_port = self._entry(f, placeholder="5060")

        self._label(f, "SIP-Benutzername (Name des IP-Telefons in FritzBox):")
        self.ent_sip_user = self._entry(f, placeholder="ilija2026")

        self._label(f, "SIP-Passwort:")
        self.ent_sip_pw = self._entry(f, show="*", placeholder="dein-sip-passwort")

        self._label(f, "Lokale PC-IP (leer = automatisch ermitteln):")
        row_ip = ctk.CTkFrame(f, fg_color="transparent")
        row_ip.pack(fill="x", padx=4, pady=2)
        self.ent_sip_my_ip = ctk.CTkEntry(row_ip, placeholder_text="192.168.178.xx",
                                           fg_color=C_BG3, border_color="#44445a",
                                           text_color=C_TEXT, height=36)
        self.ent_sip_my_ip.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row_ip, text="🔍 Automatisch erkennen", width=170,
                      fg_color=C_BG3, hover_color="#3a3a5a",
                      command=self._detect_local_ip).pack(side="right")

        self._divider(f)
        self._section(f, "🎙️  Audio-Einstellungen", C_PURPLE)
        self._hint_box(f,
            "Mikrofon-ID: leer oder 0 = Standard-Mikrofon (meist korrekt).\n"
            "Falls Ilija das falsche Mikrofon nutzt: Starte Ilija einmal über die Konsole —\n"
            "dort erscheint eine nummerierte Liste aller erkannten Mikrofone."
        )
        self._label(f, "Mikrofon-ID (leer = Standard-Mikrofon):")
        self.ent_sip_mic_id = self._entry(f, placeholder="0")

        self._divider(f)
        self._section(f, "🔗  Verbindungstest", C_BLUE)
        self._hint_box(f,
            "Prüft ob die FritzBox über Netzwerk erreichbar ist.\n"
            "Kein Ersatz für einen echten Anruf — aber ein guter erster Check."
        )
        self.lbl_sip_test = ctk.CTkLabel(f, text="⚫  Noch nicht getestet",
                                          text_color=C_MUTED, anchor="w",
                                          font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_sip_test.pack(fill="x", padx=4, pady=(4, 6))
        ctk.CTkButton(f, text="🔌  FritzBox-Verbindung jetzt testen",
                      fg_color=C_BLUE, hover_color="#3a88ef",
                      height=38, corner_radius=8,
                      command=self._test_sip_connection).pack(anchor="w", padx=4, pady=4)

    def _detect_local_ip(self):
        """Ermittelt die lokale PC-IP automatisch und trägt sie ein."""
        import socket
        sip_server = self.ent_sip_server.get().strip() or "fritz.box"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.connect((sip_server, 5060))
            ip = s.getsockname()[0]
            s.close()
            self.ent_sip_my_ip.delete(0, "end")
            self.ent_sip_my_ip.insert(0, ip)
            self._log(f"FritzBox: Lokale IP erkannt → {ip}")
        except Exception as e:
            messagebox.showerror("Fehler", f"IP konnte nicht automatisch ermittelt werden:\n{e}\n\n"
                                           "Bitte IP manuell in ipconfig (Windows) oder ip a (Linux) nachschauen.")

    def _test_sip_connection(self):
        """Testet ob die FritzBox über TCP auf dem SIP-Port erreichbar ist."""
        import socket
        server = self.ent_sip_server.get().strip() or "fritz.box"
        try:
            port = int(self.ent_sip_port.get().strip() or "5060")
        except ValueError:
            port = 5060
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            result = s.connect_ex((server, port))
            s.close()
            if result == 0:
                self.lbl_sip_test.configure(
                    text=f"✅  FritzBox erreichbar auf {server}:{port}",
                    text_color=C_GREEN)
                self._log(f"FritzBox-Test OK: {server}:{port}")
            else:
                self.lbl_sip_test.configure(
                    text=f"❌  Kein SIP-Port {port} auf {server} erreichbar — Adresse prüfen!",
                    text_color=C_RED)
                self._log(f"FritzBox-Test FEHLGESCHLAGEN: {server}:{port} (Code {result})")
        except socket.gaierror:
            self.lbl_sip_test.configure(
                text=f"❌  Host '{server}' nicht gefunden — im Heimnetz?",
                text_color=C_RED)
            self._log(f"FritzBox-Test: Host '{server}' nicht auflösbar.")
        except Exception as e:
            self.lbl_sip_test.configure(text=f"❌  Fehler: {e}", text_color=C_RED)
            self._log(f"FritzBox-Test Fehler: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 8: Eingangskanäle (Telefon + WhatsApp)
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_eingangskanale(self):
        f = self._scrollable("8. Eingangskanäle")

        # ── Allgemeine Angaben ────────────────────────────────────────────────
        self._section(f, "🏢  Allgemeine Angaben", C_GREEN)
        self._hint_box(f,
            "Diese Angaben gelten für alle Eingangskanäle (Telefon, WhatsApp).\n"
            "Ilija verwendet sie um sich korrekt vorzustellen."
        )
        self._label(f, "Firmenname / Ihr Name:")
        self.ent_phone_firma = self._entry(f, placeholder="Mein Unternehmen")

        # ══════════════════════════════════════════════════════════════════════
        # TELEFON
        # ══════════════════════════════════════════════════════════════════════
        self._divider(f)
        self._section(f, "📞  Telefon", C_GREEN)
        self._hint_box(f,
            "Konfiguration für eingehende Anrufe via Fritzbox.\n"
            "Gilt für /listen und /call im Telegram-Bot."
        )

        self._label(f, "Begrüßung (gesprochen wenn Ilija abhebt):")
        self.txt_phone_begruessung = ctk.CTkTextbox(f, height=80, font=ctk.CTkFont(size=13),
                                                     fg_color=C_BG3, text_color=C_TEXT,
                                                     border_color=C_MUTED, border_width=1)
        self.txt_phone_begruessung.pack(fill="x", padx=4, pady=4)

        self._label(f, "Angebotene Dienste (ein Eintrag pro Zeile):")
        self._hint_box(f, "Ilija nennt diese wenn der Anrufer fragt was sie kann.\n"
                          "Keine Software-Namen — nur was der Kunde hören soll.")
        self.txt_phone_dienste = ctk.CTkTextbox(f, height=90, font=ctk.CTkFont(size=13),
                                                 fg_color=C_BG3, text_color=C_TEXT,
                                                 border_color=C_MUTED, border_width=1)
        self.txt_phone_dienste.pack(fill="x", padx=4, pady=4)

        self._label(f, "Ilija's Rolle am Telefon:")
        self.ent_phone_rolle = self._entry(f, placeholder="Ich bin Ilija, die KI-Assistentin.")

        self._label(f, "Verabschiedung:")
        self.ent_phone_abschluss = self._entry(
            f, placeholder="Ich wünsche Ihnen noch einen schönen Tag. Auf Wiederhören!")

        self._label(f, "Antwort bei unbekannten Anfragen:")
        self.ent_phone_nicht_zustaendig = self._entry(
            f, placeholder="Dafür bin ich leider nicht zuständig. Kann ich anderweitig helfen?")

        self._label(f, "📚  Wissensbasis-Ordner (öffentliche Infos für Anrufer):")
        self._hint_box(f, "Ordner mit .txt / .md / .pdf Dateien (Produktinfos, FAQ, Preislisten…)\n"
                          "Ilija durchsucht diese automatisch bei jeder Anfrage.")
        row_phone_info = ctk.CTkFrame(f, fg_color="transparent")
        row_phone_info.pack(fill="x", padx=4, pady=2)
        self.ent_phone_info_pfad = self._entry(row_phone_info, placeholder="data/public_info")
        self.ent_phone_info_pfad.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row_phone_info, text="📁", width=36, fg_color=C_BG3,
                      command=lambda: self._choose_dir(self.ent_phone_info_pfad)
                      ).pack(side="left", padx=(4, 0))
        ctk.CTkButton(row_phone_info, text="Ordner öffnen", width=110, fg_color=C_BG3,
                      command=lambda: self._open_folder(self.ent_phone_info_pfad)
                      ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(f, text="💾  Telefon-Einstellungen speichern",
                      fg_color=C_GREEN, hover_color="#00b86e",
                      command=self._save_phone_config).pack(anchor="w", padx=4, pady=10)

        # ══════════════════════════════════════════════════════════════════════
        # WHATSAPP
        # ══════════════════════════════════════════════════════════════════════
        self._divider(f)
        self._section(f, "💬  WhatsApp", C_TEAL)
        self._hint_box(f,
            "Konfiguration für den WhatsApp-Assistenten.\n"
            "Ilija antwortet hier per Text — kürzer und direkter als am Telefon."
        )

        self._label(f, "Begrüßung (erste Nachricht an neue Kontakte):")
        self.txt_wa_begruessung = ctk.CTkTextbox(f, height=70, font=ctk.CTkFont(size=13),
                                                  fg_color=C_BG3, text_color=C_TEXT,
                                                  border_color=C_MUTED, border_width=1)
        self.txt_wa_begruessung.pack(fill="x", padx=4, pady=4)

        self._label(f, "Angebotene Dienste (ein Eintrag pro Zeile):")
        self.txt_wa_dienste = ctk.CTkTextbox(f, height=90, font=ctk.CTkFont(size=13),
                                              fg_color=C_BG3, text_color=C_TEXT,
                                              border_color=C_MUTED, border_width=1)
        self.txt_wa_dienste.pack(fill="x", padx=4, pady=4)

        self._label(f, "Ilija's Rolle in WhatsApp:")
        self.ent_wa_rolle = self._entry(f, placeholder="Ich bin Ilija, die digitale Assistentin.")

        self._label(f, "Antwort bei unbekannten Anfragen:")
        self.ent_wa_nicht_zustaendig = self._entry(
            f, placeholder="Das liegt leider nicht in meinem Bereich. Wie kann ich dir sonst helfen?")

        self._label(f, "📚  Wissensbasis-Ordner (öffentliche Infos für Kunden):")
        self._hint_box(f, "Derselbe oder ein eigener Ordner wie beim Telefon.\n"
                          "Ilija durchsucht diese automatisch bei jeder Nachricht.")
        row_wa_info = ctk.CTkFrame(f, fg_color="transparent")
        row_wa_info.pack(fill="x", padx=4, pady=2)
        self.ent_wa_info_pfad = self._entry(row_wa_info, placeholder="data/public_info")
        self.ent_wa_info_pfad.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row_wa_info, text="📁", width=36, fg_color=C_BG3,
                      command=lambda: self._choose_dir(self.ent_wa_info_pfad)
                      ).pack(side="left", padx=(4, 0))
        ctk.CTkButton(row_wa_info, text="Ordner öffnen", width=110, fg_color=C_BG3,
                      command=lambda: self._open_folder(self.ent_wa_info_pfad)
                      ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(f, text="💾  WhatsApp-Einstellungen speichern",
                      fg_color=C_TEAL, hover_color="#1a9fd4",
                      command=self._save_whatsapp_config).pack(anchor="w", padx=4, pady=10)

        # ══════════════════════════════════════════════════════════════════════
        # KALENDER-SYNCHRONISATION
        # ══════════════════════════════════════════════════════════════════════
        self._divider(f)
        self._section(f, "📅  Kalender-Synchronisation", C_GREEN)
        self._hint_box(f,
            "Ilija nutzt intern immer den lokalen Kalender.\n"
            "Push (Lokal → Provider): Nach jedem Anruf wird die neue Buchung automatisch übertragen.\n"
            "Pull (Provider → Lokal): Externe Termine werden im eingestellten Intervall importiert.\n"
            "\n"
            "Google Kalender: Push + Pull vollautomatisch über die Google Calendar API.\n"
            "Outlook: Push funktioniert automatisch — ein Chrome-Fenster öffnet sich kurz nach dem\n"
            "  Anruf und trägt den Termin ein (Workaround, da Microsoft keine kostenfreie API bietet).\n"
            "  Pull ist für Outlook nicht verfügbar (Selenium liefert nur Tagestext, keine Rohdaten).\n"
            "  Einrichtung: Outlook einmalig über den Skill 'outlook_login_einrichten' anmelden."
        )

        self._label(f, "Externer Kalender-Provider:")
        self.cbo_sync_provider = ctk.CTkOptionMenu(
            f, values=["keiner", "google", "outlook"],
            fg_color=C_BG3, button_color=C_MUTED, button_hover_color=C_GREEN,
            text_color=C_TEXT, font=ctk.CTkFont(size=13))
        self.cbo_sync_provider.pack(anchor="w", padx=4, pady=4)

        self._label(f, "Pull-Intervall (Extern → Lokal):")
        self.cbo_sync_intervall = ctk.CTkOptionMenu(
            f, values=["manuell", "3x_taeglich", "stuendlich"],
            fg_color=C_BG3, button_color=C_MUTED, button_hover_color=C_GREEN,
            text_color=C_TEXT, font=ctk.CTkFont(size=13))
        self.cbo_sync_intervall.pack(anchor="w", padx=4, pady=4)

        self.var_auto_push = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(f, text="Auto-Push: Neue Buchungen sofort nach Anruf übertragen",
                        variable=self.var_auto_push,
                        text_color=C_TEXT, font=ctk.CTkFont(size=13),
                        fg_color=C_GREEN, hover_color="#00b86e"
                        ).pack(anchor="w", padx=4, pady=4)

        row_sync = ctk.CTkFrame(f, fg_color="transparent")
        row_sync.pack(fill="x", padx=4, pady=4)
        ctk.CTkButton(row_sync, text="💾  Sync-Einstellungen speichern",
                      fg_color=C_GREEN, hover_color="#00b86e",
                      command=self._save_sync_config).pack(side="left")
        ctk.CTkButton(row_sync, text="▶  Jetzt Pull starten",
                      fg_color=C_BG3, hover_color=C_MUTED,
                      command=self._manual_pull).pack(side="left", padx=(8, 0))

        self._label(f, "Letzter Sync-Status:")
        self.lbl_sync_status = ctk.CTkLabel(f, text="—", text_color=C_MUTED,
                                             font=ctk.CTkFont(size=12), anchor="w")
        self.lbl_sync_status.pack(anchor="w", padx=4, pady=(0, 8))

    def _save_phone_config(self):
        """Speichert phone_config.json."""
        import json as _json
        path = os.path.join(get_base_dir(), "phone_config.json")
        dienste = [d.strip() for d in
                   self.txt_phone_dienste.get("1.0", "end").strip().splitlines() if d.strip()]
        info_pfad = self.ent_phone_info_pfad.get().strip() or "data/public_info"
        # Ordner anlegen falls er noch nicht existiert
        abs_info = info_pfad if os.path.isabs(info_pfad) else os.path.join(get_base_dir(), info_pfad)
        os.makedirs(abs_info, exist_ok=True)
        config = {
            "firmenname":       self.ent_phone_firma.get().strip(),
            "begruessung":      self.txt_phone_begruessung.get("1.0", "end").strip(),
            "ki_rolle":         self.ent_phone_rolle.get().strip(),
            "dienste":          dienste if dienste else ["Allgemeine Anfragen"],
            "abschluss":        self.ent_phone_abschluss.get().strip(),
            "nicht_zustaendig": self.ent_phone_nicht_zustaendig.get().strip(),
            "public_info_pfad": info_pfad,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(config, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("✅ Gespeichert", "Telefon-Einstellungen gespeichert!\n"
                                                   f"Wissensbasis-Ordner: {abs_info}")
            self._log("Telefon-Konfiguration gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte phone_config.json nicht speichern:\n{e}")

    def _save_whatsapp_config(self):
        """Speichert whatsapp_config.json."""
        import json as _json
        path = os.path.join(get_data_dir(), "whatsapp", "whatsapp_config.json")
        dienste = [d.strip() for d in
                   self.txt_wa_dienste.get("1.0", "end").strip().splitlines() if d.strip()]
        info_pfad = self.ent_wa_info_pfad.get().strip() or "data/public_info"
        abs_info = info_pfad if os.path.isabs(info_pfad) else os.path.join(get_base_dir(), info_pfad)
        os.makedirs(abs_info, exist_ok=True)
        config = {
            "firmenname":       self.ent_phone_firma.get().strip(),
            "begruessung":      self.txt_wa_begruessung.get("1.0", "end").strip(),
            "ki_rolle":         self.ent_wa_rolle.get().strip(),
            "dienste":          dienste if dienste else ["Allgemeine Anfragen"],
            "nicht_zustaendig": self.ent_wa_nicht_zustaendig.get().strip(),
            "public_info_pfad": info_pfad,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(config, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("✅ Gespeichert", "WhatsApp-Einstellungen gespeichert!\n"
                                                   f"Wissensbasis-Ordner: {abs_info}")
            self._log("WhatsApp-Konfiguration gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte whatsapp_config.json nicht speichern:\n{e}")

    def _save_sync_config(self):
        """Speichert kalender_sync.json."""
        import json as _json
        path = os.path.join(get_base_dir(), "data", "kalender_sync.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cfg = {
            "provider":       self.cbo_sync_provider.get(),
            "pull_intervall": self.cbo_sync_intervall.get(),
            "auto_push":      self.var_auto_push.get(),
            "letzte_sync":    "",
        }
        # letzte_sync behalten falls vorhanden
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    alt = _json.load(f)
                cfg["letzte_sync"] = alt.get("letzte_sync", "")
            except Exception:
                pass
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(cfg, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("✅ Gespeichert", "Kalender-Sync-Einstellungen gespeichert.")
            self._log("Kalender-Sync-Konfiguration gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte kalender_sync.json nicht speichern:\n{e}")

    def _manual_pull(self):
        """Führt einen manuellen Pull vom externen Provider aus."""
        import threading as _threading
        self.lbl_sync_status.configure(text="⏳ Pull läuft...", text_color=C_MUTED)

        def _run():
            try:
                from skills.kalender_sync_skill import pull_extern_zu_lokal
                erg = pull_extern_zu_lokal()
            except Exception as e:
                erg = f"Fehler: {e}"
            self.lbl_sync_status.configure(
                text=erg[:120],
                text_color=C_GREEN if "abgeschlossen" in erg else C_MUTED
            )
            self._log(f"Kalender-Sync Pull: {erg}")

        _threading.Thread(target=_run, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 8: Start
    # ─────────────────────────────────────────────────────────────────────────
    def _tab_start(self):
        f = self.tabview.tab("9. Start")

        # Module starten
        ctk.CTkLabel(f, text="🚀  Ilija Module starten",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_GREEN).pack(pady=(20, 10))

        self.btn_server = ctk.CTkButton(
            f, text="▶  Web-Server & Ilija Studio starten",
            fg_color=C_GREEN, hover_color="#00b86e",
            text_color="black", font=ctk.CTkFont(size=13, weight="bold"),
            height=48, corner_radius=8,
            command=self._start_server)
        self.btn_server.pack(fill="x", padx=24, pady=8)

        self.btn_tg = ctk.CTkButton(
            f, text="▶  Telegram Bot starten",
            fg_color=C_TEAL, hover_color="#1a9fd4",
            text_color="black", font=ctk.CTkFont(size=13, weight="bold"),
            height=48, corner_radius=8,
            command=self._start_telegram)
        self.btn_tg.pack(fill="x", padx=24, pady=8)

        self.btn_open = ctk.CTkButton(
            f, text="🌐  Browser: Workflow Studio öffnen",
            fg_color=C_YELLOW, hover_color="#d98c00",
            text_color="black", font=ctk.CTkFont(size=13, weight="bold"),
            height=48, corner_radius=8, state="disabled",
            command=lambda: webbrowser.open(f"http://localhost:{self._get_port()}"))
        self.btn_open.pack(fill="x", padx=24, pady=8)

        # Stopp-Buttons
        ctk.CTkFrame(f, height=1, fg_color="#44445a").pack(fill="x", padx=24, pady=10)
        ctk.CTkLabel(f, text="⏹  Module stoppen",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_RED).pack(pady=(0, 8))

        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(fill="x", padx=24)

        self.btn_stop_server = ctk.CTkButton(
            btn_row, text="⏹  Server stoppen",
            fg_color="#3a1818", hover_color="#5a2020",
            font=ctk.CTkFont(size=12), height=38, state="disabled",
            command=self._stop_server)
        self.btn_stop_server.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_stop_tg = ctk.CTkButton(
            btn_row, text="⏹  Telegram stoppen",
            fg_color="#3a1818", hover_color="#5a2020",
            font=ctk.CTkFont(size=12), height=38, state="disabled",
            command=self._stop_telegram)
        self.btn_stop_tg.pack(side="right", expand=True, fill="x", padx=(6, 0))

        # Logs
        ctk.CTkFrame(f, height=1, fg_color="#44445a").pack(fill="x", padx=24, pady=10)
        ctk.CTkLabel(f, text="📋  Live-Log",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C_MUTED).pack(anchor="w", padx=24)
        self.log_box = ctk.CTkTextbox(f, height=140, fg_color=C_BG3,
                                      text_color=C_MUTED,
                                      font=ctk.CTkFont(family="Courier", size=10),
                                      activate_scrollbars=True)
        self.log_box.pack(fill="x", padx=24, pady=(4, 16))
        self._log("Bereit. Bitte Einstellungen speichern und Module starten.")

    # ─────────────────────────────────────────────────────────────────────────
    # Logik
    # ─────────────────────────────────────────────────────────────────────────
    def _log(self, msg):
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"→ {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception:
            pass

    def _get_port(self):
        try:
            p = int(self.ent_port.get().strip())
            return p
        except Exception:
            return 5000

    def _refresh_ollama(self):
        models = get_local_ollama_models()
        if models:
            self.cbo_ollama.configure(values=models)
            self.cbo_ollama.set(models[0])
            self._log(f"Ollama: {len(models)} lokale Modelle gefunden.")
        else:
            self.cbo_ollama.configure(values=["Keine Modelle gefunden – läuft Ollama?"])
            self.cbo_ollama.set("Keine Modelle gefunden – läuft Ollama?")
            self._log("Ollama: Keine Modelle gefunden. Läuft Ollama?")

    def _on_email_provider_change(self, choice):
        cfg = EMAIL_PROVIDERS.get(choice, {})
        for widget, key in [
            (self.ent_imap_host, "imap_host"),
            (self.ent_smtp_host, "smtp_host"),
        ]:
            widget.delete(0, "end")
            widget.insert(0, str(cfg.get(key, "")))
        for widget, key in [
            (self.ent_imap_port, "imap_port"),
            (self.ent_smtp_port, "smtp_port"),
        ]:
            widget.delete(0, "end")
            widget.insert(0, str(cfg.get(key, "")))
        # bei "eigener" Felder editierbar
        state = "normal" if choice == "eigener" else "normal"  # immer editierbar

    def _upload_google_json(self):
        filepath = filedialog.askopenfilename(
            title="credentials.json auswählen",
            filetypes=[("JSON Files", "*.json"), ("Alle Dateien", "*.*")]
        )
        if filepath:
            target_dir = os.path.join(get_data_dir(), "google_kalender")
            os.makedirs(target_dir, exist_ok=True)
            target_file = os.path.join(target_dir, "credentials.json")
            try:
                shutil.copy(filepath, target_file)
                self.lbl_google_status.configure(
                    text="✅  credentials.json erfolgreich installiert!", text_color=C_GREEN)
                self._log("Google: credentials.json installiert.")
                messagebox.showinfo("Erfolg", "Google Credentials wurden erfolgreich installiert.")
            except Exception as e:
                messagebox.showerror("Fehler", f"Kopieren fehlgeschlagen:\n{e}")

    def _delete_token(self, token_path):
        if os.path.exists(token_path):
            if messagebox.askyesno("Token löschen",
                                   f"Token löschen?\n{token_path}\n\nIlija öffnet beim nächsten Start "
                                   "automatisch den Browser zur erneuten Anmeldung."):
                os.remove(token_path)
                self._log(f"Token gelöscht: {token_path}")
                messagebox.showinfo("Gelöscht", "Token wurde gelöscht. Bitte Server neu starten.")
        else:
            messagebox.showinfo("Nicht vorhanden", "Kein Token für diesen Dienst gefunden.")

    def _choose_dir(self, entry_widget):
        path = filedialog.askdirectory(title="Ordner auswählen")
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)

    def _open_folder(self, entry_widget):
        """Öffnet den eingetragenen Ordner im Datei-Explorer. Legt ihn an wenn nötig."""
        pfad = entry_widget.get().strip()
        if not pfad:
            pfad = os.path.join(get_base_dir(), "data", "public_info")
        if not os.path.isabs(pfad):
            pfad = os.path.join(get_base_dir(), pfad)
        os.makedirs(pfad, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(pfad)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", pfad])
        except Exception as e:
            messagebox.showerror("Fehler", f"Ordner konnte nicht geöffnet werden:\n{e}")

    # ── Einstellungen laden ──────────────────────────────────────────────────
    def load_all_settings(self):
        env = load_env_dict()

        # KI Modelle
        self.ent_anthropic.insert(0, env.get("ANTHROPIC_API_KEY", ""))
        self.ent_openai.insert(0, env.get("OPENAI_API_KEY", ""))
        self.ent_gemini.insert(0, env.get("GOOGLE_API_KEY", env.get("GEMINI_API_KEY", "")))
        self.ent_ollama_url.insert(0, env.get("OLLAMA_BASE_URL", "http://localhost:11434"))
        self.ent_whisper_model.insert(0, env.get("WHISPER_MODEL", ""))
        self.ent_anthropic_model.insert(0, env.get("ANTHROPIC_MODEL", ""))
        self.ent_gemini_model.insert(0, env.get("GOOGLE_MODEL", ""))
        self.ent_openai_model.insert(0, env.get("OPENAI_MODEL", ""))
        self._refresh_ollama()

        # Telegram
        self.ent_tg_token.insert(0, env.get("TELEGRAM_BOT_TOKEN", ""))
        self.ent_tg_users.insert(0, env.get("TELEGRAM_ALLOWED_USERS", ""))
        tg_cfg = load_json_config(os.path.join(get_data_dir(), "telegram", "telegram_config.json"))
        self.ent_tg_chat_id.insert(0, tg_cfg.get("chat_id", ""))

        # Google Status
        creds = os.path.join(get_data_dir(), "google_kalender", "credentials.json")
        if os.path.exists(creds):
            self.lbl_google_status.configure(
                text="✅  credentials.json ist installiert.", text_color=C_GREEN)

        # Email
        em_cfg = load_json_config(os.path.join(get_data_dir(), "email", "email_config.json"))
        if em_cfg:
            prov = em_cfg.get("provider", "gmail")
            if prov in EMAIL_PROVIDERS:
                self.cbo_em_prov.set(prov)
            self.ent_em_addr.insert(0, em_cfg.get("email_adresse", ""))
            self.ent_em_pw.insert(0, em_cfg.get("passwort", ""))
            self.ent_imap_host.insert(0, em_cfg.get("imap_host", ""))
            self.ent_imap_port.insert(0, str(em_cfg.get("imap_port", 993)))
            self.ent_smtp_host.insert(0, em_cfg.get("smtp_host", ""))
            self.ent_smtp_port.insert(0, str(em_cfg.get("smtp_port", 587)))
        else:
            self._on_email_provider_change("gmail")

        # DMS
        dms_cfg = load_json_config(os.path.join(get_data_dir(), "dms", "dms_config.json"))
        default_archiv = os.path.join(get_data_dir(), "dms", "archiv")
        default_import = os.path.join(get_data_dir(), "dms", "import")
        self.ent_dms_archiv.insert(0, dms_cfg.get("archiv_pfad", default_archiv))
        self.ent_dms_import.insert(0, dms_cfg.get("import_pfad", default_import))
        if dms_cfg.get("passwort_aktiv"):
            self.lbl_dms_status.configure(text="🔒 DMS-Passwortschutz aktiv", text_color=C_GREEN)
        else:
            self.lbl_dms_status.configure(text="🔓 DMS-Passwortschutz inaktiv", text_color=C_MUTED)

        # Server
        self.ent_host.insert(0, env.get("HOST", "0.0.0.0"))
        self.ent_port.insert(0, env.get("PORT", "5000"))
        self.ent_web_user.insert(0, env.get("WEB_USER", ""))
        self.ent_web_pw.insert(0, env.get("WEB_PASSWORD", ""))
        self.var_debug.set(env.get("DEBUG", "false").lower() == "true")

        # FritzBox SIP
        self.ent_sip_server.insert(0, env.get("SIP_SERVER", "fritz.box"))
        self.ent_sip_port.insert(0, env.get("SIP_PORT", "5060"))
        self.ent_sip_user.insert(0, env.get("SIP_USER", ""))
        self.ent_sip_pw.insert(0, env.get("SIP_PASSWORD", ""))
        self.ent_sip_my_ip.insert(0, env.get("SIP_MY_IP", ""))
        self.ent_sip_mic_id.insert(0, env.get("SIP_MIC_ID", ""))

        # Eingangskanäle – Telefon
        phone_cfg = load_json_config(os.path.join(get_base_dir(), "phone_config.json"))
        self.ent_phone_firma.insert(0, phone_cfg.get("firmenname", ""))
        self.txt_phone_begruessung.insert("1.0", phone_cfg.get("begruessung", ""))
        self.ent_phone_rolle.insert(0, phone_cfg.get("ki_rolle", ""))
        self.txt_phone_dienste.insert("1.0", "\n".join(phone_cfg.get("dienste", [])))
        self.ent_phone_abschluss.insert(0, phone_cfg.get("abschluss", ""))
        self.ent_phone_nicht_zustaendig.insert(0, phone_cfg.get("nicht_zustaendig", ""))
        self.ent_phone_info_pfad.insert(0, phone_cfg.get("public_info_pfad", "data/public_info"))

        # Eingangskanäle – WhatsApp
        wa_cfg = load_json_config(os.path.join(get_data_dir(), "whatsapp", "whatsapp_config.json"))
        self.txt_wa_begruessung.insert("1.0", wa_cfg.get("begruessung", ""))
        self.ent_wa_rolle.insert(0, wa_cfg.get("ki_rolle", ""))
        self.txt_wa_dienste.insert("1.0", "\n".join(wa_cfg.get("dienste", [])))
        self.ent_wa_nicht_zustaendig.insert(0, wa_cfg.get("nicht_zustaendig", ""))
        self.ent_wa_info_pfad.insert(0, wa_cfg.get("public_info_pfad", "data/public_info"))

        # Kalender-Synchronisation
        sync_cfg = load_json_config(os.path.join(get_base_dir(), "data", "kalender_sync.json"))
        self.cbo_sync_provider.set(sync_cfg.get("provider", "keiner"))
        self.cbo_sync_intervall.set(sync_cfg.get("pull_intervall", "3x_taeglich"))
        self.var_auto_push.set(sync_cfg.get("auto_push", True))
        letzte = sync_cfg.get("letzte_sync", "")
        if letzte:
            self.lbl_sync_status.configure(text=f"Letzte Sync: {letzte}", text_color=C_MUTED)

    # ── Einstellungen speichern ──────────────────────────────────────────────
    def save_all_settings(self):
        errors = []

        # 1. ENV
        ollama_model = self.cbo_ollama.get()
        if "Keine" in ollama_model or "suchen" in ollama_model:
            ollama_model = ""

        new_env = {
            "ANTHROPIC_API_KEY":  self.ent_anthropic.get().strip(),
            "OPENAI_API_KEY":     self.ent_openai.get().strip(),
            "GOOGLE_API_KEY":     self.ent_gemini.get().strip(),
            "TELEGRAM_BOT_TOKEN": self.ent_tg_token.get().strip(),
            "TELEGRAM_ALLOWED_USERS": self.ent_tg_users.get().strip(),
            "OLLAMA_BASE_URL":    self.ent_ollama_url.get().strip() or "http://localhost:11434",
            "OLLAMA_MODEL":       ollama_model,
            "WHISPER_MODEL":      self.ent_whisper_model.get().strip(),
            "ANTHROPIC_MODEL":    self.ent_anthropic_model.get().strip(),
            "GOOGLE_MODEL":       self.ent_gemini_model.get().strip(),
            "OPENAI_MODEL":       self.ent_openai_model.get().strip(),
            "HOST":               self.ent_host.get().strip() or "0.0.0.0",
            "PORT":               self.ent_port.get().strip() or "5000",
            "DEBUG":              "true" if self.var_debug.get() else "false",
            "WEB_USER":           self.ent_web_user.get().strip(),
            "WEB_PASSWORD":       self.ent_web_pw.get().strip(),
            # FritzBox SIP
            "SIP_SERVER":         self.ent_sip_server.get().strip() or "fritz.box",
            "SIP_PORT":           self.ent_sip_port.get().strip() or "5060",
            "SIP_USER":           self.ent_sip_user.get().strip(),
            "SIP_PASSWORD":       self.ent_sip_pw.get().strip(),
            "SIP_MY_IP":          self.ent_sip_my_ip.get().strip(),
            "SIP_MIC_ID":         self.ent_sip_mic_id.get().strip(),
        }
        save_env_dict(new_env)

        # 2. Telegram Config (chat_id)
        tg_chat_id = self.ent_tg_chat_id.get().strip()
        if tg_chat_id:
            tg_cfg_path = os.path.join(get_data_dir(), "telegram", "telegram_config.json")
            tg_cfg = load_json_config(tg_cfg_path)
            tg_cfg["chat_id"] = tg_chat_id
            save_json_config(tg_cfg_path, tg_cfg)

        # 3. Email Config
        prov = self.cbo_em_prov.get().strip()
        addr = self.ent_em_addr.get().strip()
        pw   = self.ent_em_pw.get().strip()
        if addr and pw:
            try:
                imap_port = int(self.ent_imap_port.get().strip() or "993")
                smtp_port = int(self.ent_smtp_port.get().strip() or "587")
            except ValueError:
                errors.append("IMAP/SMTP-Port muss eine Zahl sein.")
                imap_port, smtp_port = 993, 587

            em_cfg = {
                "provider":      prov,
                "email_adresse": addr,
                "passwort":      pw,
                "imap_host":     self.ent_imap_host.get().strip(),
                "imap_port":     imap_port,
                "smtp_host":     self.ent_smtp_host.get().strip(),
                "smtp_port":     smtp_port,
            }
            import datetime
            em_cfg["konfiguriert_am"] = datetime.datetime.now().isoformat()
            save_json_config(os.path.join(get_data_dir(), "email", "email_config.json"), em_cfg)

        # 4. DMS Config
        dms_archiv = self.ent_dms_archiv.get().strip()
        dms_import = self.ent_dms_import.get().strip()
        dms_cfg_path = os.path.join(get_data_dir(), "dms", "dms_config.json")
        dms_cfg = load_json_config(dms_cfg_path)

        dms_pw  = self.ent_dms_pw.get()
        dms_pw2 = self.ent_dms_pw2.get()

        if dms_pw or dms_pw2:
            if dms_pw != dms_pw2:
                errors.append("DMS-Passwörter stimmen nicht überein!")
            elif len(dms_pw) < 6:
                errors.append("DMS-Passwort muss mindestens 6 Zeichen lang sein.")
            else:
                dms_cfg["passwort_hash"] = hashlib.sha256(dms_pw.encode()).hexdigest()
                dms_cfg["passwort_aktiv"] = True
                self.lbl_dms_status.configure(text="🔒 DMS-Passwortschutz aktiv", text_color=C_GREEN)
                self.ent_dms_pw.delete(0, "end")
                self.ent_dms_pw2.delete(0, "end")

        if not dms_pw and not dms_pw2:
            pass  # Passwort unverändert

        if dms_archiv:
            dms_cfg["archiv_pfad"] = dms_archiv
            os.makedirs(dms_archiv, exist_ok=True)
        if dms_import:
            dms_cfg["import_pfad"] = dms_import
            os.makedirs(dms_import, exist_ok=True)

        save_json_config(dms_cfg_path, dms_cfg)

        if errors:
            messagebox.showwarning("Gespeichert mit Hinweisen",
                                   "Gespeichert! Aber bitte prüfen:\n\n" + "\n".join(f"• {e}" for e in errors))
        else:
            messagebox.showinfo("✅ Gespeichert", "Alle Einstellungen wurden erfolgreich gespeichert!\n"
                                                  "Du kannst die Module nun starten.")
        self._log("Einstellungen gespeichert.")

    # ── Server starten/stoppen ───────────────────────────────────────────────
    def _start_server(self):
        if self._server_running:
            return
        self._server_running = True
        self.btn_server.configure(text="Web-Server läuft...", state="disabled",
                                  fg_color="#354E44")
        self.btn_stop_server.configure(state="normal")
        self.btn_open.configure(state="normal")
        self.lbl_srv_status.configure(text="🟢 Server: läuft", text_color=C_GREEN)

        def run():
            try:
                from web_server import app
                import logging
                logging.getLogger('werkzeug').setLevel(logging.ERROR)
                port = self._get_port()
                host = self.ent_host.get().strip() or "0.0.0.0"
                self._log(f"Server gestartet auf {host}:{port}")
                app.run(host=host, port=port, use_reloader=False)
            except Exception as e:
                self._log(f"Server-Fehler: {e}")
                messagebox.showerror("Server Fehler", f"{e}")
                self._server_running = False

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

    def _stop_server(self):
        """Versucht den Flask-Server zu stoppen. (Nur möglich wenn Flask mit shutdown-Endpoint)"""
        self._server_running = False
        self.btn_server.configure(text="▶  Web-Server & Ilija Studio starten",
                                  state="normal", fg_color=C_GREEN)
        self.btn_stop_server.configure(state="disabled")
        self.btn_open.configure(state="disabled")
        self.lbl_srv_status.configure(text="⚫ Server: gestoppt", text_color=C_MUTED)
        self._log("Server-Stop angefordert. (Wird nach letzter Anfrage beendet)")
        # Flask in daemon-Thread → endet mit App-Beendigung
        # Für sofortigen Stop: os._exit() verwenden – das tut _quit_all()

    # ── Telegram starten/stoppen ─────────────────────────────────────────────
    def _start_telegram(self):
        if not self.ent_tg_token.get().strip():
            messagebox.showwarning("Fehlt", "Bitte erst einen Telegram Token eintragen und speichern!")
            return
        if self._telegram_running:
            return
        self._telegram_running = True
        self.btn_tg.configure(text="Telegram läuft...", state="disabled",
                              fg_color="#354E44")
        self.btn_stop_tg.configure(state="normal")
        self.lbl_tg_status.configure(text="🟢 Telegram: läuft", text_color=C_TEAL)

        def run():
            try:
                import telegram_bot
                self._log("Telegram Bot gestartet.")
                telegram_bot.main()
            except Exception as e:
                self._log(f"Telegram-Fehler: {e}")
                messagebox.showerror("Telegram Fehler", f"{e}")
                self._telegram_running = False

        self.telegram_thread = threading.Thread(target=run, daemon=True)
        self.telegram_thread.start()

    def _stop_telegram(self):
        self._telegram_running = False
        self.btn_tg.configure(text="▶  Telegram Bot starten", state="normal", fg_color=C_TEAL)
        self.btn_stop_tg.configure(state="disabled")
        self.lbl_tg_status.configure(text="⚫ Telegram: gestoppt", text_color=C_MUTED)
        self._log("Telegram-Stop angefordert.")

    # ── Alles beenden ─────────────────────────────────────────────────────────
    def _quit_all(self):
        if messagebox.askyesno("Ilija beenden",
                               "Alle Module (Server, Telegram Bot) beenden\nund Ilija schließen?"):
            self._log("Beende alle Module...")
            # Daemon-Threads enden automatisch mit dem Prozess
            self.destroy()
            os._exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback-Version mit Standard-TKinter (falls customtkinter fehlt)
# ─────────────────────────────────────────────────────────────────────────────
class IlijaAppTkFallback(tk.Tk):
    """Minimaler Fallback – bitte customtkinter installieren!"""
    def __init__(self):
        super().__init__()
        self.title("Ilija AI – Setup (Fallback-Modus)")
        self.geometry("600x400")
        self.configure(bg="#1e1e2e")
        tk.Label(self, text="⚡ Ilija AI – Setup & Control Center",
                 font=("Helvetica", 16, "bold"), bg="#1e1e2e", fg="#00D882").pack(pady=30)
        tk.Label(self,
                 text="customtkinter ist nicht installiert!\n\n"
                      "Bitte ausführen:\n\n    pip install customtkinter\n\n"
                      "und Ilija neu starten.",
                 font=("Helvetica", 12), bg="#1e1e2e", fg="#e2e2ee", justify="center").pack(pady=10)
        tk.Button(self, text="Beenden", bg="#ef4444", fg="white", font=("Helvetica", 11, "bold"),
                  command=self.destroy).pack(pady=30, ipadx=20, ipady=8)


# ─────────────────────────────────────────────────────────────────────────────
# Einstiegspunkt
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if HAS_CTK:
        app = IlijaApp()
        app.mainloop()
    else:
        app = IlijaAppTkFallback()
        app.mainloop()
