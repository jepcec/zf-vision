from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.local_store import load_config
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def test_status_renders_activation_when_no_config(client: TestClient) -> None:
    r = client.get("/status")
    assert r.status_code == 200
    assert "Activá tu agente" in r.text


def test_activation_persists_config_and_redirects(client: TestClient) -> None:
    r = client.post("/activation", data={"code": "ABCD-1234"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/cameras"

    cfg = load_config()
    assert cfg["activation"] is not None
    assert cfg["activation"]["api_key"].startswith("zf_ak_")
    assert cfg["activation"]["entity_name"] == "Banco de la Nación"


def test_short_code_is_rejected(client: TestClient) -> None:
    r = client.post("/activation", data={"code": "AB"})
    assert r.status_code == 400
    assert "al menos 4" in r.text
    assert load_config()["activation"] is None


def test_status_advances_through_steps(client: TestClient) -> None:
    assert client.get("/api/local/status").json()["state"] == "activation"

    client.post("/activation", data={"code": "ABCD-1234"})
    assert client.get("/api/local/status").json()["state"] == "camera"


def test_reset_returns_to_activation(client: TestClient) -> None:
    client.post("/activation", data={"code": "ABCD-1234"})
    r = client.post("/reset", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/activation"
    assert load_config()["activation"] is None


def test_get_aliases_redirect_to_status(client: TestClient) -> None:
    for path in ("/activation", "/cameras", "/roi"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"] == "/status", path
