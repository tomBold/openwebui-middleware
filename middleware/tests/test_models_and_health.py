import httpx
import pytest
import respx
import structlog
from fastapi import FastAPI
from httpx import AsyncClient

from app.logging_config import configure_logging, get_logger

MODELS_URL = "/models"
UPSTREAM_MODELS = {
    "object": "list",
    "data": [
        {"id": "gpt-5.4-mini", "object": "model"},
        {"id": "text-embedding-3-small", "object": "model"},
    ],
}


@pytest.mark.parametrize(
    ("allowlist", "expected_ids"),
    [
        (["gpt-5.4-mini"], ["gpt-5.4-mini"]),
        ([], ["gpt-5.4-mini", "text-embedding-3-small"]),
        (["model-the-account-cannot-see"], []),
    ],
)
async def test_models_are_filtered_by_allowlist(
    app: FastAPI,
    client: AsyncClient,
    mock_upstream: respx.MockRouter,
    allowlist: list[str],
    expected_ids: list[str],
) -> None:
    mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)
    app.state.settings = app.state.settings.model_copy(update={"openai_models": allowlist})

    response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert [model["id"] for model in response.json()["data"]] == expected_ids


async def test_models_upstream_failure_is_relayed(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).mock(side_effect=httpx.ConnectError("refused"))

    response = await client.get("/v1/models")

    assert response.status_code == 502


async def test_health_does_not_touch_upstream(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    route = mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not route.called


async def test_ready_reports_ready_when_upstream_responds(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_ready_failure_is_a_503_with_the_lifecycle_logged_in_order(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(status_code=401, json={"error": {"message": "bad key"}})

    with structlog.testing.capture_logs() as logs:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "upstream_unavailable"}
    assert [(log["event"], log["log_level"]) for log in logs] == [
        ("request.started", "info"),
        ("readiness.failed", "warning"),
        ("request.completed", "info"),
    ]
    assert logs[-1]["status_code"] == 503
    assert isinstance(logs[-1]["duration_ms"], int)


async def test_status_page_is_served_at_root(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Middleware status" in response.text


async def test_request_id_is_echoed_or_generated(client: AsyncClient) -> None:
    echoed = await client.get("/health", headers={"X-Request-ID": "abc123"})
    generated = await client.get("/health")

    assert echoed.headers["X-Request-ID"] == "abc123"
    assert len(generated.headers["X-Request-ID"]) == 32


def test_console_renderer_is_used_when_json_is_off(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=False)
    get_logger("test").info("hello.text", answer=42)
    configure_logging("INFO", json=True)

    line = capsys.readouterr().out.strip()
    assert line.startswith("20")
    assert "hello.text" in line
    assert "answer=42" in line
