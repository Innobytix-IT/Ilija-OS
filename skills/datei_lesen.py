"""
datei_lesen.py – Lokale Datei einlesen für Ilija Public Edition
"""
import os

# ── Robuste Pfad-Blockliste (startswith statt Regex — sicherer & eindeutiger) ─
# Pfade werden normalisiert (lowercase, forward-slash) vor dem Vergleich.
_BLOCKED_PREFIXES = [
    # Linux/macOS Systempfade
    "/etc/",
    "/proc/",
    "/sys/",
    "/dev/",
    "/boot/",
    "/run/",
    # Windows Systempfade
    "c:/windows/",
    "c:\\windows\\",
    "c:/users/default/",
    "c:/programdata/microsoft/",
]

# Einzelne Dateinamen die absolut nie gelesen werden dürfen (Endteil des Pfads)
_BLOCKED_FILENAMES = {
    "passwd", "shadow", "sudoers", "sam", "ntds.dit",
    "id_rsa", "id_ed25519", "id_ecdsa",
    ".env",
}

# Verzeichnisanteile im Pfad die gesperrt sind
_BLOCKED_SEGMENTS = {
    ".ssh", ".gnupg", ".aws", ".kube",
    "system32", "syswow64",
}


def datei_lesen(pfad: str) -> str:
    """
    Liest den vollständigen Textinhalt einer lokalen Datei aus.
    Unterstützt: .txt, .md, .py, .json, .csv und alle anderen Textdateien.
    Beispiel: datei_lesen(pfad="/home/user/dokumente/notiz.txt")
    """
    try:
        pfad = os.path.expandvars(os.path.expanduser(pfad))
        pfad = os.path.normpath(pfad)

        # Pfad normalisiert für Vergleiche (forward-slash, lowercase)
        pfad_norm = pfad.replace("\\", "/").lower()

        # 1. Gesperrte Präfixe (Systempfade)
        for blocked in _BLOCKED_PREFIXES:
            if pfad_norm.startswith(blocked) or pfad_norm == blocked.rstrip("/"):
                return "❌ Zugriff verweigert: Dieser Pfad ist aus Sicherheitsgründen gesperrt."

        # 2. Gesperrte Dateinamen (Endteil)
        dateiname = os.path.basename(pfad_norm)
        if dateiname in _BLOCKED_FILENAMES:
            return "❌ Zugriff verweigert: Dieser Dateiname ist aus Sicherheitsgründen gesperrt."

        # 3. Gesperrte Verzeichnissegmente (credentials, .ssh etc.)
        segmente = set(pfad_norm.replace("\\", "/").split("/"))
        if segmente & _BLOCKED_SEGMENTS:
            return "❌ Zugriff verweigert: Dieser Pfad enthält ein gesperrtes Verzeichnis."

        # 4. credentials.json / secrets*.json über Namensmuster
        if (dateiname.startswith("credential") or dateiname.startswith("secret")
                or dateiname == ".env"):
            return "❌ Zugriff verweigert: Credentials-Dateien sind gesperrt."

        if not os.path.exists(pfad):
            return f"❌ Datei nicht gefunden: {pfad}"
        if os.path.isdir(pfad):
            return f"❌ Pfad ist ein Verzeichnis, keine Datei: {pfad}"

        with open(pfad, "r", encoding="utf-8", errors="replace") as f:
            inhalt = f.read()
        groesse = len(inhalt)
        return f"📄 {os.path.basename(pfad)} ({groesse} Zeichen):\n\n{inhalt}"
    except PermissionError:
        return f"❌ Keine Leseberechtigung für: {pfad}"
    except Exception as e:
        return f"❌ Fehler beim Lesen: {e}"


AVAILABLE_SKILLS = [datei_lesen]
