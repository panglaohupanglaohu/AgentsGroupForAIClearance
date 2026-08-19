# -*- coding: utf-8 -*-
"""T811/T812 — Assembly module contract + immutable compile for engine runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

TEAM_CHANNELS = {
    "team:ai_news_60s": "ai_news_60s",
    "ai_news_60s": "ai_news_60s",
    "team:dufu_world_intel": "dufu_world_intel",
    "dufu_world_intel": "dufu_world_intel",
}

VALID_KINDS = frozenset({"team", "source", "document", "market", "engine"})


@dataclass
class AssemblyModule:
    module_id: str
    kind: str
    name: str = ""
    enabled: bool = True
    priority: int = 1
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssemblyModule":
        mid = str(
            data.get("module_id")
            or data.get("sourceId")
            or data.get("source_id")
            or data.get("id")
            or ""
        )
        kind = str(data.get("kind") or "source").lower()
        if kind not in VALID_KINDS:
            # Infer from id prefixes used by the frontend parts bank
            if mid.startswith("team:"):
                kind = "team"
            elif mid.startswith("document:"):
                kind = "document"
            elif mid.startswith("market:") or mid.startswith("engine:"):
                kind = "market"
            else:
                kind = "source"
        return cls(
            module_id=mid,
            kind=kind,
            name=str(data.get("name") or mid),
            enabled=bool(data.get("enabled", True)),
            priority=int(data.get("priority") or 1),
            config=dict(data.get("config") or {}),
        )


@dataclass
class AssemblyPlan:
    ticker: str
    cutoff: str
    channels: List[str]
    document_ids: List[str]
    source_ids: List[str]
    module_order: List[str]
    modules: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)
    snapshot_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _dedupe(items: Sequence[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def normalize_modules(raw_modules: Optional[Sequence[Dict[str, Any]]]) -> List[AssemblyModule]:
    modules: List[AssemblyModule] = []
    for i, row in enumerate(raw_modules or []):
        if not isinstance(row, dict):
            continue
        m = AssemblyModule.from_dict(row)
        if not m.module_id:
            continue
        if m.priority <= 0:
            m.priority = i + 1
        modules.append(m)
    return modules


def compile_assembly(
    modules: Sequence[Any],
    *,
    ticker: str,
    cutoff: str,
    known_document_as_of: Optional[Dict[str, str]] = None,
) -> AssemblyPlan:
    """Compile drag-drop modules into a frozen run plan.

    Future documents (as_of > cutoff) are dropped with a warning.
    """
    normalized: List[AssemblyModule] = []
    for m in modules:
        if isinstance(m, AssemblyModule):
            normalized.append(m)
        elif isinstance(m, dict):
            normalized.append(AssemblyModule.from_dict(m))
    ordered = sorted([m for m in normalized if m.enabled], key=lambda x: (x.priority, x.module_id))
    channels: List[str] = []
    documents: List[str] = []
    source_ids: List[str] = []
    warnings: List[str] = []
    known = known_document_as_of or {}

    for module in ordered:
        if module.kind == "team":
            ch = TEAM_CHANNELS.get(module.module_id) or module.config.get("channel")
            if ch:
                channels.append(str(ch))
            else:
                warnings.append(f"unknown team module: {module.module_id}")
        elif module.kind == "document":
            doc_id = module.module_id
            as_of = known.get(doc_id) or module.config.get("as_of")
            if as_of and cutoff and str(as_of) > str(cutoff):
                warnings.append(f"dropped future document {doc_id} (as_of={as_of} > cutoff={cutoff})")
                continue
            documents.append(doc_id)
        elif module.kind == "source":
            source_ids.append(module.module_id)
        elif module.kind in ("market", "engine"):
            # Engine fixtures (event clock etc.) — recorded in order only
            pass
        else:
            warnings.append(f"unsupported kind {module.kind}: {module.module_id}")

    plan = AssemblyPlan(
        ticker=str(ticker or "").upper(),
        cutoff=str(cutoff or ""),
        channels=_dedupe(channels),
        document_ids=_dedupe(documents),
        source_ids=_dedupe(source_ids),
        module_order=[m.module_id for m in ordered],
        modules=[m.to_dict() for m in ordered],
        warnings=warnings,
    )
    raw = json.dumps(
        {
            "ticker": plan.ticker,
            "cutoff": plan.cutoff,
            "module_order": plan.module_order,
            "channels": plan.channels,
            "document_ids": plan.document_ids,
            "source_ids": plan.source_ids,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    plan.snapshot_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return plan


def modules_from_legacy_sources(sources: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Accept either assembly modules or legacy {sourceId,priority,name,kind}."""
    out: List[Dict[str, Any]] = []
    for i, s in enumerate(sources or []):
        if not isinstance(s, dict):
            continue
        if s.get("module_id"):
            out.append(s)
            continue
        out.append(
            {
                "module_id": s.get("sourceId") or s.get("source_id") or s.get("id"),
                "kind": s.get("kind") or "source",
                "name": s.get("name") or "",
                "enabled": s.get("enabled", True),
                "priority": s.get("priority") or (i + 1),
                "config": s.get("config") or {},
            }
        )
    return out
