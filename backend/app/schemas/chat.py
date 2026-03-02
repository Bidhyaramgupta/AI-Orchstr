from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

Role = Literal["system", "user", "assistant"]

class Message(BaseModel):
    role: Role
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = False

    # BYO keys (prototype): user can provide 1+ provider keys
    api_keys: Dict[str, str] = Field(
        default_factory=dict,
        description="Map provider->api_key, e.g. {'openai': '...', 'anthropic': '...', 'gemini': '...'}"
    )

    provider: Literal["openai", "anthropic", "gemini"] = "openai"
    model: str = "gpt-4o-mini"

    preference: Literal["fast", "cheap", "best"] = "best"
    provider_allowlist: Optional[List[str]] = None

class ChatResponse(BaseModel):
    request_id: str
    provider: str
    model: str
    output_text: str
    meta: Dict[str, Any] = Field(default_factory=dict)