from __future__ import annotations
from typing import AsyncIterator, List, Optional, Dict, Any

from openai import AsyncOpenAI
from app.schemas.chat import Message
from app.providers.base import LLMProvider, ProviderResult


class OpenAIProvider(LLMProvider):
    name = "openai"

    def _client(self, api_key: str) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=api_key)

    def _system_instructions(self, messages: List[Message]) -> Optional[str]:
        # Responses API supports an "instructions" field (system-level guidance) :contentReference[oaicite:3]{index=3}
        sys_parts = [m.content for m in messages if m.role == "system"]
        return "\n".join(sys_parts) if sys_parts else None

    def _to_responses_input(self, messages: List[Message]) -> list[dict]:
        # Responses API accepts either a string input or a list of message-like items with typed content :contentReference[oaicite:4]{index=4}
        items: list[dict] = []
        for m in messages:
            if m.role == "system":
                continue
            items.append(
                {
                    "role": m.role,
                    "content": [{"type": "input_text", "text": m.content}],
                }
            )
        return items

    async def chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: List[Message],
        timeout_s: float = 30.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        client = self._client(api_key)
        extra = extra or {}

        instructions = self._system_instructions(messages)
        input_items = self._to_responses_input(messages)

        resp = await client.responses.create(
            model=model,
            instructions=instructions,
            input=input_items if input_items else "",
            timeout=timeout_s,
            **extra,
        )

        # Responses SDK provides output_text helper :contentReference[oaicite:5]{index=5}
        text = getattr(resp, "output_text", "") or ""

        return ProviderResult(
            provider=self.name,
            model=model,
            output_text=text,
            raw={"id": getattr(resp, "id", None)},
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
        client = self._client(api_key)
        extra = extra or {}

        instructions = self._system_instructions(messages)
        input_items = self._to_responses_input(messages)

        # Streaming responses via SSE is supported; async uses same interface :contentReference[oaicite:6]{index=6}
        stream = await client.responses.create(
            model=model,
            instructions=instructions,
            input=input_items if input_items else "",
            stream=True,
            timeout=timeout_s,
            **extra,
        )

        async for event in stream:
            # In OpenAI event streams, text deltas commonly appear on:
            # "response.output_text.delta" with `event.delta` :contentReference[oaicite:7]{index=7}
            etype = getattr(event, "type", None)
            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if delta:
                    yield delta
            elif etype in ("response.output_text.done", "response.done"):
                # done events; we just stop naturally when stream ends
                continue