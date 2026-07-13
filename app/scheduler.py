from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.backend_client import BackendClient
from app.config import get_settings
from app.local_store import load_config
from app.vision.pipeline import QueuePipeline

log = logging.getLogger(__name__)


class PushScheduler:
    def __init__(self, client: BackendClient, pipeline: QueuePipeline) -> None:
        self.client = client
        self.pipeline = pipeline
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False
        self._interval = get_settings().PUSH_INTERVAL_S

    @property
    def running(self) -> bool:
        return self._running

    @property
    def interval_s(self) -> int:
        return self._interval

    async def start(self) -> None:
        cfg = load_config()
        if not (cfg.get("activation") or {}).get("api_key"):
            log.info("scheduler: no api_key, no se inicia")
            return
        if self._running:
            return
        self._stop.clear()
        self.pipeline.start()
        self._task = asyncio.create_task(self._loop(), name="zf-tick")
        self._running = True
        log.info("scheduler: iniciado (intervalo único=%ds)", self._interval)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(self._task, return_exceptions=True),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                log.warning("scheduler: task no terminó en 2s, continuando")
        self._task = None
        self.pipeline.stop()
        log.info("scheduler: detenido")

    async def _send_metric_safe(self) -> None:
        try:
            r = self.pipeline.count()
            payload = {
                "people": r.people,
                "queue_status": r.queue_status,
                "fps": round(r.fps, 1),
                "model_version": "yolov8n" if r.model_loaded else "unloaded",
                "infer_ms": round(r.last_infer_ms, 1),
                "polygons_used": r.polygons_used,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            await self.client.send_metric(payload)
        except Exception as e:
            log.warning("metric falló: %s", e)

    async def _send_heartbeat_safe(self) -> None:
        try:
            await self.client.send_heartbeat({
                "ts": datetime.now(timezone.utc).isoformat(),
                "version": "0.1.0",
            })
        except Exception as e:
            log.warning("heartbeat falló: %s", e)

    async def _poll_commands_safe(self) -> None:
        try:
            await self.client.poll_commands(wait_seconds=self._interval)
        except Exception as e:
            log.warning("commands falló: %s", e)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            await asyncio.gather(
                self._send_metric_safe(),
                self._send_heartbeat_safe(),
                self._poll_commands_safe(),
            )
            elapsed = time.monotonic() - t0
            remaining = max(0.0, self._interval - elapsed)
            if remaining > 0:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
