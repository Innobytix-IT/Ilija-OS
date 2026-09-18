"""
fritzbox_telegram_erweiterung.py
=================================
Ergänzungen für fritzbox_skill.py + telegram_bot.py
damit Ilija per Telefonanruf mit dem Gesprächspartner sprechen kann.

ÄNDERUNGEN ÜBERSICHT
--------------------
1. fritzbox_skill.py  → 3 Fixes / Ergänzungen  (Abschnitt A)
2. telegram_bot.py    → 3 neue Befehle          (Abschnitt B)

INSTALLATION
------------
Die markierten Code-Blöcke in die jeweiligen Dateien einfügen/ersetzen.
"""


# ══════════════════════════════════════════════════════════════
# ABSCHNITT A – fritzbox_skill.py
# ══════════════════════════════════════════════════════════════

# ── A1: Bug-Fix in skill_ausfuehren() ────────────────────────
# PROBLEM: ki_modus wird doppelt berechnet (Zeile 783 + 795),
#          und ki_modus.lower() crasht wenn ki_modus="" (leerer String = False ist OK,
#          aber der zweite Aufruf auf Zeile 795 hat kein "if ki_modus"-Guard).
#
# ERSETZE Zeilen 783–805 in skill_ausfuehren() durch:

SKILL_AUSFUEHREN_ANRUFEN_FIX = '''
        use_ki      = ki_modus.lower() in ("ja", "yes", "true", "1") if ki_modus else False
        begruessung = "Hallo, hier ist Ilija. Wie kann ich dir helfen?" if use_ki else ""

        # Kontaktname in Nummer auflösen
        rufnummer = nummer_aufloesen(nummer)

        # Telefon starten falls noch nicht aktiv
        if _phone is None or not _phone.is_registered:
            logger.info("[Fritzbox] Starte Telefon für Anruf...")
            if not telefon_starten():
                return "❌ Telefon konnte nicht gestartet werden. SIP_USER/SIP_PASSWORD in .env prüfen."

        # Anruf starten (KI-Kernel wird übergeben damit STT→chat()→TTS funktioniert)
        ergebnis = _phone.anrufen(
            rufnummer,
            ki_modus=use_ki,
            ki_kernel=kernel,       # ← Kernel-Referenz für kernel.chat()
            ki_begruessung=begruessung,
        )

        # Optionaler End-Callback: Telegram-Bot informieren wenn Gespräch endet
        if use_ki and _phone:
            _phone._end_callback = globals().get("_call_end_callback")

        return ergebnis
'''

# ── A2: Callback-Mechanismus in FritzboxPhone ────────────────
# Füge diese Zeilen in FritzboxPhone.__init__() ein (nach self._status_log):
#
#     self._end_callback = None   # Callable() → wird gerufen wenn Gespräch endet

# Füge in _handle_sip(), im "BYE"-Block, nach self.is_audio_running = False ein:
#
#     if self._end_callback:
#         try:
#             self._end_callback(reason="BYE")
#         except Exception:
#             pass
#
# Gleiches für den "486 Busy"- und "603/480/487"-Block.

# ── A3: Globaler Callback-Slot ────────────────────────────────
# Füge am Ende von fritzbox_skill.py (vor AVAILABLE_SKILLS) ein:

FRITZBOX_SKILL_CALLBACK_SLOT = '''
# ── Globaler End-Callback (für Telegram-Bot) ──────────────────
# Der Telegram-Bot kann hier eine async-kompatible Funktion einhängen,
# die gerufen wird wenn ein Gespräch endet (BYE / Besetzt / Abgelehnt).
_call_end_callback = None   # wird von telegram_bot.py gesetzt


def set_call_end_callback(fn):
    """Registriert eine Funktion die beim Gesprächsende gerufen wird."""
    global _call_end_callback
    _call_end_callback = fn
'''


# ══════════════════════════════════════════════════════════════
# ABSCHNITT B – telegram_bot.py  (direkt einfügbar)
# ══════════════════════════════════════════════════════════════
# Füge diesen Block VOR der main()-Funktion ein.
# Außerdem in main() die drei CommandHandler-Zeilen ergänzen (siehe unten).

TELEGRAM_BOT_ERWEITERUNG = '''
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
            "📞 Verwendung: /call <Nummer oder Kontaktname>\\n"
            "Beispiel: /call Mama  oder  /call 015112345678\\n\\n"
            "Ilija führt das Gespräch dann selbst (Sprache ↔ KI)."
        )
        return

    ziel = " ".join(args).strip()
    await update.message.reply_text(f"📞 Starte Anruf zu: {ziel}\\nIlija übernimmt das Gespräch...")

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

    # Sync-Wrapper da der Fritzbox-Callback nicht async ist
    def _sync_end_callback(reason: str = ""):
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    loop.create_task, _notify_call_ended(reason)
                )
        except Exception:
            pass

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
        ergebnis = await asyncio.to_thread(
            skill_ausfuehren,
            "anrufen",          # aktion
            ziel,               # nummer
            "",                 # name (leer, da in nummer)
            "",                 # suche
            "ja",               # ki_modus → Ilija spricht selbst
            k,                  # kernel → für kernel.chat()
        )
        await update.message.reply_text(ergebnis)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler beim Anruf: {e}")


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
        await update.message.reply_text(f"❌ Fehler: {e}")


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
'''

# In main() ergänzen — direkt nach den bestehenden add_handler-Zeilen:
TELEGRAM_BOT_MAIN_ERGAENZUNG = '''
    app_bot.add_handler(CommandHandler("call",         cmd_call))
    app_bot.add_handler(CommandHandler("hangup",       cmd_hangup))
    app_bot.add_handler(CommandHandler("phone_status", cmd_phone_status))
'''


# ══════════════════════════════════════════════════════════════
# ABSCHNITT C – Erklärung des Gesamtflusses
# ══════════════════════════════════════════════════════════════

ABLAUF_ERKLAERUNG = """
GESPRÄCHSFLUSS NACH DEM PATCH
══════════════════════════════

Nutzer → Telegram: /call Mama
         │
         ▼
telegram_bot.py: cmd_call()
  1. Löst Kontaktname auf (fritzbox_skill.nummer_aufloesen)
  2. Registriert _sync_end_callback (Benachrichtigung wenn Gespräch endet)
  3. Ruft skill_ausfuehren("anrufen", ziel, ki_modus="ja", kernel=k)
         │
         ▼
fritzbox_skill.py: skill_ausfuehren()
  4. Telefon registrieren (SIP REGISTER → Fritzbox)
  5. SIP INVITE senden → Fritzbox wählt Mama an
         │
         ▼
Fritzbox: Mama nimmt ab
         │
         ▼
fritzbox_skill.py: _audio_ki_loop() läuft im Hintergrund-Thread
  6. Begrüßung: "Hallo, hier ist Ilija. Wie kann ich dir helfen?"
     (gTTS → 8kHz PCM → G.711 PCMA → RTP → Fritzbox → Mama hört Ilija)
         │
  7. Mama spricht → RTP-Pakete ankommen
     → RMS-Analyse erkennt Sprache
     → PCM puffern bis Stille (1.2s)
         │
  8. STT: Whisper / OpenAI Whisper-1
     PCM → WAV → Text ("Ich brauche einen Termin beim Arzt")
         │
  9. KI: kernel.chat(text)
     → Ilija denkt nach, nutzt alle Skills (Kalender, Email, ...)
     → Antwort: "Ich schaue gleich in deinen Kalender..."
         │
  10. TTS: gTTS → 8kHz PCM → RTP → Fritzbox → Mama hört Ilija
         │
  (Schleife: weiter zuhören → STT → chat() → TTS)
         │
  11. Mama legt auf → SIP BYE
     → is_audio_running = False
     → _end_callback() → Telegram: "📵 Gespräch beendet."

Nutzer → Telegram: /hangup  (jederzeit möglich)
  → skill_ausfuehren("auflegen") → SIP CANCEL/BYE
"""


if __name__ == "__main__":
    print(ABLAUF_ERKLAERUNG)
    print("\\nDiese Datei enthält Code-Snippets zum Einfügen.")
    print("Lies die Kommentare für Installationsanweisungen.")
