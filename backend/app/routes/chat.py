import uuid
import asyncio
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.providers.registry import get_provider

router = APIRouter(tags=["chat"])


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())

    # provider exists?
    try:
        provider = get_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # key exists?
    api_key = req.api_keys.get(req.provider)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"Missing api_keys['{req.provider}']")

    # call provider
    try:
        res = await provider.chat(
            api_key=api_key,
            model=req.model,
            messages=req.messages,
            timeout_s=30.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {type(e).__name__}")

    return ChatResponse(
        request_id=request_id,
        provider=res["provider"],
        model=res["model"],
        output_text=res["output_text"],
        meta={"stream": False},
    )


@router.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    request_id = str(uuid.uuid4())

    try:
        provider = get_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    api_key = req.api_keys.get(req.provider)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"Missing api_keys['{req.provider}']")

    async def event_generator():
        yield {
            "event": "meta",
            "data": f'{{"request_id":"{request_id}","provider":"{req.provider}","model":"{req.model}"}}',
        }
        try:
            async for tok in provider.stream_chat(
                api_key=api_key,
                model=req.model,
                messages=req.messages,
                timeout_s=30.0,
            ):
                yield {"event": "token", "data": tok}
        except Exception as e:
            yield {"event": "error", "data": f"Provider error: {type(e).__name__}"}
        finally:
            await asyncio.sleep(0.01)
            yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())