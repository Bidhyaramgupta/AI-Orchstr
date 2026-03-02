from __future__ import annotations
from typing import AsyncIterator, List, Optional, Dict, Any
import json
import httpx

from app.schemas.chat import Message
from app.providers.base import LLMProvider, ProviderResult

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/messages"

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def _to_anthropic_messages(self, messages: List[Message]):
        # Anthropic uses role=user|assistant for messages; system is separate
        out = []
        for m in messages:
            if m.role in ("user", "assistant"):
                out.append({"role": m.role, "content": m.content})
        return out

    def _system_prompt(self, messages: List[Message]) -> Optional[str]:
        # Combine all system messages
        sys_parts = [m.content for m in messages if m.role == "system"]
        return "\n".join(sys_parts) if sys_parts else None

    async def chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: List[Message],
        timeout_s: float = 30.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        extra = extra or {}
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": extra.pop("max_tokens", 1024),
            "messages": self._to_anthropic_messages(messages),
            **extra,
        }
        system = self._system_prompt(messages)
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(ANTHROPIC_BASE_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        # content is a list of blocks; take text blocks
        text_parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return ProviderResult(
            provider=self.name,
            model=model,
            output_text="".join(text_parts),
            raw={"id": data.get("id")},
        )

    async def stream_chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: List[Message],
        timeout_s: float = 30.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        extra = extra or {}
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": extra.pop("max_tokens", 1024),
            "messages": self._to_anthropic_messages(messages),
            "stream": True,
            **extra,
        }
        system = self._system_prompt(messages)
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", ANTHROPIC_BASE_URL, headers=headers, json=payload) as resp:
                resp.raise_for_status()

                # Anthropic streams SSE events like: "event: content_block_delta" + "data: {...}"
                event_type = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        continue

                    # Emit text deltas
                    if event_type == "content_block_delta":
                        delta = obj.get("delta", {})
                        if delta.get("type") == "text_delta":
                            txt = delta.get("text", "")
                            if txt:
                                yield txt