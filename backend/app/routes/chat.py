import uuid
import asyncio
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])

@router.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())

    # TODO: router selects provider+model based on req.preference + health stats
    provider = "stub"
    model = "stub-model"

    # TODO: call worker/provider adapter
    output_text = "Hello! This is a placeholder response. Next: hook provider adapters."

    return ChatResponse(
        request_id=request_id,
        provider=provider,
        model=model,
        output_text=output_text,
        meta={"stream": False},
    )

@router.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    request_id = str(uuid.uuid4())
    provider = "stub"
    model = "stub-model"

    async def event_generator():
        # First event: metadata
        yield {"event": "meta", "data": f'{{"request_id":"{request_id}","provider":"{provider}","model":"{model}"}}'}

        # Fake token streaming (replace with real provider streaming later)
        text = "Streaming placeholder... "
        for ch in text:
            await asyncio.sleep(0.02)
            yield {"event": "token", "data": ch}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())