"""
providers.py – KI-Provider-Management für Ilija Public Edition
Unterstützte Provider: Claude (Anthropic), ChatGPT (OpenAI), Gemini (Google), Ollama (lokal)
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()


class Provider:
    def __init__(self, name: str):
        self.name = name

    def chat(self, messages: list, system: str = None) -> str:
        raise NotImplementedError


class ClaudeProvider(Provider):
    def __init__(self):
        super().__init__("Claude")
        import anthropic
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model  = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6")

    def chat(self, messages: list, system: str = None) -> str:
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        return response.content[0].text


class OpenAIProvider(Provider):
    def __init__(self):
        super().__init__("ChatGPT")
        from openai import OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model  = os.getenv("OPENAI_MODEL", "gpt-4o")

    def chat(self, messages: list, system: str = None) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = self.client.chat.completions.create(model=self.model, messages=msgs)
        return response.choices[0].message.content


class GeminiProvider(Provider):
    def __init__(self):
        super().__init__("Gemini")
        self.api_key   = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

    def chat(self, messages: list, system: str = None) -> str:
        import requests

        # Bewährter EVO-Ansatz: alles als flacher Text-Block in einem einzigen Content-Objekt.
        # Verhindert den "letzter Turn muss user sein"-Fehler bei Gesprächsverläufen.
        parts = []

        if system:
            parts.append({"text": f"System: {system}"})

        for m in messages:
            role    = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append({"text": f"System: {content}"})
            elif role == "assistant":
                parts.append({"text": f"Assistant: {content}"})
            else:
                parts.append({"text": f"User: {content}"})

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model_name}:generateContent")
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json",
                         "X-goog-api-key": self.api_key},
                json={"contents": [{"parts": parts}],
                      "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}},
                timeout=30,
            )
            data = resp.json()
            if resp.status_code == 429:
                raise Exception("Rate-Limit – bitte kurz warten")
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}: {data}")
            return "".join(
                p.get("text", "")
                for p in data["candidates"][0]["content"]["parts"]
            )
        except Exception as e:
            raise Exception(f"Gemini Fehler: {e}")


class OllamaProvider(Provider):
    def __init__(self, model: str = None):
        super().__init__("Ollama")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    def chat(self, messages: list, system: str = None) -> str:
        import ollama
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = ollama.chat(model=self.model, messages=msgs)
        return response["message"]["content"]


def select_provider(mode: str = "auto") -> tuple:
    """
    Wählt den besten verfügbaren Provider.
    Reihenfolge: Claude → GPT → Gemini → Ollama
    Gibt (name, provider_instance) zurück.
    """
    # Modell-Registry laden falls vorhanden
    try:
        with open("models_config.json", "r") as f:
            cfg = json.load(f)
        mode = cfg.get("default_provider", mode)
    except Exception:
        pass

    if mode == "claude" or (mode == "auto" and os.getenv("ANTHROPIC_API_KEY")):
        try:
            p = ClaudeProvider()
            return "Claude", p
        except Exception:
            if mode == "claude":
                raise

    if mode == "openai" or (mode == "auto" and os.getenv("OPENAI_API_KEY")):
        try:
            p = OpenAIProvider()
            return "ChatGPT", p
        except Exception:
            if mode == "openai":
                raise

    if mode == "gemini" or (mode == "auto" and (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))):
        try:
            p = GeminiProvider()
            return "Gemini", p
        except Exception:
            if mode == "gemini":
                raise

    # Ollama als letzter Fallback
    try:
        import ollama
        p = OllamaProvider()
        return "Ollama", p
    except Exception as e:
        raise RuntimeError(
            "Kein KI-Provider verfügbar. Bitte mindestens einen API-Key in .env eintragen "
            "oder Ollama installieren."
        ) from e


def get_available_providers() -> list:
    """Gibt eine Liste aller konfigurierten Provider zurück."""
    available = []
    if os.getenv("ANTHROPIC_API_KEY"):
        available.append("Claude")
    if os.getenv("OPENAI_API_KEY"):
        available.append("ChatGPT")
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        available.append("Gemini")
    try:
        import ollama
        ollama.list()
        available.append("Ollama")
    except Exception:
        pass
    return available
