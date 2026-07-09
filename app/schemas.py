from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── Activation ──────────────────────────────────────────────────────

class ActivationRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)


class ActivationResponse(BaseModel):
    agent_id: int
    api_key: str
    entity_id: int
    entity_name: str
    activated_at: str


# ── Camera ──────────────────────────────────────────────────────────

class UsbCameraInfo(BaseModel):
    index: int
    width: int
    height: int
    fps: float


class CameraPickRequest(BaseModel):
    kind: Literal["usb", "rtsp"]
    index: int | None = None
    source_uri: str | None = None


# ── ROI ─────────────────────────────────────────────────────────────

class Point(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class RoiPayload(BaseModel):
    polygons: list[list[Point]]
