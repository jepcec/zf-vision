from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.backend_client import BackendClient
from app.local_store import load_config
from app.vision.pipeline import QueuePipeline

log = logging.getLogger(__name__)

METRIC_INTERVAL_S = 5
HEARTBEAT_INTERVAL_S = 30
COMMANDS_INTERVAL_S = 60


class PushScheduler:
    def __init__(self, client: BackendClient, pipeline: QueuePipeline) -> None:
        self.client = client
        self.pipeline = pipeline
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        cfg = load_config()
        if not (cfg.get("activation") or {}).get("api_key"):
            log.info("scheduler: no api_key, no se inicia")
            return
        if self._running:
            return
        self._stop.clear()
        self.pipeline.start()
        self._tasks = [
            asyncio.create_task(self._metric_loop(), name="zf-metric"),
            asyncio.create_task(self._heartbeat_loop(), name="zf-heartbeat"),
            asyncio.create_task(self._commands_loop(), name="zf-commands"),
        ]
        self._running = True
        log.info(
            "scheduler: iniciado (metric=%ds, heartbeat=%ds, commands=%ds)",
            METRIC_INTERVAL_S, HEARTBEAT_INTERVAL_S, COMMANDS_INTERVAL_S,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=2.0,
            )
        except asyncio.TimeoutError:
            log.warning("scheduler: tasks no terminaron en 2s, continuando")
        self._tasks.clear()
        self.pipeline.stop()
        log.info("scheduler: detenido")

    async def _metric_loop(self) -> None:
        while not self._stop.is_set():
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
                log.warning("metric tick falló: %s", e)
            await asyncio.sleep(METRIC_INTERVAL_S)

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.client.send_heartbeat({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "version": "0.1.0",
                })
            except Exception as e:
                log.warning("heartbeat tick falló: %s", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)

    async def _commands_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.client.poll_commands(wait_seconds=COMMANDS_INTERVAL_S)
            except Exception as e:
                log.warning("commands tick falló: %s", e)
            await asyncio.sleep(1)
