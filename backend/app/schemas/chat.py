from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

Role = Literal["system", "user", "assistant"]

class Message(BaseModel):
    role: Role
    content: str

class ChatRequest(BaseModel):
    # Keep it OpenAI-ish for familiarity
    messages: List[Message]
    stream: bool = False

    # gateway-level routing hints (optional)
    preference: Literal["fast", "cheap", "best"] = "best"
    provider_allowlist: Optional[List[str]] = None  # e.g. ["openai", "anthropic"]

class ChatResponse(BaseModel):
    request_id: str
    provider: str
    model: str
    output_text: str
    meta: Dict[str, Any] = Field(default_factory=dict)