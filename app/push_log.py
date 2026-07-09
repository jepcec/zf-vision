from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class PushEvent:
    id: int
    ts: str
    method: str
    path: str
    body: str
    status: int | None
    duration_ms: int | None
    note: str
    mode: str

    def to_json(self) -> dict:
        return asdict(self)


class PushLog:
    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[PushEvent] = deque(maxlen=max_events)
        self._next_id = 1

    def record_request(self, method: str, path: str, body: str, mode: str) -> int:
        eid = self._next_id
        self._next_id += 1
        self._events.append(
            PushEvent(
                id=eid,
                ts=datetime.now(timezone.utc).isoformat(),
                method=method,
                path=path,
                body=body,
                status=None,
                duration_ms=None,
                note="pending",
                mode=mode,
            )
        )
        return eid

    def record_response(
        self,
        eid: int,
        status: int | None,
        duration_ms: int,
        note: str,
    ) -> None:
        for ev in self._events:
            if ev.id == eid:
                ev.status = status
                ev.duration_ms = duration_ms
                ev.note = note
                return

    def all(self) -> list[dict]:
        return [e.to_json() for e in reversed(self._events)]

    def counts(self) -> dict[str, int]:
        c: Counter[str] = Counter()
        completed = 0
        errors = 0
        for ev in self._events:
            if ev.note == "pending":
                continue
            completed += 1
            bucket = _bucket_for(ev.path)
            if bucket:
                c[bucket] += 1
            if ev.note not in ("ok", "MOCK"):
                errors += 1
        return {
            "total": completed,
            "by_path": dict(c),
            "errors": errors,
        }

    def clear(self) -> None:
        self._events.clear()
        self._next_id = 1


def _bucket_for(path: str) -> str | None:
    if "/activate" in path:
        return "activate"
    if "/heartbeat" in path:
        return "heartbeat"
    if "/metrics" in path:
        return "metrics"
    if "/commands" in path:
        return "commands"
    return None
