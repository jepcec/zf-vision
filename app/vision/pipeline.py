from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

log = logging.getLogger(__name__)

CLASS_PERSON = 0
CONF_THRESHOLD = 0.45
NMS_THRESHOLD = 0.45
FRAME_SKIP = 2
EMA_ALPHA = 0.4
INFER_WIDTH = 640
INFER_HEIGHT = 640
DEFAULT_THRESHOLDS = {"free": 0, "low": 3, "medium": 8}

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "yolov8n.onnx"


@dataclass
class CountResult:
    people: int
    queue_status: str
    fps: float
    polygons_used: int
    model_loaded: bool
    last_infer_ms: float
    last_jpeg: bytes | None = None


class QueuePipeline:
    """Pipeline de visión: cámara + YOLOv8n (ONNX) + filtro ROI.

    - Corre en un thread dedicado (no bloquea el event loop de FastAPI).
    - ``count()`` devuelve el último ``CountResult`` cacheado, sin esperar.
    - Suavizado exponencial (EMA) sobre el conteo para evitar parpadeo.
    - Sin tracking en este slice: el conteo es por-frame con EMA. Suficiente
      para validar el loop end-to-end. Tracking se agrega cuando haga falta
      estabilidad extra (e.g. recuentos cada 5s con personas estáticas).
    """

    def __init__(
        self,
        source: Callable[[], cv2.VideoCapture] | None = None,
        roi_provider: Callable[[], list[list[tuple[float, float]]]] | None = None,
        model_path: Path | None = None,
    ) -> None:
        self._source_factory = source
        self._roi_provider = roi_provider
        self._model_path = model_path or MODEL_PATH
        self._latest = CountResult(0, "FREE", 0.0, 0, False, 0.0)
        self._net: cv2.dnn.Net | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None
        self._cap_lock = threading.Lock()
        self._thresholds = DEFAULT_THRESHOLDS

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="zf-pipeline", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.is_running():
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
        self._latest = CountResult(0, "FREE", 0.0, 0, self._net is not None, 0.0)
        log.info("pipeline: detenido")

    def set_thresholds(self, free: int, low: int, medium: int) -> None:
        self._thresholds = {"free": free, "low": low, "medium": medium}

    def count(self) -> CountResult:
        return self._latest

    def _run(self) -> None:
        try:
            if not self._model_path.exists():
                log.error("pipeline: modelo no encontrado en %s", self._model_path)
                return
            self._net = cv2.dnn.readNetFromONNX(str(self._model_path))
            self._latest = CountResult(
                0, "FREE", 0.0, 0, True, 0.0, self._latest.last_jpeg
            )
            log.info("pipeline: modelo ONNX cargado (%s)", self._model_path.name)
        except Exception as e:
            log.error("pipeline: no se pudo cargar el modelo: %s", e)
            return

        ema: float | None = None
        last_t = time.monotonic()
        frames = 0

        while not self._stop.is_set():
            cap = self._get_cap()
            if cap is None:
                time.sleep(1.0)
                continue

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            enc_ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if enc_ok:
                self._latest.last_jpeg = buf.tobytes()

            frames += 1
            if frames % FRAME_SKIP != 0:
                continue

            rois = (self._roi_provider or (lambda: []))()
            t0 = time.monotonic()
            count_raw = self._count_in_rois(frame, rois)
            infer_ms = (time.monotonic() - t0) * 1000.0

            ema = float(count_raw) if ema is None else EMA_ALPHA * count_raw + (1 - EMA_ALPHA) * ema
            people = int(round(ema))
            now = time.monotonic()
            fps = 1.0 / max(1e-6, now - last_t)
            last_t = now
            status = self._classify(people)
            self._latest = CountResult(people, status, fps, len(rois), True, infer_ms)

    def _get_cap(self) -> cv2.VideoCapture | None:
        with self._cap_lock:
            if self._cap is not None and self._cap.isOpened():
                return self._cap
            if self._source_factory is None:
                return None
            try:
                if self._cap is not None:
                    self._cap.release()
                self._cap = self._source_factory()
                return self._cap
            except Exception as e:
                log.warning("pipeline: no se pudo abrir cámara: %s", e)
                self._cap = None
                return None

    def _count_in_rois(
        self, frame: np.ndarray, rois: list[list[tuple[float, float]]]
    ) -> int:
        if self._net is None:
            return 0
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1 / 255.0, (INFER_WIDTH, INFER_HEIGHT), swapRB=True, crop=False
        )
        self._net.setInput(blob)
        out = self._net.forward()
        # yolov5/v8 raw output: (1, N, 85) → xywh, obj_conf, class_scores
        preds = out[0]
        if preds.ndim == 3:
            preds = preds[0]

        boxes: list[tuple[int, int, int, int, float]] = []
        for det in preds:
            obj_conf = float(det[4])
            if obj_conf < CONF_THRESHOLD:
                continue
            class_scores = det[5:]
            class_id = int(np.argmax(class_scores))
            class_score = float(class_scores[class_id])
            if class_id != CLASS_PERSON or class_score < CONF_THRESHOLD:
                continue
            cx, cy, bw, bh = det[0], det[1], det[2], det[3]
            x1 = int((cx - bw / 2) * w / INFER_WIDTH)
            y1 = int((cy - bh / 2) * h / INFER_HEIGHT)
            x2 = int((cx + bw / 2) * w / INFER_WIDTH)
            y2 = int((cy + bh / 2) * h / INFER_HEIGHT)
            boxes.append((x1, y1, x2, y2, obj_conf * class_score))

        if not boxes:
            return 0

        xyxy = np.array([(b[0], b[1], b[2], b[3]) for b in boxes], dtype=np.int32)
        scores = np.array([b[4] for b in boxes], dtype=np.float32)
        idxs = cv2.dnn.NMSBoxes(xyxy.tolist(), scores.tolist(), CONF_THRESHOLD, NMS_THRESHOLD)
        if len(idxs) == 0:
            return 0
        if isinstance(idxs, tuple):
            idxs = idxs[0]
        idxs = idxs.flatten()

        count = 0
        for i in idxs:
            x1, y1, x2, y2, _ = boxes[i]
            cx_n = (x1 + x2) / 2.0 / w
            cy_n = (y1 + y2) / 2.0 / h
            if any(_point_in_polygon(cx_n, cy_n, poly) for poly in rois):
                count += 1
        return count

    def _classify(self, people: int) -> str:
        t = self._thresholds
        if people <= t["free"]:
            return "FREE"
        if people <= t["low"]:
            return "LOW"
        if people <= t["medium"]:
            return "MEDIUM"
        return "HIGH"


def _point_in_polygon(
    x: float, y: float, poly: list[tuple[float, float]]
) -> bool:
    """Ray casting clásico. poly en coords normalizadas [0..1]."""
    if len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside
