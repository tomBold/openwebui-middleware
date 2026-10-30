import json

from app.streaming import UsageTracker, sse_error_event, usage_fields

USAGE_EVENT = (
    b'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":7,"total_tokens":12}}\n\n'
)


def test_usage_tracker_reads_usage_from_final_event() -> None:
    tracker = UsageTracker()

    tracker.feed(b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n')
    tracker.feed(USAGE_EVENT)
    tracker.feed(b"data: [DONE]\n\n")

    assert tracker.usage == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}


def test_usage_tracker_handles_events_split_across_chunks() -> None:
    tracker = UsageTracker()
    midpoint = len(USAGE_EVENT) // 2

    tracker.feed(USAGE_EVENT[:midpoint])
    assert tracker.usage is None

    tracker.feed(USAGE_EVENT[midpoint:])
    assert tracker.usage is not None


def test_usage_tracker_ignores_malformed_and_non_data_lines() -> None:
    tracker = UsageTracker()

    tracker.feed(b": keep-alive\n\ndata: not json\n\ndata: [DONE]\n\ndata: 42\n\n")

    assert tracker.usage is None


def test_usage_fields_defaults_to_none_without_usage() -> None:
    assert usage_fields(None) == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cached_tokens": None,
    }


def test_usage_fields_reports_cached_prompt_tokens() -> None:
    usage = {"prompt_tokens": 1513, "prompt_tokens_details": {"cached_tokens": 1408}}

    assert usage_fields(usage)["cached_tokens"] == 1408


def test_sse_error_event_is_a_single_openai_shaped_event() -> None:
    event = sse_error_event(502, "boom", "upstream_unavailable")

    assert event.endswith(b"\n\n")
    assert json.loads(event.removeprefix(b"data: ")) == {
        "error": {"message": "boom", "type": "upstream_unavailable", "code": 502}
    }
