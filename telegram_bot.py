"""
telegram_bot.py – Telegram-Bot für Ilija Public Edition
Gecurter Fix für Markdown-Fehler bei Dateinamen
+ Fritzbox-Telefonie: /call, /listen, /hangup, /phone_status
"""

import os
import asyncio
import logging
import tempfile
import threading
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from kernel import Kernel

# Voice-Mode State (pro Chat)
voice_mode_chats: set = set()

load_dotenv()

logging.basicConfig(
    format="%(asctime)s – %(name)s – %(levelname)s – %(message)s",
    level=logging.WARNING
)

TOKEN         = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = set(
    int(uid.strip()) for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip().isdigit()
)

# Globaler Kernel
kernel      = None
kernel_lock = threading.RLock()


def get_kernel() -> Kernel:
    global kernel
    if kernel is None:
        with kernel_lock:
            if kernel is None:
                kernel = Kernel()
    return kernel


def is_allowed(user_id: int) -> bool:
    return not ALLOWED_USERS or user_id in ALLOWED_USERS


# ── Command Handlers ──────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "👋 Hallo! Ich bin Ilija – dein persönlicher KI-Assistent.\n\n"
        "Ich kann dir helfen mit:\n"
        "📁 Dokumente archivieren und suchen\n"
        "💬 WhatsApp überwachen und beantworten\n"
        "🔍 Internet-Recherchen\n"
        "📅 Termine und Kalender\n"
        "📞 Telefonieren (via Fritzbox)\n\n"
        "Schreib mir einfach, was du brauchst!"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "📖 Verfügbare Befehle:\n\n"
        "/start – Begrüßung\n"
        "/help – Diese Hilfe\n"
        "/reload – Skills neu laden\n"
        "/status – System-Status\n"
        "/clear – Chatverlauf löschen\n"
        "/switch – Provider wechseln\n\n"
        "Telefonie (Fritzbox):\n"
        "/call <Nummer/Name> – Anruf starten (Ilija spricht)\n"
        "/listen – Ilija geht ans Telefon wenn es klingelt\n"
        "/hangup – Laufendes Gespräch beenden\n"
        "/phone_status – Telefonstatus\n\n"
        "Für das DMS:\n"
        "/dms_import – Dateien im Import-Ordner anzeigen\n"
        "/dms_sort – Dokumente einsortieren\n"
        "/dms_stats – Archiv-Statistiken"
    )


async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    with kernel_lock:
        k   = get_kernel()
        msg = k.reload_skills()
    await update.message.reply_text(f"🔄 {msg}")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    with kernel_lock:
        k    = get_kernel()
        info = k.get_debug_info()
    await update.message.reply_text(f"System-Status:\n{info}")


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    with kernel_lock:
        k = get_kernel()
        k.state.clear_history()
    await update.message.reply_text("🗑️ Chat-Verlauf gelöscht.")


async def cmd_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    args = ctx.args
    mode = args[0].lower() if args else "auto"
    with kernel_lock:
        k   = get_kernel()
        msg = k.switch_provider(mode)
    await update.message.reply_text(msg)


async def cmd_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Schaltet Voice-Modus an/aus."""
    if not is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    if chat_id in voice_mode_chats:
        voice_mode_chats.discard(chat_id)
        await update.message.reply_text("🔇 Voice-Modus deaktiviert. Ilija antwortet wieder als Text.")
    else:
        voice_mode_chats.add(chat_id)
        await update.message.reply_text("🔊 Voice-Modus aktiviert! Ilija antwortet jetzt als Sprachnachricht.")


async def cmd_dms_import(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from skills.dms import dms_import_scan
    result = dms_import_scan()
    await update.message.reply_text(result)


async def cmd_dms_sort(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("⏳ KI analysiert und sortiert Dokumente ein...")
    with kernel_lock:
        k = get_kernel()
    from skills.dms import dms_einsortieren
    result = dms_einsortieren(provider=k.provider)
    if len(result) > 4000:
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000])
    else:
        await update.message.reply_text(result)


async def cmd_dms_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from skills.dms import dms_stats, dms_archiv_uebersicht
    stats      = dms_stats()
    uebersicht = dms_archiv_uebersicht()
    msg = (
        f"📊 DMS-Statistiken\n\n"
        f"📁 Dokumente gesamt: {stats['gesamt']}\n"
        f"💾 Speicher: {stats['groesse_mb']} MB\n"
        f"📥 Im Import-Ordner: {stats['import_count']}\n\n"
        f"{uebersicht}"
    )
    await update.message.reply_text(msg)


# ── Fritzbox-Telefonie Befehle ────────────────────────────────

async def cmd_call(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /call <Nummer oder Kontaktname>
    Ilija ruft die Nummer an und führt das Gespräch selbst (KI-Modus).
    Beispiel: /call Mama   oder   /call 015112345678
    """
    if not is_allowed(update.effective_user.id):
        return

    args = ctx.args
    if not args:
        await update.message.reply_text(
            "📞 Verwendung: /call <Nummer oder Kontaktname>\n"
            "Beispiel: /call Mama  oder  /call 015112345678\n\n"
            "Ilija führt das Gespräch dann selbst (Sprache ↔ KI)."
        )
        return

    ziel = " ".join(args).strip()
    await update.message.reply_text(f"📞 Starte Anruf zu: {ziel}\nIlija übernimmt das Gespräch...")

    chat_id = update.effective_chat.id

    # End-Callback: Telegram bekommt Bescheid wenn Gespräch endet
    async def _notify_call_ended(reason: str = ""):
        try:
            await ctx.bot.send_message(
                chat_id=chat_id,
                text=f"📵 Gespräch beendet.{' (' + reason + ')' if reason else ''}"
            )
        except Exception as e:
            logging.warning(f"[Call] End-Notify fehlgeschlagen: {e}")

    import asyncio
    main_loop = asyncio.get_running_loop()

    # Sync-Wrapper da der Fritzbox-Callback nicht async ist und im Neben-Thread läuft
    def _sync_end_callback(reason: str = ""):
        try:
            asyncio.run_coroutine_threadsafe(_notify_call_ended(reason), main_loop)
        except Exception as e:
            logging.warning(f"[Call] Callback-Loop-Fehler: {e}")

    # Callback im Skill registrieren
    try:
        from skills.fritzbox_skill import set_call_end_callback
        set_call_end_callback(_sync_end_callback)
    except ImportError:
        pass  # Callback-Feature noch nicht gepatcht — funktioniert auch ohne

    # Anruf starten (KI-Modus=ja, Kernel wird übergeben)
    with kernel_lock:
        k = get_kernel()

    try:
        from skills.fritzbox_skill import skill_ausfuehren
        from customer_kernel import CustomerKernel
        phone_k = CustomerKernel(haupt_kernel=k)
        ergebnis = await asyncio.to_thread(
            skill_ausfuehren,
            "anrufen",          # aktion
            ziel,               # nummer
            "",                 # name (leer, da in nummer)
            "",                 # suche
            "ja",               # ki_modus → Ilija spricht selbst
            phone_k,            # CustomerKernel → sicher + Kalender-Whitelist
        )
        await update.message.reply_text(ergebnis)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler beim Anruf: {e}")


async def cmd_listen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /listen – Schaltet Ilija in den "Anrufbeantworter"-Modus.
    Sie registriert sich an der Fritzbox und nimmt eingehende Anrufe sofort an.
    """
    if not is_allowed(update.effective_user.id):
        return

    await update.message.reply_text("⏳ Verbinde Ilija mit der Fritzbox für eingehende Anrufe...")
    chat_id = update.effective_chat.id

    # Benachrichtigung, wenn ein Gespräch beendet wird
    async def _notify_call_ended(reason: str = ""):
        try:
            await ctx.bot.send_message(
                chat_id=chat_id,
                text=f"📵 Gespräch beendet.{' (' + reason + ')' if reason else ''}"
            )
        except Exception as e:
            logging.warning(f"[Call] End-Notify fehlgeschlagen: {e}")

    import asyncio
    main_loop = asyncio.get_running_loop()

    def _sync_end_callback(reason: str = ""):
        try:
            asyncio.run_coroutine_threadsafe(_notify_call_ended(reason), main_loop)
        except Exception:
            pass

    try:
        from skills.fritzbox_skill import set_call_end_callback
        set_call_end_callback(_sync_end_callback)
    except ImportError:
        pass

    with kernel_lock:
        k = get_kernel()

    try:
        from skills.fritzbox_skill import skill_ausfuehren
        from customer_kernel import CustomerKernel
        phone_k = CustomerKernel(haupt_kernel=k)
        ergebnis = await asyncio.to_thread(
            skill_ausfuehren,
            "listen",           # aktion: zuhören/empfangen
            "",                 # nummer
            "",                 # name
            "",                 # suche
            "ja",               # ki_modus aktiv
            phone_k,            # CustomerKernel → sicher + Kalender-Whitelist
        )
        await update.message.reply_text(ergebnis)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_hangup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /hangup – Laufendes Gespräch beenden.
    """
    if not is_allowed(update.effective_user.id):
        return
    try:
        from skills.fritzbox_skill import skill_ausfuehren
        ergebnis = await asyncio.to_thread(skill_ausfuehren, "auflegen")
        await update.message.reply_text(ergebnis)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler beim Auflegen: {e}")


async def cmd_phone_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /phone_status – Telefonstatus abfragen.
    """
    if not is_allowed(update.effective_user.id):
        return
    try:
        from skills.fritzbox_skill import skill_ausfuehren
        ergebnis = await asyncio.to_thread(skill_ausfuehren, "status")
        await update.message.reply_text(ergebnis)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


# ── Spracherkennung ───────────────────────────────────────────
def transcribe_voice_sync(file_path: str) -> str:
    try:
        import whisper, warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="whisper")
        warnings.filterwarnings("ignore", category=UserWarning, module="torch")
        model  = whisper.load_model("base", device="cpu")
        result = model.transcribe(file_path, language="de")
        return result["text"].strip()
    except:
        pass

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            with open(file_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", file=f, language="de"
                )
            return transcript.text.strip()
        except Exception as e:
            return f"[Fehler: {e}]"
    return "[Spracherkennung nicht verfügbar]"


# ── Markdown-Bereinigung für TTS ─────────────────────────────
def _fuer_tts_bereinigen(text: str) -> str:
    """
    Entfernt Markdown-Formatierung damit sie nicht vorgelesen wird.
    Aus '**fett** und *kursiv*' wird 'fett und kursiv'.
    """
    import re

    # Code-Blöcke komplett entfernen (```...```)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Inline-Code entfernen (`code`)
    text = re.sub(r'`[^`]+`', '', text)

    # Überschriften: ### Titel → Titel
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Fett+Kursiv: ***text*** oder ___text___
    text = re.sub(r'\*{3}(.+?)\*{3}', r'\1', text)
    text = re.sub(r'_{3}(.+?)_{3}', r'\1', text)
    # Fett: **text** oder __text__
    text = re.sub(r'\*{2}(.+?)\*{2}', r'\1', text)
    text = re.sub(r'_{2}(.+?)_{2}', r'\1', text)
    # Kursiv: *text* oder _text_ (nur wenn nicht Leerzeichen daneben)
    text = re.sub(r'\*([^\s*][^*]*[^\s*])\*', r'\1', text)
    text = re.sub(r'\*([^\s*])\*', r'\1', text)
    text = re.sub(r'_([^\s_][^_]*[^\s_])_', r'\1', text)

    # Links: [Text](URL) → Text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Horizontale Linien
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Tabellen: | und --- Zeilen entfernen / bereinigen
    text = re.sub(r'^\|[-:| ]+\|$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\|', ' ', text)

    # Listen-Marker: - item, * item, + item, 1. item
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Blockquotes: > text
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)

    # Mehrfache Leerzeilen auf eine reduzieren
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Mehrfache Leerzeichen
    text = re.sub(r'  +', ' ', text)

    return text.strip()


# ── Text-to-Speech ───────────────────────────────────────────
def tts_to_ogg(text: str) -> str:
    from gtts import gTTS
    import subprocess, shutil

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        ogg_path = f.name

    tts = gTTS(text=text, lang="de", slow=False)
    tts.save(mp3_path)

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(
        [ffmpeg, "-y", "-i", mp3_path, "-filter:a", "atempo=1.2",
         "-c:a", "libopus", ogg_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
    os.unlink(mp3_path)
    return ogg_path


async def send_response(update: Update, text: str):
    """Sendet Antwort als Sprache oder Text je nach Voice-Mode."""
    chat_id = update.effective_chat.id
    if chat_id in voice_mode_chats:
        try:
            tts_text = _fuer_tts_bereinigen(text)
            ogg_path = await asyncio.to_thread(tts_to_ogg, tts_text)
            with open(ogg_path, "rb") as f:
                await update.message.reply_voice(voice=f)
            os.unlink(ogg_path)
            return
        except Exception as e:
            logging.warning(f"TTS fehlgeschlagen: {e} – sende als Text")
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    else:
        await update.message.reply_text(text)


# ── Message Handler ───────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_input = update.message.text or ""
    if not user_input.strip():
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    with kernel_lock:
        k = get_kernel()
    response = k.chat(user_input)
    await send_response(update, response)


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("🎤 Transkribiere Sprachnachricht...")
    voice_file = await ctx.bot.get_file(update.message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await voice_file.download_to_drive(tmp_path)
        transcript = await asyncio.to_thread(transcribe_voice_sync, tmp_path)
        await update.message.reply_text(f"📝 Erkannt: {transcript}")
        with kernel_lock:
            k = get_kernel()
        response = k.chat(transcript)
        await send_response(update, response)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Dokumente direkt in DMS-Import speichern."""
    if not is_allowed(update.effective_user.id):
        return
    doc  = update.message.document
    file = await ctx.bot.get_file(doc.file_id)
    import_dir = os.path.join("data", "dms", "import")
    os.makedirs(import_dir, exist_ok=True)
    filepath = os.path.join(import_dir, doc.file_name)
    await file.download_to_drive(filepath)
    await update.message.reply_text(
        f"📥 {doc.file_name} gespeichert.\n"
        f"Nutze /dms_sort zum Archivieren."
    )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fotos (Dokument-Scans) in DMS-Import speichern."""
    if not is_allowed(update.effective_user.id):
        return
    photo    = update.message.photo[-1]
    file     = await ctx.bot.get_file(photo.file_id)
    filename = f"scan_{photo.file_id[:8]}.jpg"
    import_dir = os.path.join("data", "dms", "import")
    os.makedirs(import_dir, exist_ok=True)
    filepath = os.path.join(import_dir, filename)
    await file.download_to_drive(filepath)

    caption = update.message.caption or ""
    prompt  = f"Foto erhalten: {filename}. {caption}"

    with kernel_lock:
        k = get_kernel()
    response = k.chat(prompt)
    await update.message.reply_text(f"📸 Scan gespeichert als {filename}\n\n{response}")


# ── Bot starten ───────────────────────────────────────────────
def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN nicht gesetzt!")
        return
    app_bot = Application.builder().token(TOKEN).build()

    # Standard-Befehle
    app_bot.add_handler(CommandHandler("start",        cmd_start))
    app_bot.add_handler(CommandHandler("help",         cmd_help))
    app_bot.add_handler(CommandHandler("reload",       cmd_reload))
    app_bot.add_handler(CommandHandler("status",       cmd_status))
    app_bot.add_handler(CommandHandler("clear",        cmd_clear))
    app_bot.add_handler(CommandHandler("switch",       cmd_switch))
    app_bot.add_handler(CommandHandler("voice",        cmd_voice))
    app_bot.add_handler(CommandHandler("dms_import",   cmd_dms_import))
    app_bot.add_handler(CommandHandler("dms_sort",     cmd_dms_sort))
    app_bot.add_handler(CommandHandler("dms_stats",    cmd_dms_stats))

    # Fritzbox-Telefonie
    app_bot.add_handler(CommandHandler("call",         cmd_call))
    app_bot.add_handler(CommandHandler("listen",       cmd_listen))
    app_bot.add_handler(CommandHandler("hangup",       cmd_hangup))
    app_bot.add_handler(CommandHandler("phone_status", cmd_phone_status))

    # Nachrichten-Handler
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_bot.add_handler(MessageHandler(filters.VOICE | filters.AUDIO,   handle_voice))
    app_bot.add_handler(MessageHandler(filters.Document.ALL,            handle_document))
    app_bot.add_handler(MessageHandler(filters.PHOTO,                   handle_photo))

    print("[Ilija] Bot läuft...")
    app_bot.run_polling()


if __name__ == "__main__":
    main()