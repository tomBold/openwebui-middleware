from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.dependencies import SettingsDep, UpstreamDep
from app.logging_config import get_logger
from app.schemas import HealthResponse
from app.upstream import UpstreamError

log = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def ready(upstream: UpstreamDep, settings: SettingsDep) -> JSONResponse:
    try:
        await upstream.list_models(timeout_s=settings.readiness_timeout)
    except UpstreamError as exc:
        log.warning("readiness.failed", status_code=exc.status_code, error=exc.message)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthResponse(status="upstream_unavailable").model_dump(),
        )
    return JSONResponse(content=HealthResponse(status="ready").model_dump())
