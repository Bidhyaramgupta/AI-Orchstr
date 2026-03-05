import uuid
import asyncio
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.routing.router import run_with_fallback, stream_with_fallback

router = APIRouter(tags=["chat"])


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())

    provider, model, text = await run_with_fallback(
        api_keys=req.api_keys,
        messages=req.messages,
        preference=req.preference,
        provider_allowlist=req.provider_allowlist,
        timeout_s=30.0,
    )

    return ChatResponse(
        request_id=request_id,
        provider=provider,
        model=model,
        output_text=text,
        meta={"stream": False, "routing": req.preference},
    )


@router.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    request_id = str(uuid.uuid4())

    async def event_generator():
        # Include request_id first (gateway metadata)
        yield {"event": "meta", "data": f'{{"request_id":"{request_id}"}}'}

        async for ev in stream_with_fallback(
            api_keys=req.api_keys,
            messages=req.messages,
            preference=req.preference,
            provider_allowlist=req.provider_allowlist,
            timeout_s=30.0,
        ):
            yield ev

        await asyncio.sleep(0.01)

    return EventSourceResponse(event_generator())