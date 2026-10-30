import httpx
import respx
from httpx import ASGITransport, AsyncClient

from app.config import Settings
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


async def test_request_id_is_echoed_when_provided(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32
