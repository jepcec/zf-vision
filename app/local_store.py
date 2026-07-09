from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from app.paths import config_file


def empty_config() -> dict[str, Any]:
    return {
        "activation": None,
        "camera": None,
        "roi": None,
    }


def load_config() -> dict[str, Any]:
    """Carga la config local. Si el archivo no existe, devuelve un dict con
    todas las claves en None (nunca falla)."""
    cfg = empty_config()
    path = config_file()
    if not path.exists():
        return cfg
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for key in cfg:
        if key in data:
            cfg[key] = data[key]
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    """Persiste la config local en YAML. Aplica chmod 600 en Linux/macOS."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(empty_config())
    payload.update(cfg or {})
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def reset_config() -> None:
    path = config_file()
    if path.exists():
        path.unlink()


# ── helpers de paso ─────────────────────────────────────────────────

def current_step(cfg: dict[str, Any] | None = None) -> str:
    """Devuelve el paso actual del flujo: activation | camera | roi | done."""
    cfg = cfg if cfg is not None else load_config()
    if not cfg.get("activation"):
        return "activation"
    if not cfg.get("camera"):
        return "camera"
    if not cfg.get("roi") or not (cfg["roi"] or {}).get("polygons"):
        return "roi"
    return "done"


def has_api_key(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg if cfg is not None else load_config()
    return bool((cfg.get("activation") or {}).get("api_key"))
