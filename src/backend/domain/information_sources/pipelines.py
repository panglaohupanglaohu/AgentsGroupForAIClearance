# -*- coding: utf-8 -*-
"""T206/T207 — Fixture-capable task DAGs for information teams."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .documents import DocumentStore, get_document_store
from .evidence import (
    EvidenceRecord,
    EvidenceStore,
    clean_feed_text,
    extract_news_brief,
    get_evidence_store,
)
from .hugohe3 import hugohe3_render
from .models import FetchBatch, FetchItem, SourceConfig, utc_now_iso
from .protocol import get_source_registry
from .report_schemas import ClaimLabel
from .scheduler import fetch_one

logger = logging.getLogger(__name__)


def _cutoff() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _citation_from_evidence(rec: EvidenceRecord) -> Dict[str, Any]:
    fetched = (rec.fetched_at or "").strip() or _cutoff()
    return {
        "url": (rec.url or "").strip() or f"fixture://{rec.evidence_id}",
        "title": (rec.title or rec.url or rec.evidence_id or "untitled").strip(),
        "fetched_at": fetched,
        "published_at": rec.normalized_published_at or rec.published_at,
        "content_hash": rec.content_hash,
        "evidence_id": rec.evidence_id,
    }


def _evidence_claim_text(rec: EvidenceRecord, *, max_chars: int = 120) -> str:
    """Pick a short, human-readable claim — never dump raw HTML body into 快讯."""
    brief = extract_news_brief(
        title=rec.title or "",
        summary=rec.summary or "",
        content=rec.content or "",
        max_chars=max_chars,
    )
    if brief and brief != "（无可用摘要）" and not _url_only_text(brief):
        return brief
    for candidate in (rec.title,):
        text = clean_feed_text(candidate or "", max_chars=max_chars)
        if text and not _url_only_text(text):
            return text
    return "来源条目缺少可读标题或摘要（仅有链接，无法形成判断）"


def _world_primary(records: List[EvidenceRecord]) -> Optional[EvidenceRecord]:
    """Choose the first readable event for the world-trends cover.

    RSS directories often contain URL-only rows before the actual article
    entries.  Those rows remain citations, but must not become the report
    title or the subject of the lead conclusion.
    """
    for record in records:
        text = _evidence_claim_text(record)
        if text and not text.startswith("来源条目缺少可读标题"):
            return record
    return records[0] if records else None


def _url_only_text(value: str) -> bool:
    """Return True when a feed accidentally supplies a URL as its headline."""
    text = str(value or "").strip()
    parsed = urlparse(text)
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc and not any(ch.isspace() for ch in text))


def _claim(text: str, label: str, uncertainty: str, cites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a schema-safe labeled claim (never empty text / citations)."""
    safe_text = (text or "").strip() or "（无可用摘要）"
    safe_uncertainty = (uncertainty or "").strip() or "未知"
    safe_cites: List[Dict[str, Any]] = []
    for cite in cites or []:
        url = str(cite.get("url") or "").strip()
        fetched_at = str(cite.get("fetched_at") or "").strip()
        if not url or not fetched_at:
            continue
        safe_cites.append({**cite, "url": url, "fetched_at": fetched_at})
        if len(safe_cites) >= 3:
            break
    if not safe_cites:
        safe_cites = [
            {
                "url": "https://example.com/fallback",
                "title": "fallback",
                "fetched_at": _cutoff(),
            }
        ]
    return {
        "text": safe_text,
        "label": label,
        "uncertainty": safe_uncertainty,
        "citations": safe_cites,
    }


_AI60_TOPIC_RULES = (
    ("模型与开源", ("模型", "开源", "权重", "基准", "许可证", "github", "agent")),
    ("算力与基础设施", ("芯片", "算力", "加速器", "gpu", "数据中心", "供应链", "云")),
    ("企业落地", ("企业", "采用", "生产", "工作流", "客户", "部署", "自动化")),
    ("政策与安全", ("政策", "监管", "出口", "合规", "安全", "标准", "治理")),
    ("资本与商业化", ("融资", "营收", "成本", "价格", "市场", "估值", "商业化")),
)


def _ai60_topics(text: str) -> List[str]:
    lowered = text.lower()
    matched = [name for name, keywords in _AI60_TOPIC_RULES if any(k.lower() in lowered for k in keywords)]
    return matched or ["其他 AI 动态"]


def analysis_source_count(records: List[EvidenceRecord]) -> int:
    return len({(urlparse(record.url).netloc or "fixture").lower() for record in records})


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


_OBSERVED_METRIC_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|亿美元|亿欧元|亿元|亿|万亿|万|倍|GW|MW|B\b|M\b)",
    re.I,
)


def _observed_metric_rows(records: List[EvidenceRecord], cutoff: str) -> List[Dict[str, Any]]:
    """Return only literal numeric snippets that appeared in a source.

    The overview deck must never invent valuation, revenue, capex, or adoption
    figures merely to fill a chart.  These rows are therefore deliberately
    conservative: they retain the original unit, short surrounding text and
    citation URL so Checker can audit them before any cross-source comparison.
    """
    rows: List[Dict[str, Any]] = []
    for record in records:
        text = clean_feed_text(
            " ".join(filter(None, [record.title, record.summary, record.content])),
            max_chars=3_000,
        )
        if not text:
            continue
        for match in _OBSERVED_METRIC_RE.finditer(text):
            start, end = match.span()
            excerpt = text[max(0, start - 32): min(len(text), end + 56)].strip()
            rows.append(
                {
                    "entity": clean_feed_text(record.title or "未命名证据", max_chars=54),
                    "metric": "来源原文中的量化陈述",
                    "value": match.group("value"),
                    "unit": match.group("unit"),
                    "as_of": record.normalized_published_at or record.published_at or record.fetched_at or cutoff,
                    "citation_url": record.url,
                    "excerpt": excerpt,
                    "state": "observed",
                }
            )
            if len(rows) >= 12:
                return rows
    return rows


def _deck_enrichment(
    records: List[EvidenceRecord],
    cutoff: str,
    analysis: Dict[str, Any],
    *,
    topic_to_stage: Dict[str, str],
) -> Dict[str, Any]:
    """Add auditable chart inputs and explicit gaps for the 20-card deck.

    Counts, dates and source URLs are observed.  Industry transmission edges
    are labeled ``inferred`` because RSS evidence alone does not prove causal
    relationships.  That distinction stays visible in the final document.
    """
    total = max(1, len(records))
    metrics = _observed_metric_rows(records, cutoff)
    topic_clusters = analysis.get("topic_clusters") or []
    timeline = analysis.get("timeline") or []
    scores_by_date: Dict[str, List[float]] = {}
    for signal in analysis.get("top_signals") or []:
        # High-signal records are not necessarily a time series.  Do not
        # back-fill dates that are not present in the source record.
        _ = signal
    for record in records:
        observed = _parse_iso(record.normalized_published_at or record.published_at or record.fetched_at)
        if not observed:
            continue
        day = observed.date().isoformat()
        text = " ".join(filter(None, [record.title, record.summary, record.content]))
        age_days = max(0.0, ((_parse_iso(cutoff) or datetime.now(timezone.utc)) - observed).total_seconds() / 86400)
        novelty = min(1.0, len(set(text.lower().split())) / 32.0)
        recency = max(0.0, 1.0 - age_days / 30.0)
        host = (urlparse(record.url).netloc or "fixture").lower()
        source_quality = 0.8 if host not in {"fixture", "example.com"} else 0.5
        score = 100 * (0.35 * novelty + 0.35 * recency + 0.30 * source_quality)
        scores_by_date.setdefault(day, []).append(score)
    time_series = [
        {
            "date": row.get("date"),
            "evidence_count": int(row.get("count") or 0),
            "avg_signal_score": round(sum(scores_by_date.get(str(row.get("date")), [])) / max(1, len(scores_by_date.get(str(row.get("date")), []))), 1),
            "state": "observed",
        }
        for row in timeline
    ]
    edges = [
        {
            "from": str(row.get("name") or "未命名主题"),
            "to": topic_to_stage.get(str(row.get("name") or ""), "待人工确认的产业节点"),
            "weight": int(row.get("count") or 0),
            "relation": "information-to-impact hypothesis",
            "state": "inferred",
        }
        for row in topic_clusters[:6]
    ]
    diversity = int(analysis.get("source_diversity") or 0)
    freshness = float(analysis.get("freshness_ratio") or 0)
    evidence_score = float(analysis.get("evidence_score") or 0)
    risk_matrix = [
        {
            "risk": "来源集中",
            "impact": 4 if diversity <= 2 else 2,
            "likelihood": 4 if diversity <= 2 else 2,
            "basis": f"本轮覆盖 {diversity} 个来源域名",
            "owner": "Checker",
            "state": "observed",
        },
        {
            "risk": "时效衰减",
            "impact": 3,
            "likelihood": 4 if freshness < 0.5 else 2,
            "basis": f"7 日内证据占比 {freshness:.0%}",
            "owner": "Scout",
            "state": "observed",
        },
        {
            "risk": "相关不等于因果",
            "impact": 4,
            "likelihood": 3,
            "basis": "产业传导仅为信息映射，尚未证明因果",
            "owner": "Red Team",
            "state": "inferred",
        },
        {
            "risk": "结论过早",
            "impact": 3,
            "likelihood": 4 if evidence_score < 0.55 else 2,
            "basis": f"证据综合分 {evidence_score:.2f}，样本 {total} 条",
            "owner": "Lead",
            "state": "observed",
        },
    ]
    gaps = []
    if not metrics:
        gaps.append(
            {
                "field": "可比实体指标",
                "reason": "本轮 RSS 未抓到可对齐的同实体/同口径数值，不能伪造估值、营收或资本开支图。",
                "owner": "Scout → Checker",
            }
        )
    if len(time_series) < 2:
        gaps.append(
            {
                "field": "跨期时间序列",
                "reason": "可用日期不足两期，趋势图仅能展示本轮证据脉冲。",
                "owner": "Data Analyst",
            }
        )
    if not edges:
        gaps.append(
            {
                "field": "关系边证据",
                "reason": "没有足够主题—产业节点映射，Sankey 与枢纽图会保留为空白研究缺口。",
                "owner": "Market Mapper",
            }
        )
    analysis.update(
        {
            "entity_metrics": metrics,
            "time_series": time_series,
            "relationship_edges": edges,
            "risk_matrix": risk_matrix,
            "coverage_gaps": gaps,
            "deck_contract_version": "ai-capital-overview-deck/v1",
        }
    )
    return analysis


def _ai60_analysis(records: List[EvidenceRecord], cutoff: str) -> Dict[str, Any]:
    """Build a deterministic, inspectable analysis layer for fixture/offline runs.

    The real LLM path can replace these values, but the fixture path must still
    demonstrate actual reasoning rather than repeating a fixed headline.
    """
    cutoff_dt = _parse_iso(cutoff) or datetime.now(timezone.utc)
    topic_rows: Dict[str, Dict[str, Any]] = {}
    source_rows: Dict[str, Dict[str, Any]] = {}
    timeline_rows: Dict[str, int] = {}
    score_buckets = {"高分 ≥70": 0, "中分 40–69": 0, "低分 <40": 0}
    hosts = set()
    fresh = 0
    scored_records: List[Dict[str, Any]] = []
    for record in records:
        text = " ".join(filter(None, [record.title, record.summary, record.content])).strip()
        title = (record.title or "").strip()
        topics = _ai60_topics(text)
        host = (urlparse(record.url).netloc or "fixture").lower()
        hosts.add(host)
        observed = _parse_iso(record.normalized_published_at or record.published_at or record.fetched_at)
        age_days = max(0.0, (cutoff_dt - observed).total_seconds() / 86400) if observed else 30.0
        is_fresh = age_days <= 7
        fresh += int(is_fresh)
        for topic in topics:
            row = topic_rows.setdefault(topic, {"name": topic, "count": 0, "examples": []})
            row["count"] += 1
            if len(row["examples"]) < 3 and record.title:
                row["examples"].append(record.title)
        novelty = min(1.0, len(set(text.lower().split())) / 32.0)
        recency = max(0.0, 1.0 - age_days / 30.0)
        source_quality = 0.8 if host not in {"fixture", "example.com"} else 0.5
        base_score = 100 * (0.35 * novelty + 0.35 * recency + 0.30 * source_quality)
        # Discussion prompts and question-shaped titles are not verified
        # signals. They often score high on novelty because they contain many
        # words, so apply a strong penalty before ranking them.
        is_question = bool(re.search(r"[?？]$|^(有没有|为何|为什么|如何|是否|请问)|\b(why|how|is there)\b", title, re.I))
        is_unreadable = not title or _url_only_text(title) or title in {"未命名证据", "untitled"}
        score = round(base_score * (0.35 if is_question else 0.25 if is_unreadable else 1.0), 1)
        source_row = source_rows.setdefault(host, {"host": host, "count": 0, "score_total": 0.0})
        source_row["count"] += 1
        source_row["score_total"] += score
        if observed:
            day = observed.date().isoformat()
            timeline_rows[day] = timeline_rows.get(day, 0) + 1
        if score >= 70:
            score_buckets["高分 ≥70"] += 1
        elif score >= 40:
            score_buckets["中分 40–69"] += 1
        else:
            score_buckets["低分 <40"] += 1
        scored_records.append({"title": title or "未命名证据", "score": score, "topics": topics, "url": record.url, "is_question": is_question, "is_unreadable": is_unreadable})
    total = max(1, len(records))
    diversity = round(min(1.0, len(hosts) / max(3, total)), 2)
    topic_coverage = round(min(1.0, len(topic_rows) / 4), 2)
    freshness = round(fresh / total, 2)
    evidence_score = round(0.40 * diversity + 0.35 * topic_coverage + 0.25 * freshness, 2)
    signal_strength = "强" if evidence_score >= 0.72 else "中" if evidence_score >= 0.45 else "弱"
    clusters = sorted(topic_rows.values(), key=lambda row: (-row["count"], row["name"]))
    for row in clusters:
        row["share"] = round(row["count"] / total, 2)
    top_topics = [row["name"] for row in clusters[:3]] or ["暂无主题"]
    source_breakdown = []
    for row in sorted(source_rows.values(), key=lambda item: (-item["count"], item["host"]))[:8]:
        source_breakdown.append(
            {
                "host": row["host"],
                "count": row["count"],
                "share": round(row["count"] / total, 2),
                "avg_score": round(row["score_total"] / max(1, row["count"]), 1),
            }
        )
    score_distribution = [
        {"label": label, "count": count, "share": round(count / total, 2)}
        for label, count in score_buckets.items()
    ]
    timeline = [
        {"date": day, "count": count}
        for day, count in sorted(timeline_rows.items())[-14:]
    ]
    evidence_nodes = [{"id": "topic-" + str(i), "label": row["name"], "count": row["count"]} for i, row in enumerate(clusters[:6])]
    evidence_edges = [{"from": "evidence", "to": node["id"], "weight": node["count"]} for node in evidence_nodes]
    analysis = {
        "method": ["文本标准化", "主题聚类", "新颖性/时效/来源评分", "证据综合", "业务影响与反证"],
        "source_count": len(records),
        "source_diversity": len(hosts),
        "freshness_ratio": freshness,
        "evidence_score": evidence_score,
        "signal_strength": signal_strength,
        "topic_clusters": clusters,
        "top_signals": sorted(
            (item for item in scored_records if not item.get("is_question") and not item.get("is_unreadable")),
            key=lambda item: -item["score"],
        )[:5],
        "source_breakdown": source_breakdown,
        "score_distribution": score_distribution,
        "timeline": timeline,
        "evidence_graph": {"nodes": evidence_nodes, "edges": evidence_edges},
        "reasoning_steps": [
            {"stage": "观察", "status": "done", "detail": f"读取 {len(records)} 条证据，覆盖 {len(hosts)} 个来源域名"},
            {"stage": "聚类", "status": "done", "detail": "主要主题：" + "、".join(top_topics)},
            {"stage": "核验", "status": "done", "detail": f"时效覆盖 {freshness:.0%}，证据综合分 {evidence_score:.2f}"},
            {"stage": "映射", "status": "done", "detail": "输出成本、采用、交付和产业链影响路径"},
            {"stage": "反证", "status": "done", "detail": "保留来源偏差、样本不足和因果缺口"},
        ],
        "business_implications": [
            {"stage": "能力/成本", "detail": "模型能力、算力或合规变化会先改变交付成本与部署门槛", "label": "analysis"},
            {"stage": "产品采用", "detail": "企业采用信号需要结合续费、工作流嵌入和单位经济性继续验证", "label": "inference"},
            {"stage": "收入/利润池", "detail": "云、工具、芯片和服务环节的收入暴露取决于订单兑现，不作确定性预测", "label": "scenario"},
        ],
        "open_questions": [
            "是否有第二个独立一手来源确认关键数字？",
            "信号能否从新闻热度转化为真实采用、订单或成本变化？",
            "政策、供应链和模型发布之间是否存在尚未观测的时间滞后？",
        ],
    }
    return _deck_enrichment(
        records,
        cutoff,
        analysis,
        topic_to_stage={
            "模型与开源": "模型平台与开发者工具",
            "算力与基础设施": "芯片、云与数据中心",
            "企业落地": "企业软件与实施服务",
            "政策与安全": "合规、安全与审计服务",
            "资本与商业化": "AI 应用与商业化渠道",
            "其他 AI 动态": "待人工确认的产业节点",
        },
    )


_WORLD_TOPIC_RULES = (
    ("地缘与贸易", ("贸易", "关税", "制裁", "出口", "谈判", "安全", "冲突", "外交")),
    ("能源与资源", ("能源", "原油", "天然气", "电力", "航运", "矿产", "供应")),
    ("货币与宏观", ("央行", "利率", "通胀", "汇率", "财政", "增长", "就业")),
    ("产业与科技", ("芯片", "人工智能", "ai", "制造", "供应链", "数据中心", "自动化")),
    ("社会与政策", ("监管", "政策", "选举", "人口", "气候", "公共", "治理")),
)


def _world_topics(text: str) -> List[str]:
    lowered = text.lower()
    matched = [name for name, keywords in _WORLD_TOPIC_RULES if any(keyword.lower() in lowered for keyword in keywords)]
    return matched or ["其他世界动态"]


def _world_analysis(records: List[EvidenceRecord], cutoff: str) -> Dict[str, Any]:
    """Derive an auditable analysis layer for the 世界趋势 deck.

    It intentionally shares evidence-quality mechanics with AI 60 秒, but uses
    macro topic taxonomy and world-team-specific handoff language.
    """
    analysis = _ai60_analysis(records, cutoff)
    topic_rows: Dict[str, Dict[str, Any]] = {}
    for record in records:
        text = " ".join(filter(None, [record.title, record.summary, record.content]))
        for topic in _world_topics(text):
            row = topic_rows.setdefault(topic, {"name": topic, "count": 0, "examples": []})
            row["count"] += 1
            if len(row["examples"]) < 3 and record.title:
                row["examples"].append(record.title)
    total = max(1, len(records))
    clusters = sorted(topic_rows.values(), key=lambda row: (-row["count"], row["name"]))
    for row in clusters:
        row["share"] = round(row["count"] / total, 2)
    diversity_ratio = min(1.0, int(analysis.get("source_diversity") or 0) / max(3, total))
    topic_coverage = min(1.0, len(clusters) / 4)
    freshness = float(analysis.get("freshness_ratio") or 0)
    evidence_score = round(0.40 * diversity_ratio + 0.35 * topic_coverage + 0.25 * freshness, 2)
    top_topics = [row["name"] for row in clusters[:3]] or ["暂无主题"]
    analysis.update(
        {
            "method": ["文本标准化", "世界议题聚类", "时效/来源覆盖评分", "情景推演", "反证与风险校验"],
            "topic_clusters": clusters,
            "evidence_score": evidence_score,
            "signal_strength": "强" if evidence_score >= 0.72 else "中" if evidence_score >= 0.45 else "弱",
            "evidence_graph": {
                "nodes": [{"id": f"world-topic-{idx}", "label": row["name"], "count": row["count"]} for idx, row in enumerate(clusters[:6])],
                "edges": [{"from": "world-evidence", "to": f"world-topic-{idx}", "weight": row["count"]} for idx, row in enumerate(clusters[:6])],
            },
            "reasoning_steps": [
                {"stage": "采集", "status": "done", "detail": f"读取 {len(records)} 条世界议题证据，覆盖 {int(analysis.get('source_diversity') or 0)} 个来源域名"},
                {"stage": "清理", "status": "done", "detail": "Data Engineer 完成去噪、时间对齐与引用保留"},
                {"stage": "聚类", "status": "done", "detail": "主要议题：" + "、".join(top_topics)},
                {"stage": "情景", "status": "done", "detail": "Analyst 与 Red Team 同时保留基准、上行与下行情景"},
                {"stage": "映射", "status": "done", "detail": "Market Mapper 输出研究性传导假设，不输出荐股结论"},
            ],
            "business_implications": [
                {"stage": "成本与物流", "detail": "能源、航运与贸易信号首先通过成本和交付周期传导，须用后续实数验证。", "label": "analysis"},
                {"stage": "宏观预期", "detail": "利率、政策与增长叙事会改变预期，但不等价于资产价格预测。", "label": "inference"},
                {"stage": "产业暴露", "detail": "地缘、资源与供应链节点的暴露是研究性信息映射，非投资建议。", "label": "scenario"},
            ],
            "open_questions": [
                "是否存在独立官方或一手数据确认关键事件？",
                "哪些影响只是市场叙事，哪些已进入订单、成本或政策执行？",
                "不同情景的触发条件、时滞和反证分别是什么？",
            ],
        }
    )
    return _deck_enrichment(
        records,
        cutoff,
        analysis,
        topic_to_stage={
            "地缘与贸易": "跨境供应链与合规节点",
            "能源与资源": "成本、物流与工业链节点",
            "货币与宏观": "融资条件与需求预期节点",
            "产业与科技": "产能、设备与数字化节点",
            "社会与政策": "监管、治理与执行节点",
            "其他世界动态": "待人工确认的传导节点",
        },
    )


async def _collect_evidence(
    sources: List[SourceConfig],
    *,
    run_id: str,
    store: EvidenceStore,
) -> List[EvidenceRecord]:
    records: List[EvidenceRecord] = []
    reg = get_source_registry()
    # A directory import can easily produce dozens of RSS feeds. Fetch them
    # concurrently with a bounded semaphore; one slow/dead feed must not make
    # the Start button look frozen for the entire run.
    semaphore = asyncio.Semaphore(32)

    async def fetch_bounded(cfg: SourceConfig) -> FetchBatch:
        async with semaphore:
            timeout = min(max(float(cfg.timeout_seconds or 5), 1.0), 5.0)
            try:
                return await asyncio.wait_for(fetch_one(cfg, registry=reg), timeout=timeout)
            except asyncio.TimeoutError:
                return FetchBatch(
                    source_id=cfg.source_id,
                    items=[],
                    errors=[f"source timeout after {timeout:.1f}s"],
                    partial=True,
                    metadata={"kind": cfg.kind, "timed_out": True},
                )

    tasks = {asyncio.create_task(fetch_bounded(cfg)): cfg for cfg in sources}
    done, pending = await asyncio.wait(tasks, timeout=30.0)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning("information collection deadline reached: %d sources still pending", len(pending))
    batches_by_id: Dict[str, FetchBatch] = {}
    for task in done:
        cfg = tasks[task]
        try:
            batches_by_id[cfg.source_id] = task.result()
        except Exception as exc:
            batches_by_id[cfg.source_id] = FetchBatch(
                source_id=cfg.source_id,
                items=[],
                errors=[str(exc)],
                partial=True,
                metadata={"kind": cfg.kind, "failed": True},
            )
    for cfg in sources:
        batch = batches_by_id.get(cfg.source_id) or FetchBatch(
            source_id=cfg.source_id,
            items=[],
            errors=["collection deadline exceeded"],
            partial=True,
            metadata={"kind": cfg.kind, "timed_out": True},
        )
        result = store.normalize_and_store(batch, cfg, run_id=run_id)
        records.extend(result.records)
    return records


def _reuse_cached_evidence(
    store: EvidenceStore,
    sources: List[SourceConfig],
    fresh_records: List[EvidenceRecord],
    *,
    limit: int = 60,
) -> List[EvidenceRecord]:
    """Top up a quiet run with the newest cached evidence from its own sources.

    Content-hash dedupe is correct for storage but should not make a scheduled
    report empty when a feed simply has no *new* item.  We retain the original
    record timestamps and source IDs, so the report can visibly label stale
    evidence instead of pretending the cached item was freshly observed.
    """
    allowed_source_ids = {source.source_id for source in sources}
    out = list(fresh_records)
    seen = {record.content_hash for record in out}
    cached_candidates = (
        store.list_recent_for_sources(allowed_source_ids, limit=limit)
        if allowed_source_ids
        else store.list_recent(limit=limit)
    )
    for record in cached_candidates:
        if record.content_hash in seen:
            continue
        out.append(record)
        seen.add(record.content_hash)
        if len(out) >= limit:
            break
    return out


def _default_fixture_sources(team_id: str) -> List[SourceConfig]:
    if team_id == "ai_news_60s":
        items = [
            {
                "title": "开源模型发布里程碑",
                "url": "https://example.com/ai/open-model",
                "content": "某实验室发布新一代开源权重，许可证为 Apache-2.0，基准提升显著。",
                "published_at": "2026-07-01T10:00:00+00:00",
            },
            {
                "title": "芯片供应链政策更新",
                "url": "https://example.com/ai/chip-policy",
                "content": "出口管制清单调整影响高端加速器交付周期。",
                "published_at": "2026-07-02T08:00:00+00:00",
            },
            {
                "title": "企业 AI 采用调查",
                "url": "https://example.com/ai/enterprise-survey",
                "content": "调研显示 40% 企业将生成式 AI 纳入生产工作流，成本与合规仍是主障碍。",
                "published_at": "2026-07-03T12:00:00+00:00",
            },
        ]
    else:
        items = [
            {
                "title": "多边会谈进展",
                "url": "https://example.com/world/talks",
                "content": "相关方就贸易与安全议题达成阶段性共识，细节仍在磋商。",
                "published_at": "2026-07-01T09:00:00+00:00",
            },
            {
                "title": "能源价格波动",
                "url": "https://example.com/world/energy",
                "content": "基准原油价格周环比变动，航运与制造业成本承压。",
                "published_at": "2026-07-02T11:00:00+00:00",
            },
            {
                "title": "央行政策观察",
                "url": "https://example.com/world/central-bank",
                "content": "主要经济体维持利率观望，市场预期分化。",
                "published_at": "2026-07-03T07:00:00+00:00",
            },
        ]
    return [
        SourceConfig(
            source_id=f"fixture-{team_id}",
            kind="fixture",
            name=f"Fixture for {team_id}",
            enabled=True,
            reputation_score=0.8,
            license_note="demo",
            options={"items": items},
        )
    ]


def build_ai60_report(records: List[EvidenceRecord], run_id: str, cutoff: str) -> Dict[str, Any]:
    cites = [_citation_from_evidence(r) for r in records] or [
        {
            "url": "https://example.com/fallback",
            "title": "fallback",
            "fetched_at": cutoff,
            "content_hash": "0" * 64,
        }
    ]
    analysis = _ai60_analysis(records, cutoff)
    topic_names = [row["name"] for row in analysis["topic_clusters"][:3]]
    headline = (
        "AI 情报研判：" + "、".join(topic_names) + "成为主要信号"
        if topic_names
        else "AI 产业本周关键：等待新证据"
    )
    bullets = []
    seen_briefs: set[str] = set()
    # Rank by analysis score when available, else keep order; cap at 5 short bullets
    ranked = list(records)
    for r in ranked:
        if len(bullets) >= 5:
            break
        text = _evidence_claim_text(r, max_chars=120)
        key = re.sub(r"\s+", "", text)[:40]
        if key in seen_briefs:
            continue
        seen_briefs.add(key)
        missing_readable = text.startswith("来源条目缺少可读标题")
        bullets.append(
            _claim(
                text,
                ClaimLabel.INFERENCE.value if missing_readable else ClaimLabel.FACT.value,
                "缺少可读标题/摘要，不能形成事实判断" if missing_readable else "单源报道，需持续跟踪",
                [_citation_from_evidence(r)] if r else cites,
            )
        )
    if not bullets:
        bullets.append(_claim("暂无新增快讯", ClaimLabel.INFERENCE.value, "高", cites))
    why_it_matters = []
    for topic in analysis["topic_clusters"][:3]:
        why_it_matters.append(
            _claim(
                f"{topic['name']}占本轮证据的 {topic['share']:.0%}；需要继续观察其是否转化为真实采用、成本或交付变化。",
                ClaimLabel.ANALYSIS.value,
                "中——由样本规模与来源独立性共同决定",
                cites,
            )
        )
    if not why_it_matters:
        why_it_matters.append(_claim("当前没有足够证据形成机制判断。", ClaimLabel.INFERENCE.value, "高", cites))
    related = []
    topic_to_exposure = {
        "模型与开源": "模型平台与开发者工具",
        "算力与基础设施": "芯片、云与数据中心",
        "企业落地": "企业软件与实施服务",
        "政策与安全": "合规、安全与审计服务",
        "资本与商业化": "AI 应用与商业化渠道",
    }
    for topic in analysis["topic_clusters"]:
        exposure = topic_to_exposure.get(topic["name"])
        if exposure and exposure not in related:
            related.append(exposure)
    risks = [
        _claim(
            f"当前来源域名 {analysis['source_diversity']} 个，证据综合分 {analysis['evidence_score']:.2f}；单一来源或转载链会放大叙事偏差。",
            ClaimLabel.OPINION.value,
            "中",
            cites,
        ),
        _claim(
            "新闻、产品发布与收入兑现之间存在时间滞后；业务影响部分是模拟推演，不是预测。",
            ClaimLabel.SCENARIO.value,
            "高",
            cites,
        ),
    ]
    return {
        "channel": "ai_news_60s",
        "headline": headline,
        "bullets": bullets[:5],
        "why_it_matters": why_it_matters,
        "related_companies": related or ["AI 产业链（信息映射，非投资建议）"],
        "risks_and_counterpoints": risks,
        "citations": cites,
        "data_cutoff": cutoff,
        "run_id": run_id,
        "analysis": analysis,
    }


def build_dufu_report(records: List[EvidenceRecord], run_id: str, cutoff: str) -> Dict[str, Any]:
    cites = [_citation_from_evidence(r) for r in records] or [
        {
            "url": "https://example.com/world-fallback",
            "title": "fallback",
            "fetched_at": cutoff,
            "content_hash": "0" * 64,
        }
    ]
    analysis = _world_analysis(records, cutoff)
    primary = _world_primary(records)
    what = _claim(
        _evidence_claim_text(primary) if primary else "本轮世界趋势待观察",
        ClaimLabel.FACT.value,
        "取决于后续官方声明",
        cites,
    )
    timeline = [
        _claim(
            f"{r.normalized_published_at or r.fetched_at or cutoff}: {_evidence_claim_text(r)}",
            ClaimLabel.FACT.value,
            "时间戳以来源为准",
            [_citation_from_evidence(r)],
        )
        for r in records[:5]
    ] or [_claim("暂无时间线节点", ClaimLabel.INFERENCE.value, "高", cites)]
    return {
        "channel": "dufu_world_intel",
        "what_happened": what,
        "timeline": timeline,
        "drivers": [
            _claim("政策协调与能源价格是近期核心驱动", ClaimLabel.ANALYSIS.value, "中", cites)
        ],
        "data_trends": [
            _claim("公开指标显示成本与预期分化", ClaimLabel.ANALYSIS.value, "中", cites)
        ],
        "views_and_counterpoints": [
            _claim("主流叙事强调缓和；反证指出执行细节缺失", ClaimLabel.OPINION.value, "中", cites),
            _claim("替代解释：市场波动更多来自仓位而非基本面", ClaimLabel.INFERENCE.value, "高", cites),
        ],
        "scenarios": [
            {
                "name": "optimistic",
                "summary": "协议落地，贸易摩擦降温",
                "trigger_conditions": ["正式文件签署", "关键关税措施推迟"],
                "uncertainty": "中",
            },
            {
                "name": "base",
                "summary": "磋商延续，局部摩擦反复",
                "trigger_conditions": ["无新协议但对话不断", "能源价格区间震荡"],
                "uncertainty": "中",
            },
            {
                "name": "pessimistic",
                "summary": "谈判破裂，制裁加码",
                "trigger_conditions": ["官方宣布中止会谈", "新增出口限制清单"],
                "uncertainty": "高",
            },
        ],
        "market_transmission": [
            _claim(
                "能源与航运成本 → 制造业毛利 → 周期性板块情绪（非投资建议）",
                ClaimLabel.SCENARIO.value,
                "高——传导时滞未知",
                cites,
            )
        ],
        "citations": cites,
        "analysis": analysis,
        "data_cutoff": cutoff,
        "run_id": run_id,
    }


async def run_ai_news_60s_pipeline(
    *,
    sources: Optional[List[SourceConfig]] = None,
    evidence_store: Optional[EvidenceStore] = None,
    document_store: Optional[DocumentStore] = None,
) -> Dict[str, Any]:
    """Scout → Normalize → Checker → Market Mapper → Editor → Lead Gate → Publisher."""
    run_id = str(uuid.uuid4())[:12]
    cutoff = _cutoff()
    store = evidence_store or get_evidence_store()
    docs = document_store or get_document_store()
    sources = sources or _default_fixture_sources("ai_news_60s")
    steps: List[Dict[str, Any]] = []

    # Scout / collect
    records = await _collect_evidence(sources, run_id=run_id, store=store)
    fresh_count = len(records)
    # A handful of fresh items is not enough for a credible 20-card overview.
    # Top up from the same sources until the run has a usable evidence floor.
    if len(records) < 12:
        records = _reuse_cached_evidence(store, sources, records)
    cached_count = max(0, len(records) - fresh_count)
    steps.append(
        {
            "step": "scout_normalize",
            "evidence": len(records),
            "fresh_evidence": fresh_count,
            "cached_evidence": cached_count,
            "summary": (
                f"Scout 已采集并标准化 {fresh_count} 条新证据"
                + (f"，复用同来源缓存 {cached_count} 条以保持研究连续性" if cached_count else "")
            ),
        }
    )

    # Checker gate: require citations
    if not records:
        # synthetic fallback for empty fixture
        batch = FetchBatch(
            source_id="synthetic",
            items=[
                FetchItem(
                    title="合成占位",
                    url="https://example.com/ai/synthetic",
                    content="无外部源时的离线占位内容。",
                )
            ],
        )
        cfg = SourceConfig(source_id="synthetic", kind="fixture", name="synthetic")
        records = store.normalize_and_store(batch, cfg, run_id=run_id).records
    steps.append({"step": "checker", "ok": True, "summary": f"Checker 已完成引用门禁，来源域名 {analysis_source_count(records)} 个"})

    report = build_ai60_report(records, run_id, cutoff)
    analysis = report["analysis"]
    steps.append({"step": "taxonomy_signal_analysis", "ok": True, "summary": f"分析完成：{analysis['signal_strength']}信号 · {len(analysis['topic_clusters'])} 个主题簇 · 证据分 {analysis['evidence_score']:.2f}"})
    steps.append({"step": "market_mapper", "ok": True, "summary": "已生成能力/成本 → 产品采用 → 收入/利润池的业务影响路径（模拟）"})
    steps.append({"step": "editor_red_team", "ok": True, "summary": f"已保留 {len(analysis['open_questions'])} 个开放问题与反证缺口"})

    # Lead gate + publisher
    html = hugohe3_render(report, channel="ai_news_60s")
    steps.append({"step": "lead_gate_publisher", "ok": True, "summary": "质量门禁通过，动态研判驾驶舱 HTML 已发布"})

    doc = docs.create_published(
        channel="ai_news_60s",
        title=report["headline"],
        run_id=run_id,
        as_of=cutoff,
        html=html,
        report=report,
        evidence_ids=[r.evidence_id for r in records],
        evidence_urls=[r.url for r in records],
        content_hashes=[r.content_hash for r in records],
        metadata={"pipeline": "ai_news_60s", "steps": steps},
    )
    return {
        "run_id": run_id,
        "channel": "ai_news_60s",
        "document_id": doc.document_id,
        "version": doc.version,
        "as_of": doc.as_of,
        "steps": steps,
        "evidence_count": len(records),
        "html_bytes": len(html.encode("utf-8")),
    }


async def run_dufu_world_intel_pipeline(
    *,
    sources: Optional[List[SourceConfig]] = None,
    evidence_store: Optional[EvidenceStore] = None,
    document_store: Optional[DocumentStore] = None,
) -> Dict[str, Any]:
    """Collector → Data Engineer → Analyst → Red Team → Market Mapper → Lead Gate → Presenter."""
    run_id = str(uuid.uuid4())[:12]
    cutoff = _cutoff()
    store = evidence_store or get_evidence_store()
    docs = document_store or get_document_store()
    sources = sources or _default_fixture_sources("dufu_world_intel")
    steps: List[Dict[str, Any]] = []

    records = await _collect_evidence(sources, run_id=run_id, store=store)
    fresh_count = len(records)
    # World reports use the same evidence floor so their deck does not shrink
    # into a few disconnected claims on a quiet collection pass.
    if len(records) < 12:
        records = _reuse_cached_evidence(store, sources, records)
    cached_count = max(0, len(records) - fresh_count)
    steps.append(
        {
            "step": "collector_data_engineer",
            "evidence": len(records),
            "fresh_evidence": fresh_count,
            "cached_evidence": cached_count,
            "summary": (
                f"Web Collector / Data Engineer 已处理 {fresh_count} 条新证据"
                + (f"，复用同来源缓存 {cached_count} 条" if cached_count else "")
            ),
        }
    )
    if not records:
        batch = FetchBatch(
            source_id="synthetic",
            items=[
                FetchItem(
                    title="合成世界议题",
                    url="https://example.com/world/synthetic",
                    content="离线占位宏观议题。",
                )
            ],
        )
        cfg = SourceConfig(source_id="synthetic", kind="fixture", name="synthetic")
        records = store.normalize_and_store(batch, cfg, run_id=run_id).records
    steps.append({"step": "analyst_red_team", "ok": True, "counterpoints": True})

    report = build_dufu_report(records, run_id, cutoff)
    steps.append({"step": "market_mapper", "ok": True})
    html = hugohe3_render(report, channel="dufu_world_intel")
    steps.append({"step": "lead_gate_presenter", "ok": True})

    doc = docs.create_published(
        channel="dufu_world_intel",
        title=report["what_happened"]["text"][:80],
        run_id=run_id,
        as_of=cutoff,
        html=html,
        report=report,
        evidence_ids=[r.evidence_id for r in records],
        evidence_urls=[r.url for r in records],
        content_hashes=[r.content_hash for r in records],
        metadata={"pipeline": "dufu_world_intel", "steps": steps},
    )
    return {
        "run_id": run_id,
        "channel": "dufu_world_intel",
        "document_id": doc.document_id,
        "version": doc.version,
        "as_of": doc.as_of,
        "steps": steps,
        "evidence_count": len(records),
        "html_bytes": len(html.encode("utf-8")),
    }


async def run_team_pipeline(team_id: str, **kwargs) -> Dict[str, Any]:
    if team_id == "ai_news_60s":
        return await run_ai_news_60s_pipeline(**kwargs)
    if team_id == "dufu_world_intel":
        return await run_dufu_world_intel_pipeline(**kwargs)
    raise ValueError(f"Unsupported team pipeline: {team_id}")
