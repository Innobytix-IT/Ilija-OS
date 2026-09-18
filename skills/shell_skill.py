"""
shell_skill.py – Shell-Ausführung für den Ilija-Agenten (Gemini-Kernel)
Nur aktiv wenn der Nutzer die Shell-Freigabe bewusst eingeschaltet hat.
"""
import os
import subprocess

# Derselbe Flag-Pfad wie in agent_core.py
_SHELL_FLAG = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "agent", "shell_enabled")
)


def shell_ausfuehren(befehl: str, timeout: int = 30) -> str:
    """
    Führt einen Shell-Befehl aus und gibt die Ausgabe zurück.
    Nur verfügbar wenn der Nutzer die Shell-Freigabe in der App aktiviert hat.
    befehl: Der auszuführende Shell-Befehl (z.B. "ls -la ~/Desktop")
    timeout: Maximale Wartezeit in Sekunden (Standard: 30)
    Beispiel: shell_ausfuehren(befehl="ls ~/Desktop")
    Beispiel: shell_ausfuehren(befehl="pip install selenium --upgrade", timeout=60)
    """
    if not os.path.exists(_SHELL_FLAG):
        return (
            "❌ Shell-Ausführung nicht freigegeben.\n"
            "Bitte in der App unter dem Chat-Fenster den Shell-Toggle aktivieren."
        )
    try:
        result = subprocess.run(
            befehl,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.expanduser("~"),
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"⚠️ Befehl beendet mit Exit-Code {result.returncode}:\n{err or out}"
        return out if out else "✅ Befehl erfolgreich ausgeführt (keine Ausgabe)"
    except subprocess.TimeoutExpired:
        return f"❌ Timeout nach {timeout}s – Befehl abgebrochen"
    except Exception as e:
        return f"❌ Fehler: {e}"


AVAILABLE_SKILLS = [shell_ausfuehren]
