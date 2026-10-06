"""
Router mit Modell-Fallback bei Quota-Erschöpfung (429/503).
Unterstützt Non-Streaming und zuverlässiges Streaming mit First-Chunk-Prüfung.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator
from google.genai import types as gt
from providers.api import GeminiAPIProvider, RateLimitError, ModelInfo


@dataclass
class RouterResponse:
    text: str
    used_model: str
    usage: dict
    attempts: list[str] = field(default_factory=list)


def _short(exc: BaseException, n: int = 140) -> str:
    s = " ".join(str(exc).split())
    return s if len(s) <= n else s[: n - 1] + "…"


class Router:
    def __init__(self, api: GeminiAPIProvider | None):
        self.api = api

    def _order_candidates(self, preferred: str | None) -> list[ModelInfo]:
        if not self.api or not self.api.models:
            return []
        models = list(self.api.models)
        if not preferred or preferred in ("", "auto"):
            return models
        exact = [m for m in models if m.name == preferred]
        rest = [m for m in models if m.name != preferred]
        return exact + rest

    async def generate(
        self,
        contents: list[gt.Content],
        system: str | None,
        preferred: str | None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> RouterResponse:
        attempts: list[str] = []
        candidates = self._order_candidates(preferred)

        if not candidates:
            raise RuntimeError("Keine Gemini-Modelle verfügbar. Bitte API-Key prüfen.")

        for mi in candidates:
            try:
                text, usage = await self.api.generate(
                    mi.name, contents, system, temperature, max_tokens
                )
                return RouterResponse(text=text, used_model=mi.name, usage=usage, attempts=attempts)
            except RateLimitError as e:
                attempts.append(f"{mi.name}: rate-limited ({_short(e)})")
            except Exception as e:
                attempts.append(f"{mi.name}: {_short(e)}")

        raise RuntimeError("Alle Modelle erschöpft oder fehlgeschlagen:\n  - " + "\n  - ".join(attempts))

    async def generate_stream(
        self,
        contents: list[gt.Content],
        system: str | None,
        preferred: str | None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, AsyncIterator[str]]:
        """
        Streaming-Fallback mit First-Chunk-Peeking:
        Erzwingt das erste Token, bevor die HTTP-Response an den Client startet.
        Tritt ein 429/503 auf, wird sofort zum nächsten Modell gewechselt.
        """
        candidates = self._order_candidates(preferred)
        if not candidates:
            raise RuntimeError("Keine Gemini-Modelle verfügbar.")

        attempts: list[str] = []
        for mi in candidates:
            try:
                stream_iter = self.api.generate_stream(
                    mi.name, contents, system, temperature, max_tokens
                )
                
                # Erstes Token erzwingen (prüft Verbindung und Quota)
                first_chunk = await stream_iter.__anext__()

                # Erstes Token und Rest-Stream nahtlos verknüpfen
                async def combined_generator() -> AsyncIterator[str]:
                    yield first_chunk
                    async for chunk in stream_iter:
                        yield chunk

                return mi.name, combined_generator()

            except (RateLimitError, StopAsyncIteration) as e:
                attempts.append(f"{mi.name}: rate-limited/leer ({_short(e)})")
                continue
            except Exception as e:
                attempts.append(f"{mi.name}: {_short(e)}")
                continue

        raise RuntimeError("Streaming fehlgeschlagen: Alle Modelle rate-limited.\n  - " + "\n  - ".join(attempts))