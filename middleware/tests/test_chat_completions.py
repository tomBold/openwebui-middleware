import json
from typing import Any

import httpx
import pytest
import respx
from httpx import AsyncClient

from tests.conftest import SYSTEM_PROMPT, sse_response

CHAT_URL = "/chat/completions"
USER_MESSAGE = {"role": "user", "content": "invoice 42"}
COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
}
USAGE_CHUNK = (
    b'data: {"id":"chatcmpl-1","choices":[],"usage":'
    b'{"prompt_tokens":11,"completion_tokens":2,"total_tokens":13}}\n\n'
)
STREAM_CHUNKS = [
    b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"He"}}]}\n\n',
    b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"llo"}}]}\n\n',
    USAGE_CHUNK,
    b"data: [DONE]\n\n",
]


def chat_payload(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"model": "gpt-5.4-mini", "messages": [USER_MESSAGE], **overrides}


def forwarded_body(route: respx.Route) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(route.calls.last.request.content)
    return body


async def test_non_streaming_injects_prompt_and_returns_completion(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.post(CHAT_URL).respond(json=COMPLETION)

    response = await client.post("/v1/chat/completions", json=chat_payload(temperature=0.2))

    assert response.status_code == 200
    assert response.json() == COMPLETION
    forwarded = forwarded_body(route)
    assert forwarded["messages"] == [{"role": "system", "content": SYSTEM_PROMPT}, USER_MESSAGE]
    assert forwarded["temperature"] == 0.2
    assert "stream_options" not in forwarded


async def test_streaming_relays_upstream_events_verbatim(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.post(CHAT_URL).mock(return_value=sse_response(STREAM_CHUNKS))

    async with client.stream(
        "POST", "/v1/chat/completions", json=chat_payload(stream=True)
    ) as response:
        body = b"".join([chunk async for chunk in response.aiter_bytes()])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert body == b"".join(STREAM_CHUNKS)
    forwarded = forwarded_body(route)
    assert forwarded["stream_options"] == {"include_usage": True}
    assert forwarded["messages"][0]["content"] == SYSTEM_PROMPT


async def test_streaming_preserves_caller_stream_options(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.post(CHAT_URL).mock(return_value=sse_response(STREAM_CHUNKS))

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json=chat_payload(stream=True, stream_options={"chunk_size": 2}),
    ) as response:
        await response.aread()

    assert forwarded_body(route)["stream_options"] == {"chunk_size": 2, "include_usage": True}


async def test_stream_failure_mid_flight_emits_error_event_and_done(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.post(CHAT_URL).mock(
        return_value=sse_response(STREAM_CHUNKS[:1], httpx.ReadError("connection lost"))
    )

    async with client.stream(
        "POST", "/v1/chat/completions", json=chat_payload(stream=True)
    ) as response:
        body = b"".join([chunk async for chunk in response.aiter_bytes()])

    events = [event for event in body.split(b"\n\n") if event]
    error = json.loads(events[1].removeprefix(b"data: "))
    assert response.status_code == 200
    assert error["error"]["type"] == "upstream_unavailable"
    assert events[-1] == b"data: [DONE]"


@pytest.mark.parametrize("status_code", [400, 401, 429, 500])
async def test_upstream_error_status_is_relayed(
    client: AsyncClient, mock_upstream: respx.MockRouter, status_code: int
) -> None:
    mock_upstream.post(CHAT_URL).respond(
        status_code=status_code,
        json={"error": {"message": "upstream says no", "type": "invalid_request_error"}},
    )

    response = await client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == status_code
    assert response.json()["error"]["message"] == "upstream says no"
    assert response.json()["error"]["type"] == "invalid_request_error"


async def test_upstream_error_without_json_body_is_relayed(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.post(CHAT_URL).respond(status_code=503, text="service unavailable")

    response = await client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 503
    assert response.json()["error"] == {
        "message": "service unavailable",
        "type": "upstream_error",
        "code": 503,
    }


async def test_upstream_timeout_returns_gateway_timeout(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("too slow"))

    response = await client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 504
    assert response.json()["error"]["type"] == "upstream_timeout"


async def test_upstream_connection_error_returns_bad_gateway(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.post(CHAT_URL).mock(side_effect=httpx.ConnectError("refused"))

    response = await client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_unavailable"


async def test_streaming_upstream_error_is_relayed_before_streaming(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.post(CHAT_URL).respond(
        status_code=429, json={"error": {"message": "rate limited", "type": "rate_limit_error"}}
    )

    response = await client.post("/v1/chat/completions", json=chat_payload(stream=True))

    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit_error"


async def test_invalid_request_body_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/v1/chat/completions", json={"model": "gpt-5.4-mini"})

    assert response.status_code == 422
