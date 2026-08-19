# -*- coding: utf-8 -*-
"""P9 — Persistent information runs, events, attempts, and analysis cards.

File-backed first; same shapes can be re-implemented on SQLite/PostgreSQL.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

_DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "storage" / "information_runs"

RUN_STATUSES = (
    "queued",
    "fetching",
    "normalizing",
    "analyzing",
    "rendering",
    "publishing",
    "completed",
    "degraded",
    "failed",
    "cancelled",
)

# Stable 20-card deck for research workbench (gap-aware)
REQUIRED_CARD_IDS = (
    "cover",
    "editor-note",
    "contents",
    "signal-landscape",
    "evidence-pulse",
    "two-state-gap",
    "confidence-bubble",
    "evidence-donut",
    "top-three",
    "source-ranking",
    "dual-track",
    "second-tier",
    "focal-signal",
    "flow-map",
    "pareto",
    "evidence-hub",
    "uncertainty",
    "adoption-cost-proxy",
    "risk-quadrant",
    "closing",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def floor_window(now: Optional[datetime] = None, minutes: int = 30) -> str:
    """UTC floor bucket for schedule idempotency keys."""
    dt = now or _utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    bucket = (dt.minute // max(1, minutes)) * max(1, minutes)
    floored = dt.replace(minute=bucket, second=0, microsecond=0)
    return floored.strftime("%Y%m%dT%H%MZ")


@dataclass
class RunEvent:
    seq: int
    run_id: str
    agent: str
    status: str  # started|progress|delivered|degraded|failed|phase
    phase: str = ""
    message: str = ""
    structured: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunEvent":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class SourceAttempt:
    source_id: str
    status: str = "pending"  # pending|ok|failed|cached|skipped
    error: str = ""
    evidence_count: int = 0
    latency_ms: float = 0.0
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceAttempt":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class AnalysisCard:
    card_id: str
    status: str = "gap"  # observed|inferred|gap
    title: str = ""
    summary: str = ""
    unit: str = ""
    as_of: str = ""
    sample_size: int = 0
    citation_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    next_agent: str = ""
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisCard":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class InformationRun:
    run_id: str
    team_id: str
    status: str = "queued"
    source_ids: List[str] = field(default_factory=list)
    trigger: str = "manual"  # manual|schedule|api
    schedule_id: str = ""
    idempotency_key: str = ""
    input_snapshot: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: List[SourceAttempt] = field(default_factory=list)
    cards: List[AnalysisCard] = field(default_factory=list)
    worker_id: str = ""
    lease_until: str = ""
    created_at: str = field(default_factory=_iso)
    updated_at: str = field(default_factory=_iso)
    started_at: str = ""
    finished_at: str = ""
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InformationRun":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload["attempts"] = [
            SourceAttempt.from_dict(x) if isinstance(x, dict) else x
            for x in payload.get("attempts") or []
        ]
        payload["cards"] = [
            AnalysisCard.from_dict(x) if isinstance(x, dict) else x
            for x in payload.get("cards") or []
        ]
        return cls(**payload)


def compile_twenty_cards(
    *,
    team_id: str,
    report: Optional[Dict[str, Any]] = None,
    evidence_ids: Optional[List[str]] = None,
    as_of: str = "",
    analysis: Optional[Dict[str, Any]] = None,
) -> List[AnalysisCard]:
    """Ensure all 20 stable cards exist as observed/inferred/gap."""
    report = report or {}
    analysis = analysis or report.get("analysis") or {}
    evidence_ids = list(evidence_ids or [])
    topic_clusters = analysis.get("topic_clusters") or []
    evidence_score = analysis.get("evidence_score")
    signal = analysis.get("signal_strength") or ""
    cards: List[AnalysisCard] = []

    def _card(
        card_id: str,
        *,
        status: str,
        title: str,
        summary: str,
        next_agent: str = "",
        unit: str = "",
        sample_size: int = 0,
    ) -> AnalysisCard:
        return AnalysisCard(
            card_id=card_id,
            status=status,
            title=title,
            summary=summary,
            unit=unit,
            as_of=as_of or "",
            sample_size=sample_size or len(evidence_ids),
            citation_ids=evidence_ids[:5],
            evidence_ids=evidence_ids[:12],
            next_agent=next_agent,
        )

    topic_names = [str(t.get("name") or t) for t in topic_clusters[:5]] if topic_clusters else []
    observed_topics = "observed" if topic_names else "gap"
    score_status = "inferred" if evidence_score is not None else "gap"

    mapping = {
        "cover": _card(
            "cover",
            status="observed" if report.get("headline") or report.get("what_happened") else "gap",
            title="封面",
            summary=str(report.get("headline") or (report.get("what_happened") or {}).get("text") or "待生成"),
        ),
        "editor-note": _card(
            "editor-note",
            status="inferred",
            title="编辑说明",
            summary="研究用途，不构成投资建议；证据有截止时间。",
        ),
        "contents": _card(
            "contents",
            status="observed",
            title="目录",
            summary="20 卡固定结构：信号、证据、路径、风险、缺口。",
        ),
        "signal-landscape": _card(
            "signal-landscape",
            status=observed_topics,
            title="信号全景",
            summary="、".join(topic_names) if topic_names else "本轮无主题簇；需 Scout 补证",
            next_agent="scout" if not topic_names else "",
        ),
        "evidence-pulse": _card(
            "evidence-pulse",
            status="observed" if evidence_ids else "gap",
            title="证据脉搏",
            summary=f"证据 {len(evidence_ids)} 条" if evidence_ids else "无证据入库",
            sample_size=len(evidence_ids),
            next_agent="scout" if not evidence_ids else "",
        ),
        "two-state-gap": _card(
            "two-state-gap",
            status="inferred",
            title="观察 vs 缺口",
            summary="已观察主题与尚未核验的因果链分开标注。",
        ),
        "confidence-bubble": _card(
            "confidence-bubble",
            status=score_status,
            title="置信气泡",
            summary=f"信号强度 {signal or '—'} · 证据分 {evidence_score if evidence_score is not None else '—'}",
            unit="score_0_1",
        ),
        "evidence-donut": _card(
            "evidence-donut",
            status="observed" if evidence_ids else "gap",
            title="证据构成",
            summary=f"样本 {len(evidence_ids)}",
            sample_size=len(evidence_ids),
        ),
        "top-three": _card(
            "top-three",
            status=observed_topics,
            title="Top3 主题",
            summary=" / ".join(topic_names[:3]) if topic_names else "缺口：无主题",
            next_agent="checker" if not topic_names else "",
        ),
        "source-ranking": _card(
            "source-ranking",
            status="inferred" if evidence_ids else "gap",
            title="来源排序",
            summary="按来源独立性与时效启发式排序（非权威排名）。",
        ),
        "dual-track": _card(
            "dual-track",
            status="inferred",
            title="双轨解读",
            summary="事实轨道与叙事轨道分离，避免把发布会写成营收。",
        ),
        "second-tier": _card(
            "second-tier",
            status="gap" if len(topic_names) < 2 else "observed",
            title="次级信号",
            summary="、".join(topic_names[1:4]) if len(topic_names) > 1 else "次级主题不足",
        ),
        "focal-signal": _card(
            "focal-signal",
            status=observed_topics,
            title="焦点信号",
            summary=topic_names[0] if topic_names else "无焦点",
        ),
        "flow-map": _card(
            "flow-map",
            status="inferred",
            title="传导路径",
            summary="能力/成本 → 采用 → 收入/利润池（模拟，非预测）。",
            next_agent="market_mapper",
        ),
        "pareto": _card(
            "pareto",
            status="inferred" if topic_clusters else "gap",
            title="集中度",
            summary="主题份额近似 Pareto 观察；缺结构化财务数据。",
        ),
        "evidence-hub": _card(
            "evidence-hub",
            status="observed" if evidence_ids else "gap",
            title="证据枢纽",
            summary=f"{len(evidence_ids)} 条可追溯 evidence_id",
        ),
        "uncertainty": _card(
            "uncertainty",
            status="inferred",
            title="不确定性",
            summary="单源、转载链与时间滞后是主要不确定性来源。",
            next_agent="red_team",
        ),
        "adoption-cost-proxy": _card(
            "adoption-cost-proxy",
            status="gap",
            title="采用/成本代理",
            summary="禁止由标题推造营收/估值/Capex；需结构化数据源。",
            next_agent="data_engineer",
        ),
        "risk-quadrant": _card(
            "risk-quadrant",
            status="inferred",
            title="风险象限",
            summary="来源偏差、样本不足、政策突变、执行时滞。",
        ),
        "closing": _card(
            "closing",
            status="observed",
            title="收束",
            summary=f"team={team_id} · 卡齐套 {len(REQUIRED_CARD_IDS)}",
        ),
    }
    for card_id in REQUIRED_CARD_IDS:
        cards.append(mapping[card_id])
    assert {c.card_id for c in cards} == set(REQUIRED_CARD_IDS)
    assert all(c.status in {"observed", "inferred", "gap"} for c in cards)
    return cards


@runtime_checkable
class RunRepository(Protocol):
    def create(self, run: InformationRun) -> InformationRun: ...
    def get(self, run_id: str) -> Optional[InformationRun]: ...
    def update(self, run_id: str, **fields: Any) -> Optional[InformationRun]: ...
    def get_by_idempotency(self, key: str) -> Optional[InformationRun]: ...
    def list_recent(self, limit: int = 50) -> List[InformationRun]: ...
    def list_queued(self) -> List[InformationRun]: ...


@runtime_checkable
class EventRepository(Protocol):
    def append(self, run_id: str, event: RunEvent) -> RunEvent: ...
    def list_after(self, run_id: str, after_seq: int = 0) -> List[RunEvent]: ...
    def next_seq(self, run_id: str) -> int: ...


class FileRunRepository:
    """JSON-per-run under storage/information_runs/."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index_path = self.root / "index.json"
        self._idem_path = self.root / "idempotency.json"

    def _run_path(self, run_id: str) -> Path:
        return self.root / "runs" / f"{run_id}.json"

    def _load_index(self) -> List[str]:
        if not self._index_path.exists():
            return []
        try:
            return list(json.loads(self._index_path.read_text(encoding="utf-8")).get("run_ids") or [])
        except Exception:
            return []

    def _save_index(self, run_ids: List[str]) -> None:
        _atomic_write(self._index_path, json.dumps({"run_ids": run_ids[-500:]}, ensure_ascii=False, indent=2))

    def _load_idem(self) -> Dict[str, str]:
        if not self._idem_path.exists():
            return {}
        try:
            return dict(json.loads(self._idem_path.read_text(encoding="utf-8")))
        except Exception:
            return {}

    def _save_idem(self, mapping: Dict[str, str]) -> None:
        # keep last 2000 keys
        items = list(mapping.items())[-2000:]
        _atomic_write(self._idem_path, json.dumps(dict(items), ensure_ascii=False, indent=2))

    def create(self, run: InformationRun) -> InformationRun:
        with self._lock:
            if run.idempotency_key:
                existing = self.get_by_idempotency(run.idempotency_key)
                if existing:
                    return existing
            path = self._run_path(run.run_id)
            if path.exists():
                return self.get(run.run_id)  # type: ignore[return-value]
            _atomic_write(path, json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
            ids = self._load_index()
            if run.run_id not in ids:
                ids.append(run.run_id)
                self._save_index(ids)
            if run.idempotency_key:
                idem = self._load_idem()
                idem[run.idempotency_key] = run.run_id
                self._save_idem(idem)
            return run

    def get(self, run_id: str) -> Optional[InformationRun]:
        path = self._run_path(run_id)
        if not path.exists():
            return None
        try:
            return InformationRun.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def update(self, run_id: str, **fields: Any) -> Optional[InformationRun]:
        with self._lock:
            run = self.get(run_id)
            if not run:
                return None
            data = run.to_dict()
            data.update(fields)
            data["updated_at"] = _iso()
            updated = InformationRun.from_dict(data)
            _atomic_write(
                self._run_path(run_id),
                json.dumps(updated.to_dict(), ensure_ascii=False, indent=2),
            )
            return updated

    def get_by_idempotency(self, key: str) -> Optional[InformationRun]:
        if not key:
            return None
        with self._lock:
            run_id = self._load_idem().get(key)
            if not run_id:
                return None
            return self.get(run_id)

    def list_recent(self, limit: int = 50) -> List[InformationRun]:
        ids = self._load_index()[-limit:]
        out: List[InformationRun] = []
        for rid in reversed(ids):
            run = self.get(rid)
            if run:
                out.append(run)
        return out[:limit]

    def list_queued(self) -> List[InformationRun]:
        return [r for r in self.list_recent(200) if r.status == "queued"]


class FileEventRepository:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, run_id: str) -> Path:
        return self.root / "events" / f"{run_id}.jsonl"

    def next_seq(self, run_id: str) -> int:
        events = self.list_after(run_id, 0)
        return (events[-1].seq + 1) if events else 1

    def append(self, run_id: str, event: RunEvent) -> RunEvent:
        with self._lock:
            if event.seq <= 0:
                event.seq = self.next_seq(run_id)
            event.run_id = run_id
            path = self._path(run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            return event

    def list_after(self, run_id: str, after_seq: int = 0) -> List[RunEvent]:
        path = self._path(run_id)
        if not path.exists():
            return []
        out: List[RunEvent] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = RunEvent.from_dict(json.loads(line))
                if ev.seq > after_seq:
                    out.append(ev)
        except Exception:
            return out
        out.sort(key=lambda e: e.seq)
        return out


_run_repo: Optional[FileRunRepository] = None
_event_repo: Optional[FileEventRepository] = None


def get_run_repository() -> FileRunRepository:
    global _run_repo
    if _run_repo is None:
        _run_repo = FileRunRepository()
    return _run_repo


def get_event_repository() -> FileEventRepository:
    global _event_repo
    if _event_repo is None:
        _event_repo = FileEventRepository()
    return _event_repo


def reset_run_stores_for_tests(
    run_repo: Optional[FileRunRepository] = None,
    event_repo: Optional[FileEventRepository] = None,
) -> None:
    global _run_repo, _event_repo
    _run_repo = run_repo
    _event_repo = event_repo
