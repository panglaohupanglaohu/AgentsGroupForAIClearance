# -*- coding: utf-8 -*-
"""P9 — File-backed run queue with lease claim / heartbeat."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol, runtime_checkable

from .run_store import (
    FileRunRepository,
    InformationRun,
    get_run_repository,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).replace(microsecond=0).isoformat()


def _parse(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@runtime_checkable
class RunQueue(Protocol):
    async def enqueue(self, run_id: str) -> None: ...
    async def claim(self, worker_id: str, lease_seconds: int = 120) -> Optional[InformationRun]: ...
    async def heartbeat(self, run_id: str, worker_id: str, lease_seconds: int = 120) -> None: ...
    async def complete(self, run_id: str, worker_id: str) -> None: ...
    async def release(self, run_id: str, worker_id: str) -> None: ...


class FileRunQueue:
    """Queue semantics on top of FileRunRepository statuses + leases."""

    def __init__(self, repo: Optional[FileRunRepository] = None) -> None:
        self.repo = repo or get_run_repository()

    async def enqueue(self, run_id: str) -> None:
        run = self.repo.get(run_id)
        if not run:
            raise KeyError(run_id)
        if run.status in ("completed", "failed", "cancelled"):
            return
        if run.status != "queued":
            # allow re-queue only if lease expired while active
            lease = _parse(run.lease_until)
            if lease and lease > _utc_now():
                return
        self.repo.update(run_id, status="queued", worker_id="", lease_until="")

    async def claim(self, worker_id: str, lease_seconds: int = 120) -> Optional[InformationRun]:
        now = _utc_now()
        candidates = self.repo.list_recent(300)
        # Prefer pure queued; then expired leases mid-flight
        ordered = sorted(
            candidates,
            key=lambda r: (0 if r.status == "queued" else 1, r.created_at),
        )
        for run in ordered:
            if run.status in ("completed", "failed", "cancelled", "degraded"):
                continue
            if run.status == "queued" or self._lease_expired(run, now):
                lease_until = _iso(now + timedelta(seconds=lease_seconds))
                updated = self.repo.update(
                    run.run_id,
                    status="fetching" if run.status == "queued" else run.status,
                    worker_id=worker_id,
                    lease_until=lease_until,
                    started_at=run.started_at or _iso(now),
                )
                if updated and updated.worker_id == worker_id:
                    logger.info("worker %s claimed run %s", worker_id, run.run_id)
                    return updated
        return None

    def _lease_expired(self, run: InformationRun, now: datetime) -> bool:
        if run.status == "queued":
            return True
        if not run.worker_id:
            return run.status not in ("completed", "failed", "cancelled")
        lease = _parse(run.lease_until)
        return lease is None or lease <= now

    async def heartbeat(self, run_id: str, worker_id: str, lease_seconds: int = 120) -> None:
        run = self.repo.get(run_id)
        if not run or run.worker_id != worker_id:
            return
        self.repo.update(
            run_id,
            lease_until=_iso(_utc_now() + timedelta(seconds=lease_seconds)),
        )

    async def complete(self, run_id: str, worker_id: str) -> None:
        run = self.repo.get(run_id)
        if not run or (run.worker_id and run.worker_id != worker_id):
            return
        self.repo.update(run_id, worker_id="", lease_until="")

    async def release(self, run_id: str, worker_id: str) -> None:
        run = self.repo.get(run_id)
        if not run or run.worker_id != worker_id:
            return
        if run.status not in ("completed", "failed", "cancelled", "degraded"):
            self.repo.update(run_id, status="queued", worker_id="", lease_until="")


_queue: Optional[FileRunQueue] = None


def get_run_queue() -> FileRunQueue:
    global _queue
    if _queue is None:
        _queue = FileRunQueue()
    return _queue


def reset_run_queue_for_tests(queue: Optional[FileRunQueue] = None) -> None:
    global _queue
    _queue = queue


def new_worker_id() -> str:
    return f"w-{uuid.uuid4().hex[:8]}"
