"""Append-only, per-job observable event log."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import EVENTS_PATH, JOBS_PATH

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class EventStore:
    def __init__(self, path: Path = EVENTS_PATH, jobs_path: Path = JOBS_PATH):
        self.path, self.jobs_path = path, jobs_path

    def append(self, job_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        prior = list(self.read(job_id))
        event = {"event_id": str(uuid.uuid4()), "job_id": job_id, "seq": len(prior) + 1,
                 "schema_version": SCHEMA_VERSION, "at": _now(), "kind": kind, "payload": payload}
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        return event

    def read(self, job_id: str | None = None) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return iter(())
        def records() -> Iterator[dict[str, Any]]:
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if job_id is None or value.get("job_id") == job_id:
                    yield value
        return records()

    def read_since(self, event_id: str | None = None) -> Iterator[dict[str, Any]]:
        """Yield the complete log, or the records written after ``event_id``.

        Event ids are opaque UUIDs, so a client can reconnect without depending
        on the per-job sequence counter.
        """
        records = list(self.read())
        if event_id is None:
            return iter(records)
        for index, event in enumerate(records):
            if event.get("event_id") == event_id:
                return iter(records[index + 1:])
        return iter(records)

    def save_job(self, job: dict[str, Any]) -> Path:
        self.jobs_path.mkdir(parents=True, exist_ok=True)
        path = self.jobs_path / f"{job['job_id']}.json"
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load_job(self, job_id: str) -> dict[str, Any] | None:
        path = self.jobs_path / f"{job_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
