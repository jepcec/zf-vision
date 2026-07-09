from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.backend_client import BackendAuthError, BackendClient
from app.config import get_settings
from app.local_store import current_step, load_config, save_config
from app.paths import web_dir

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(web_dir() / "templates"))


def get_client(request: Request) -> BackendClient:
    return request.app.state.backend


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/status", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/activation", include_in_schema=False)
def activation_alias() -> RedirectResponse:
    return RedirectResponse(url="/status", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/cameras", include_in_schema=False)
def cameras_alias() -> RedirectResponse:
    return RedirectResponse(url="/status", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/roi", include_in_schema=False)
def roi_alias() -> RedirectResponse:
    return RedirectResponse(url="/status", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/status", include_in_schema=False)
def status_page(
    request: Request,
    client: BackendClient = Depends(get_client),
) -> object:
    cfg = load_config()
    step = current_step(cfg)
    if step == "done":
        template = "_step_done.html"
    elif step == "camera":
        template = "_step_camera.html"
    elif step == "roi":
        template = "_step_roi.html"
    else:
        template = "_step_activation.html"

    ctx: dict = {
        "request": request,
        "current_step": step,
        "mock_label": "MOCK" if client.mock else "REAL",
        "activation": cfg.get("activation") or {},
        "camera": cfg.get("camera"),
        "roi": cfg.get("roi"),
    }
    if step == "camera":
        from app.camera import list_usb_cameras

        ctx["usb_cameras"] = list_usb_cameras()
    return templates.TemplateResponse(request, template, ctx)


@router.post("/reset", include_in_schema=False)
async def reset(request: Request) -> RedirectResponse:
    await request.app.state.scheduler.stop()
    from app.local_store import reset_config
    reset_config()
    return RedirectResponse(url="/activation", status_code=status.HTTP_303_SEE_OTHER)
