# -*- coding: utf-8 -*-
"""把控制台上组装的情报来源解析成门禁可见的参考证据.

设计红线：解析在后端完成，前端只提交引用（kind + ref_id）。
产出的 Evidence 一律 ``advisory=True``——外部团队的采集与分析只作风险信号，
不进入门禁规则求值，不能让任何一道门自动通过或失败（对齐标准 §6.1 与 §9）。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .models import Evidence, EvidenceContribution, utc_now_iso
from .standard import GATE_BY_ID

COLLECTOR_VERSION = "1.0.0"

# 单条参考证据保留的分析条目上限，避免把整份报告塞进申请档案。
_MAX_ITEMS = 8


def _clip(items: Any, limit: int = _MAX_ITEMS) -> List[Any]:
    return list(items)[:limit] if isinstance(items, (list, tuple)) else []


def _digest_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """只摘取可复核的结构化结论，丢掉 HTML 正文。"""
    return {
        "evidence_score": report.get("evidence_score"),
        "signal_strength": report.get("signal_strength"),
        "topic_clusters": [
            {"name": c.get("name"), "count": c.get("count"), "share": c.get("share")}
            for c in _clip(report.get("topic_clusters"))
            if isinstance(c, dict)
        ],
        # 采集与处理的阶段轨迹：评审人靠它判断这条情报是怎么得出来的
        "reasoning_steps": [
            {"stage": s.get("stage"), "status": s.get("status"), "detail": s.get("detail")}
            for s in _clip(report.get("reasoning_steps"))
            if isinstance(s, dict)
        ],
        "business_implications": [
            {"stage": b.get("stage"), "label": b.get("label"), "detail": b.get("detail")}
            for b in _clip(report.get("business_implications"))
            if isinstance(b, dict)
        ],
        "open_questions": [str(q) for q in _clip(report.get("open_questions"))],
    }


def _make_evidence(gate: str, collector: str, payload: Dict[str, Any]) -> Evidence:
    return Evidence(
        evidence_id=f"ev-adv-{uuid.uuid4().hex[:10]}",
        gate=gate,
        check_id=f"{gate}-ADVISORY",
        collector=collector,
        collector_version=COLLECTOR_VERSION,
        collected_at=utc_now_iso(),
        payload=payload,
        advisory=True,
    )


def _resolve_channel(channel: str, contribution: EvidenceContribution, before: Optional[str]) -> Dict[str, Any]:
    from ..information_sources.documents import get_document_store

    store = get_document_store()
    docs = (
        store.documents_for_context(before=before, channels=[channel], limit=1)
        if before
        else store.list_documents(channel, limit=1)
    )
    if not docs:
        return {
            "_status": "missing",
            "kind": contribution.kind,
            "ref_id": contribution.ref_id,
            "note": "该情报通道尚无已发布文档，按缺证处理",
        }
    doc = docs[0]
    return {
        "_status": "ok",
        "kind": contribution.kind,
        "ref_id": contribution.ref_id,
        "channel": doc.channel,
        "document_id": doc.document_id,
        "version": doc.version,
        "title": doc.title,
        "as_of": doc.as_of,
        "run_id": doc.run_id,
        "analysis": _digest_report(doc.report or {}),
    }


def _resolve_document(contribution: EvidenceContribution) -> Dict[str, Any]:
    from ..information_sources.documents import get_document_store

    doc = get_document_store().get_document(contribution.ref_id)
    if doc is None:
        return {
            "_status": "missing",
            "kind": contribution.kind,
            "ref_id": contribution.ref_id,
            "note": "引用的文档不存在，按缺证处理",
        }
    return {
        "_status": "ok",
        "kind": contribution.kind,
        "ref_id": contribution.ref_id,
        "channel": doc.channel,
        "document_id": doc.document_id,
        "version": doc.version,
        "title": doc.title,
        "as_of": doc.as_of,
        "analysis": _digest_report(doc.report or {}),
    }


def _resolve_run(contribution: EvidenceContribution) -> Dict[str, Any]:
    """一次具体的采集与处理运行：连同它的阶段轨迹一起归档。"""
    from ..information_sources.run_store import get_run_repository

    run = get_run_repository().get(contribution.ref_id)
    if run is None:
        return {
            "_status": "missing",
            "kind": contribution.kind,
            "ref_id": contribution.ref_id,
            "note": "引用的采集运行不存在，按缺证处理",
        }
    return {
        "_status": "ok",
        "kind": contribution.kind,
        "ref_id": contribution.ref_id,
        "team_id": run.team_id,
        "run_status": run.status,
        "source_count": len(run.source_ids or []),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "analysis": _digest_report(run.result or {}),
    }


def resolve_contributions(
    contributions: List[EvidenceContribution],
    gate: str,
    *,
    before: Optional[str] = None,
) -> List[Evidence]:
    """把绑定到某道门禁的贡献解析成参考证据。解析失败按缺证记录，绝不静默丢弃。"""
    if gate not in GATE_BY_ID:
        return []

    out: List[Evidence] = []
    for c in contributions:
        if c.gate != gate:
            continue
        collector = f"external:{c.kind}:{c.ref_id}"
        try:
            if c.kind == "document":
                payload = _resolve_document(c)
            elif c.kind == "run":
                payload = _resolve_run(c)
            elif c.kind in ("team", "source"):
                payload = _resolve_channel(c.ref_id, c, before)
            else:
                payload = {
                    "_status": "missing",
                    "kind": c.kind,
                    "ref_id": c.ref_id,
                    "note": "未知的情报来源类型",
                }
        except Exception as exc:  # 解析失败也要留痕，便于复核
            payload = {
                "_status": "error",
                "kind": c.kind,
                "ref_id": c.ref_id,
                "error": str(exc),
            }
        payload["label"] = c.label or c.ref_id
        out.append(_make_evidence(gate, collector, payload))
    return out
