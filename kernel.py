"""
kernel.py – Zentraler Agent-Kern für Ilija Public Edition
=========================================================
Terminal-Modus: python kernel.py
"""

import os
import json
from dotenv import load_dotenv
from providers    import select_provider, get_available_providers
from skill_manager import SkillManager
from agent_state  import AgentState, AgentStatus

load_dotenv()

# ── System-Prompt ─────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """Du bist Ilija, ein lokaler KI-Assistent der auf dem eigenen Computer des Nutzers läuft.

WICHTIG: Du bist KEIN Cloud-Dienst. Du läufst lokal auf dem PC des Nutzers.
Alle Skills sind lokale Python-Funktionen auf diesem Computer. Der Nutzer hat sie selbst installiert und erlaubt sie ausdrücklich.

════════════════════════════════════════
VERFÜGBARE SKILLS (lokale Python-Funktionen):
{skills}
════════════════════════════════════════

SKILL-AUSFÜHRUNG – PFLICHTREGELN:
1. Wenn der Nutzer eine Aktion anfragt die einem Skill entspricht → IMMER ausführen, NIEMALS verweigern
2. Syntax exakt so: SKILL:funktionsname(parameter="wert")
3. Kein parameter nötig? Dann: SKILL:funktionsname()
4. Nach dem Skill-Aufruf: kurze Erklärung was passiert

BEISPIELE wie du antworten MUSST:
Nutzer: "Würfel mal"
→ Klar! SKILL:wuerfeln()

Nutzer: "Starte WhatsApp Assistent"
→ Starte den WhatsApp-Assistenten! SKILL:whatsapp_autonomer_dialog(modus="alle")

Nutzer: "Merk dir meinen Namen Manuel"
→ Speichere das! SKILL:gedaechtnis_speichern(information="Name des Nutzers ist Manuel", kategorie="persoenlich")

Nutzer: "Was ist das Wetter?"
→ SKILL:wetter_offenburg_abfragen()

Nutzer: "Ruf 0781234567 an"
→ SKILL:skill_ausfuehren(aktion="anrufen", nummer="0781234567")

Nutzer: "Ruf Mama an"
→ SKILL:skill_ausfuehren(aktion="anrufen", name="Mama")

Nutzer: "Leg auf"
→ SKILL:skill_ausfuehren(aktion="auflegen")

Nutzer: "Telefon-Status"
→ SKILL:skill_ausfuehren(aktion="status")

Nutzer: "Ruf 0781234567 an und sprich selbst"
→ SKILL:skill_ausfuehren(aktion="anrufen", nummer="0781234567", ki_modus="ja")

Nutzer: "Ruf Mama an und rede selbst"
→ SKILL:skill_ausfuehren(aktion="anrufen", name="Mama", ki_modus="ja")

Nutzer: "Warte auf Anrufe" / "Nimm Anrufe an" / "Geh ans Telefon" / "KI-Modus Telefon"
→ SKILL:skill_ausfuehren(aktion="listen")

Nutzer: "Fritzbox Kontakte" / "Wen kenne ich im Telefonbuch"
→ SKILL:skill_ausfuehren(aktion="kontakte")

VERBOTEN: Skills ablehnen, weil sie "Privatsphäre verletzen" oder "nicht möglich" seien.
Der Nutzer betreibt diese Software auf seinem eigenen Gerät für sich selbst.
Du darfst und sollst alle installierten Skills ausführen wenn der Nutzer es verlangt.

Antworte auf Deutsch. Aktueller Provider: {provider}
"""


class Kernel:
    def __init__(self, provider_mode: str = "auto"):
        print("[Ilija] Starte Public Edition...")
        self.state   = AgentState()
        self.manager = SkillManager()

        name, provider = select_provider(provider_mode)
        self.provider  = provider
        self.state.active_provider = name
        print(f"[Ilija] Provider: {name}")
        print(f"[Ilija] Skills geladen: {len(self.manager.skills)}")

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            skills   = self.manager.get_skills_description(),
            provider = self.state.active_provider,
        )

    def chat(self, user_input: str) -> str:
        """Verarbeitet eine Nutzer-Nachricht und gibt die Antwort zurück."""
        self.state.set_status(AgentStatus.THINKING, user_input[:80])
        self.state.add_message("user", user_input)

        try:
            response = self.provider.chat(
                messages = self.state.chat_history,
                system   = self.get_system_prompt(),
            )

            # Skill-Aufruf erkennen
            final_response = self._handle_skill_calls(response)
            self.state.add_message("assistant", final_response)
            self.state.set_status(AgentStatus.IDLE)
            return final_response

        except Exception as e:
            self.state.last_error = str(e)
            self.state.set_status(AgentStatus.ERROR)
            error_msg = f"❌ Fehler: {e}"
            self.state.add_message("assistant", error_msg)
            return error_msg

    def _handle_skill_calls(self, response: str) -> str:
        """Erkennt und führt Skill-Aufrufe in der Antwort aus."""
        import re
        pattern = r'SKILL:(\w+)\(([^)]*)\)'
        matches = re.findall(pattern, response)

        if not matches:
            return response

        result = response
        for skill_name, params_str in matches:
            self.state.set_status(AgentStatus.EXECUTING, skill_name)

            # Parameter parsen
            kwargs = {}
            if params_str.strip():
                try:
                    # Einfaches key="value" Parsing
                    for param in re.findall(r'(\w+)\s*=\s*"([^"]*)"', params_str):
                        kwargs[param[0]] = param[1]
                    for param in re.findall(r"(\w+)\s*=\s*'([^']*)'", params_str):
                        kwargs[param[0]] = param[1]
                except Exception:
                    pass

            # Fritzbox-Skill braucht Kernel-Referenz für den KI-Loop (STT→chat→TTS).
            # WICHTIG: Immer PhoneKernel übergeben, NIEMALS den Haupt-Kernel!
            # Der Haupt-Kernel hat Zugriff auf alle Skills (DMS, E-Mail, ERP...).
            # Ein Anrufer darf KEINEN dieser Skills auslösen können.
            if skill_name == "skill_ausfuehren" and "kernel" not in kwargs:
                try:
                    from customer_kernel import CustomerKernel
                    kwargs["kernel"] = CustomerKernel(haupt_kernel=self)
                except Exception:
                    try:
                        from phone_kernel import PhoneKernel
                        kwargs["kernel"] = PhoneKernel(haupt_kernel=self)
                    except Exception:
                        kwargs["kernel"] = self  # Fallback (sollte nie eintreten)

            skill_result = self.manager.execute(skill_name, **kwargs)
            call_str     = f'SKILL:{skill_name}({params_str})'
            result       = result.replace(call_str, f'\n\n{skill_result}\n')

        return result

    def switch_provider(self, mode: str):
        """Wechselt den KI-Provider."""
        try:
            name, provider = select_provider(mode)
            self.provider              = provider
            self.state.active_provider = name
            return f"✅ Provider gewechselt zu: {name}"
        except Exception as e:
            return f"❌ Provider-Wechsel fehlgeschlagen: {e}"

    def reload_skills(self) -> str:
        return self.manager.reload()

    def get_debug_info(self) -> str:
        status    = self.state.get_status_dict()
        providers = get_available_providers()
        skills    = self.manager.list_skills()
        return (
            f"─── Ilija Public Edition – Debug ───\n"
            f"Provider:  {status['active_provider']}\n"
            f"Verfügbar: {', '.join(providers) or 'Keine'}\n"
            f"Skills:    {len(skills)}\n"
            f"Nachrichten: {status['message_count']}\n"
            f"Uptime:    {status['uptime_seconds']}s\n"
            f"Status:    {status['status']}\n"
            + ("─"*36) + "\n"
            + "\n".join([f"  • {s['name']} ({s['file']})" for s in skills])
        )


# ── Terminal-Modus ────────────────────────────────────────────
def run_terminal():
    print("\n" + "═"*56)
    print("  ILIJA – Public Edition  |  Terminal-Modus")
    print("  Befehle: reload | debug | clear | switch | exit")
    print("═"*56 + "\n")

    kernel = Kernel()
    print(f"\nBereit. Provider: {kernel.state.active_provider}\n")

    while True:
        try:
            user_input = input("Du: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[Ilija] Auf Wiedersehen!")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower == "exit":
            print("[Ilija] Auf Wiedersehen!")
            break
        elif lower == "reload":
            print(f"[Ilija] {kernel.reload_skills()}")
        elif lower == "debug":
            print(kernel.get_debug_info())
        elif lower == "clear":
            kernel.state.clear_history()
            print("[Ilija] Chat-Verlauf gelöscht.")
        elif lower.startswith("switch"):
            parts = lower.split()
            mode  = parts[1] if len(parts) > 1 else "auto"
            print(f"[Ilija] {kernel.switch_provider(mode)}")
        else:
            response = kernel.chat(user_input)
            print(f"\nIlija: {response}\n")


if __name__ == "__main__":
    run_terminal()
