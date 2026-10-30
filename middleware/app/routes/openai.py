import time
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.dependencies import SettingsDep, SystemPromptDep, UpstreamDep
from app.logging_config import get_logger
from app.prompt import inject_system_prompt
from app.schemas import ChatCompletionRequest
from app.streaming import relay_sse, usage_fields

log = get_logger(__name__)
router = APIRouter(tags=["openai"])

STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/models")
async def list_models(upstream: UpstreamDep, settings: SettingsDep) -> dict[str, Any]:
    models = await upstream.list_models()
    allowed = set(settings.openai_models)
    data = [model for model in models if not allowed or model["id"] in allowed]
    if allowed and not data:
        log.warning(
            "models.allowlist_matched_nothing",
            allowed=sorted(allowed),
            upstream_count=len(models),
        )
    return {"object": "list", "data": data}


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    body: ChatCompletionRequest,
    upstream: UpstreamDep,
    system_prompt: SystemPromptDep,
) -> Response:
    payload = body.model_dump(exclude_unset=True)
    payload["messages"] = inject_system_prompt(body.messages, system_prompt)
    log.info(
        "chat.request",
        model=body.model,
        stream=body.stream,
        messages_in=len(body.messages),
        messages_out=len(payload["messages"]),
        system_prompt_injected=True,
    )

    if not body.stream:
        completion = await upstream.chat_completion(payload)
        log.info("chat.completed", **usage_fields(completion.get("usage")))
        return JSONResponse(completion)

    payload["stream_options"] = {**(body.stream_options or {}), "include_usage": True}
    started = time.perf_counter()
    response = await upstream.open_chat_stream(payload)
    return StreamingResponse(
        relay_sse(response, started), media_type="text/event-stream", headers=STREAM_HEADERS
    )
