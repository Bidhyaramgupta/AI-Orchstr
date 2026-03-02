from __future__ import annotations

from typing import AsyncIterator, List, Optional, Dict, Any
import json
import httpx

from app.schemas.chat import Message
from app.providers.base import LLMProvider, ProviderResult

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def _to_gemini_contents(self, messages: List[Message]) -> list[dict]:
        contents = []
        for m in messages:
            # Gemini REST roles are typically "user" and "model"
            role = "user" if m.role in ("system", "user") else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        return contents

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
        url = f"{GEMINI_BASE}/{model}:generateContent"
        params = {"key": api_key}

        payload: Dict[str, Any] = {"contents": self._to_gemini_contents(messages)}
        if extra:
            payload["generationConfig"] = extra

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, params=params, json=payload)
            r.raise_for_status()
            data = r.json()

        text = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if "text" in p)

        return ProviderResult(provider=self.name, model=model, output_text=text, raw={})

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
        url = f"{GEMINI_BASE}/{model}:streamGenerateContent"
        params = {"key": api_key}

        payload: Dict[str, Any] = {"contents": self._to_gemini_contents(messages)}
        if extra:
            payload["generationConfig"] = extra

        # Ask for SSE explicitly (helps consistency)
        headers = {"accept": "text/event-stream"}

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, params=params, headers=headers, json=payload) as resp:
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    print("RAW_LINE:", repr(line))
                    if not line:
                        continue

                    # Handle SSE "data: {...}" or raw JSON lines
                    if line.startswith("data:"):
                        line = line[len("data:"):].strip()

                    if line in ("[DONE]", "DONE"):
                        break

                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    candidates = obj.get("candidates", [])
                    if not candidates:
                        continue

                    parts = candidates[0].get("content", {}).get("parts", [])
                    for p in parts:
                        txt = p.get("text")
                        if txt:
                            yield txt