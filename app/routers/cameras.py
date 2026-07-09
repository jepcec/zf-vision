from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.camera import (
    JPEG_QUALITY,
    PREVIEW_FPS_CAP,
    list_usb_cameras,
    open_source,
    test_source,
)
from app.local_store import load_config, save_config
from app.paths import web_dir

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(web_dir() / "templates"))


def _save_camera(kind: str, index: int | None, source_uri: str | None,
                 width: int | None = None, height: int | None = None) -> None:
    cfg = load_config()
    cfg["camera"] = {
        "kind": kind,
        "index": index,
        "source_uri": source_uri,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }
    if width and height:
        cfg["camera"]["width"] = width
        cfg["camera"]["height"] = height
    save_config(cfg)


@router.post("/cameras")
async def pick_camera(
    request: Request,
    kind: str = Form(...),
    index: str | None = Form(None),
    source_uri: str | None = Form(None),
):
    if kind not in ("usb", "rtsp"):
        return _camera_error(request, "Tipo de cámara no soportado.", source_uri or "")

    idx = int(index) if (kind == "usb" and index not in (None, "")) else None
    uri = (source_uri or "").strip() or None

    if kind == "usb" and idx is None:
        return _camera_error(request, "Falta el índice de la cámara USB.", uri or "")
    if kind == "rtsp" and not uri:
        return _camera_error(request, "Falta la URL RTSP.", uri or "")

    ok = await request.app.state.loop.run_in_executor(
        None, test_source, kind, idx, uri, 5.0
    )
    if not ok:
        msg = "No pudimos abrir la cámara. Revisá la conexión o las credenciales."
        return _camera_error(request, msg, uri or "")

    width = height = None
    try:
        cap = await request.app.state.loop.run_in_executor(
            None, open_source, kind, idx, uri
        )
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        cap.release()
    except Exception:
        pass

    _save_camera(kind, idx, uri, width, height)
    return RedirectResponse(url="/roi", status_code=303)


def _camera_error(request: Request, message: str, source_uri: str):
    return templates.TemplateResponse(
        request,
        "_step_camera.html",
        {
            "current_step": "camera",
            "error": message,
            "source_uri": source_uri,
            "usb_cameras": list_usb_cameras(),
        },
        status_code=400,
    )


# ── MJPEG preview ──────────────────────────────────────────────────

def _placeholder_jpeg(running: bool, model_loaded: bool) -> bytes:
    img = np.full((360, 640, 3), 60, dtype="uint8")
    if not running:
        msg = "Pipeline no iniciada"
    elif not model_loaded:
        msg = "Cargando modelo YOLOv8n..."
    else:
        msg = "Esperando frame de la camara..."
    cv2.putText(
        img, msg, (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2
    )
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buf.tobytes() if ok else b""


@router.get("/cameras/preview")
async def preview(request: Request) -> StreamingResponse:
    pipeline = request.app.state.pipeline

    def generator():
        delay = 1.0 / max(1.0, PREVIEW_FPS_CAP)
        while True:
            r = pipeline.count()
            body = r.last_jpeg
            if body is None:
                body = _placeholder_jpeg(pipeline.is_running(), r.model_loaded)
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
                + body + b"\r\n"
            )
            time.sleep(delay)

    return StreamingResponse(
        generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
