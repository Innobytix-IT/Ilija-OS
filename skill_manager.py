"""
skill_manager.py – Skill-Verwaltung für Ilija Public Edition
Vereinfachte Version ohne dynamische Code-Generierung oder gefährliche Operationen.
"""

import os
import importlib.util
import inspect
import json
from pathlib import Path

SKILLS_DIR = os.path.abspath("skills")

# Skills-Ordner dauerhaft in sys.path damit Skills sich gegenseitig importieren können
import sys
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)

# Skills die NIEMALS geladen werden dürfen (Sicherheits-Whitelist-Logik)
BLOCKED_SKILL_NAMES = {
    "cmd_ausfuehren", "shell_execute", "subprocess_run",
    "skill_erstellen", "create_skill", "eval_code",
    "datei_loeschen_system", "system_shutdown",
}


class SkillManager:
    def __init__(self):
        self.skills      = {}   # name -> callable
        self.skill_docs  = {}   # name -> docstring
        self.loaded_from = {}   # name -> filepath
        self.load_all()

    def load_all(self):
        """Lädt alle Skills aus dem skills/-Ordner."""
        self.skills     = {}
        self.skill_docs = {}
        loaded_count    = 0
        errors          = []

        for filepath in sorted(Path(SKILLS_DIR).glob("*.py")):
            if filepath.name.startswith("_"):
                continue
            try:
                count = self._load_file(str(filepath))
                loaded_count += count
            except Exception as e:
                errors.append(f"{filepath.name}: {e}")

        print(f"[SkillManager] {loaded_count} Skills geladen aus {SKILLS_DIR}/")
        if errors:
            for err in errors:
                print(f"[SkillManager] ⚠ {err}")

        return loaded_count

    def _load_file(self, filepath: str) -> int:
        """Lädt Skills aus einer einzelnen Python-Datei."""
        spec   = importlib.util.spec_from_file_location("_skill_mod", filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # AVAILABLE_SKILLS Liste bevorzugen
        skill_list = getattr(module, "AVAILABLE_SKILLS", None)

        if skill_list is None:
            # Fallback: alle öffentlichen Callables
            skill_list = [
                obj for name, obj in inspect.getmembers(module, inspect.isfunction)
                if not name.startswith("_")
            ]

        count = 0
        for func in skill_list:
            name = func.__name__

            # Sicherheitscheck
            if name in BLOCKED_SKILL_NAMES:
                print(f"[SkillManager] ⛔ Blockiert: {name}")
                continue

            self.skills[name]      = func
            self.skill_docs[name]  = inspect.getdoc(func) or ""
            self.loaded_from[name] = filepath
            count += 1

        return count

    def reload(self) -> str:
        """Skills neu laden."""
        old_count = len(self.skills)
        new_count = self.load_all()
        return f"Skills neu geladen: {new_count} (vorher: {old_count})"

    def get_skills_description(self) -> str:
        """Beschreibung aller verfügbaren Skills für den System-Prompt."""
        if not self.skills:
            return "Keine Skills verfügbar."
        lines = []
        for name, func in self.skills.items():
            doc = self.skill_docs.get(name, "Keine Beschreibung")
            sig = str(inspect.signature(func))
            lines.append(f"- {name}{sig}: {doc}")
        return "\n".join(lines)

    def execute(self, skill_name: str, **kwargs):
        """Führt einen Skill aus."""
        if skill_name not in self.skills:
            return f"❌ Unbekannter Skill: {skill_name}"
        try:
            func   = self.skills[skill_name]
            result = func(**kwargs)
            return result
        except Exception as e:
            return f"❌ Fehler in Skill '{skill_name}': {e}"

    def list_skills(self) -> list:
        """Gibt eine Liste aller geladenen Skills zurück."""
        return [
            {
                "name": name,
                "doc":  self.skill_docs.get(name, ""),
                "file": Path(self.loaded_from.get(name, "")).name,
            }
            for name in sorted(self.skills.keys())
        ]
