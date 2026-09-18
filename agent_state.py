"""
agent_state.py – Zustandsverwaltung für Ilija Public Edition
"""

from enum import Enum
from datetime import datetime


class AgentStatus(Enum):
    IDLE        = "idle"
    THINKING    = "thinking"
    EXECUTING   = "executing"
    WAITING     = "waiting"
    ERROR       = "error"


class AgentState:
    def __init__(self):
        self.status          = AgentStatus.IDLE
        self.current_task    = None
        self.chat_history    = []
        self.active_provider = None
        self.started_at      = datetime.now()
        self.message_count   = 0
        self.last_error      = None

    def set_status(self, status: AgentStatus, task: str = None):
        self.status       = status
        self.current_task = task

    def add_message(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})
        self.message_count += 1
        # Verlauf auf 50 Nachrichten begrenzen (Kontext-Fenster)
        if len(self.chat_history) > 50:
            self.chat_history = self.chat_history[-50:]

    def clear_history(self):
        self.chat_history = []
        self.message_count = 0

    def get_status_dict(self) -> dict:
        return {
            "status":          self.status.value,
            "current_task":    self.current_task,
            "active_provider": self.active_provider,
            "message_count":   self.message_count,
            "uptime_seconds":  int((datetime.now() - self.started_at).total_seconds()),
            "last_error":      self.last_error,
        }
