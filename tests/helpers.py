"""
helpers.py – Gemeinsame Hilfsklassen und -funktionen für die Testsuite
=======================================================================
Direkt importierbar aus allen Testmodulen.
"""
import os
import sys
import inspect
from unittest.mock import MagicMock

# Projektwurzel im Pfad
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _MockSkillManager:
    """Echter Mini-SkillManager der direkt Skills aus skills/ lädt."""

    def __init__(self):
        self.skills     = {}
        self.skill_docs = {}
        self._laden()

    def _laden(self):
        # Direkt aus basis_tools und wuerfeln laden (immer verfügbar)
        try:
            from skills.basis_tools import taschenrechner, uhrzeit_datum, notiz_speichern, notizen_lesen
            from skills.wuerfeln    import wuerfeln
            from skills.muenze_werfen import muenze_werfen
            for fn in (taschenrechner, uhrzeit_datum, notiz_speichern, notizen_lesen,
                       wuerfeln, muenze_werfen):
                self.skills[fn.__name__]     = fn
                self.skill_docs[fn.__name__] = fn.__doc__ or ""
        except ImportError:
            pass

    def execute(self, name: str, **params):
        fn = self.skills.get(name)
        if fn is None:
            return f"❌ Skill '{name}' nicht gefunden."
        try:
            return fn(**params)
        except Exception as e:
            return f"❌ Fehler: {e}"

    def get_skill_list(self):
        return "\n".join(f"- {n}()" for n in self.skills)


class MockKernel:
    """Leichtgewichtiger Kernel-Ersatz für API-Tests ohne KI-Abhängigkeiten."""

    def __init__(self, antwort: str = "Test-Antwort von Ilija"):
        self._antwort      = antwort
        self.provider_name = "mock"
        self.state         = MagicMock()
        self.state.status.value = "idle"
        self.manager       = _MockSkillManager()

    def chat(self, nachricht: str, *args, **kwargs) -> str:
        return self._antwort

    def get_provider_info(self):
        return {"name": "mock", "model": "mock-model"}


def make_node(nid: str, ntype: str, config: dict = None, pos: tuple = (0, 0)) -> dict:
    """Erstellt einen minimalen Workflow-Node."""
    return {
        "id":     nid,
        "type":   ntype,
        "config": config or {},
        "x":      pos[0],
        "y":      pos[1],
    }


def make_connection(src: str, dst: str) -> dict:
    """Erstellt eine Workflow-Verbindung (Format: from/to wie in workflow_routes.py)."""
    return {"from": src, "to": dst}


def workflow_payload(nodes: list, connections: list = None) -> dict:
    """Erstellt ein vollständiges Workflow-Payload für /api/workflow/execute."""
    return {"nodes": nodes, "connections": connections or []}
