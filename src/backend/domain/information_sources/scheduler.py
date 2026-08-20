# -*- coding: utf-8 -*-
"""Source-agnostic batch scheduler.

Depends only on SourceRegistry + SourceConnector protocol. A single source
failure must not abort other sources in the same batch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .models import FetchBatch, SourceConfig
from .protocol import SourceRegistry, get_source_registry

logger = logging.getLogger(__name__)

ACTIVE_SCHEDULE_TEAMS = frozenset({"ai_news_60s", "dufu_world_intel", "open_weights"})
DEFAULT_SCHEDULE_INTERVAL_MINUTES = 30
_SCHEDULE_PATH = Path(__file__).resolve().parents[4] / "storage" / "information_sources" / "schedules.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).isoformat()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass
class ScheduleConfig:
    """Persistent periodic pipeline task shown in the data workbench."""

    schedule_id: str
    name: str
    team_id: str
    interval_minutes: int = DEFAULT_SCHEDULE_INTERVAL_MINUTES
    enabled: bool = True
    source_ids: List[str] = field(default_factory=list)
    run_immediately: bool = False
    next_run_at: str = ""
    last_run_at: str = ""
    last_status: str = "never"
    last_error: str = ""
    run_count: int = 0
    created_at: str = field(default_factory=_iso)
    updated_at: str = field(default_factory=_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{key: value for key, value in data.items() if key in known})


class ScheduleStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _SCHEDULE_PATH

    def _load(self) -> List[ScheduleConfig]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [ScheduleConfig.from_dict(item) for item in data.get("schedules", [])]
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Unable to load information schedules: %s", exc)
            return []

    def _save(self, schedules: List[ScheduleConfig]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps({"schedules": [item.to_dict() for item in schedules]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def list(self) -> List[ScheduleConfig]:
        return self._load()

    def get(self, schedule_id: str) -> Optional[ScheduleConfig]:
        return next((item for item in self._load() if item.schedule_id == schedule_id), None)

    def create(self, data: Dict[str, Any]) -> ScheduleConfig:
        schedules = self._load()
        now = _now()
        interval = int(data.get("interval_minutes", DEFAULT_SCHEDULE_INTERVAL_MINUTES))
        immediate = bool(data.get("run_immediately", False))
        item = ScheduleConfig(
            schedule_id=str(data.get("schedule_id") or uuid.uuid4().hex[:12]),
            name=str(data.get("name") or "未命名定时任务"),
            team_id=str(data["team_id"]),
            interval_minutes=interval,
            enabled=bool(data.get("enabled", True)),
            source_ids=[str(value) for value in data.get("source_ids") or []],
            run_immediately=immediate,
            next_run_at=_iso(now if immediate else now + timedelta(minutes=interval)),
            created_at=_iso(now),
            updated_at=_iso(now),
        )
        schedules.append(item)
        self._save(schedules)
        return item

    def update(self, schedule_id: str, patch: Dict[str, Any]) -> Optional[ScheduleConfig]:
        schedules = self._load()
        for index, item in enumerate(schedules):
            if item.schedule_id != schedule_id:
                continue
            merged = item.to_dict()
            merged.update({key: value for key, value in patch.items() if value is not None})
            merged["schedule_id"] = schedule_id
            merged["interval_minutes"] = int(merged.get("interval_minutes", item.interval_minutes))
            merged["source_ids"] = [str(value) for value in merged.get("source_ids") or []]
            merged["updated_at"] = _iso()
            if "interval_minutes" in patch and "next_run_at" not in patch:
                merged["next_run_at"] = _iso(_now() + timedelta(minutes=merged["interval_minutes"]))
            updated = ScheduleConfig.from_dict(merged)
            schedules[index] = updated
            self._save(schedules)
            return updated
        return None

    def delete(self, schedule_id: str) -> bool:
        schedules = self._load()
        remaining = [item for item in schedules if item.schedule_id != schedule_id]
        if len(remaining) == len(schedules):
            return False
        self._save(remaining)
        return True


PipelineRunner = Callable[..., Awaitable[Dict[str, Any]]]


class InformationScheduler:
    """Small in-process scheduler; persistence makes tasks survive restarts."""

    def __init__(self, store: Optional[ScheduleStore] = None, runner: Optional[PipelineRunner] = None):
        self.store = store or ScheduleStore()
        self.runner = runner
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="stockagents-information-scheduler")

    async def stop(self) -> None:
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def list(self) -> List[ScheduleConfig]:
        return self.store.list()

    async def run_once(self, schedule_id: str) -> Dict[str, Any]:
        """Enqueue a background run (idempotent per schedule window).

        If a custom ``runner`` is injected (tests), keep the synchronous path
        for deterministic unit tests.
        """
        item = self.store.get(schedule_id)
        if item is None:
            raise KeyError(schedule_id)
        self.store.update(schedule_id, {"last_status": "running", "last_error": ""})
        try:
            if self.runner is not None:
                from .source_store import get_source_config_store

                source_store = get_source_config_store()
                sources = [source_store.get(source_id) for source_id in item.source_ids]
                sources = [source for source in sources if source is not None]
                result = await self.runner(item.team_id, sources=sources or None)
                next_at = _now() + timedelta(minutes=item.interval_minutes)
                self.store.update(
                    schedule_id,
                    {
                        "last_run_at": _iso(),
                        "last_status": "success",
                        "last_error": "",
                        "run_count": item.run_count + 1,
                        "next_run_at": _iso(next_at),
                    },
                )
                return {"ok": True, "schedule_id": schedule_id, "result": result}

            from .run_service import enqueue_run_async, schedule_idempotency_key, wait_for_run

            key = schedule_idempotency_key(schedule_id, item.interval_minutes)
            run = await enqueue_run_async(
                team_id=item.team_id,
                source_ids=list(item.source_ids or []),
                trigger="schedule",
                schedule_id=schedule_id,
                idempotency_key=key,
                input_snapshot={
                    "schedule_id": schedule_id,
                    "interval_minutes": item.interval_minutes,
                    "name": item.name,
                },
            )
            # Short wait so schedule UI still sees success/failure without blocking minutes
            finished = await wait_for_run(run.run_id, timeout=90.0, poll=0.3)
            next_at = _now() + timedelta(minutes=item.interval_minutes)
            ok = finished.status in ("completed", "degraded")
            self.store.update(
                schedule_id,
                {
                    "last_run_at": _iso(),
                    "last_status": "success" if ok else "failed",
                    "last_error": finished.error if not ok else "",
                    "run_count": item.run_count + 1,
                    "next_run_at": _iso(next_at),
                },
            )
            return {
                "ok": ok,
                "schedule_id": schedule_id,
                "run_id": finished.run_id,
                "status": finished.status,
                "result": finished.result,
                "error": finished.error,
            }
        except Exception as exc:
            next_at = _now() + timedelta(minutes=item.interval_minutes)
            self.store.update(
                schedule_id,
                {
                    "last_run_at": _iso(),
                    "last_status": "failed",
                    "last_error": str(exc)[:500],
                    "run_count": item.run_count + 1,
                    "next_run_at": _iso(next_at),
                },
            )
            logger.warning("Information schedule %s failed: %s", schedule_id, exc)
            return {"ok": False, "schedule_id": schedule_id, "error": str(exc)}

    async def _loop(self) -> None:
        while not self._stopping:
            now = _now()
            for item in self.store.list():
                due = item.enabled and (_parse(item.next_run_at) or now) <= now
                if due:
                    await self.run_once(item.schedule_id)
            await asyncio.sleep(15)


_scheduler: Optional[InformationScheduler] = None


def get_information_scheduler() -> InformationScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = InformationScheduler()
        # Give a fresh install one useful, safe fixture-backed task. Users can
        # pause or delete it from the workbench; no external key is required.
        if _scheduler.store.path == _SCHEDULE_PATH and not _scheduler.store.list():
            _scheduler.store.create(
                {
                    "name": "AI 60 秒每 30 分钟播报",
                    "team_id": "ai_news_60s",
                    "interval_minutes": DEFAULT_SCHEDULE_INTERVAL_MINUTES,
                    "enabled": True,
                }
            )
    return _scheduler


async def fetch_one(
    config: SourceConfig,
    *,
    since: Optional[datetime] = None,
    cursor: Optional[str] = None,
    registry: Optional[SourceRegistry] = None,
) -> FetchBatch:
    reg = registry or get_source_registry()
    if not config.enabled:
        return FetchBatch(
            source_id=config.source_id,
            items=[],
            errors=["source disabled"],
            partial=True,
            metadata={"skipped": True},
        )
    try:
        connector = reg.create(config.kind, config)
        return await connector.fetch(since=since, cursor=cursor, config=config)
    except Exception as exc:
        logger.warning("source %s failed: %s", config.source_id, exc)
        return FetchBatch(
            source_id=config.source_id,
            items=[],
            cursor=cursor,
            errors=[str(exc)],
            partial=True,
            metadata={"kind": config.kind, "failed": True},
        )


async def fetch_many(
    configs: List[SourceConfig],
    *,
    since: Optional[datetime] = None,
    cursors: Optional[Dict[str, str]] = None,
    registry: Optional[SourceRegistry] = None,
) -> List[FetchBatch]:
    """Fetch all sources concurrently; isolate failures per source."""
    cursors = cursors or {}
    tasks = [
        fetch_one(
            cfg,
            since=since,
            cursor=cursors.get(cfg.source_id),
            registry=registry,
        )
        for cfg in configs
    ]
    if not tasks:
        return []
    return list(await asyncio.gather(*tasks))
