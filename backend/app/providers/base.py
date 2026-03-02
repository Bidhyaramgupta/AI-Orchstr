from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional, Dict, Any
from app.schemas.chat import Message

class ProviderResult(dict):
    """
    Simple dict-like result:
      {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "output_text": "...",
        "raw": {...optional...}
      }
    """

class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: List[Message],
        timeout_s: float = 30.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        ...

    @abstractmethod
    async def stream_chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: List[Message],
        timeout_s: float = 30.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        ...