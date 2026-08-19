# -*- coding: utf-8 -*-
"""P9 — Background worker for information runs.

Executes pipelines outside the HTTP request lifecycle with per-domain
concurrency limits and progress events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .run_queue import FileRunQueue, get_run_queue, new_worker_id
from .run_store import (
    FileEventRepository,
    FileRunRepository,
    RunEvent,
    SourceAttempt,
    compile_twenty_cards,
    get_event_repository,
    get_run_repository,
)

logger = logging.getLogger(__name__)

# Soft concurrency guards (process-local)
_GLOBAL_FETCH_SEM = asyncio.Semaphore(6)
_DOMAIN_SEMS: Dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(2))
_SOURCE_LOCKS: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


class InformationWorker:
    def __init__(
        self,
        *,
        repo: Optional[FileRunRepository] = None,
        events: Optional[FileEventRepository] = None,
        queue: Optional[FileRunQueue] = None,
        worker_id: Optional[str] = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self.repo = repo or get_run_repository()
        self.events = events or get_event_repository()
        self.queue = queue or get_run_queue()
        self.worker_id = worker_id or new_worker_id()
        self.poll_seconds = poll_seconds
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop yet (import/sync context). Caller will start from async.
            logger.debug("InformationWorker %s deferred start (no running loop)", self.worker_id)
            return
        self._task = loop.create_task(self._loop(), name=f"info-worker-{self.worker_id}")
        logger.info("InformationWorker %s started", self.worker_id)

    async def stop(self) -> None:
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                run = await self.queue.claim(self.worker_id, lease_seconds=180)
                if run:
                    await self._execute(run.run_id)
                else:
                    await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("worker loop error: %s", exc)
                await asyncio.sleep(self.poll_seconds)

    def _emit(
        self,
        run_id: str,
        *,
        agent: str,
        status: str,
        phase: str = "",
        message: str = "",
        structured: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.events.append(
            run_id,
            RunEvent(
                seq=0,
                run_id=run_id,
                agent=agent,
                status=status,
                phase=phase,
                message=message,
                structured=structured or {},
            ),
        )

    async def _execute(self, run_id: str) -> None:
        run = self.repo.get(run_id)
        if not run:
            return
        self._emit(run_id, agent="worker", status="started", phase="fetching", message="run claimed")
        try:
            await self.queue.heartbeat(run_id, self.worker_id)
            self.repo.update(run_id, status="fetching")
            self._emit(run_id, agent="scout", status="progress", phase="fetching", message="collecting sources")

            from .pipelines import run_team_pipeline
            from .source_store import get_source_config_store

            sources = None
            attempts: List[SourceAttempt] = []
            if run.source_ids:
                store = get_source_config_store()
                sources = []
                for sid in run.source_ids:
                    cfg = store.get(sid)
                    if not cfg:
                        attempts.append(SourceAttempt(source_id=sid, status="skipped", error="not found"))
                        continue
                    host = (urlparse(cfg.url or "").netloc or "fixture").lower()
                    t0 = time.perf_counter()
                    async with _GLOBAL_FETCH_SEM:
                        async with _DOMAIN_SEMS[host]:
                            async with _SOURCE_LOCKS[sid]:
                                # Pipeline collects itself; we only record attempt metadata shell
                                sources.append(cfg)
                    attempts.append(
                        SourceAttempt(
                            source_id=sid,
                            status="ok",
                            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                        )
                    )
                self.repo.update(run_id, attempts=[a.to_dict() for a in attempts], status="normalizing")
                self._emit(
                    run_id,
                    agent="scout",
                    status="delivered",
                    phase="normalizing",
                    message=f"sources ready: {len(sources or [])}",
                    structured={"source_count": len(sources or [])},
                )

            await self.queue.heartbeat(run_id, self.worker_id)
            self.repo.update(run_id, status="analyzing")
            self._emit(run_id, agent="analyst", status="progress", phase="analyzing", message="pipeline running")

            result = await run_team_pipeline(run.team_id, sources=sources or None)

            self.repo.update(run_id, status="rendering")
            self._emit(run_id, agent="publisher", status="progress", phase="rendering", message="compiling cards")

            report = {}
            evidence_ids = []
            as_of = result.get("as_of") or ""
            # Prefer document report if available
            try:
                from .documents import get_document_store

                doc = get_document_store().get_latest(run.team_id)
                if doc and doc.run_id == result.get("run_id"):
                    report = doc.report or {}
                    evidence_ids = list(doc.evidence_ids or [])
                    as_of = doc.as_of or as_of
            except Exception:
                pass

            cards = compile_twenty_cards(
                team_id=run.team_id,
                report=report,
                evidence_ids=evidence_ids,
                as_of=as_of,
                analysis=report.get("analysis") if isinstance(report, dict) else None,
            )
            gap_n = sum(1 for c in cards if c.status == "gap")
            final_status = "degraded" if gap_n >= 8 and not evidence_ids else "completed"

            self.repo.update(run_id, status="publishing")
            self._emit(
                run_id,
                agent="publisher",
                status="delivered",
                phase="publishing",
                message=f"cards={len(cards)} gaps={gap_n}",
            )

            self.repo.update(
                run_id,
                status=final_status,
                result=result,
                cards=[c.to_dict() for c in cards],
                attempts=[a.to_dict() for a in attempts] if attempts else run.attempts,
                finished_at=_iso_now(),
                error="",
            )
            self._emit(
                run_id,
                agent="worker",
                status="delivered",
                phase=final_status,
                message="run finished",
                structured={"document_id": result.get("document_id"), "version": result.get("version")},
            )
            await self.queue.complete(run_id, self.worker_id)
        except Exception as exc:
            logger.exception("run %s failed: %s", run_id, exc)
            self.repo.update(
                run_id,
                status="failed",
                error=str(exc)[:800],
                finished_at=_iso_now(),
            )
            self._emit(run_id, agent="worker", status="failed", phase="failed", message=str(exc)[:400])
            await self.queue.complete(run_id, self.worker_id)


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_worker: Optional[InformationWorker] = None


def get_information_worker() -> InformationWorker:
    global _worker
    if _worker is None:
        _worker = InformationWorker()
    return _worker


def start_information_worker() -> InformationWorker:
    w = get_information_worker()
    w.start()
    return w


async def stop_information_worker() -> None:
    global _worker
    if _worker is not None:
        await _worker.stop()
        _worker = None


def reset_worker_for_tests(worker: Optional[InformationWorker] = None) -> None:
    global _worker
    _worker = worker
