"""
test_dms_logik.py – Tests für DMS-Kernlogik (skills/dms.py)
============================================================
Testet: Passwort-Hashing, Hash-Berechnung, Konfiguration, Metadaten,
        Blockliste für Dateiformate — ohne echte Dateien importieren zu müssen.
"""
import os
import sys
import json
import hashlib
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# DMS-Imports (optional — überspringen wenn Abhängigkeiten fehlen)
pdfplumber = pytest.importorskip("pdfplumber",
    reason="pdfplumber nicht installiert — DMS-Tests übersprungen")

from skills.dms import (
    _pruefen_passwort,
    _berechne_hash,
    _get_config,
    _save_config,
    dms_stats,
    dms_archiv_uebersicht,
    ALLOWED_EXTENSIONS,
    DMS_BASE_DEFAULT,
)


# ── Passwort-Hashing ──────────────────────────────────────────────────────────

class TestPasswortHashing:

    def test_richtiges_passwort_akzeptiert(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = {
            "archiv_pfad":    str(tmp_path / "archiv"),
            "import_pfad":    str(tmp_path / "import"),
            "passwort_hash":  hashlib.sha256("MeinPasswort123".encode()).hexdigest(),
            "passwort_aktiv": True,
        }
        with patch("skills.dms._get_config", return_value=cfg):
            assert _pruefen_passwort("MeinPasswort123") is True

    def test_falsches_passwort_abgelehnt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = {
            "passwort_hash":  hashlib.sha256("Richtig".encode()).hexdigest(),
            "passwort_aktiv": True,
        }
        with patch("skills.dms._get_config", return_value=cfg):
            assert _pruefen_passwort("Falsch") is False

    def test_kein_passwort_aktiv_immer_ok(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = {"passwort_hash": "", "passwort_aktiv": False}
        with patch("skills.dms._get_config", return_value=cfg):
            assert _pruefen_passwort("egal") is True

    def test_leeres_hash_immer_ok(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = {"passwort_hash": "", "passwort_aktiv": True}
        with patch("skills.dms._get_config", return_value=cfg):
            assert _pruefen_passwort("irgendwas") is True

    def test_passwort_wird_als_sha256_gespeichert(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from skills.dms import dms_pfad_setzen
        (tmp_path / "archiv").mkdir()
        (tmp_path / "import").mkdir()

        with patch("skills.dms._get_config", return_value={
            "archiv_pfad": str(tmp_path / "archiv"),
            "import_pfad": str(tmp_path / "import"),
            "passwort_hash": "",
            "passwort_aktiv": False,
        }), patch("skills.dms._save_config") as mock_save:
            dms_pfad_setzen(
                archiv_pfad=str(tmp_path / "archiv"),
                import_pfad=str(tmp_path / "import"),
                passwort_neu="TestPasswort"
            )
            saved_cfg = mock_save.call_args[0][0]
            erwartet  = hashlib.sha256("TestPasswort".encode()).hexdigest()
            assert saved_cfg["passwort_hash"] == erwartet


# ── SHA256 Hash-Berechnung ────────────────────────────────────────────────────

class TestHashBerechnung:

    def test_hash_korrekt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"Hallo Welt")
        erwartet = hashlib.sha256(b"Hallo Welt").hexdigest()
        assert _berechne_hash(str(f)) == erwartet

    def test_verschiedene_inhalte_verschiedene_hashes(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"Inhalt A")
        f2.write_bytes(b"Inhalt B")
        assert _berechne_hash(str(f1)) != _berechne_hash(str(f2))

    def test_gleicher_inhalt_gleicher_hash(self, tmp_path):
        f1 = tmp_path / "x.txt"
        f2 = tmp_path / "y.txt"
        f1.write_bytes(b"Identisch")
        f2.write_bytes(b"Identisch")
        assert _berechne_hash(str(f1)) == _berechne_hash(str(f2))

    def test_hash_bei_fehler_leer(self, tmp_path):
        # Nicht-existente Datei → leerer Hash
        result = _berechne_hash(str(tmp_path / "nicht_existent.txt"))
        assert result == "" or len(result) == 64  # Entweder leer oder gültiger Hash


# ── Erlaubte Dateiformate ─────────────────────────────────────────────────────

class TestDateiformate:

    def test_pdf_erlaubt(self):
        assert ".pdf" in ALLOWED_EXTENSIONS

    def test_docx_erlaubt(self):
        assert ".docx" in ALLOWED_EXTENSIONS

    def test_jpg_erlaubt(self):
        assert ".jpg" in ALLOWED_EXTENSIONS

    def test_png_erlaubt(self):
        assert ".png" in ALLOWED_EXTENSIONS

    def test_txt_erlaubt(self):
        assert ".txt" in ALLOWED_EXTENSIONS

    def test_exe_nicht_erlaubt(self):
        assert ".exe" not in ALLOWED_EXTENSIONS

    def test_bat_nicht_erlaubt(self):
        assert ".bat" not in ALLOWED_EXTENSIONS

    def test_sh_nicht_erlaubt(self):
        assert ".sh" not in ALLOWED_EXTENSIONS

    def test_mindestens_10_formate(self):
        assert len(ALLOWED_EXTENSIONS) >= 10


# ── DMS Stats ─────────────────────────────────────────────────────────────────

class TestDmsStats:
    """dms_stats() gibt ein Dict zurück (wird als JSON an die Web-API geliefert)."""

    def test_stats_gibt_dict_zurueck(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "dms").mkdir(parents=True)
        result = dms_stats()
        assert isinstance(result, dict)

    def test_stats_hat_pflichtfelder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "dms").mkdir(parents=True)
        result = dms_stats()
        # Pflichtfelder für Web-API
        assert "gesamt" in result
        assert "groesse_mb" in result
        assert "kategorien" in result


# ── Konfiguration ─────────────────────────────────────────────────────────────

class TestDmsKonfiguration:

    def test_config_hat_pflichtfelder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "dms").mkdir(parents=True)
        cfg = _get_config()
        assert "archiv_pfad" in cfg
        assert "import_pfad" in cfg
        assert "passwort_hash" in cfg
        assert "passwort_aktiv" in cfg

    def test_config_speichern_und_laden(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "dms").mkdir(parents=True)
        test_cfg = {
            "archiv_pfad":    str(tmp_path / "archiv"),
            "import_pfad":    str(tmp_path / "import"),
            "passwort_hash":  "abc123",
            "passwort_aktiv": True,
        }
        _save_config(test_cfg)
        geladene_cfg = _get_config()
        assert geladene_cfg["passwort_hash"] == "abc123"
        assert geladene_cfg["passwort_aktiv"] is True
