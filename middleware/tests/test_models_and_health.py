import httpx
import pytest
import respx
import structlog
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.logging_config import configure_logging, get_logger
from app.main import create_app

MODELS_URL = "/models"
UPSTREAM_MODELS = {
    "object": "list",
    "data": [
        {"id": "gpt-5.4-mini", "object": "model"},
        {"id": "text-embedding-3-small", "object": "model"},
    ],
}


async def models_with_allowlist(settings: Settings, allowlist: list[str]) -> list[dict[str, str]]:
    app = create_app(settings.model_copy(update={"openai_models": allowlist}))
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://middleware.test") as client,
        app.router.lifespan_context(app),
    ):
        response = await client.get("/v1/models")
    data: list[dict[str, str]] = response.json()["data"]
    return data


async def test_models_are_filtered_by_allowlist(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)

    response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [{"id": "gpt-5.4-mini", "object": "model"}],
    }


async def test_empty_allowlist_passes_every_upstream_model_through(
    settings: Settings, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)

    assert await models_with_allowlist(settings, []) == UPSTREAM_MODELS["data"]


async def test_allowlist_matching_nothing_returns_empty_list(
    settings: Settings, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)

    assert await models_with_allowlist(settings, ["model-the-account-cannot-see"]) == []


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


async def test_ready_reports_unavailable_when_upstream_fails(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(status_code=401, json={"error": {"message": "bad key"}})

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "upstream_unavailable"}


async def test_status_page_is_served_at_root(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Middleware status" in response.text


async def test_request_id_is_echoed_when_provided(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32


async def test_lifecycle_and_failure_events_are_logged_in_order(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(status_code=401, json={"error": {"message": "bad key"}})

    with structlog.testing.capture_logs() as logs:
        await client.get("/ready")

    events = [(log["event"], log["log_level"]) for log in logs]
    assert events == [
        ("request.started", "info"),
        ("readiness.failed", "warning"),
        ("request.completed", "info"),
    ]
    assert logs[-1]["status_code"] == 503
    assert isinstance(logs[-1]["duration_ms"], int)


def test_console_renderer_is_used_when_json_is_off(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=False)
    get_logger("test").info("hello.text", answer=42)
    configure_logging("INFO", json=True)

    line = capsys.readouterr().out.strip()
    assert line.startswith("20")
    assert "hello.text" in line
    assert "answer=42" in line
