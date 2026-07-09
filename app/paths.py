from __future__ import annotations

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    """Directorio de configuración del agente.

    - Windows: %APPDATA%/zf-vision/
    - Linux/macOS: $XDG_CONFIG_HOME/zf-vision/ o ~/.config/zf-vision/
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "zf-vision"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) / "zf-vision" if xdg else Path.home() / ".config" / "zf-vision"
    base.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            os.chmod(base, 0o700)
        except OSError:
            pass
    return base


def config_file() -> Path:
    return config_dir() / "config.yaml"


def web_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "web"
