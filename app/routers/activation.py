from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from httpx import HTTPError

from app.backend_client import BackendClient
from app.local_store import load_config, save_config
from app.paths import web_dir

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(web_dir() / "templates"))


def get_client(request: Request) -> BackendClient:
    return request.app.state.backend


@router.post("/activation")
async def submit_activation(
    request: Request,
    code: str = Form(...),
    client: BackendClient = Depends(get_client),
):
    code = (code or "").strip()
    if len(code) < 4:
        return _activation_error(request, code, "El código debe tener al menos 4 caracteres.")

    try:
        result = await client.activate(code)
    except HTTPError as e:
        log.warning("activate failed: %s", e)
        return _activation_error(request, code, "No se pudo contactar al backend.")
    except Exception as e:
        log.exception("activate unexpected error")
        return _activation_error(request, code, f"Error inesperado: {e}")

    cfg = load_config()
    cfg["activation"] = {
        "agent_id": result.get("agent_id"),
        "api_key": result.get("api_key"),
        "entity_id": result.get("entity_id"),
        "entity_name": result.get("entity_name"),
        "activated_at": result.get("activated_at"),
        "code": code,
    }
    save_config(cfg)
    await request.app.state.scheduler.start()
    return RedirectResponse(url="/cameras", status_code=303)


def _activation_error(request: Request, code: str, message: str):
    return templates.TemplateResponse(
        request,
        "_step_activation.html",
        {"current_step": "activation", "error": message, "code": code},
        status_code=400,
    )
