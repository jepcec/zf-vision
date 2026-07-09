from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import cv2
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.backend_client import BackendClient
from app.config import get_settings
from app.local_store import load_config
from app.paths import web_dir
from app.push_log import PushLog
from app.routers import activation, api, cameras, log as log_router, pages, preview, roi
from app.scheduler import PushScheduler
from app.vision.pipeline import QueuePipeline

log = logging.getLogger(__name__)


def _open_camera_for_pipeline() -> cv2.VideoCapture:
    cfg = load_config()
    cam = cfg.get("camera") or {}
    kind = cam.get("kind")
    if kind == "usb":
        return cv2.VideoCapture(cam.get("index"))
    if kind == "rtsp":
        return cv2.VideoCapture(cam.get("source_uri"))
    raise RuntimeError("no hay cámara configurada")


def _load_rois_for_pipeline() -> list[list[tuple[float, float]]]:
    cfg = load_config()
    roi_cfg = cfg.get("roi") or {}
    polys = roi_cfg.get("polygons") or []
    out: list[list[tuple[float, float]]] = []
    for poly in polys:
        out.append([(float(p["x"]), float(p["y"])) for p in poly])
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.push_log = PushLog(max_events=200)
    app.state.backend = BackendClient(
        base_url=settings.BACKEND_URL or None,
        mock=settings.MOCK_BACKEND,
        log=app.state.push_log,
    )
    app.state.loop = asyncio.get_running_loop()
    app.state.pipeline = QueuePipeline(
        source=_open_camera_for_pipeline,
        roi_provider=_load_rois_for_pipeline,
    )
    app.state.scheduler = PushScheduler(
        client=app.state.backend, pipeline=app.state.pipeline
    )
    await app.state.scheduler.start()
    log.info(
        "zf-vision starting · mock=%s · backend=%s",
        app.state.backend.mock,
        app.state.backend.base_url,
    )
    try:
        yield
    finally:
        await app.state.scheduler.stop()
        await app.state.backend.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title="zf-vision",
        version="0.1.0",
        description="Agente local de Zero Fila · activación + ROI + detección",
        lifespan=lifespan,
    )

    static_dir = web_dir() / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(pages.router)
    app.include_router(activation.router)
    app.include_router(cameras.router)
    app.include_router(roi.router)
    app.include_router(api.router)
    app.include_router(log_router.router)
    app.include_router(preview.router)

    return app


app = create_app()
