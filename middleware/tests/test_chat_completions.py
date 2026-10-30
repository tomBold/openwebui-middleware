import json
from typing import Any

import httpx
import pytest
import respx
import structlog
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
STREAM_CHUNKS = [
    b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"He"}}]}\n\n',
    b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"llo"}}]}\n\n',
    b'data: {"usage":{"prompt_tokens":11,"completion_tokens":2,"total_tokens":13}}\n\n',
    b"data: [DONE]\n\n",
]
TRANSPORT_ERRORS = [
    (httpx.ReadTimeout("too slow"), {"code": 504, "type": "upstream_timeout"}),
    (httpx.ConnectError("refused"), {"code": 502, "type": "upstream_unavailable"}),
]


def chat_payload(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"model": "gpt-5.4-mini", "messages": [USER_MESSAGE], **overrides}


def forwarded_body(route: respx.Route) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(route.calls.last.request.content)
    return body


async def stream_events(client: AsyncClient, payload: dict[str, Any]) -> list[bytes]:
    async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
        body = b"".join([chunk async for chunk in response.aiter_bytes()])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return [event for event in body.split(b"\n\n") if event]


async def test_non_streaming_injects_prompt_and_returns_completion(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.post(CHAT_URL).respond(json=COMPLETION)

    with structlog.testing.capture_logs() as logs:
        response = await client.post("/v1/chat/completions", json=chat_payload(temperature=0.2))

    assert response.status_code == 200
    assert response.json() == COMPLETION
    forwarded = forwarded_body(route)
    assert forwarded["messages"] == [{"role": "system", "content": SYSTEM_PROMPT}, USER_MESSAGE]
    assert forwarded["temperature"] == 0.2
    assert "stream_options" not in forwarded
    events = {log["event"]: log for log in logs}
    assert events["chat.request"]["messages_in"] == 1
    assert events["chat.request"]["messages_out"] == 2
    assert events["chat.request"]["system_prompt_injected"] is True
    assert events["chat.completed"]["prompt_tokens"] == 11


async def test_streaming_relays_upstream_events_verbatim(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.post(CHAT_URL).mock(return_value=sse_response(STREAM_CHUNKS))

    with structlog.testing.capture_logs() as logs:
        events = await stream_events(client, chat_payload(stream=True))

    assert b"\n\n".join(events) + b"\n\n" == b"".join(STREAM_CHUNKS)
    forwarded = forwarded_body(route)
    assert forwarded["stream_options"] == {"include_usage": True}
    assert forwarded["messages"][0]["content"] == SYSTEM_PROMPT
    [completed] = [log for log in logs if log["event"] == "upstream.stream_completed"]
    assert completed["prompt_tokens"] == 11
    assert completed["completion_tokens"] == 2


async def test_streaming_preserves_caller_stream_options(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.post(CHAT_URL).mock(return_value=sse_response(STREAM_CHUNKS))

    await stream_events(client, chat_payload(stream=True, stream_options={"chunk_size": 2}))

    assert forwarded_body(route)["stream_options"] == {"chunk_size": 2, "include_usage": True}


@pytest.mark.parametrize(("exc", "expected"), TRANSPORT_ERRORS)
async def test_stream_failure_mid_flight_emits_error_event_and_done(
    client: AsyncClient,
    mock_upstream: respx.MockRouter,
    exc: httpx.HTTPError,
    expected: dict[str, Any],
) -> None:
    mock_upstream.post(CHAT_URL).mock(return_value=sse_response(STREAM_CHUNKS[:1], exc))

    events = await stream_events(client, chat_payload(stream=True))

    assert events[0] == STREAM_CHUNKS[0].strip()
    error = json.loads(events[1].removeprefix(b"data: "))["error"]
    assert {key: error[key] for key in expected} == expected
    assert events[-1] == b"data: [DONE]"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("exc", "expected"), TRANSPORT_ERRORS)
async def test_transport_failure_before_response_is_typed(
    client: AsyncClient,
    mock_upstream: respx.MockRouter,
    exc: httpx.HTTPError,
    expected: dict[str, Any],
    stream: bool,  # noqa: FBT001
) -> None:
    mock_upstream.post(CHAT_URL).mock(side_effect=exc)

    response = await client.post("/v1/chat/completions", json=chat_payload(stream=stream))

    assert response.status_code == expected["code"]
    assert response.json()["error"]["type"] == expected["type"]


@pytest.mark.parametrize(
    ("status_code", "stream"), [(400, False), (401, False), (429, True), (500, False)]
)
async def test_upstream_error_status_is_relayed(
    client: AsyncClient,
    mock_upstream: respx.MockRouter,
    status_code: int,
    stream: bool,  # noqa: FBT001
) -> None:
    mock_upstream.post(CHAT_URL).respond(
        status_code=status_code,
        json={"error": {"message": "upstream says no", "type": "invalid_request_error"}},
    )

    response = await client.post("/v1/chat/completions", json=chat_payload(stream=stream))

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


@pytest.mark.parametrize("body", [{"text": "<html>not json</html>"}, {"json": []}])
async def test_upstream_success_without_json_object_is_a_bad_gateway(
    client: AsyncClient, mock_upstream: respx.MockRouter, body: dict[str, Any]
) -> None:
    mock_upstream.post(CHAT_URL).respond(**body)

    response = await client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_unavailable"
    assert response.json()["error"]["message"].startswith("Upstream returned a non-JSON body")


async def test_invalid_request_body_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/v1/chat/completions", json={"model": "gpt-5.4-mini"})

    assert response.status_code == 422
