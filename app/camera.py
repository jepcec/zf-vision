from __future__ import annotations

import logging
import time
from typing import Iterator

import cv2

from app.schemas import UsbCameraInfo

log = logging.getLogger(__name__)

USB_PROBE_MAX = 4
JPEG_QUALITY = 75
PREVIEW_FPS_CAP = 15.0


def list_usb_cameras(max_index: int = USB_PROBE_MAX) -> list[UsbCameraInfo]:
    """Prueba ``cv2.VideoCapture(0..max_index)`` y devuelve las que abren.

    Cierra cada captura inmediatamente — solo queremos saber si están ahí.
    """
    found: list[UsbCameraInfo] = []
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            continue
        ok, _ = cap.read()
        if not ok:
            cap.release()
            continue
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
        cap.release()
        found.append(UsbCameraInfo(index=i, width=w, height=h, fps=fps))
    return found


def open_source(kind: str, index: int | None, source_uri: str | None) -> cv2.VideoCapture:
    """Abre una cámara USB por índice o una URL RTSP. Lanza RuntimeError si falla."""
    if kind == "usb":
        if index is None:
            raise RuntimeError("Falta el índice de la cámara USB")
        cap = cv2.VideoCapture(index)
    elif kind == "rtsp":
        if not source_uri:
            raise RuntimeError("Falta la URL RTSP")
        cap = cv2.VideoCapture(source_uri)
    else:
        raise RuntimeError(f"Tipo de cámara no soportado: {kind}")

    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir la cámara")
    return cap


def test_source(kind: str, index: int | None, source_uri: str | None,
                timeout_s: float = 5.0) -> bool:
    """Abre la fuente, intenta leer un frame en ``timeout_s`` segundos, y cierra."""
    cap = None
    try:
        cap = open_source(kind, index, source_uri)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            ok, _ = cap.read()
            if ok:
                return True
            time.sleep(0.1)
        return False
    except RuntimeError:
        return False
    finally:
        if cap is not None:
            cap.release()


def mjpeg_frames(cap: cv2.VideoCapture, fps_cap: float = PREVIEW_FPS_CAP) -> Iterator[bytes]:
    """Generador que produce frames JPEG como un stream MJPEG.

    El caller es responsable de cerrar ``cap`` cuando termine.
    """
    delay = 1.0 / max(1.0, fps_cap)
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(delay)
            continue
        ok, buf = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            time.sleep(delay)
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(buf)).encode() + b"\r\n\r\n"
            + buf.tobytes() + b"\r\n"
        )
        time.sleep(delay)
