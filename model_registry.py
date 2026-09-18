"""
model_registry.py – Modell-Konfiguration für Ilija Public Edition
"""

import os
import json

CONFIG_FILE = "models_config.json"

DEFAULT_CONFIG = {
    "default_provider": "auto",
    "models": {
        "claude":  "claude-opus-4-6",
        "openai":  "gpt-4o",
        "gemini":  "gemini-2.5-flash",
        "ollama":  "qwen2.5:7b",
    }
}


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_model(provider: str) -> str:
    config = load_config()
    return config.get("models", {}).get(provider, DEFAULT_CONFIG["models"].get(provider, ""))


def set_default_provider(provider: str):
    config = load_config()
    config["default_provider"] = provider
    save_config(config)
