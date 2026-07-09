from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.backend_client import BackendClient
from app.local_store import current_step, has_api_key, load_config

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/local/status")
def local_status(request: Request) -> dict:
    client: BackendClient = request.app.state.backend
    cfg = load_config()
    return {
        "state": current_step(cfg),
        "has_api_key": has_api_key(cfg),
        "has_camera": bool(cfg.get("camera")),
        "has_roi": bool((cfg.get("roi") or {}).get("polygons")),
        "mock_backend": client.mock,
        "activation": cfg.get("activation"),
        "camera": cfg.get("camera"),
        "roi": cfg.get("roi"),
    }


@router.get("/api/local/push-log")
def get_push_log(request: Request) -> dict:
    log = request.app.state.push_log
    return {"events": log.all(), "counts": log.counts()}


@router.delete("/api/local/push-log")
def clear_push_log(request: Request) -> dict:
    request.app.state.push_log.clear()
    return {"ok": True}


@router.get("/api/local/agent-status")
def agent_status(request: Request) -> dict:
    pipeline = request.app.state.pipeline
    scheduler = request.app.state.scheduler
    r = pipeline.count()
    return {
        "scheduler_running": scheduler.running,
        "pipeline_running": pipeline.is_running(),
        "model_loaded": r.model_loaded,
        "people": r.people,
        "queue_status": r.queue_status,
        "fps": round(r.fps, 1),
        "infer_ms": round(r.last_infer_ms, 1),
        "polygons_used": r.polygons_used,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
