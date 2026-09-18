"""
customer_kernel.py – Sicherer Kernel für Kundenkanäle (Telefon, WhatsApp)
=========================================================================
Dünner Wrapper um PhoneDialog (Zustandsmaschine).

Architektur:
  PhoneKernel   → Eingeschränkter LLM-Kontext, Injection-Schutz, Provider
  PhoneDialog   → Python-gesteuerte Zustandsmaschine (alle Gesprächsschritte)
  CustomerKernel→ Verbindet beide — stellt die öffentliche API bereit

Die gesamte Gesprächslogik (Slot-Filling, Kalender-Check, Buchstabier-Modus,
3-Faktor-Identifikation) liegt in phone_dialog.py.
CustomerKernel ergänzt nur den Injection-Guard und die Antwort-Bereinigung.

Verwendung:
  from customer_kernel import CustomerKernel
  kernel = CustomerKernel(haupt_kernel=main_kernel)
  kernel.set_caller_id("+49761...")     # bei eingehendem Anruf
  antwort = kernel.chat("Guten Tag")
  kernel.reset_history()                # nach Gesprächsende
"""

import re
import logging
from phone_kernel import PhoneKernel, _bereinige_antwort, INJECTION_MUSTER

logger = logging.getLogger(__name__)


class CustomerKernel(PhoneKernel):
    """
    Öffentliche API für Telefon- und WhatsApp-Kanäle.

    - set_caller_id(caller_id)  → bei eingehendem Anruf aufrufen
    - reset_history()           → nach Gesprächsende aufrufen
    - begruessung               → Begrüßungsformel für TTS
    - chat(user_input)          → gibt TTS-fertige Antwort zurück
                                  oder "" während des Buchstabier-Modus
    """

    def __init__(self, haupt_kernel=None, config_pfad: str = "",
                 caller_id: str = ""):
        super().__init__(haupt_kernel=haupt_kernel, config_pfad=config_pfad)
        from phone_dialog import PhoneDialog
        self._dialog = PhoneDialog(
            provider=self.provider,
            config=self.config,
            info_reader=self._info_reader,
            caller_id=caller_id,
        )

    # ── Öffentliche API ───────────────────────────────────────────────────────

    def set_caller_id(self, caller_id: str):
        """Setzt die Anrufer-Kennung (Telefonnummer oder WhatsApp-Sender-ID)."""
        self._dialog.set_caller_id(caller_id)
        logger.info(f"[CustomerKernel] caller_id gesetzt: '{caller_id.strip()}'")

    def reset_history(self):
        """
        Gesprächsverlauf und Identifikation zurücksetzen.
        Wird von fritzbox_skill zu Beginn jedes neuen Anrufs aufgerufen.
        """
        self._dialog.reset()
        logger.info("[CustomerKernel] Gesprächsverlauf zurückgesetzt")

    @property
    def is_spelling_active(self) -> bool:
        """Gibt an, ob wir uns im Buchstabier-Modus befinden."""
        if hasattr(self, "_dialog") and hasattr(self._dialog, "slots"):
            return getattr(self._dialog.slots, "spelling_active", False)
        return False

    @property
    def begruessung(self) -> str:
        """Begrüßungsformel aus phone_config.json — für TTS beim Gesprächsbeginn."""
        return self.config.get("begruessung", "Guten Tag!")

    def chat(self, user_input: str) -> str:
        """
        Verarbeitet eine Kundennachricht und gibt eine TTS-fertige Antwort zurück.

        Rückgabe "" bedeutet: Buchstabier-Modus — kein TTS-Interrupt, einfach warten.
        """
        # Injection-Guard (aus PhoneKernel)
        user_lower = user_input.lower()
        for muster in INJECTION_MUSTER:
            if re.search(muster, user_lower):
                logger.warning(
                    f"[CustomerKernel] Prompt-Injection erkannt: '{user_input[:60]}'"
                )
                return self.config["nicht_zustaendig"]

        # Gesamte Gesprächslogik liegt in PhoneDialog
        response = self._dialog.process(user_input)

        if not response:
            return ""  # Buchstabier-Modus — kein TTS-Interrupt

        return _bereinige_antwort(response)
