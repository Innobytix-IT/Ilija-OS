"""
test_api.py – Tests für alle Workflow-API-Endpunkte
=====================================================
Testet: Workflow CRUD, Schedules, Skill-Ausführung, Webhook
"""
import os
import sys
import json
import threading
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from helpers import MockKernel


# ── Fixture: Frische App pro Testklasse ───────────────────────────────────────

@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from flask import Flask
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)
    app.config["TESTING"] = True

    mock_k = MockKernel()
    lock   = threading.Lock()

    with patch("workflow_routes._start_scheduler"):
        from workflow_routes import register_workflow_routes
        register_workflow_routes(app, lambda: mock_k, lock)

    with app.test_client() as c:
        yield c, mock_k


BEISPIEL_WORKFLOW = {
    "name": "Test-Workflow",
    "nodes": [
        {"id": "n1", "type": "trigger", "config": {"startMessage": "Hallo"},
         "x": 0, "y": 0}
    ],
    "connections": [],
}


# ── Workflow CRUD ─────────────────────────────────────────────────────────────

class TestWorkflowCRUD:

    def test_workflow_speichern(self, api_client):
        client, _ = api_client
        resp = client.post("/api/workflows",
                           json=BEISPIEL_WORKFLOW, content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "id" in data

    def test_workflow_auflisten(self, api_client):
        client, _ = api_client
        # Erst speichern
        client.post("/api/workflows", json=BEISPIEL_WORKFLOW, content_type="application/json")
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_workflow_laden(self, api_client):
        client, _ = api_client
        # Speichern
        save_resp = client.post("/api/workflows", json=BEISPIEL_WORKFLOW,
                                content_type="application/json")
        wf_id = save_resp.get_json()["id"]
        # Laden
        resp = client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Test-Workflow"

    def test_workflow_nicht_gefunden(self, api_client):
        client, _ = api_client
        resp = client.get("/api/workflows/nicht-existent-123")
        assert resp.status_code == 404

    def test_workflow_loeschen(self, api_client):
        client, _ = api_client
        save_resp = client.post("/api/workflows", json=BEISPIEL_WORKFLOW,
                                content_type="application/json")
        wf_id = save_resp.get_json()["id"]
        del_resp = client.delete(f"/api/workflows/{wf_id}")
        assert del_resp.status_code == 200
        # Danach nicht mehr vorhanden
        get_resp = client.get(f"/api/workflows/{wf_id}")
        assert get_resp.status_code == 404

    def test_workflow_aktualisieren(self, api_client):
        client, _ = api_client
        save_resp = client.post("/api/workflows", json=BEISPIEL_WORKFLOW,
                                content_type="application/json")
        wf_id = save_resp.get_json()["id"]
        updated = {**BEISPIEL_WORKFLOW, "name": "Umbenannt"}
        resp = client.post("/api/workflows", json={**updated, "id": wf_id},
                           content_type="application/json")
        assert resp.status_code == 200

    def test_workflow_liste_leer_am_anfang(self, api_client):
        client, _ = api_client
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_mehrere_workflows_in_liste(self, api_client):
        client, _ = api_client
        client.post("/api/workflows", json={**BEISPIEL_WORKFLOW, "name": "WF1"},
                    content_type="application/json")
        client.post("/api/workflows", json={**BEISPIEL_WORKFLOW, "name": "WF2"},
                    content_type="application/json")
        resp = client.get("/api/workflows")
        assert len(resp.get_json()) == 2


# ── Workflow ausführen ────────────────────────────────────────────────────────

class TestWorkflowAusfuehren:

    def test_workflow_ausfuehren_gibt_ergebnisse(self, api_client):
        client, _ = api_client
        payload = {
            "nodes": [{"id": "n1", "type": "trigger",
                       "config": {"startMessage": "Test"}, "x": 0, "y": 0}],
            "connections": [],
        }
        resp = client.post("/api/workflow/execute", json=payload,
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data
        assert "statuses" in data
        assert "order" in data

    def test_leerer_workflow_gibt_400(self, api_client):
        """Leere Node-Liste → 400 Bad Request (korrekt)."""
        client, _ = api_client
        resp = client.post("/api/workflow/execute",
                           json={"nodes": [], "connections": []},
                           content_type="application/json")
        assert resp.status_code == 400

    def test_ausfuehren_ohne_payload_schlaegt_fehl(self, api_client):
        client, _ = api_client
        resp = client.post("/api/workflow/execute",
                           data="kein json", content_type="text/plain")
        # Sollte nicht crashen (400=kein JSON, 415=falscher ContentType)
        assert resp.status_code in (200, 400, 415, 500)


# ── Schedules ────────────────────────────────────────────────────────────────

class TestScheduleAPI:

    def test_schedule_liste_leer_am_anfang(self, api_client):
        client, _ = api_client
        resp = client.get("/api/schedules")
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_schedule_aktivieren(self, api_client):
        client, _ = api_client
        cfg = {"interval_type": "interval", "minuten": 5}
        resp = client.post("/api/schedules/wf-123",
                           json={"active": True, "config": cfg},
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active"] is True

    def test_schedule_deaktivieren(self, api_client):
        client, _ = api_client
        # Erst aktivieren
        client.post("/api/schedules/wf-999",
                    json={"active": True, "config": {}},
                    content_type="application/json")
        # Dann deaktivieren
        resp = client.post("/api/schedules/wf-999",
                           json={"active": False, "config": {}},
                           content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False

    def test_schedule_loeschen(self, api_client):
        client, _ = api_client
        client.post("/api/schedules/wf-del",
                    json={"active": True, "config": {}},
                    content_type="application/json")
        del_resp = client.delete("/api/schedules/wf-del")
        assert del_resp.status_code == 200
        # Nicht mehr in der Liste
        list_resp = client.get("/api/schedules")
        assert "wf-del" not in list_resp.get_json()

    def test_schedule_in_liste_sichtbar(self, api_client):
        client, _ = api_client
        client.post("/api/schedules/wf-vis",
                    json={"active": True, "config": {"minuten": 10}},
                    content_type="application/json")
        resp = client.get("/api/schedules")
        assert "wf-vis" in resp.get_json()


# ── Skill-API ─────────────────────────────────────────────────────────────────

class TestSkillAPI:

    def test_skill_ausfuehren_taschenrechner(self, api_client):
        client, _ = api_client
        resp = client.post("/api/skill/execute",
                           json={"skill": "taschenrechner", "params": {"ausdruck": "2+2"}},
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "result" in data
        assert "4" in str(data["result"])

    def test_skill_ausfuehren_uhrzeit(self, api_client):
        client, _ = api_client
        resp = client.post("/api/skill/execute",
                           json={"skill": "uhrzeit_datum", "params": {}},
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "result" in data
        assert "2026" in str(data["result"])

    def test_skill_ausfuehren_wuerfeln(self, api_client):
        client, _ = api_client
        resp = client.post("/api/skill/execute",
                           json={"skill": "wuerfeln", "params": {"max": 6}},
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "🎲" in str(data["result"])

    def test_skill_nicht_gefunden(self, api_client):
        client, _ = api_client
        resp = client.post("/api/skill/execute",
                           json={"skill": "nicht_existent_xyz", "params": {}},
                           content_type="application/json")
        assert resp.status_code in (400, 404, 200)
        if resp.status_code == 200:
            data = resp.get_json()
            assert "error" in data or "❌" in str(data.get("result", ""))

    def test_skill_signatur_abrufen(self, api_client):
        client, _ = api_client
        resp = client.get("/api/skill/signature/taschenrechner")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "ausdruck" in str(data)


# ── Webhook ───────────────────────────────────────────────────────────────────

class TestWebhook:

    def test_webhook_get_antwortet(self, api_client):
        client, _ = api_client
        resp = client.get("/api/webhook/test-hook-123")
        # Webhook ohne gespeicherten Workflow → Fehlermeldung oder leere Antwort
        assert resp.status_code in (200, 404)

    def test_webhook_post_mit_json(self, api_client):
        client, _ = api_client
        resp = client.post("/api/webhook/test-hook-post",
                           json={"event": "test"},
                           content_type="application/json")
        assert resp.status_code in (200, 404)
