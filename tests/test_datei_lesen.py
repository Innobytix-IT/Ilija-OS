"""
test_datei_lesen.py – Tests für skills/datei_lesen.py
======================================================
Testet: datei_lesen — Erfolg, Fehlerbehandlung, Path-Traversal-Schutz
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skills.datei_lesen import datei_lesen


# ── Erfolgreiche Lesevorgänge ──────────────────────────────────────────────────

class TestDateiLesenErfolg:

    def test_liest_textdatei(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hallo Welt", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "Hallo Welt" in result

    def test_ausgabe_enthaelt_dateinamen(self, tmp_path):
        f = tmp_path / "meine_datei.txt"
        f.write_text("Inhalt", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "meine_datei.txt" in result

    def test_ausgabe_enthaelt_zeichenanzahl(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("12345", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "5" in result  # 5 Zeichen

    def test_liest_json_datei(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = datei_lesen(str(f))
        assert '"key"' in result

    def test_liest_markdown_datei(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Titel\nInhalt hier.", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "# Titel" in result

    def test_liest_csv_datei(self, tmp_path):
        f = tmp_path / "daten.csv"
        f.write_text("name,alter\nAnna,30", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "Anna" in result

    def test_mehrzeilige_datei(self, tmp_path):
        inhalt = "\n".join([f"Zeile {i}" for i in range(100)])
        f = tmp_path / "lang.txt"
        f.write_text(inhalt, encoding="utf-8")
        result = datei_lesen(str(f))
        assert "Zeile 0" in result
        assert "Zeile 99" in result

    def test_symbol_im_output(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("x", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "📄" in result

    def test_leere_datei(self, tmp_path):
        f = tmp_path / "leer.txt"
        f.write_text("", encoding="utf-8")
        result = datei_lesen(str(f))
        # Kein Fehler, aber 0 Zeichen
        assert "0" in result or "leer" in result.lower() or "📄" in result


# ── Fehlerfälle ───────────────────────────────────────────────────────────────

class TestDateiLesenFehler:

    def test_datei_nicht_gefunden(self, tmp_path):
        result = datei_lesen(str(tmp_path / "nicht_vorhanden.txt"))
        assert "❌" in result
        assert "nicht gefunden" in result.lower() or "Datei" in result

    def test_verzeichnis_statt_datei(self, tmp_path):
        result = datei_lesen(str(tmp_path))
        assert "❌" in result

    def test_leere_eingabe_fuhrt_zu_fehler(self):
        result = datei_lesen("")
        assert "❌" in result or "nicht gefunden" in result.lower()


# ── Sicherheit: Path-Traversal ────────────────────────────────────────────────

class TestDateiLesenSicherheit:

    def test_etc_passwd_blockiert(self):
        result = datei_lesen("/etc/passwd")
        # Entweder blockiert oder nicht gefunden (Windows)
        assert "❌" in result

    def test_windows_system32_blockiert(self, tmp_path):
        result = datei_lesen("C:/Windows/System32/cmd.exe")
        assert "❌" in result

    def test_windows_sam_blockiert(self, tmp_path):
        result = datei_lesen("C:/Windows/System32/config/SAM")
        assert "❌" in result

    def test_etc_shadow_blockiert(self):
        result = datei_lesen("/etc/shadow")
        assert "❌" in result

    def test_ssh_key_blockiert(self, tmp_path):
        result = datei_lesen(str(tmp_path / ".ssh" / "id_rsa"))
        assert "❌" in result

    def test_env_datei_blockiert(self, tmp_path):
        # .env Datei anlegen und versuchen zu lesen
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=abc123", encoding="utf-8")
        result = datei_lesen(str(env_file))
        assert "❌" in result

    def test_traversal_mit_doppelpunkt_normalisiert(self, tmp_path):
        # ../../../etc/passwd durch normpath bereinigt
        fake_path = str(tmp_path) + "/../../etc/passwd"
        result = datei_lesen(fake_path)
        assert "❌" in result

    def test_credentials_json_blockiert(self, tmp_path):
        result = datei_lesen(str(tmp_path / "credentials.json"))
        # Datei existiert gar nicht → nicht gefunden ist ok
        # Aber der Name muss blockiert sein falls Datei existieren würde
        f = tmp_path / "credentials.json"
        f.write_text('{"secret": "123"}', encoding="utf-8")
        result2 = datei_lesen(str(f))
        assert "❌" in result2

    def test_secrets_json_blockiert(self, tmp_path):
        f = tmp_path / "secrets.json"
        f.write_text('{"api_key": "xyz"}', encoding="utf-8")
        result = datei_lesen(str(f))
        assert "❌" in result

    def test_proc_cpuinfo_blockiert(self):
        result = datei_lesen("/proc/cpuinfo")
        assert "❌" in result

    def test_normale_datei_ausserhalb_system_erlaubt(self, tmp_path):
        # Normale Datei im temp-Verzeichnis darf gelesen werden
        f = tmp_path / "dokument.txt"
        f.write_text("Normal", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "Normal" in result

    # ── Neue Blocklist-Kategorien (Gemini-Fix: startswith statt Regex) ────────

    def test_aws_credentials_blockiert(self, tmp_path):
        """.aws-Verzeichnis wird über Segment-Prüfung blockiert."""
        f = tmp_path / ".aws" / "credentials"
        f.parent.mkdir(parents=True)
        f.write_text("[default]\naws_access_key_id = FAKE", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "❌" in result

    def test_gnupg_verzeichnis_blockiert(self, tmp_path):
        f = tmp_path / ".gnupg" / "secring.gpg"
        f.parent.mkdir(parents=True)
        f.write_text("fake gpg key", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "❌" in result

    def test_dev_null_blockiert(self):
        """/dev/ Präfix wird blockiert."""
        result = datei_lesen("/dev/null")
        assert "❌" in result

    def test_id_rsa_direkt_blockiert(self, tmp_path):
        """id_rsa als Dateiname direkt blockiert (ohne .ssh-Ordner)."""
        f = tmp_path / "id_rsa"
        f.write_text("-----BEGIN RSA PRIVATE KEY-----", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "❌" in result

    def test_sudoers_blockiert(self, tmp_path):
        f = tmp_path / "sudoers"
        f.write_text("root ALL=(ALL) ALL", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "❌" in result

    def test_ntds_dit_blockiert(self, tmp_path):
        f = tmp_path / "ntds.dit"
        f.write_text("fake AD database", encoding="utf-8")
        result = datei_lesen(str(f))
        assert "❌" in result

    def test_system32_segment_blockiert(self, tmp_path):
        """system32 als Pfadsegment wird blockiert."""
        result = datei_lesen(str(tmp_path / "system32" / "evil.exe"))
        assert "❌" in result

    def test_c_windows_pfad_blockiert(self):
        """c:/windows/ Präfix-Check (startswith, nicht Regex)."""
        result = datei_lesen("C:/Windows/win.ini")
        assert "❌" in result

    def test_gewoehnlicher_name_mit_aehnlichem_anfang_erlaubt(self, tmp_path):
        """'secrets_backup' beginnt mit 'secret' → blockiert."""
        f = tmp_path / "secrets_backup.txt"
        f.write_text("nur ein backup", encoding="utf-8")
        result = datei_lesen(str(f))
        # 'secrets_backup'.startswith('secret') → True → blockiert
        assert "❌" in result

    def test_normale_json_datei_erlaubt(self, tmp_path):
        """config.json (kein gesperrter Name) darf gelesen werden."""
        f = tmp_path / "config.json"
        f.write_text('{"theme": "dark"}', encoding="utf-8")
        result = datei_lesen(str(f))
        assert "theme" in result
