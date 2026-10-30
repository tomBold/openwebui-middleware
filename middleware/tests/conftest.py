from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

UPSTREAM = "https://upstream.test/v1"
SYSTEM_PROMPT = "SYSTEM PROMPT UNDER TEST"


class AsyncByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Sequence[bytes], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error


def sse_response(chunks: Sequence[bytes], error: Exception | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"Content-Type": "text/event-stream"},
        stream=AsyncByteStream(chunks, error),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text(SYSTEM_PROMPT, encoding="utf-8")
    return Settings(
        openai_api_key="test-key",
        openai_base_url="https://upstream.test/v1",
        openai_models=["gpt-4o-mini"],
        system_prompt_path=prompt_path,
        readiness_timeout=1.0,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def mock_upstream() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=UPSTREAM, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://middleware.test") as http_client,
        app.router.lifespan_context(app),
    ):
        yield http_client
