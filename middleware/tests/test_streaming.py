import json

from app.streaming import UsageTracker, usage_fields

USAGE = {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
USAGE_EVENT = b"data: " + json.dumps({"choices": [], "usage": USAGE}).encode() + b"\n\n"


def test_usage_tracker_reads_usage_split_across_chunks() -> None:
    tracker = UsageTracker()
    midpoint = len(USAGE_EVENT) // 2

    tracker.feed(b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n' + USAGE_EVENT[:midpoint])
    assert tracker.usage is None

    tracker.feed(USAGE_EVENT[midpoint:] + b"data: [DONE]\n\n")
    assert tracker.usage == USAGE


def test_usage_tracker_ignores_malformed_and_non_data_lines() -> None:
    tracker = UsageTracker()

    tracker.feed(b": keep-alive\n\ndata: not json\n\ndata: [DONE]\n\ndata: 42\n\n")

    assert tracker.usage is None


def test_usage_fields_reports_cached_tokens_and_defaults_to_none() -> None:
    cached = {**USAGE, "prompt_tokens_details": {"cached_tokens": 4}}

    assert usage_fields(cached) == {**USAGE, "cached_tokens": 4}
    assert usage_fields(None) == dict.fromkeys([*USAGE, "cached_tokens"])
