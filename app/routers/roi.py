from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.local_store import load_config, save_config
from app.paths import web_dir

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(web_dir() / "templates"))


def _validate_polygons(raw: str) -> tuple[list[list[dict]] | None, str | None]:
    if not raw:
        return None, "No se enviaron polígonos."
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Formato de polígonos inválido."

    if not isinstance(data, list) or not data:
        return None, "Dibujá al menos un polígono."

    cleaned: list[list[dict]] = []
    for i, poly in enumerate(data):
        if not isinstance(poly, list) or len(poly) < 3:
            return None, f"El polígono {i + 1} necesita al menos 3 puntos."
        pts: list[dict] = []
        for j, pt in enumerate(poly):
            if not isinstance(pt, dict) or "x" not in pt or "y" not in pt:
                return None, f"Punto inválido en polígono {i + 1}, vértice {j + 1}."
            x, y = float(pt["x"]), float(pt["y"])
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return None, f"Coordenadas fuera de rango en polígono {i + 1}."
            pts.append({"x": round(x, 4), "y": round(y, 4)})
        if _polygon_area(pts) < 0.005:
            return None, f"El polígono {i + 1} es demasiado pequeño."
        cleaned.append(pts)
    return cleaned, None


def _polygon_area(pts: list[dict]) -> float:
    if len(pts) < 3:
        return 0.0
    s = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        s += pts[i]["x"] * pts[j]["y"] - pts[j]["x"] * pts[i]["y"]
    return abs(s) / 2.0


@router.post("/roi")
async def save_roi(
    request: Request,
    polygons: str = Form(...),
):
    cleaned, err = _validate_polygons(polygons)
    if err:
        return templates.TemplateResponse(
            request,
            "_step_roi.html",
            {"current_step": "roi", "error": err},
            status_code=400,
        )

    cfg = load_config()
    cfg["roi"] = {
        "polygons": cleaned,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_config(cfg)
    return RedirectResponse(url="/status", status_code=303)
