import httpx
import respx
from httpx import AsyncClient

MODELS_URL = "/models"
UPSTREAM_MODELS = {
    "object": "list",
    "data": [
        {"id": "gpt-4o-mini", "object": "model"},
        {"id": "text-embedding-3-small", "object": "model"},
    ],
}


async def test_models_are_filtered_by_allowlist(
    client: AsyncClient, mock_upstream: respx.MockRouter
) -> None:
    mock_upstream.get(MODELS_URL).respond(json=UPSTREAM_MODELS)

    response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": [{"id": "gpt-4o-mini", "object": "model"}]}


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
