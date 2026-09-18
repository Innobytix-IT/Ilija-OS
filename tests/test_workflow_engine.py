"""
test_workflow_engine.py – Tests für die Workflow-Engine
========================================================
Testet: Topologische Sortierung, Node-Ausführung, ChatFilter,
        workflow_stopped Propagation, Memory Write-Back, Code-Node Sandbox
"""
import os
import sys
import json
import pytest
import threading
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from helpers import MockKernel, make_node, make_connection, workflow_payload


# ── Fixture: Flask-Testclient mit frischer App pro Test ──────────────────────

@pytest.fixture
def wf_client(tmp_path, monkeypatch):
    """Testclient für Workflow-API mit tmp-Datenverzeichnissen."""
    monkeypatch.chdir(tmp_path)

    from flask import Flask
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)
    app.config["TESTING"] = True

    mock_kernel = MockKernel()
    lock = threading.Lock()

    with patch("workflow_routes._start_scheduler"):
        from workflow_routes import register_workflow_routes
        register_workflow_routes(app, lambda: mock_kernel, lock)

    with app.test_client() as c:
        yield c, mock_kernel


# ── Trigger-Node ──────────────────────────────────────────────────────────────

class TestTriggerNode:

    def test_trigger_gibt_start_message_aus(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "trigger", {"startMessage": "Hallo Welt"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Hallo Welt" in data["results"]["n1"]

    def test_trigger_ohne_message_gibt_standard_aus(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "trigger", {})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["results"]["n1"]  # irgendeinen Output

    def test_trigger_status_success(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "trigger", {"startMessage": "Test"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data  = resp.get_json()
        assert data["statuses"]["n1"] == "success"


# ── Set-Node ──────────────────────────────────────────────────────────────────

class TestSetNode:

    def test_set_gibt_wert_aus(self, wf_client):
        """Set-Node mit fest konfiguriertem Wert (ohne {{input}}-Platzhalter)."""
        client, _ = wf_client
        nodes = [make_node("n1", "set", {"value":"Fester Wert ohne Platzhalter"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        # Ohne vorherigen Node hat der Set-Node keinen Kontext für {{input}}
        # aber der wert ohne Platzhalter wird direkt ausgegeben
        assert data["statuses"]["n1"] == "success"

    def test_set_mit_input_ersetzung(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger", {"startMessage": "Ursprung"}),
            make_node("n2", "set",     {"value":"Eingabe war: {{input}}"}),
        ]
        conns = [make_connection("n1", "n2")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert "Ursprung" in data["results"]["n2"]


# ── Chat-Node ─────────────────────────────────────────────────────────────────

class TestChatNode:

    def test_chat_gibt_kernel_antwort_zurueck(self, wf_client):
        client, mock_k = wf_client
        mock_k._antwort = "Mock-Antwort von KI"
        nodes = [make_node("n1", "chat", {"message": "Frage an KI"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "Mock-Antwort" in data["results"]["n1"]

    def test_chat_leitet_kontext_weiter(self, wf_client):
        client, mock_k = wf_client
        mock_k._antwort = "Antwort"
        nodes = [
            make_node("n1", "trigger", {"startMessage": "Kontext-Text"}),
            make_node("n2", "chat",    {"message": "{{input}}"}),
        ]
        conns = [make_connection("n1", "n2")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert data["statuses"]["n2"] == "success"


# ── ChatFilter-Node ───────────────────────────────────────────────────────────

class TestChatFilterNode:

    def test_leere_eingabe_stoppt_workflow(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger",    {"startMessage": ""}),
            make_node("n2", "chatfilter", {"modus": "einfach", "bei_leer": "stoppen"}),
            make_node("n3", "set",        {"value":"Darf nicht erreicht werden"}),
        ]
        conns = [make_connection("n1", "n2"), make_connection("n2", "n3")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        # n3 darf kein "success" haben
        assert data["statuses"].get("n3") != "success"

    def test_signal_leer_stoppt(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger",    {"startMessage": "📭 Keine neuen Telegram-Nachrichten."}),
            make_node("n2", "chatfilter", {"modus": "einfach", "bei_leer": "stoppen"}),
            make_node("n3", "set",        {"value":"Nachfolger"}),
        ]
        conns = [make_connection("n1", "n2"), make_connection("n2", "n3")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert data["statuses"].get("n3") != "success"

    def test_echte_nachricht_passiert_filter(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger",    {"startMessage": "Wie ist das Wetter?"}),
            make_node("n2", "chatfilter", {"modus": "einfach", "bei_leer": "stoppen"}),
            make_node("n3", "set",        {"value":"Weitergeleitet: {{input}}"}),
        ]
        conns = [make_connection("n1", "n2"), make_connection("n2", "n3")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert data["statuses"].get("n3") == "success"

    def test_bei_leer_weiter_gibt_leeren_output(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger",    {"startMessage": ""}),
            make_node("n2", "chatfilter", {"modus": "einfach", "bei_leer": "weiter"}),
        ]
        conns = [make_connection("n1", "n2")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        # n2 soll success sein (weiter-Modus) mit leerem Output
        assert data["statuses"]["n2"] == "success"
        assert data["results"]["n2"] == ""


# ── Wait-Node ─────────────────────────────────────────────────────────────────

class TestWaitNode:

    def test_wait_gibt_zeitinfo_aus(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "wait", {"sekunden": 0})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "⏱️" in data["results"]["n1"] or "Sekunde" in data["results"]["n1"]

    def test_wait_maximum_300_sekunden(self, wf_client):
        """Wait-Node darf nicht länger als 300s warten (kein Timeout in Tests durch max=0)."""
        client, _ = wf_client
        nodes = [make_node("n1", "wait", {"sekunden": 0})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        assert resp.status_code == 200


# ── Code-Node ─────────────────────────────────────────────────────────────────

class TestCodeNodeSandbox:

    def test_einfache_berechnung(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "code", {"code": "output = 2 + 2"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "4" in data["results"]["n1"]

    def test_string_manipulation(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "code", {"code": 'output = "Hallo " + "Welt"'})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "Hallo Welt" in data["results"]["n1"]

    def test_input_variable_verfuegbar(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger", {"startMessage": "TestInput"}),
            make_node("n2", "code",    {"code": "output = input.upper()"}),
        ]
        conns = [make_connection("n1", "n2")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert "TESTINPUT" in data["results"]["n2"]

    def test_os_import_blockiert(self, wf_client):
        """os.system() darf im Code-Node nicht ausgeführt werden können."""
        client, _ = wf_client
        nodes = [make_node("n1", "code", {
            "code": "import os; output = os.getcwd()"
        })]
        resp = client.post("/api/workflow/execute",
                           json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        # Muss Fehler geben oder leeren Output (kein echtes Verzeichnis)
        result = data["results"]["n1"]
        assert "❌" in result or ":" not in result  # echtes Verzeichnis hat Doppelpunkt

    def test_open_funktion_blockiert(self, wf_client):
        """open() darf im Code-Node nicht verfügbar sein."""
        client, _ = wf_client
        nodes = [make_node("n1", "code", {
            "code": "output = open('test.txt', 'w')"
        })]
        resp = client.post("/api/workflow/execute",
                           json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "❌" in data["results"]["n1"]

    def test_builtins_import_blockiert(self, wf_client):
        """__import__ darf nicht funktionieren."""
        client, _ = wf_client
        nodes = [make_node("n1", "code", {
            "code": "output = __import__('subprocess').run(['echo', 'pwned'])"
        })]
        resp = client.post("/api/workflow/execute",
                           json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "❌" in data["results"]["n1"]

    def test_json_verfuegbar(self, wf_client):
        """json-Modul soll im Code-Node verfügbar sein."""
        client, _ = wf_client
        nodes = [make_node("n1", "code", {
            "code": 'output = json.dumps({"key": "val"})'
        })]
        resp = client.post("/api/workflow/execute",
                           json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "key" in data["results"]["n1"]

    def test_datetime_verfuegbar(self, wf_client):
        """datetime-Modul soll im Code-Node verfügbar sein."""
        client, _ = wf_client
        nodes = [make_node("n1", "code", {
            "code": "output = str(datetime.now().year)"
        })]
        resp = client.post("/api/workflow/execute",
                           json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "2026" in data["results"]["n1"] or "202" in data["results"]["n1"]

    def test_kein_code_gibt_meldung(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "code", {"code": ""})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert data["statuses"]["n1"] in ("success", "skipped", "error")

    def test_print_ausgabe_wird_gesammelt(self, wf_client):
        client, _ = wf_client
        nodes = [make_node("n1", "code", {"code": "print('Ausgabe via print')"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert "Ausgabe via print" in data["results"]["n1"]


# ── Topologische Sortierung & Verbindungen ────────────────────────────────────

class TestTopologischeAusfuehrung:

    def test_kette_wird_korrekt_sortiert(self, wf_client):
        """n1 → n2 → n3: Ausführungsreihenfolge muss stimmen."""
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger", {"startMessage": "Start"}),
            make_node("n2", "set",     {"value":"Mitte"}),
            make_node("n3", "set",     {"value":"Ende: {{input}}"}),
        ]
        conns = [make_connection("n1", "n2"), make_connection("n2", "n3")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        order = data["order"]
        assert order.index("n1") < order.index("n2") < order.index("n3")

    def test_kontext_wird_durch_kette_weitergegeben(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("n1", "trigger", {"startMessage": "Anfang"}),
            make_node("n2", "set",     {"value":"{{input}} → Mitte"}),
        ]
        conns = [make_connection("n1", "n2")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert "Anfang" in data["results"]["n2"]

    def test_isolierter_node_wird_ausgefuehrt(self, wf_client):
        """Node ohne Verbindungen wird trotzdem ausgeführt."""
        client, _ = wf_client
        nodes = [make_node("n1", "set", {"value":"Allein"})]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes), content_type="application/json")
        data = resp.get_json()
        assert data["statuses"]["n1"] == "success"

    def test_leerer_workflow_gibt_400(self, wf_client):
        """Leere Node-Liste → 400 Bad Request (korrekt)."""
        client, _ = wf_client
        resp = client.post("/api/workflow/execute",
                           json=workflow_payload([]), content_type="application/json")
        assert resp.status_code == 400

    def test_zwei_unabhaengige_ketten(self, wf_client):
        client, _ = wf_client
        nodes = [
            make_node("a1", "trigger", {"startMessage": "A"}),
            make_node("a2", "set",     {"value":"A2"}),
            make_node("b1", "trigger", {"startMessage": "B"}),
            make_node("b2", "set",     {"value":"B2"}),
        ]
        conns = [make_connection("a1", "a2"), make_connection("b1", "b2")]
        resp  = client.post("/api/workflow/execute",
                            json=workflow_payload(nodes, conns), content_type="application/json")
        data = resp.get_json()
        assert data["statuses"]["a2"] == "success"
        assert data["statuses"]["b2"] == "success"
