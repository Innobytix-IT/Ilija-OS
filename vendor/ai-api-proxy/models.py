"""Pydantic-Modelle für die OpenAI-Schnittstelle."""
from typing import Optional, Union, Any
from pydantic import BaseModel, Field


class OpenAIMessage(BaseModel):
    role: str
    content: Union[str, list[dict[str, Any]], None] = ""
    name: Optional[str] = None


class OpenAIChatRequest(BaseModel):
    model: Optional[str] = "auto"
    messages: list[OpenAIMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    stop: Optional[Union[str, list[str]]] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0