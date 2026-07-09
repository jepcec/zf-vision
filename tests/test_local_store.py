from __future__ import annotations

from app.local_store import (
    current_step,
    empty_config,
    has_api_key,
    load_config,
    reset_config,
    save_config,
)


def test_load_empty_when_no_file() -> None:
    cfg = load_config()
    assert cfg == empty_config()
    assert current_step(cfg) == "activation"
    assert has_api_key(cfg) is False


def test_save_and_load_roundtrip() -> None:
    cfg = empty_config()
    cfg["activation"] = {
        "agent_id": 1,
        "api_key": "zf_ak_test",
        "entity_id": 9,
        "entity_name": "Test",
        "activated_at": "2026-01-01T00:00:00Z",
    }
    save_config(cfg)

    loaded = load_config()
    assert loaded["activation"]["api_key"] == "zf_ak_test"
    assert current_step(loaded) == "camera"


def test_current_step_progression() -> None:
    cfg = empty_config()
    assert current_step(cfg) == "activation"

    cfg["activation"] = {"api_key": "x"}
    assert current_step(cfg) == "camera"

    cfg["camera"] = {"kind": "usb", "index": 0}
    assert current_step(cfg) == "roi"

    cfg["roi"] = {"polygons": [[{"x": 0, "y": 0}, {"x": 0.5, "y": 0}, {"x": 0.5, "y": 0.5}]]}
    assert current_step(cfg) == "done"


def test_reset_clears_file() -> None:
    save_config({"activation": {"api_key": "x"}})
    assert load_config()["activation"] is not None
    reset_config()
    assert load_config() == empty_config()
