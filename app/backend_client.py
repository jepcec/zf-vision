from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.local_store import load_config
from app.push_log import PushLog


class BackendAuthError(Exception):
    """El api_key fue rechazado o el agente aún no está activado."""


class BackendRateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"rate_limited, retry after {retry_after}s")
        self.retry_after = retry_after


class BackendClient:
    """Cliente HTTP del agente hacia el backend SaaS.

    Patrón: PUSH del agente al backend. Solo ``poll_commands`` hace pull,
    y es long-polling (el agente pregunta y se queda esperando).
    """

    def __init__(
        self,
        base_url: str | None = None,
        mock: bool | None = None,
        log: PushLog | None = None,
    ) -> None:
        self.base_url = (
            base_url
            if base_url is not None
            else os.environ.get("BACKEND_URL", "http://localhost:8000")
        ).rstrip("/")
        if mock is None:
            env_mock = os.environ.get("MOCK_BACKEND", "true").lower()
            mock = env_mock in ("1", "true", "yes", "on")
        self.mock = mock
        self.log = log
        self.mode_label = "MOCK" if self.mock else "REAL"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── push: agente → backend ────────────────────────────────────

    async def activate(self, code: str) -> dict[str, Any]:
        body = json.dumps({"activation_code": code})
        eid = self._begin("POST", "/v1/agents/activate", body)
        t0 = time.monotonic()
        if self.mock:
            result = {
                "agent_id": 7,
                "api_key": f"zf_ak_{secrets.token_urlsafe(32)}",
                "entity_id": 1,
                "entity_name": "Banco de la Nación",
                "activated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._end(eid, None, 0, "MOCK")
            return result
        try:
            r = await self._client.post(
                f"{self.base_url}/v1/agents/activate",
                json={"activation_code": code},
            )
            r.raise_for_status()
            self._end(eid, r.status_code, self._ms(t0), "ok")
            return r.json()
        except httpx.HTTPError as e:
            self._end(eid, None, self._ms(t0), "network_error")
            raise

    async def send_heartbeat(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload)
        eid = self._begin("POST", "/v1/agents/me/heartbeat", body)
        t0 = time.monotonic()
        if self.mock:
            self._end(eid, None, 0, "MOCK")
            return
        try:
            r = await self._client.post(
                f"{self.base_url}/v1/agents/me/heartbeat",
                json=payload,
                headers={"X-Agent-Key": self._require_api_key()},
            )
            self._end(eid, r.status_code, self._ms(t0), self._note_for(r.status_code))
            if r.status_code == 401:
                raise BackendAuthError("api_key_invalid")
            r.raise_for_status()
        except httpx.HTTPError as e:
            if eid is not None and self.log:
                self._end(eid, None, self._ms(t0), "network_error")
            raise

    async def send_metric(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload)
        eid = self._begin("POST", "/v1/agents/me/metrics", body)
        t0 = time.monotonic()
        if self.mock:
            self._end(eid, None, 0, "MOCK")
            return
        try:
            r = await self._client.post(
                f"{self.base_url}/v1/agents/me/metrics",
                json=payload,
                headers={"X-Agent-Key": self._require_api_key()},
            )
            self._end(eid, r.status_code, self._ms(t0), self._note_for(r.status_code))
            if r.status_code == 401:
                raise BackendAuthError("api_key_invalid")
            if r.status_code == 429:
                retry = int(r.headers.get("Retry-After", 5))
                raise BackendRateLimited(retry)
            r.raise_for_status()
        except httpx.HTTPError as e:
            if eid is not None and self.log:
                self._end(eid, None, self._ms(t0), "network_error")
            raise

    # ── pull: comandos del backend (long-poll) ───────────────────

    async def poll_commands(self, wait_seconds: int = 30) -> list[dict[str, Any]]:
        path = f"/v1/agents/me/commands?wait={wait_seconds}"
        eid = self._begin("GET", path, "")
        t0 = time.monotonic()
        if self.mock:
            self._end(eid, None, 0, "MOCK")
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            return []
        try:
            r = await self._client.get(
                f"{self.base_url}/v1/agents/me/commands",
                params={"wait": wait_seconds},
                headers={"X-Agent-Key": self._require_api_key()},
                timeout=wait_seconds + 5,
            )
            self._end(eid, r.status_code, self._ms(t0), self._note_for(r.status_code))
            if r.status_code == 204:
                return []
            if r.status_code == 401:
                raise BackendAuthError("api_key_invalid")
            r.raise_for_status()
            body = r.json()
            return body if isinstance(body, list) else []
        except httpx.HTTPError as e:
            if eid is not None and self.log:
                self._end(eid, None, self._ms(t0), "network_error")
            raise

    # ── helpers ──────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        cfg = load_config()
        api_key = (cfg.get("activation") or {}).get("api_key")
        if not api_key:
            raise BackendAuthError("agent_not_activated")
        return api_key

    def _begin(self, method: str, path: str, body: str) -> int | None:
        if not self.log:
            return None
        return self.log.record_request(method, path, body, self.mode_label)

    def _end(self, eid: int | None, status: int | None, duration_ms: int, note: str) -> None:
        if eid is not None and self.log:
            self.log.record_response(eid, status, duration_ms, note)

    @staticmethod
    def _ms(t0: float) -> int:
        return int((time.monotonic() - t0) * 1000)

    @staticmethod
    def _note_for(status: int) -> str:
        if 200 <= status < 300:
            return "ok"
        if status == 401:
            return "auth_error"
        if status == 429:
            return "rate_limited"
        return "http_error"
