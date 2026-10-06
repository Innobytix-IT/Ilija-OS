"""Proxy-Konfiguration aus .env"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_secret: str = "change-me"
    host: str = "0.0.0.0"
    port: int = 8642

    gemini_api_key: str = ""

    model_exclude: str = (
        "embedding,aqa,-image,nano-banana,imagen,tts,transcribe,-live,"
        "native-audio,robotics,veo,lyria,antigravity,computer-use,"
        "deep-research,gemma,omni,-tuning"
    )
    default_model: str = "auto"

    # ── Agent Token-Optimierung ──────────────────────────────────────────
    enable_agent_pruning: bool = True
    prune_keep_recent: int = 4          # Anzahl jüngster Nachrichten, die voll erhalten bleiben
    prune_max_middle_chars: int = 350   # Ältere Tool-Outputs / Scratchpad-Texte hierauf kürzen

    def exclude_terms(self) -> list[str]:
        return [t.strip().lower() for t in self.model_exclude.split(",") if t.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        protected_namespaces=(),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()