from __future__ import annotations

import json

import httpx
import pytest

from app.backend_client import (
    BackendAuthError,
    BackendClient,
    BackendRateLimited,
)
from app.local_store import save_config


# ── mock mode ──────────────────────────────────────────────────────


def test_mock_activate_returns_valid_dict() -> None:
    async def run() -> None:
        c = BackendClient(mock=True)
        try:
            r = await c.activate("CODE-1234")
            assert r["api_key"].startswith("zf_ak_")
            assert r["entity_name"] == "Banco de la Nación"
            assert isinstance(r["agent_id"], int)
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())


def test_mock_send_heartbeat_and_metric_are_noop() -> None:
    async def run() -> None:
        c = BackendClient(mock=True)
        try:
            await c.send_heartbeat({"ts": "now"})
            await c.send_metric({"people": 5, "queue_status": "LOW"})
            assert await c.poll_commands(wait_seconds=0) == []
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())


# ── real mode: contrato HTTP via MockTransport ────────────────────


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, dict | None, dict | None]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append(
            (request.method, request.url.path, request.url.query, body, dict(request.headers))
        )
        if request.url.path == "/v1/agents/activate":
            return httpx.Response(
                200,
                json={
                    "agent_id": 42,
                    "api_key": "zf_ak_real",
                    "entity_id": 3,
                    "entity_name": "Real",
                    "activated_at": "2026-07-08T00:00:00Z",
                },
            )
        if request.url.path == "/v1/agents/me/metrics" and request.method == "POST":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/agents/me/heartbeat" and request.method == "POST":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/agents/me/commands" and request.method == "GET":
            return httpx.Response(204)
        return httpx.Response(404, json={"error": "not_found"})


def test_activate_calls_correct_path_and_method() -> None:
    rec = _Recorder()
    transport = httpx.MockTransport(rec.handler)

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        c._client = httpx.AsyncClient(transport=transport)
        try:
            r = await c.activate("XYZ-9999")
            assert r["agent_id"] == 42
            assert r["api_key"] == "zf_ak_real"
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())

    method, path, query, body, _ = rec.calls[0]
    assert method == "POST"
    assert path == "/v1/agents/activate"
    assert body == {"activation_code": "XYZ-9999"}


def test_send_metric_uses_api_key_and_correct_method() -> None:
    rec = _Recorder()
    transport = httpx.MockTransport(rec.handler)
    save_config({"activation": {"api_key": "zf_ak_local"}})

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        c._client = httpx.AsyncClient(transport=transport)
        try:
            await c.send_metric({"people": 7, "queue_status": "HIGH"})
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())

    method, path, _, body, headers = rec.calls[0]
    assert method == "POST"
    assert path == "/v1/agents/me/metrics"
    assert headers.get("x-agent-key") == "zf_ak_local"
    assert body == {"people": 7, "queue_status": "HIGH"}


def test_send_heartbeat_is_post() -> None:
    rec = _Recorder()
    transport = httpx.MockTransport(rec.handler)
    save_config({"activation": {"api_key": "zf_ak_local"}})

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        c._client = httpx.AsyncClient(transport=transport)
        try:
            await c.send_heartbeat({"ts": "now", "version": "0.1.0"})
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())

    method, path, _, _, _ = rec.calls[0]
    assert method == "POST"
    assert path == "/v1/agents/me/heartbeat"


def test_poll_commands_uses_get_with_wait_param() -> None:
    rec = _Recorder()
    transport = httpx.MockTransport(rec.handler)
    save_config({"activation": {"api_key": "zf_ak_local"}})

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        c._client = httpx.AsyncClient(transport=transport)
        try:
            cmds = await c.poll_commands(wait_seconds=10)
            assert cmds == []
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())

    method, path, query, _, headers = rec.calls[0]
    assert method == "GET"
    assert path == "/v1/agents/me/commands"
    query_str = query.decode() if isinstance(query, (bytes, bytearray)) else query
    assert "wait=10" in query_str
    assert headers.get("x-agent-key") == "zf_ak_local"


def test_send_metric_raises_on_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "api_key_invalid"})

    transport = httpx.MockTransport(handler)
    save_config({"activation": {"api_key": "bad"}})

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        c._client = httpx.AsyncClient(transport=transport)
        try:
            with pytest.raises(BackendAuthError):
                await c.send_metric({"people": 0})
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())


def test_send_metric_raises_on_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": "rate_limited"})

    transport = httpx.MockTransport(handler)
    save_config({"activation": {"api_key": "ok"}})

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        c._client = httpx.AsyncClient(transport=transport)
        try:
            with pytest.raises(BackendRateLimited) as exc:
                await c.send_metric({"people": 0})
            assert exc.value.retry_after == 7
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())


def test_send_metric_without_api_key_raises() -> None:
    save_config({})

    async def run() -> None:
        c = BackendClient(base_url="https://api.example.com", mock=False)
        try:
            with pytest.raises(BackendAuthError):
                await c.send_metric({"people": 0})
        finally:
            await c.aclose()

    import asyncio

    asyncio.run(run())
