# -*- coding: utf-8 -*-
"""T401 — InvestmentSimulation models (no Plaza dependency)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


STATUSES = ("queued", "running", "completed", "failed", "cancelled")


@dataclass
class InvestmentSimulation:
    run_id: str
    ticker: str
    trade_date: str
    sector: str = ""
    asset_type: str = "stock"
    initial_cash: float = 100_000.0
    source_versions: List[Dict[str, Any]] = field(default_factory=list)
    models: Dict[str, Any] = field(default_factory=dict)
    analysts: List[str] = field(default_factory=lambda: ["market", "social", "news", "fundamentals"])
    debate_rounds: int = 1
    risk_rounds: int = 1
    sources: List[Dict[str, Any]] = field(default_factory=list)  # drag-drop source priority
    assembly_snapshot: Dict[str, Any] = field(default_factory=dict)  # immutable at create
    engine_config_snapshot: Dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    mode: str = "fixture"  # fixture | live
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    graph_shape: List[str] = field(default_factory=list)
    adapter_version: str = "1.0.0"
    checkpoint: Dict[str, Any] = field(default_factory=dict)
    last_event_cursor: int = 0
    error: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    cost: Dict[str, Any] = field(default_factory=dict)
    # Explicitly no plaza_id / discussion_id

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestmentSimulation":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        cleaned = {k: v for k, v in data.items() if k in known}
        # Strip accidental plaza fields
        cleaned.pop("plaza_id", None)
        cleaned.pop("discussion_id", None)
        return cls(**cleaned)

    @classmethod
    def create(
        cls,
        *,
        ticker: str,
        trade_date: str,
        sector: str = "",
        initial_cash: float = 100_000.0,
        asset_type: str = "stock",
        **kwargs: Any,
    ) -> "InvestmentSimulation":
        return cls(
            run_id=str(uuid.uuid4())[:12],
            ticker=ticker.upper().strip(),
            trade_date=trade_date,
            sector=str(sector or "").strip()[:80],
            initial_cash=float(initial_cash),
            asset_type=asset_type,
            **kwargs,
        )


@dataclass
class InvestmentEvent:
    run_id: str
    seq: int
    participant: str
    phase: str
    content: str
    status: str = "completed"
    evidence: List[str] = field(default_factory=list)
    node: str = ""
    structured: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestmentEvent":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        cleaned = {k: v for k, v in data.items() if k in known}
        cleaned.setdefault("structured", {})
        cleaned.setdefault("evidence", [])
        return cls(**cleaned)
