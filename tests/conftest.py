from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cada test usa un config dir temporal, para no tocar ~/.zf-vision."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path))
    yield tmp_path
