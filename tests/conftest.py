"""
conftest.py – Gemeinsame Fixtures für die Ilija-Public-Edition Testsuite
=========================================================================
Stellt Flask-Testclient, Mock-Kernel, temp. Verzeichnisse und Hilfsfunktionen bereit.
"""
import os
import sys
import json
import threading
import tempfile
import pytest
from unittest.mock import MagicMock, patch

# Projektwurzel zum Python-Pfad hinzufügen
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TESTS_DIR    = os.path.dirname(__file__)
for _p in (PROJECT_ROOT, TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from helpers import MockKernel, make_node, make_connection, workflow_payload  # noqa: F401


# ── Flask-App Fixture ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def flask_app(tmp_path_factory):
    """Erstellt eine Flask-Test-App mit Mock-Kernel."""
    from flask import Flask
    from flask_cors import CORS

    # Temporäre Datendirectories damit Tests nicht in echte Daten schreiben
    data_dir = tmp_path_factory.mktemp("data")
    os.environ["ILIJA_DATA_DIR"] = str(data_dir)

    app = Flask(
        __name__,
        template_folder=os.path.join(PROJECT_ROOT, "templates"),
        static_folder=os.path.join(PROJECT_ROOT, "static") if os.path.exists(os.path.join(PROJECT_ROOT, "static")) else None,
    )
    CORS(app)
    app.config["TESTING"] = True

    mock_kernel = MockKernel()
    lock = threading.Lock()

    # Workflow-Routen registrieren mit Mock-Kernel
    # _start_scheduler patchen damit kein Background-Thread gestartet wird
    with patch("workflow_routes._start_scheduler"):
        from workflow_routes import register_workflow_routes
        register_workflow_routes(app, lambda: mock_kernel, lock)

    # web_server Routen (Chat etc.) minimal nachbauen
    @app.route("/api/status")
    def status():
        from flask import jsonify
        return jsonify({"status": "idle", "provider": "mock", "model": "mock-model"})

    return app


@pytest.fixture
def client(flask_app):
    """HTTP-Testclient für die Flask-App."""
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def mock_kernel():
    """Isolierter Mock-Kernel für Unit-Tests."""
    return MockKernel()


# ── Temp-Verzeichnis Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tmp_notizen(tmp_path, monkeypatch):
    """Patcht basis_tools auf ein temporäres Notiz-Verzeichnis."""
    notizen_dir = tmp_path / "notizen"
    notizen_dir.mkdir()

    import skills.basis_tools as bt
    original_join = os.path.join

    def patched_join(a, b, *args):
        if a == "data/notizen":
            return str(notizen_dir / b)
        return original_join(a, b, *args)

    monkeypatch.setattr(os.path, "join", patched_join)
    monkeypatch.setattr(os, "makedirs", lambda p, **kw: None)
    return notizen_dir


@pytest.fixture
def tmp_datei(tmp_path):
    """Erstellt eine temporäre Textdatei für datei_lesen-Tests."""
    f = tmp_path / "test.txt"
    f.write_text("Hallo Ilija!\nZeile 2\nZeile 3", encoding="utf-8")
    return f


@pytest.fixture
def workflows_dir(tmp_path):
    """Gibt ein temporäres Workflow-Verzeichnis zurück."""
    d = tmp_path / "workflows"
    d.mkdir()
    return d


# Hinweis: make_node, make_connection, workflow_payload kommen aus helpers.py (oben importiert)
# Verbindungsformat: {"from": src, "to": dst} — konsistent mit workflow_routes.py
