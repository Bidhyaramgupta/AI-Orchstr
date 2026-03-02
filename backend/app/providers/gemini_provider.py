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
        # Minimal mapping:
        # - system message becomes a first "user" part (simple prototype)
        # - user/assistant mapped to contents roles where possible
        # Gemini REST expects contents[].parts[].text
        contents = []
        for m in messages:
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

        payload: Dict[str, Any] = {
            "contents": self._to_gemini_contents(messages),
        }
        # optional generation config
        if extra:
            payload["generationConfig"] = extra

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, params=params, json=payload)
            r.raise_for_status()
            data = r.json()

        # Extract text
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

        payload: Dict[str, Any] = {
            "contents": self._to_gemini_contents(messages),
        }
        if extra:
            payload["generationConfig"] = extra

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, params=params, json=payload) as resp:
                resp.raise_for_status()

                # SSE lines: "data: {...}"
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        continue

                    # obj usually contains candidates with content parts
                    candidates = obj.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for p in parts:
                        txt = p.get("text")
                        if txt:
                            yield txt