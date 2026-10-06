"""
Offizielle Gemini API (Google AI Studio) via `google-genai` SDK.
Unterstützt asynchrone Generierung, Streaming und Token-Usage-Extraktion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import AsyncIterator, Iterable

from google import genai
from google.genai import types as gt


_VER_RE = re.compile(r"gemini-(\d+(?:\.\d+)?)")
_RATE_MSG_RE = re.compile(
    r"(429|503|RESOURCE[_ ]EXHAUSTED|UNAVAILABLE|RATE[_ ]LIMIT|QUOTA)",
    re.IGNORECASE,
)


def _rank(name: str) -> int:
    """
    Qualitäts-Ranking für Agenten:
    Version wiegt schwerer als Name (Gemini 2.0 Flash schlägt 1.5 Pro in Latenz & Logik).
    """
    n = name.lower()

    m = _VER_RE.search(n)
    ver_score = int(float(m.group(1)) * 2000) if m else 0

    if "-pro" in n:
        family = 2500
    elif "-flash-lite" in n:
        family = 800
    elif "-flash" in n:
        family = 2000
    else:
        family = 500

    if "-latest" in n:
        family += 10

    penalty = 0
    if "-preview" in n:
        penalty += 10
    if "-exp" in n:
        penalty += 20
    if "-customtools" in n:
        penalty += 30

    return ver_score + family - penalty


@dataclass
class ModelInfo:
    name: str
    display: str
    input_limit: int
    output_limit: int
    rank: int


class RateLimitError(Exception):
    """429, 503 oder Quota erschöpft."""


def _looks_rate_limited(exc: BaseException) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in (429, 503):
        return True
    return bool(_RATE_MSG_RE.search(str(exc)))


def _supports_generate_content(m: object) -> bool:
    for attr in ("supported_actions", "supported_generation_methods"):
        val = getattr(m, attr, None)
        if val and "generateContent" in val:
            return True
    return False


class GeminiAPIProvider:
    def __init__(self, api_key: str, exclude_terms: Iterable[str]):
        self._client = genai.Client(api_key=api_key)
        self._exclude = [t.lower() for t in exclude_terms if t.strip()]
        self.models: list[ModelInfo] = []

    def refresh_models(self) -> list[ModelInfo]:
        found: list[ModelInfo] = []
        for m in self._client.models.list():
            raw = getattr(m, "name", "") or ""
            name = raw.removeprefix("models/") if raw.startswith("models/") else raw
            if not name or "gemini-" not in name.lower():
                continue

            if not _supports_generate_content(m):
                continue

            low = name.lower()
            if any(term in low for term in self._exclude):
                continue

            found.append(ModelInfo(
                name=name,
                display=getattr(m, "display_name", "") or name,
                input_limit=int(getattr(m, "input_token_limit", 0) or 0),
                output_limit=int(getattr(m, "output_token_limit", 0) or 0),
                rank=_rank(name),
            ))

        seen: set[str] = set()
        ordered: list[ModelInfo] = []
        for mi in sorted(found, key=lambda x: (-x.rank, x.name)):
            if mi.name in seen:
                continue
            seen.add(mi.name)
            ordered.append(mi)

        self.models = ordered
        return ordered

    async def generate(
        self,
        model: str,
        contents: list[gt.Content],
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, dict]:
        config = gt.GenerateContentConfig(
            system_instruction=system if system else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            if _looks_rate_limited(exc):
                raise RateLimitError(str(exc)) from exc
            raise

        text = (getattr(resp, "text", None) or "").strip()
        if not text:
            raise RuntimeError(f"Leere Antwort von Modell {model} (evtl. Safety-Block)")

        usage_meta = getattr(resp, "usage_metadata", None)
        usage = {
            "prompt_tokens": getattr(usage_meta, "prompt_token_count", 0) or 0,
            "completion_tokens": getattr(usage_meta, "candidates_token_count", 0) or 0,
            "total_tokens": getattr(usage_meta, "total_token_count", 0) or 0,
        }
        return text, usage

    async def generate_stream(
        self,
        model: str,
        contents: list[gt.Content],
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        config = gt.GenerateContentConfig(
            system_instruction=system if system else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            if _looks_rate_limited(exc):
                raise RateLimitError(str(exc)) from exc
            raise