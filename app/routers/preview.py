from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.local_store import load_config
from app.paths import web_dir

router = APIRouter()
templates = Jinja2Templates(directory=str(web_dir() / "templates"))


@router.get("/preview", include_in_schema=False)
def preview_page(request: Request) -> object:
    cfg = load_config()
    client = request.app.state.backend
    return templates.TemplateResponse(
        request,
        "_preview.html",
        {
            "current_step": "preview",
            "mock_label": "MOCK" if client.mock else "REAL",
            "roi": cfg.get("roi") or {},
        },
    )
