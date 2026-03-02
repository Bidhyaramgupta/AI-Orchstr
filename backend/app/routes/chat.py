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

    # 1) Validate provider (client error)
    try:
        provider = get_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2) Validate user key (client error)
    if not getattr(req, "user_api_key", None):
        raise HTTPException(status_code=400, detail="Missing user_api_key")

    # 3) Call provider (upstream error)
    try:
        res = await provider.chat(
            api_key=req.user_api_key,
            model=req.model,
            messages=req.messages,
            timeout_s=30.0,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Provider error: {type(e).__name__}",
        )

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

    # 1) Validate provider (client error)
    try:
        provider = get_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2) Validate user key (client error)
    if not getattr(req, "user_api_key", None):
        raise HTTPException(status_code=400, detail="Missing user_api_key")

    async def event_generator():
        yield {
            "event": "meta",
            "data": (
                f'{{"request_id":"{request_id}",'
                f'"provider":"{req.provider}",'
                f'"model":"{req.model}"}}'
            ),
        }

        try:
            async for tok in provider.stream_chat(
                api_key=req.user_api_key,
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