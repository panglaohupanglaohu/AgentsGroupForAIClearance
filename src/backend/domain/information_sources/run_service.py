# -*- coding: utf-8 -*-
"""P9 — Enqueue information runs (manual / schedule) with idempotency."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .run_queue import get_run_queue
from .run_store import (
    InformationRun,
    floor_window,
    get_event_repository,
    get_run_repository,
)
from .worker import get_information_worker, start_information_worker


def _iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_worker_running() -> None:
    start_information_worker()


def create_and_enqueue_run(
    *,
    team_id: str,
    source_ids: Optional[List[str]] = None,
    trigger: str = "manual",
    schedule_id: str = "",
    idempotency_key: str = "",
    input_snapshot: Optional[Dict[str, Any]] = None,
) -> InformationRun:
    """Create a queued run (or return existing idempotent one) and wake the queue."""
    ensure_worker_running()
    repo = get_run_repository()
    queue = get_run_queue()

    if idempotency_key:
        existing = repo.get_by_idempotency(idempotency_key)
        if existing:
            return existing

    run_id = str(uuid.uuid4())[:12]
    snapshot = dict(input_snapshot or {})
    snapshot.setdefault("team_id", team_id)
    snapshot.setdefault("source_ids", list(source_ids or []))
    snapshot.setdefault("trigger", trigger)
    snapshot.setdefault("schema_version", 1)
    snapshot.setdefault("as_of", _iso())
    if schedule_id:
        snapshot["schedule_id"] = schedule_id

    run = InformationRun(
        run_id=run_id,
        team_id=team_id,
        status="queued",
        source_ids=list(source_ids or []),
        trigger=trigger,
        schedule_id=schedule_id or "",
        idempotency_key=idempotency_key or "",
        input_snapshot=snapshot,
    )
    created = repo.create(run)
    # If create returned an idempotent existing run, do not force re-queue completed ones
    if created.run_id != run_id:
        return created

    # Synchronous queue mark (FileRunQueue.enqueue is status-only)
    repo.update(created.run_id, status="queued", worker_id="", lease_until="")
    return created


async def enqueue_run_async(
    *,
    team_id: str,
    source_ids: Optional[List[str]] = None,
    trigger: str = "manual",
    schedule_id: str = "",
    idempotency_key: str = "",
    input_snapshot: Optional[Dict[str, Any]] = None,
) -> InformationRun:
    repo = get_run_repository()
    queue = get_run_queue()

    if idempotency_key:
        existing = repo.get_by_idempotency(idempotency_key)
        if existing:
            ensure_worker_running()
            return existing

    run_id = str(uuid.uuid4())[:12]
    snapshot = dict(input_snapshot or {})
    snapshot.setdefault("team_id", team_id)
    snapshot.setdefault("source_ids", list(source_ids or []))
    snapshot.setdefault("trigger", trigger)
    snapshot.setdefault("schema_version", 1)
    snapshot.setdefault("as_of", _iso())
    if schedule_id:
        snapshot["schedule_id"] = schedule_id

    run = InformationRun(
        run_id=run_id,
        team_id=team_id,
        status="queued",
        source_ids=list(source_ids or []),
        trigger=trigger,
        schedule_id=schedule_id or "",
        idempotency_key=idempotency_key or "",
        input_snapshot=snapshot,
    )
    created = repo.create(run)
    if created.run_id == run_id:
        await queue.enqueue(created.run_id)
    ensure_worker_running()
    return created


async def wait_for_run(run_id: str, *, timeout: float = 120.0, poll: float = 0.25) -> InformationRun:
    repo = get_run_repository()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        run = repo.get(run_id)
        if not run:
            raise KeyError(run_id)
        if run.status in ("completed", "failed", "cancelled", "degraded"):
            return run
        await asyncio.sleep(poll)
    run = repo.get(run_id)
    if not run:
        raise KeyError(run_id)
    return run


def schedule_idempotency_key(schedule_id: str, interval_minutes: int = 30) -> str:
    return f"{schedule_id}:{floor_window(minutes=interval_minutes)}"


def get_run(run_id: str) -> Optional[InformationRun]:
    return get_run_repository().get(run_id)


def list_events(run_id: str, after_seq: int = 0):
    return get_event_repository().list_after(run_id, after_seq)
