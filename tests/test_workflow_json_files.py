"""
test_workflow_json_files.py – Vollständigkeitstest der Workflow-JSON-Testdateien
=================================================================================
Lädt alle JSON-Testworkflows aus data/workflows/test/, prüft ihre Struktur
(Vollständigkeit, Konsistenz der Verbindungen) und führt sie über die echte
Workflow-Engine aus. Externes Netz und fehlende Credentials führen zu ❌-Meldungen
in den Node-Resultaten, aber nie zu Python-Exceptions oder HTTP != 200.

Abdeckung der Node-Typen nach Dateien:
  trigger            — Workflow1-30
  schedule_trigger   — Workflow2,4,6,8,13,17,22,25,28,30
  webhook_trigger    — Workflow9
  set                — Workflow5,10,15,16,19,23,26
  code               — Workflow15,23,26
  chat               — Workflow1-33 (viele)
  chatfilter         — Workflow31  ← neu
  note               — Workflow32  ← neu
  memory_window      — Workflow33  ← neu
  memory_summary     — Workflow33  ← neu
  skill              — Workflow1-33 (viele)
  loop               — Workflow10,30
  condition          — Workflow30
  switch             — Workflow16
  http               — Workflow11,18,30
  error_handler      — Workflow18,30
  wait               — Workflow21
  telegram           — Workflow4,6,9,11,13,16,21,25,30
  email              — Workflow4,8,16,17,18,24,30
  google_docs        — Workflow3,5,17,20,22,25,28,30
  google_sheets      — Workflow22,30
"""
import os
import sys
import json
import glob
import threading
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from helpers import MockKernel

# ── Alle JSON-Testworkflows einlesen ──────────────────────────────────────────

_WF_TEST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "workflows", "test")
)
_WF_FILES = sorted(glob.glob(os.path.join(_WF_TEST_DIR, "*.json")))

# Dateibasis als Test-ID (z.B. "Test_Workflow1.json")
_WF_IDS = [os.path.basename(p) for p in _WF_FILES]


def _load(path: str) -> dict:
    """Lädt eine Workflow-JSON-Datei."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Sanity-Check: Dateien vorhanden ───────────────────────────────────────────

def test_mindestens_33_workflow_dateien():
    """Es müssen mindestens 33 Test-Workflow-Dateien vorhanden sein."""
    assert len(_WF_FILES) >= 33, (
        f"Erwartet ≥33 Test-Workflow-Dateien, gefunden: {len(_WF_FILES)}"
    )


def test_alle_bekannten_dateien_vorhanden():
    """Die Basis-Dateien Test_Workflow1–30 sowie 31–33 müssen existieren."""
    namen = set(_WF_IDS)
    for i in list(range(1, 31)) + [31, 32, 33]:
        assert f"Test_Workflow{i}.json" in namen, (
            f"Test_Workflow{i}.json fehlt im Verzeichnis {_WF_TEST_DIR}"
        )


# ── Struktur-Validierung (parametrisiert über alle Dateien) ───────────────────

class TestWorkflowStruktur:
    """Jede JSON-Datei muss eine gültige, konsistente Workflow-Struktur aufweisen."""

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_valides_json(self, wf_path):
        """Datei muss als valides JSON-Objekt lesbar sein."""
        data = _load(wf_path)
        assert isinstance(data, dict), "Workflow-Root muss ein JSON-Objekt sein"

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_pflichtfelder_vorhanden(self, wf_path):
        """Pflichtfelder id, name, nodes, connections müssen vorhanden sein."""
        data = _load(wf_path)
        for feld in ("id", "name", "nodes", "connections"):
            assert feld in data, (
                f"Pflichtfeld '{feld}' fehlt in {os.path.basename(wf_path)}"
            )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_id_und_name_nicht_leer(self, wf_path):
        """Workflow-ID und -Name dürfen nicht leer sein."""
        data = _load(wf_path)
        assert data.get("id"), "Workflow-ID darf nicht leer sein"
        assert data.get("name"), "Workflow-Name darf nicht leer sein"

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_nodes_nicht_leer(self, wf_path):
        """nodes-Liste muss mindestens einen Node enthalten."""
        data = _load(wf_path)
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) >= 1, "Workflow muss mindestens einen Node haben"

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_jeder_node_hat_id_und_typ(self, wf_path):
        """Jeder Node muss 'id' und 'type' besitzen."""
        data = _load(wf_path)
        for i, node in enumerate(data["nodes"]):
            assert "id"   in node, f"Node[{i}] fehlt 'id' in {os.path.basename(wf_path)}"
            assert "type" in node, f"Node[{i}] fehlt 'type' in {os.path.basename(wf_path)}"
            assert node["id"],   f"Node[{i}] hat leere 'id' in {os.path.basename(wf_path)}"
            assert node["type"], f"Node[{i}] hat leeren 'type' in {os.path.basename(wf_path)}"

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_keine_doppelten_node_ids(self, wf_path):
        """Node-IDs müssen eindeutig sein."""
        data = _load(wf_path)
        ids   = [n["id"] for n in data["nodes"]]
        dups  = [nid for nid in set(ids) if ids.count(nid) > 1]
        assert not dups, (
            f"Doppelte Node-IDs in {os.path.basename(wf_path)}: {dups}"
        )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_verbindungen_referenzieren_valide_nodes(self, wf_path):
        """Jede Verbindung muss auf existierende Node-IDs verweisen."""
        data     = _load(wf_path)
        node_ids = {n["id"] for n in data["nodes"]}
        for conn in data["connections"]:
            frm = conn.get("from", "")
            to  = conn.get("to",   "")
            assert frm in node_ids, (
                f"Verbindung 'from': unbekannte Node-ID '{frm}' "
                f"in {os.path.basename(wf_path)}"
            )
            assert to in node_ids, (
                f"Verbindung 'to': unbekannte Node-ID '{to}' "
                f"in {os.path.basename(wf_path)}"
            )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_connections_haben_from_und_to(self, wf_path):
        """Jede Verbindung muss 'from' und 'to' enthalten."""
        data = _load(wf_path)
        for i, conn in enumerate(data["connections"]):
            assert "from" in conn, (
                f"Verbindung[{i}] fehlt 'from' in {os.path.basename(wf_path)}"
            )
            assert "to" in conn, (
                f"Verbindung[{i}] fehlt 'to' in {os.path.basename(wf_path)}"
            )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_kein_zyklus_moeglich(self, wf_path):
        """Workflow-Graph muss azyklisch sein (topologische Sortierung möglich)."""
        data  = _load(wf_path)
        nodes = {n["id"] for n in data["nodes"]}
        adj   = {nid: [] for nid in nodes}
        deg   = {nid: 0  for nid in nodes}
        for conn in data["connections"]:
            frm, to = conn.get("from", ""), conn.get("to", "")
            if frm in adj and to in deg:
                adj[frm].append(to)
                deg[to] += 1

        queue  = [nid for nid, d in deg.items() if d == 0]
        sorted_count = 0
        while queue:
            nid = queue.pop(0)
            sorted_count += 1
            for s in adj[nid]:
                deg[s] -= 1
                if deg[s] == 0:
                    queue.append(s)

        assert sorted_count == len(nodes), (
            f"Workflow {os.path.basename(wf_path)} enthält Zyklen — "
            f"Topologische Sortierung nicht möglich"
        )


# ── Node-Typ-Abdeckung ────────────────────────────────────────────────────────

class TestNodeTypAbdeckung:
    """Sicherstellt dass alle wichtigen Node-Typen in den Test-Workflows vertreten sind."""

    def _alle_typen(self):
        typen = set()
        for p in _WF_FILES:
            for n in _load(p)["nodes"]:
                typen.add(n["type"])
        return typen

    def test_trigger_vorhanden(self):
        assert "trigger" in self._alle_typen()

    def test_schedule_trigger_vorhanden(self):
        assert "schedule_trigger" in self._alle_typen()

    def test_webhook_trigger_vorhanden(self):
        assert "webhook_trigger" in self._alle_typen() or "webhook" in self._alle_typen()

    def test_set_vorhanden(self):
        assert "set" in self._alle_typen()

    def test_chat_vorhanden(self):
        assert "chat" in self._alle_typen()

    def test_chatfilter_vorhanden(self):
        assert "chatfilter" in self._alle_typen(), (
            "chatfilter-Node nicht gefunden — Test_Workflow31.json fehlt?"
        )

    def test_note_vorhanden(self):
        assert "note" in self._alle_typen(), (
            "note-Node nicht gefunden — Test_Workflow32.json fehlt?"
        )

    def test_memory_window_vorhanden(self):
        assert "memory_window" in self._alle_typen(), (
            "memory_window-Node nicht gefunden — Test_Workflow33.json fehlt?"
        )

    def test_memory_summary_vorhanden(self):
        assert "memory_summary" in self._alle_typen(), (
            "memory_summary-Node nicht gefunden — Test_Workflow33.json fehlt?"
        )

    def test_code_vorhanden(self):
        assert "code" in self._alle_typen()

    def test_skill_vorhanden(self):
        assert "skill" in self._alle_typen()

    def test_loop_vorhanden(self):
        assert "loop" in self._alle_typen()

    def test_condition_vorhanden(self):
        assert "condition" in self._alle_typen()

    def test_switch_vorhanden(self):
        assert "switch" in self._alle_typen()

    def test_http_vorhanden(self):
        assert "http" in self._alle_typen()

    def test_error_handler_vorhanden(self):
        assert "error_handler" in self._alle_typen()

    def test_wait_vorhanden(self):
        assert "wait" in self._alle_typen()

    def test_telegram_vorhanden(self):
        assert "telegram" in self._alle_typen()

    def test_email_vorhanden(self):
        assert "email" in self._alle_typen()

    def test_google_docs_vorhanden(self):
        assert "google_docs" in self._alle_typen()

    def test_google_sheets_vorhanden(self):
        assert "google_sheets" in self._alle_typen()


# ── Ausführungs-Tests (Flask-Engine) ──────────────────────────────────────────

@pytest.fixture(scope="module")
def _wf_exec_client(tmp_path_factory):
    """
    Gemeinsamer Flask-Testclient für alle Ausführungstests.
    Scope=module → ein Flask-App für alle 33 Workflow-Ausführungen.
    _sched_time.sleep wird gemockt → kein echtes Warten (z.B. wait-Node).
    """
    tmp  = tmp_path_factory.mktemp("wf_json_exec")
    orig = os.getcwd()
    os.chdir(str(tmp))

    from flask import Flask
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)
    app.config["TESTING"] = True

    mock_kernel = MockKernel()
    lock        = threading.Lock()

    with patch("workflow_routes._start_scheduler"), \
         patch("workflow_routes._sched_time") as _mt:
        _mt.sleep.return_value = None  # kein echtes Warten im wait-Node

        from workflow_routes import register_workflow_routes
        register_workflow_routes(app, lambda: mock_kernel, lock)

        with app.test_client() as client:
            yield client

    os.chdir(orig)


def _run_workflow(client, wf_path: str):
    """Führt einen Workflow über den Flask-Testclient aus und gibt die Antwort zurück."""
    data = _load(wf_path)
    resp = client.post(
        "/api/workflow/execute",
        json={"nodes": data["nodes"], "connections": data["connections"]},
        content_type="application/json",
    )
    return resp


class TestWorkflowAusfuehrung:
    """Jeder Test-Workflow muss ohne Python-Exception ausführbar sein."""

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_http_200(self, wf_path, _wf_exec_client):
        """Workflow-Engine muss HTTP 200 zurückgeben — kein Absturz."""
        resp = _run_workflow(_wf_exec_client, wf_path)
        assert resp.status_code == 200, (
            f"{os.path.basename(wf_path)}: erwartet 200, "
            f"erhalten {resp.status_code}"
        )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_antwort_hat_results_und_statuses(self, wf_path, _wf_exec_client):
        """Jede Antwort muss 'results', 'statuses' und 'order' enthalten."""
        resp   = _run_workflow(_wf_exec_client, wf_path)
        result = resp.get_json()
        assert result is not None, (
            f"{os.path.basename(wf_path)}: Antwort ist kein valides JSON"
        )
        for schluessel in ("results", "statuses", "order"):
            assert schluessel in result, (
                f"{os.path.basename(wf_path)}: "
                f"Schlüssel '{schluessel}' fehlt in der Antwort"
            )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_status_werte_sind_gueltig(self, wf_path, _wf_exec_client):
        """Jeder Node-Status muss 'success', 'error' oder 'skipped' sein."""
        resp     = _run_workflow(_wf_exec_client, wf_path)
        result   = resp.get_json()
        statuses = result.get("statuses", {})
        gueltige = {"success", "error", "skipped"}
        for nid, status in statuses.items():
            assert status in gueltige, (
                f"{os.path.basename(wf_path)}: "
                f"Node '{nid}' hat ungültigen Status '{status}'"
            )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_mindestens_ein_node_ausgefuehrt(self, wf_path, _wf_exec_client):
        """Mindestens ein Node muss ausgeführt worden sein."""
        resp     = _run_workflow(_wf_exec_client, wf_path)
        result   = resp.get_json()
        statuses = result.get("statuses", {})
        assert len(statuses) >= 1, (
            f"{os.path.basename(wf_path)}: Keine Nodes wurden ausgeführt"
        )

    @pytest.mark.parametrize("wf_path", _WF_FILES, ids=_WF_IDS)
    def test_kein_python_exception_output(self, wf_path, _wf_exec_client):
        """Node-Ausgaben dürfen keine unbehandelten Python-Tracebacks enthalten."""
        resp    = _run_workflow(_wf_exec_client, wf_path)
        result  = resp.get_json()
        results = result.get("results", {})
        for nid, output in results.items():
            assert "Traceback (most recent call last)" not in str(output), (
                f"{os.path.basename(wf_path)}: "
                f"Node '{nid}' enthält Python-Traceback in der Ausgabe"
            )
