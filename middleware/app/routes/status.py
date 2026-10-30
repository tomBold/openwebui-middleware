from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATUS_PAGE = Path(__file__).parents[1] / "static" / "index.html"

router = APIRouter(include_in_schema=False)


@router.get("/")
async def status_page() -> FileResponse:
    return FileResponse(STATUS_PAGE, media_type="text/html")
