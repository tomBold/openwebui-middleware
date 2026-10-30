import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.logging_config import get_logger
from app.schemas import ErrorDetail, ErrorResponse
from app.upstream import UpstreamError

log = get_logger(__name__)

SSE_DONE = b"data: [DONE]\n\n"
SSE_EVENT_SEPARATOR = b"\n\n"
SSE_DATA_PREFIX = b"data:"
USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def usage_fields(usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage or {}
    fields = {field: usage.get(field) for field in USAGE_FIELDS}
    fields["cached_tokens"] = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    return fields


def sse_error_event(status_code: int, message: str, error_type: str) -> bytes:
    body = ErrorResponse(error=ErrorDetail(message=message, type=error_type, code=status_code))
    return b"data: " + body.model_dump_json().encode() + SSE_EVENT_SEPARATOR


class UsageTracker:
    def __init__(self) -> None:
        self.usage: dict[str, Any] | None = None
        self._buffer = b""

    def feed(self, chunk: bytes) -> None:
        self._buffer += chunk
        *events, self._buffer = self._buffer.split(SSE_EVENT_SEPARATOR)
        for event in events:
            self._consume(event)

    def _consume(self, event: bytes) -> None:
        for line in event.splitlines():
            if not line.startswith(SSE_DATA_PREFIX):
                continue
            try:
                payload = json.loads(line[len(SSE_DATA_PREFIX) :])
            except ValueError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
                self.usage = payload["usage"]


async def relay_sse(response: httpx.Response, started: float) -> AsyncIterator[bytes]:
    tracker = UsageTracker()
    first_byte_at: float | None = None
    try:
        async for chunk in response.aiter_bytes():
            if first_byte_at is None:
                first_byte_at = time.perf_counter()
                log.info("upstream.first_byte", ttft_ms=round((first_byte_at - started) * 1000))
            tracker.feed(chunk)
            yield chunk
    except httpx.HTTPError as exc:
        error = UpstreamError.from_transport(exc)
        log.warning("upstream.stream_failed", error_type=error.error_type, error=error.message)
        yield sse_error_event(error.status_code, error.message, error.error_type)
        yield SSE_DONE
    finally:
        await response.aclose()
        log.info(
            "upstream.stream_completed",
            duration_ms=round((time.perf_counter() - started) * 1000),
            **usage_fields(tracker.usage),
        )
