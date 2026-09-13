# -*- coding: utf-8 -*-
"""Manual "run now" semantics for information schedules.

Guards two regressions behind the "点了没反应" report:
1. a wait-budget timeout was recorded as ``failed`` with an empty error;
2. the per-window idempotency key swallowed manual clicks, so no new run started.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from domain.information_sources import run_service, run_store
from domain.information_sources.scheduler import InformationScheduler, ScheduleStore


def _make_scheduler(tmpdir: str) -> tuple[InformationScheduler, str]:
    store = ScheduleStore(path=Path(tmpdir) / "schedules.json")
    item = store.create({"name": "t", "team_id": "open_weights", "interval_minutes": 30})
    return InformationScheduler(store=store), item.schedule_id


def _run(run_id: str, status: str) -> run_store.InformationRun:
    return run_store.InformationRun(run_id=run_id, team_id="open_weights", status=status)


@pytest.mark.asyncio
async def test_wait_timeout_is_not_reported_as_failure(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        scheduler, schedule_id = _make_scheduler(tmpdir)
        pending = _run("r1", "fetching")

        async def fake_enqueue(**kwargs):
            return pending

        async def fake_wait(run_id, **kwargs):
            return pending  # still in flight when the wait budget runs out

        monkeypatch.setattr(run_service, "enqueue_run_async", fake_enqueue)
        monkeypatch.setattr(run_service, "wait_for_run", fake_wait)

        result = await scheduler.run_once(schedule_id)

        assert result["pending"] is True
        assert result["ok"] is True
        assert scheduler.store.get(schedule_id).last_status == "running"


@pytest.mark.asyncio
async def test_force_starts_a_new_run_when_the_window_run_already_settled(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        scheduler, schedule_id = _make_scheduler(tmpdir)
        seen_keys = []

        async def fake_enqueue(**kwargs):
            seen_keys.append(kwargs.get("idempotency_key"))
            return _run("r2", "completed")

        async def fake_wait(run_id, **kwargs):
            return _run("r2", "completed")

        class _Repo:
            def get_by_idempotency(self, key):
                return _run("r1", "degraded")  # previous window run already finished

        monkeypatch.setattr(run_service, "enqueue_run_async", fake_enqueue)
        monkeypatch.setattr(run_service, "wait_for_run", fake_wait)
        monkeypatch.setattr(run_store, "get_run_repository", lambda: _Repo())

        await scheduler.run_once(schedule_id, force=True)
        await scheduler.run_once(schedule_id)

        assert seen_keys[0] == ""  # manual click bypasses the window key
        assert seen_keys[1]  # the timer keeps it
