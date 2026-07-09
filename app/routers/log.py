from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.paths import web_dir

router = APIRouter()
templates = Jinja2Templates(directory=str(web_dir() / "templates"))


@router.get("/log", include_in_schema=False)
def log_page(request: Request) -> object:
    client = request.app.state.backend
    return templates.TemplateResponse(
        request,
        "_log.html",
        {
            "current_step": "log",
            "mock_label": "MOCK" if client.mock else "REAL",
        },
    )
