"""
telegram_skill.py – Telegram-Integration für Ilija Public Edition
==================================================================
Ilija ist über Telegram erreichbar: Text, Dateien, Fotos, Sprachnachrichten.

Setup:
  1. pip install pyTelegramBotAPI requests
  2. Optional für Sprach-Transkription: pip install openai-whisper
  3. Bot bei @BotFather erstellen → Token kopieren
  4. telegram_konfigurieren(token="...", chat_id="...") ausführen
  5. telegram_starten() ausführen

Chat-ID herausfinden:
  Schreibe deinem Bot eine Nachricht, dann telegram_chat_id_anzeigen() aufrufen.
"""

import os
import json
import threading
import requests as _requests
from datetime import datetime

# ── Konfiguration ────────────────────────────────────────────
_CONFIG_DIR  = os.path.join("data", "telegram")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "telegram_config.json")
_DL_DIR      = os.path.join(_CONFIG_DIR, "downloads")

_bot_thread    = None
_bot_running   = False
_bot_instance  = None
_stop_event    = threading.Event()

ILIJA_API = "http://127.0.0.1:5000/api/chat"


# ── Hilfsfunktionen ──────────────────────────────────────────

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


def _ilija_fragen(nachricht: str) -> str:
    """Schickt eine Nachricht an die lokale Ilija-API und gibt die Antwort zurück."""
    try:
        r = _requests.post(ILIJA_API, json={"message": nachricht}, timeout=120)
        if r.ok:
            return r.json().get("response", "❌ Keine Antwort von Ilija.")
        return f"❌ Ilija API Fehler: {r.status_code}"
    except _requests.exceptions.ConnectionError:
        return "❌ Ilija läuft nicht (Verbindung zu 127.0.0.1:5000 fehlgeschlagen)."
    except Exception as e:
        return f"❌ Fehler: {e}"


def _transkribieren(datei_pfad: str) -> str:
    """Versucht eine Audiodatei zu transkribieren (Whisper falls installiert)."""
    try:
        import whisper
        model = whisper.load_model("base")
        ergebnis = model.transcribe(datei_pfad, language="de")
        return ergebnis.get("text", "").strip()
    except ImportError:
        return None
    except Exception as e:
        return None


def _datei_herunterladen(bot, file_id: str, dateiname: str) -> str:
    """Lädt eine Telegram-Datei herunter und gibt den lokalen Pfad zurück."""
    os.makedirs(_DL_DIR, exist_ok=True)
    try:
        datei_info = bot.get_file(file_id)
        pfad = os.path.join(_DL_DIR, dateiname)
        downloaded = bot.download_file(datei_info.file_path)
        with open(pfad, "wb") as f:
            f.write(downloaded)
        return pfad
    except Exception as e:
        return f"❌ Download fehlgeschlagen: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 1 – Konfigurieren
# ═══════════════════════════════════════════════════════════════

def telegram_konfigurieren(token: str = "", chat_id: str = "") -> str:
    """
    Telegram-Bot konfigurieren. Token vom @BotFather, Chat-ID nach erstem Schreiben mit telegram_chat_id_anzeigen() ermitteln.
    Beispiel: telegram_konfigurieren(token="123456:ABC-DEF...", chat_id="987654321")
    """
    if not token:
        return (
            "❌ Kein Token angegeben.\n\n"
            "📋 So erstellst du einen Bot:\n"
            "  1. Telegram öffnen → @BotFather suchen\n"
            "  2. /newbot eingeben → Namen vergeben\n"
            "  3. Token kopieren (sieht so aus: 123456789:ABC-DEFxyz...)\n"
            "  4. Dem neuen Bot eine Nachricht schicken\n"
            "  5. telegram_konfigurieren(token='DEIN_TOKEN') aufrufen\n"
            "  6. telegram_chat_id_anzeigen() aufrufen um deine Chat-ID zu erhalten"
        )

    cfg = {
        "token":            token,
        "chat_id":          chat_id,
        "konfiguriert_am":  datetime.now().isoformat(),
    }
    _cfg_speichern(cfg)

    status = "✅ Token gespeichert"
    if not chat_id:
        status += "\n⚠️  Noch keine Chat-ID. Schreibe dem Bot eine Nachricht, dann telegram_chat_id_anzeigen() aufrufen."
    else:
        status += f"\n✅ Chat-ID: {chat_id}"

    return status


# ═══════════════════════════════════════════════════════════════
#  SKILL 2 – Chat-ID ermitteln
# ═══════════════════════════════════════════════════════════════

def telegram_chat_id_anzeigen() -> str:
    """
    Zeigt die Chat-IDs aller Nutzer die dem Bot geschrieben haben.
    Vorher: Schreibe dem Bot eine Nachricht in Telegram.
    Beispiel: telegram_chat_id_anzeigen()
    """
    cfg = _cfg_laden()
    if not cfg.get("token"):
        return "❌ Kein Token konfiguriert. Zuerst telegram_konfigurieren() ausführen."

    try:
        import telebot
        bot = telebot.TeleBot(cfg["token"], parse_mode=None)
        updates = bot.get_updates()

        if not updates:
            return (
                "📭 Keine Nachrichten gefunden.\n"
                "Schreibe zuerst eine Nachricht an deinen Bot in Telegram, dann erneut versuchen."
            )

        gesehen = set()
        zeilen  = ["📋 Gefundene Chat-IDs:\n"]
        for upd in updates:
            if upd.message and upd.message.chat.id not in gesehen:
                gesehen.add(upd.message.chat.id)
                name = upd.message.from_user.first_name or "Unbekannt"
                zeilen.append(f"  👤 {name}: chat_id = {upd.message.chat.id}")

        zeilen.append(
            "\n💡 Tipp: telegram_konfigurieren(token='DEIN_TOKEN', chat_id='DEINE_ID') ausführen."
        )
        return "\n".join(zeilen)

    except ImportError:
        return "❌ pyTelegramBotAPI nicht installiert. Ausführen: pip install pyTelegramBotAPI"
    except Exception as e:
        return f"❌ Fehler: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 3 – Bot starten (Hintergrund-Polling)
# ═══════════════════════════════════════════════════════════════

def telegram_starten() -> str:
    """
    Startet den Telegram-Bot im Hintergrund. Nachrichten werden automatisch an Ilija weitergeleitet.
    Unterstützt: Text, Sprachnachrichten, Fotos, Dokumente.
    Beispiel: telegram_starten()
    """
    global _bot_thread, _bot_running, _bot_instance, _stop_event

    if _bot_running:
        return "⚠️  Bot läuft bereits."

    cfg = _cfg_laden()
    if not cfg.get("token"):
        return "❌ Kein Token. Zuerst telegram_konfigurieren() ausführen."
    if not cfg.get("chat_id"):
        return "❌ Keine Chat-ID. Zuerst telegram_chat_id_anzeigen() und dann telegram_konfigurieren() mit chat_id ausführen."

    try:
        import telebot
    except ImportError:
        return "❌ pyTelegramBotAPI nicht installiert.\nAusführen: pip install pyTelegramBotAPI requests"

    _stop_event.clear()

    def bot_loop():
        global _bot_running, _bot_instance

        token   = cfg["token"]
        chat_id = str(cfg["chat_id"])

        bot = telebot.TeleBot(token, parse_mode=None)
        _bot_instance = bot
        _bot_running  = True

        erlaubte_ids = {chat_id}

        def sicherheit(message):
            """Nur konfigurierte Chat-ID darf Ilija nutzen."""
            return str(message.chat.id) in erlaubte_ids

        # ── Text-Nachrichten ──────────────────────────────────
        @bot.message_handler(func=lambda m: sicherheit(m), content_types=["text"])
        def handle_text(message):
            try:
                bot.send_chat_action(message.chat.id, "typing")
                antwort = _ilija_fragen(message.text)
                # Telegram-Limit: 4096 Zeichen pro Nachricht
                for i in range(0, len(antwort), 4000):
                    bot.send_message(message.chat.id, antwort[i:i+4000])
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Fehler: {e}")

        # ── Sprachnachrichten ─────────────────────────────────
        @bot.message_handler(func=lambda m: sicherheit(m), content_types=["voice"])
        def handle_voice(message):
            try:
                bot.send_chat_action(message.chat.id, "typing")
                zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
                dateiname   = f"voice_{zeitstempel}.ogg"
                pfad        = _datei_herunterladen(bot, message.voice.file_id, dateiname)

                if pfad.startswith("❌"):
                    bot.send_message(message.chat.id, pfad)
                    return

                # Transkription versuchen
                transkript = _transkribieren(pfad)
                if transkript:
                    bot.send_message(message.chat.id, f"🎤 Ich habe verstanden: \"{transkript}\"")
                    antwort = _ilija_fragen(transkript)
                else:
                    antwort = _ilija_fragen(
                        f"[Sprachnachricht empfangen. Datei gespeichert unter: {pfad}. "
                        f"Whisper ist nicht installiert, daher keine Transkription möglich. "
                        f"Teile dem Nutzer mit wie er Whisper installieren kann: pip install openai-whisper]"
                    )

                for i in range(0, len(antwort), 4000):
                    bot.send_message(message.chat.id, antwort[i:i+4000])

            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Fehler bei Sprachnachricht: {e}")

        # ── Fotos ─────────────────────────────────────────────
        @bot.message_handler(func=lambda m: sicherheit(m), content_types=["photo"])
        def handle_photo(message):
            try:
                bot.send_chat_action(message.chat.id, "typing")
                zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Größtes verfügbares Foto nehmen
                foto      = message.photo[-1]
                dateiname = f"foto_{zeitstempel}.jpg"
                pfad      = _datei_herunterladen(bot, foto.file_id, dateiname)

                caption = message.caption or ""
                frage   = (
                    f"[Foto empfangen und gespeichert unter: {pfad}. "
                    f"Bildunterschrift: '{caption}'. "
                    f"Bestätige den Empfang und frage was mit dem Foto gemacht werden soll.]"
                )
                antwort = _ilija_fragen(frage)
                bot.send_message(message.chat.id, antwort)

            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Fehler bei Foto: {e}")

        # ── Dokumente / Dateien ───────────────────────────────
        @bot.message_handler(func=lambda m: sicherheit(m), content_types=["document"])
        def handle_dokument(message):
            try:
                bot.send_chat_action(message.chat.id, "typing")
                zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
                original_name = message.document.file_name or f"datei_{zeitstempel}"
                # Zeitstempel-Präfix um Kollisionen zu vermeiden
                dateiname = f"{zeitstempel}_{original_name}"
                pfad      = _datei_herunterladen(bot, message.document.file_id, dateiname)

                caption = message.caption or ""
                frage   = (
                    f"[Datei '{original_name}' empfangen, gespeichert unter: {pfad}. "
                    f"Kommentar: '{caption}'. "
                    f"Bestätige den Empfang und frage was mit der Datei gemacht werden soll.]"
                )
                antwort = _ilija_fragen(frage)
                bot.send_message(message.chat.id, antwort)

            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Fehler bei Datei: {e}")

        # ── Unbekannte Absender blockieren ────────────────────
        @bot.message_handler(func=lambda m: not sicherheit(m))
        def handle_unbekannt(message):
            bot.send_message(
                message.chat.id,
                "🔒 Dieser Bot ist privat und nur für autorisierte Nutzer."
            )

        print(f"[Telegram] Bot gestartet. Warte auf Nachrichten...")
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=20, stop_polling_event=_stop_event)
        except Exception as e:
            print(f"[Telegram] Bot gestoppt: {e}")
        finally:
            _bot_running = False

    _bot_thread = threading.Thread(target=bot_loop, daemon=True, name="telegram-bot")
    _bot_thread.start()

    return (
        f"✅ Telegram-Bot gestartet!\n"
        f"   Token:    ...{cfg['token'][-10:]}\n"
        f"   Chat-ID:  {cfg['chat_id']}\n"
        f"   Schreibe jetzt deinem Bot auf Telegram — Ilija antwortet direkt.\n"
        f"   Bot stoppen: telegram_stoppen()"
    )


# ═══════════════════════════════════════════════════════════════
#  SKILL 4 – Bot stoppen
# ═══════════════════════════════════════════════════════════════

def telegram_stoppen() -> str:
    """
    Stoppt den laufenden Telegram-Bot.
    Beispiel: telegram_stoppen()
    """
    global _bot_running, _bot_instance

    if not _bot_running:
        return "⚠️  Bot läuft nicht."

    try:
        _stop_event.set()
        if _bot_instance:
            _bot_instance.stop_polling()
        _bot_running = False
        return "✅ Telegram-Bot gestoppt."
    except Exception as e:
        return f"❌ Fehler beim Stoppen: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 5 – Nachricht senden (aus Workflow heraus)
# ═══════════════════════════════════════════════════════════════

def telegram_senden(nachricht: str = "") -> str:
    """
    Sendet eine Nachricht von Ilija an den konfigurierten Telegram-Chat.
    Nützlich um Workflow-Ergebnisse aktiv per Telegram zu melden.
    Beispiel: telegram_senden(nachricht="Dein Morgen-Report ist fertig!")
    """
    if not nachricht:
        return "❌ Bitte nachricht angeben."

    cfg = _cfg_laden()
    if not cfg.get("token") or not cfg.get("chat_id"):
        return "❌ Nicht konfiguriert. telegram_konfigurieren() ausführen."

    try:
        import telebot
        bot = telebot.TeleBot(cfg["token"], parse_mode=None)
        for i in range(0, len(nachricht), 4000):
            bot.send_message(cfg["chat_id"], nachricht[i:i+4000])
        return f"✅ Nachricht gesendet an Chat-ID {cfg['chat_id']}."
    except ImportError:
        return "❌ pyTelegramBotAPI nicht installiert: pip install pyTelegramBotAPI"
    except Exception as e:
        return f"❌ Fehler beim Senden: {e}"


# ═══════════════════════════════════════════════════════════════
#  SKILL 6 – Status
# ═══════════════════════════════════════════════════════════════

def telegram_status() -> str:
    """
    Zeigt den aktuellen Status des Telegram-Bots.
    Beispiel: telegram_status()
    """
    cfg = _cfg_laden()
    if not cfg:
        return "📭 Telegram nicht konfiguriert. telegram_konfigurieren() ausführen."

    status  = "🟢 Läuft" if _bot_running else "🔴 Gestoppt"
    token_k = f"...{cfg['token'][-10:]}" if cfg.get("token") else "—"

    return (
        f"📱 Telegram-Bot Status:\n"
        f"   Status:   {status}\n"
        f"   Token:    {token_k}\n"
        f"   Chat-ID:  {cfg.get('chat_id', '—')}\n"
        f"   Eingerichtet: {cfg.get('konfiguriert_am', '?')[:10]}\n"
        f"   Downloads: {_DL_DIR}"
    )


# ═══════════════════════════════════════════════════════════════
#  AVAILABLE_SKILLS
# ═══════════════════════════════════════════════════════════════

AVAILABLE_SKILLS = [
    telegram_konfigurieren,
    telegram_chat_id_anzeigen,
    telegram_starten,
    telegram_stoppen,
    telegram_senden,
    telegram_status,
]
