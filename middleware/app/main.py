from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestContextMiddleware
from app.prompt import load_system_prompt
from app.routes import health, openai
from app.schemas import ErrorDetail, ErrorResponse
from app.upstream import OpenAIUpstream, UpstreamError

log = get_logger(__name__)


async def upstream_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, UpstreamError):
        raise exc
    log.warning("upstream.error", status_code=exc.status_code, error=exc.message)
    body = ErrorResponse(
        error=ErrorDetail(message=exc.message, type=exc.error_type, code=exc.status_code)
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        timeout = httpx.Timeout(
            settings.upstream_read_timeout, connect=settings.upstream_connect_timeout
        )
        headers = {"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"}
        async with httpx.AsyncClient(
            base_url=str(settings.openai_base_url).rstrip("/"), headers=headers, timeout=timeout
        ) as client:
            app.state.settings = settings
            app.state.upstream = OpenAIUpstream(client)
            app.state.system_prompt = load_system_prompt(settings.system_prompt_path)
            log.info("app.started", upstream=str(settings.openai_base_url))
            yield

    app = FastAPI(
        title="Open WebUI Middleware",
        description="OpenAI-compatible proxy that injects a structured-extraction system prompt.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(UpstreamError, upstream_error_handler)
    app.include_router(health.router)
    app.include_router(openai.router, prefix="/v1")
    return app
