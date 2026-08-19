# -*- coding: utf-8 -*-
"""T205 — hugohe3 Skill renderer: controlled JSON → safe responsive HTML."""

from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from .report_schemas import AiNews60sReport, WorldIntelReport, validate_report

_SCRIPT_RE = re.compile(r"<\s*script\b", re.I)
_ON_ATTR_RE = re.compile(r"\son\w+\s*=", re.I)
_JS_URL_RE = re.compile(r"javascript:", re.I)


def safe_json(data: Any) -> str:
    """JSON safe for embedding in HTML (no script breakout)."""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("</", "<\\/")
    )


def validate_csp_html(html_text: str) -> None:
    if _SCRIPT_RE.search(html_text):
        raise ValueError("HTML must not contain <script> tags")
    if _ON_ATTR_RE.search(html_text):
        raise ValueError("HTML must not contain inline event handlers")
    if _JS_URL_RE.search(html_text):
        raise ValueError("HTML must not contain javascript: URLs")


def validate_citations_present(html_text: str, urls: List[str]) -> None:
    missing = [u for u in urls if u and u not in html_text]
    if missing:
        raise ValueError(f"HTML missing citation URLs: {missing[:3]}")


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _display_claim_text(value: Any) -> str:
    """Never render a bare feed URL as a factual claim in a report card."""
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not any(ch.isspace() for ch in text):
        return "来源仅提供链接，暂无可读标题或摘要，不能形成判断。"
    return text or "暂无可读结论。"


def _claim_block(claims: List[Any], heading: str) -> str:
    parts = [f"<section aria-labelledby='h-{_esc(heading)}'>"]
    parts.append(f"<h2 id='h-{_esc(heading)}'>{_esc(heading)}</h2><ul>")
    for c in claims:
        label = getattr(c, "label", None)
        label_v = label.value if hasattr(label, "value") else str(label or "")
        claim_text = _display_claim_text(getattr(c, "text", str(c)))
        if claim_text.startswith("来源仅提供链接"):
            label_v = "inference"
        parts.append(
            "<li>"
            f"<span class='claim-label' data-label='{_esc(label_v)}'>{_esc(label_v)}</span> "
            f"{_esc(claim_text)} "
            f"<em class='uncertainty'>(不确定: {_esc(getattr(c, 'uncertainty', ''))})</em>"
            "</li>"
        )
    parts.append("</ul></section>")
    return "".join(parts)


def _citations_block(citations: List[Any]) -> str:
    parts = ["<section aria-labelledby='h-citations'><h2 id='h-citations'>来源与引用</h2><ol>"]
    for c in citations:
        url = getattr(c, "url", "")
        title = getattr(c, "title", "") or url
        fetched = getattr(c, "fetched_at", "")
        parts.append(
            f"<li><a href='{_esc(url)}' target='_blank' rel='noopener noreferrer'>{_esc(title)}</a>"
            f" <time datetime='{_esc(fetched)}'>抓取: {_esc(fetched)}</time></li>"
        )
    parts.append("</ol></section>")
    return "".join(parts)


def _ai60_signal_map(report: AiNews60sReport) -> str:
    """Render a safe, screenshot-2-style evidence/impact network.

    This is deliberately SVG/HTML rather than a runtime chart library: reports
    are embedded in a sandboxed iframe and must remain readable offline.
    """
    nodes = [("主议题", report.headline, 380, 142, "hub")]
    for i, claim in enumerate(report.bullets[:4]):
        nodes.append((f"事实 {i + 1}", _display_claim_text(claim.text), 120 + i * 170, 54, "fact"))
    for i, company in enumerate(report.related_companies[:3]):
        nodes.append((f"暴露 {i + 1}", company, 180 + i * 190, 244, "exposure"))
    if len(nodes) == 1:
        nodes.append(("证据", "暂无额外事实节点", 120, 54, "fact"))
    circles = []
    edges = []
    for label, text, x, y, kind in nodes:
        radius = 34 if kind == "hub" else 27
        fill = {"hub": "#0f766e", "fact": "#dbeafe", "exposure": "#fef3c7"}[kind]
        stroke = {"hub": "#115e59", "fact": "#60a5fa", "exposure": "#f59e0b"}[kind]
        color = "#fff" if kind == "hub" else "#172033"
        safe_label = _esc(label)
        safe_text = _esc((text or "")[:22] + ("…" if len(text or "") > 22 else ""))
        circles.append(
            f"<g class='signal-node {kind}'><circle cx='{x}' cy='{y}' r='{radius}' fill='{fill}' stroke='{stroke}'/>"
            f"<text x='{x}' y='{y - 4}' text-anchor='middle' fill='{color}'>{safe_label}</text>"
            f"<text x='{x}' y='{y + 11}' text-anchor='middle' fill='{color}' class='node-detail'>{safe_text}</text></g>"
        )
        if kind != "hub":
            edges.append(f"<line x1='{x}' y1='{y}' x2='380' y2='142' class='signal-edge'/>")
    return (
        "<figure class='signal-map' aria-labelledby='signal-map-caption'>"
        "<div class='signal-map-head'><span>AI 60 秒 · 证据—影响关系图</span><span class='legend'>"
        "<i class='legend-dot fact'></i>事实 <i class='legend-dot exposure'></i>产业暴露 <i class='legend-dot hub'></i>主议题"
        "</span></div>"
        "<svg viewBox='0 0 760 300' role='img' aria-label='主议题、事实证据和产业暴露关系图'>"
        + "".join(edges) + "".join(circles)
        + "</svg><figcaption id='signal-map-caption'>节点只表示信息传导路径，不代表买卖建议；点击来源列表查看原始证据。</figcaption></figure>"
    )


def _ai60_timeline() -> str:
    return (
        "<section class='seconds-strip' aria-label='60 秒播报时间带'>"
        "<div><b>00–03</b><span>钩子</span></div><div><b>03–12</b><span>事实核</span></div>"
        "<div><b>12–30</b><span>机制</span></div><div><b>30–45</b><span>产业映射</span></div>"
        "<div><b>45–54</b><span>反证</span></div><div><b>54–60</b><span>引用/免责声明</span></div>"
        "</section>"
    )


def _analysis_overview(report: AiNews60sReport) -> str:
    """Render a compact overview layer inspired by a research-deck overview.

    The cards are deliberately CSS/HTML only so the report remains safe and
    readable inside the sandboxed iframe, while still exposing source breadth,
    score distribution, time concentration and the strongest signals.
    """
    analysis = report.analysis or {}
    clusters = analysis.get("topic_clusters") or [{"name": "暂无主题", "count": 0, "share": 0, "examples": []}]
    sources = analysis.get("source_breakdown") or [{"host": "暂无来源", "count": 0, "avg_score": 0}]
    scores = analysis.get("score_distribution") or [{"label": "暂无评分", "count": 0, "share": 0}]
    timeline = analysis.get("timeline") or [{"date": "本轮无日期", "count": 0}]
    signals = analysis.get("top_signals") or [{"title": "暂无高分信号", "score": 0}]
    implications = analysis.get("business_implications") or [{"stage": "业务影响", "detail": "暂无足够证据形成影响推演。", "label": "pending"}]
    reasoning = analysis.get("reasoning_steps") or [{"stage": "等待分析", "status": "pending", "detail": "下一轮运行后补充推理阶段。"}]
    questions = analysis.get("open_questions") or ["暂无待验证问题；需要新增信息源后继续运行。"]
    # Empty/deduplicated runs still publish a useful gap report.  Keep every
    # denominator non-zero rather than turning a quiet run into a 500 error.
    source_max = max(1, max([int(row.get("count") or 0) for row in sources] or [0]))
    topic_max = max(1.0, max([float(row.get("share") or 0) for row in clusters] or [0.0]))
    score_max = max(1, max([int(row.get("count") or 0) for row in scores] or [0]))
    time_max = max(1, max([int(row.get("count") or 0) for row in timeline] or [0]))
    signal_max = max(1.0, max([float(row.get("score") or 0) for row in signals] or [0.0]))

    source_html = "".join(
        f"<li><div class='overview-row'><b>{_esc(str(row.get('host') or 'unknown'))}</b>"
        f"<span>{int(row.get('count') or 0)} 条 · {float(row.get('avg_score') or 0):.0f}分</span></div>"
        f"<div class='overview-track'><i style='width:{max(5, int(100 * (int(row.get('count') or 0) / source_max)))}%'></i></div></li>"
        for row in sources
    ) or "<li class='overview-empty'>等待来源覆盖统计。</li>"
    topic_html = "".join(
        f"<li><div class='overview-row'><b>{_esc(str(row.get('name') or '未命名主题'))}</b>"
        f"<span>{float(row.get('share') or 0):.0%} · {int(row.get('count') or 0)} 条</span></div>"
        f"<div class='overview-track'><i style='width:{max(5, int(100 * (float(row.get('share') or 0) / topic_max)))}%'></i></div></li>"
        for row in clusters[:6]
    ) or "<li class='overview-empty'>等待主题聚类。</li>"
    score_html = "".join(
        f"<li><div class='overview-row'><b>{_esc(str(row.get('label') or '未分组'))}</b>"
        f"<span>{int(row.get('count') or 0)} 条</span></div>"
        f"<div class='overview-track score'><i style='width:{max(5, int(100 * (int(row.get('count') or 0) / score_max)))}%'></i></div></li>"
        for row in scores
    ) or "<li class='overview-empty'>等待证据评分。</li>"
    timeline_html = "".join(
        f"<li><div class='overview-row'><b>{_esc(str(row.get('date') or '—'))}</b>"
        f"<span>{int(row.get('count') or 0)} 条</span></div>"
        f"<div class='overview-track timeline'><i style='width:{max(5, int(100 * (int(row.get('count') or 0) / time_max)))}%'></i></div></li>"
        for row in timeline
    ) or "<li class='overview-empty'>暂无可对齐的发布时间。</li>"
    signal_html = "".join(
        f"<li><details class='overview-expand'><summary><div class='overview-row'><b>{_esc(str(row.get('title') or '未命名信号'))}</b>"
        f"<span>{float(row.get('score') or 0):.0f}</span></div></summary>"
        f"<p class='overview-detail'>{_esc(str(row.get('title') or '未命名信号'))}</p>"
        f"<div class='overview-track signal'><i style='width:{max(5, int(100 * (float(row.get('score') or 0) / signal_max)))}%'></i></div></details></li>"
        for row in signals[:5]
    ) or "<li class='overview-empty'>等待高分信号。</li>"
    impact_html = "".join(
        f"<li><div class='overview-row'><b>{_esc(str(item.get('stage') or '影响路径'))}</b>"
        f"<span class='overview-tag'>{_esc(str(item.get('label') or 'analysis'))}</span></div>"
        f"<p class='overview-detail'>{_esc(str(item.get('detail') or '等待业务影响分析。'))}</p></li>"
        for item in implications
    ) or "<li class='overview-empty'>等待业务影响模拟。</li>"
    reasoning_html = "".join(
        f"<li class='overview-stage'><span class='overview-stage-dot {'done' if str(step.get('status') or '').lower() == 'done' else ''}'></span>"
        f"<b>{_esc(str(step.get('stage') or '阶段'))}</b><span>{_esc(str(step.get('status') or 'pending'))}</span></li>"
        for step in reasoning
    ) or "<li class='overview-empty'>等待 Agent 阶段。</li>"
    question_html = "".join(
        f"<li><span class='question-mark'>?</span>{_esc(str(question))}</li>"
        for question in questions
    ) or "<li class='overview-empty'>暂无待验证问题。</li>"
    return (
        "<section class='analysis-overview' aria-labelledby='analysis-overview-title'>"
        "<div class='overview-heading'><div><span class='analysis-kicker'>OVERVIEW · MULTI-SOURCE DEPTH</span>"
        "<h3 id='analysis-overview-title'>证据全景概览</h3></div>"
        f"<span class='overview-count'>{int(analysis.get('source_count') or 0)} 条证据 · {int(analysis.get('source_diversity') or 0)} 个来源域</span></div>"
        f"<div class='overview-grid'><article class='overview-card'><h4>来源覆盖与质量</h4><ul>{source_html}</ul></article>"
        f"<article class='overview-card'><h4>主题占比</h4><ul>{topic_html}</ul></article>"
        f"<article class='overview-card'><h4>证据质量分布</h4><ul>{score_html}</ul></article>"
        f"<article class='overview-card'><h4>时间脉冲</h4><ul>{timeline_html}</ul></article>"
        f"<article class='overview-card'><h4>高分信号排行</h4><ul>{signal_html}</ul></article>"
        f"<article class='overview-card'><h4>业务影响传导</h4><ul>{impact_html}</ul></article>"
        f"<article class='overview-card overview-wide'><h4>待验证问题清单</h4><ul>{question_html}</ul></article></div></section>"
    )


def _analysis_dashboard(report: AiNews60sReport) -> str:
    """Render the analysis/decision layer that turns collected facts into a
    visible reasoning journey. CSS animation makes the stage feel alive while
    keeping the report self-contained and script-free inside the sandbox.
    """
    analysis = report.analysis or {}
    clusters = analysis.get("topic_clusters") or []
    steps = analysis.get("reasoning_steps") or []
    implications = analysis.get("business_implications") or []
    score = float(analysis.get("evidence_score") or 0)
    total_steps = max(1, len(steps))
    done_steps = sum(1 for step in steps if str(step.get("status") or "").lower() in {"done", "completed", "complete"})
    progress = int(round(100 * done_steps / total_steps)) if steps else 0
    live_status = "● ANALYSIS READY" if progress >= 100 else "● ANALYZING"
    metrics = [
        ("信号强度", analysis.get("signal_strength") or "待定"),
        ("证据综合", f"{score:.2f}"),
        ("来源域名", str(analysis.get("source_diversity") or 0)),
        ("时效覆盖", f"{float(analysis.get('freshness_ratio') or 0):.0%}"),
    ]
    metric_html = "".join(
        f"<div class='analysis-metric'><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>"
        for label, value in metrics
    )
    cluster_html = "".join(
        "<li><div class='topic-line'><b>"
        + _esc(row.get("name", "未命名"))
        + "</b><span>"
        + _esc(f"{float(row.get('share') or 0):.0%} · {row.get('count', 0)} 条")
        + "</span></div><div class='topic-track'><i style='width:"
        + _esc(str(min(100, max(4, int(float(row.get("share") or 0) * 100)))))
        + "%'></i></div><small>"
        + _esc("；".join(row.get("examples") or []))
        + "</small></li>"
        for row in clusters[:6]
    ) or "<li class='muted'>等待更多证据形成主题聚类。</li>"
    steps_html = "".join(
        f"<li class='reasoning-step'><span class='step-dot'></span><div><b>{_esc(step.get('stage', '阶段'))}</b>"
        f"<small>{_esc(step.get('detail', ''))}</small></div><em>{_esc(step.get('status', 'pending'))}</em></li>"
        for step in steps
    ) or "<li class='reasoning-step'><span class='step-dot'></span><div><b>等待分析</b><small>运行后显示观察、聚类、核验、映射和反证。</small></div></li>"
    impact_html = "".join(
        f"<li><span class='claim-label' data-label='{_esc(item.get('label', 'analysis'))}'>{_esc(item.get('label', 'analysis'))}</span> "
        f"{_esc(item.get('stage', '业务影响'))}：{_esc(item.get('detail', ''))}</li>"
        for item in implications
    ) or "<li>等待业务影响模拟。</li>"
    return (
        "<section class='analysis-dashboard' aria-labelledby='analysis-dashboard-title'>"
        "<div class='analysis-head'><div><span class='analysis-kicker'>LIVE REASONING BOARD</span>"
        "<h2 id='analysis-dashboard-title'>AI 60 秒 · 研判驾驶舱</h2>"
        "<p>从原始证据到主题、信号、业务影响和反证的可追溯分析链。</p></div>"
        f"<span class='analysis-pulse'>{live_status}</span></div>"
        f"<div class='analysis-progress-wrap'><div class='analysis-progress-label'><span>Agent 研判进度 · {done_steps}/{total_steps} 阶段</span><b>{progress}%</b></div>"
        f"<div class='analysis-progress-track' role='progressbar' aria-valuemin='0' aria-valuemax='100' aria-valuenow='{progress}'><i style='width:{progress}%'></i></div></div>"
        f"<div class='analysis-metrics'>{metric_html}</div>"
        f"{_analysis_overview(report)}"
        f"<div class='analysis-columns'><div class='analysis-panel'><h3>主题聚类与信号分布</h3><ul class='topic-list'>{cluster_html}</ul></div>"
        f"<div class='analysis-panel'><h3>判断路径</h3><ol class='reasoning-list'>{steps_html}</ol></div></div>"
        f"<div class='analysis-panel impact-panel'><h3>业务影响模拟（研究用途）</h3><ul>{impact_html}</ul></div>"
        "</section>"
    )


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _deck_state(value: str) -> tuple[str, str]:
    normalized = (value or "observed").lower()
    mapping = {
        "observed": ("observed", "已观察"),
        "inferred": ("inferred", "推断"),
        "pending": ("pending", "待补"),
        "gap": ("pending", "研究缺口"),
    }
    return mapping.get(normalized, ("observed", "已观察"))


def _deck_card(
    number: int,
    card_id: str,
    chapter: str,
    title: str,
    content: str,
    *,
    state: str = "observed",
    featured: bool = False,
    conclusion: Optional[Dict[str, str]] = None,
) -> str:
    state_class, state_label = _deck_state(state)
    featured_class = " research-card-featured" if featured else ""
    conclusion_html = ""
    if conclusion:
        conclusion_html = (
            "<section class='card-conclusion' aria-label='本卡结论摘要'>"
            + "".join(
                f"<details class='card-conclusion-cell'><summary><span>{_esc(label)}</span><b>{_esc(str(conclusion.get(key) or '待核验'))}</b></summary><p>{_esc(str(conclusion.get(key) or '待核验'))}</p></details>"
                for key, label in (("time", "时间"), ("place", "地点"), ("object", "对象"),
                                    ("event", "事件"), ("result", "结果"), ("impact", "影响"),
                                    ("action", "行动"))
            )
            + "</section>"
        )
    return (
        f"<article id='{_esc(card_id)}' class='research-card{featured_class}' data-card-id='{_esc(card_id)}' data-card-number='{number:02d}'>"
        f"<header class='research-card-head'><span>{number:02d} · {_esc(chapter)}</span>"
        f"<em class='deck-state {state_class}'>{_esc(state_label)}</em></header>"
        f"{conclusion_html}<h3>{_esc(title)}</h3>{content}</article>"
    )


def _card_conclusion(
    report: Union[AiNews60sReport, WorldIntelReport],
    analysis: Dict[str, Any],
    *,
    card_id: str,
    title: str,
    state: str,
    team_name: str,
) -> Dict[str, str]:
    """Build a factual, compact conclusion tuple for every deck card.

    The tuple deliberately leads with *what happened and what to do next*;
    implementation/method details stay in the card body or its folded note.
    Missing fields are explicitly marked rather than invented.
    """
    sources = list(analysis.get("source_breakdown") or [])
    topics = list(analysis.get("topic_clusters") or [])
    signals = list(analysis.get("top_signals") or [])
    evidence = int(analysis.get("source_count") or 0)
    score = _as_number(analysis.get("evidence_score"))
    date = str(getattr(report, "data_cutoff", "") or "待核验")
    place = ", ".join(str(row.get("host")) for row in sources[:2] if row.get("host")) or "多来源域名"
    obj = str((topics[0].get("name") if topics else None) or (getattr(report, "related_companies", []) or [None])[0] or team_name)
    focal = str(signals[0].get("title") or "本轮信号") if signals else "本轮证据集合"
    why = getattr(report, "why_it_matters", []) or getattr(report, "market_transmission", []) or []
    impact_text = str(why[0]) if why else "影响待结合更多来源核验"
    actions = {
        "cover": "先读核心结论，再查看证据卡",
        "editor-note": "按重点结论继续核验",
        "executive-summary": "优先核验这些核心结论",
        "signal-landscape": "关注证据强度与覆盖边界",
        "evidence-pulse": "补充低覆盖来源",
        "two-state-gap": "同时追踪信号与反证",
        "confidence-bubble": "勿把覆盖度当成规模",
        "evidence-donut": "检查来源是否过度集中",
        "top-three": "优先核验前三主题",
        "source-ranking": "优先复核高质量来源",
        "dual-track": "补充地域与一手来源",
        "second-tier": "避免被头部来源主导",
        "focal-signal": "等待第二来源确认焦点信号",
        "flow-map": "核验主题到产业节点的链路",
        "pareto": "降低单一来源依赖",
        "evidence-hub": "把共现关系与因果分开",
        "uncertainty": "保留问题，不提前下结论",
        "adoption-cost-proxy": "积累跨期数据后再比较",
        "risk-quadrant": "先处理高影响高概率风险",
        "closing": "按缺口清单进入下一轮采集",
    }
    result = {
        "cover": focal,
        "editor-note": str(getattr(report, "headline", "") or focal),
        "contents": f"{evidence} 条证据已归档",
        "signal-landscape": f"综合证据分 {score:.2f}",
        "evidence-pulse": f"{evidence} 条证据来自 {len(sources)} 个来源域",
        "two-state-gap": f"{len(signals)} 条信号，{len(analysis.get('open_questions') or [])} 个待验证问题",
        "confidence-bubble": f"{len(topics)} 个主题簇",
        "evidence-donut": "来源结构已按域名拆分",
        "top-three": "、".join(str(row.get("name")) for row in topics[:3]) or "主题待定",
        "source-ranking": "按数量与质量线索排序",
        "dual-track": "地域仅作来源代理",
        "second-tier": "长尾来源需要补证",
        "focal-signal": focal,
        "flow-map": "主题到产业节点为研究性映射",
        "pareto": "头部来源集中度已计算",
        "evidence-hub": "主题共现关系已绘制",
        "uncertainty": "仍存在未关闭的不确定性",
        "adoption-cost-proxy": "跨期代理数据待积累" if not analysis.get("time_series") else "已形成跨期代理",
        "risk-quadrant": "风险按影响与概率分布",
        "closing": "结论可追溯，下一轮继续补证",
    }.get(card_id, title)
    return {"time": date, "place": place, "object": obj, "event": focal, "result": result,
            "impact": impact_text, "action": actions.get(card_id, "继续核验")}


def _deck_bar_list(rows: List[Dict[str, Any]], *, label_key: str, value_key: str, suffix: str = "") -> str:
    if not rows:
        return "<p class='deck-empty'>等待下一轮证据填充。</p>"
    maximum = max([_as_number(row.get(value_key)) for row in rows] or [1]) or 1
    items = []
    for row in rows[:6]:
        label = str(row.get(label_key) or "未命名")
        value = _as_number(row.get(value_key))
        width = min(100, max(4, int(value / maximum * 100)))
        rendered = f"{value:.0f}{suffix}" if value == int(value) else f"{value:.1f}{suffix}"
        items.append(
            "<li><div><b>" + _esc(label) + "</b><span>" + _esc(rendered) + "</span></div>"
            f"<i style='width:{width}%'></i></li>"
        )
    return "<ul class='deck-bars'>" + "".join(items) + "</ul>"


def _deck_donut(rows: List[Dict[str, Any]], *, value_key: str = "count") -> str:
    palette = ("#E63946", "#F4A261", "#52B788", "#5EA8FF", "#B794F4", "#E8D36A")
    values = [_as_number(row.get(value_key)) for row in rows[:6]]
    total = sum(values)
    if total <= 0:
        return "<div class='deck-gap-mini'>缺少可分布的已观察数据</div>"
    cursor = 0.0
    stops = []
    legend = []
    for index, (row, value) in enumerate(zip(rows[:6], values)):
        share = value / total * 100
        color = palette[index % len(palette)]
        stops.append(f"{color} {cursor:.1f}% {cursor + share:.1f}%")
        cursor += share
        legend.append(
            f"<li><i style='background:{color}'></i><span>{_esc(str(row.get('host') or row.get('name') or '未命名'))}</span>"
            f"<b>{share:.0f}%</b></li>"
        )
    return (
        "<div class='deck-donut-wrap'><div class='deck-donut' style='background:conic-gradient("
        + ",".join(stops)
        + ")'><span>证据<br/><b>分布</b></span></div><ul class='deck-legend'>"
        + "".join(legend)
        + "</ul></div>"
    )


def _confidence_explanation(score: float) -> str:
    if score >= 0.8:
        return "高可信：多来源、时效与交叉证据均较完整"
    if score >= 0.6:
        return "中高可信：已有交叉证据，但仍需补充一手来源"
    if score >= 0.4:
        return "中等可信：方向性信号成立，细节与因果仍需核验"
    return "低可信：仅能作为线索，不能据此形成事实判断"


def _deck_sparkline(series: List[Dict[str, Any]]) -> str:
    if len(series) < 2:
        return "<div class='deck-gap-mini'>至少需要两个日期节点，才能展示跨期脉冲。</div>"
    values = [_as_number(item.get("evidence_count")) for item in series[-12:]]
    scores = [_as_number(item.get("avg_signal_score")) for item in series[-12:]]
    count_max = max(values) or 1
    score_max = max(scores) or 1
    denominator = max(1, len(values) - 1)
    count_points = " ".join(
        f"{10 + index * 280 / denominator:.1f},{78 - value / count_max * 58:.1f}"
        for index, value in enumerate(values)
    )
    score_points = " ".join(
        f"{10 + index * 280 / denominator:.1f},{78 - value / score_max * 58:.1f}"
        for index, value in enumerate(scores)
    )
    first = _esc(str(series[-len(values)].get("date") or "—"))
    last = _esc(str(series[-1].get("date") or "—"))
    return (
        "<figure class='deck-sparkline'><svg viewBox='0 0 300 96' role='img' aria-label='证据数量与平均信号分的跨期脉冲'>"
        "<path d='M10 78H290M10 48H290M10 20H290' class='deck-gridline'/>"
        f"<polyline points='{count_points}' class='deck-line evidence'/>"
        f"<polyline points='{score_points}' class='deck-line signal'/>"
        "</svg><figcaption><span><i class='evidence'></i>证据数量</span><span><i class='signal'></i>平均信号分</span>"
        f"<small>{first} → {last}</small></figcaption></figure>"
    )


def _deck_hub(nodes: List[Dict[str, Any]]) -> str:
    if not nodes:
        return "<div class='deck-gap-mini'>没有足够主题节点形成证据枢纽。</div>"
    positions = ((148, 23), (246, 72), (218, 162), (78, 162), (50, 72), (148, 194))
    parts = ["<line x1='148' y1='103' x2='148' y2='23'/>"]
    labels = []
    for index, row in enumerate(nodes[:6]):
        x, y = positions[index]
        label = str(row.get("label") or row.get("name") or "主题")[:12]
        parts.append(f"<line x1='148' y1='103' x2='{x}' y2='{y}'/>")
        parts.append(f"<circle cx='{x}' cy='{y}' r='19' class='deck-hub-node n{index % 4}'/>")
        labels.append(f"<text x='{x}' y='{y + 4}'>{_esc(label)}</text>")
    return (
        "<figure class='deck-hub'><svg viewBox='0 0 296 220' role='img' aria-label='主题与证据来源枢纽图'>"
        "<g class='deck-hub-links'>" + "".join(parts) + "</g>"
        "<circle cx='148' cy='103' r='35' class='deck-hub-core'/><text x='148' y='99' class='deck-hub-core-text'>证据</text>"
        "<text x='148' y='113' class='deck-hub-core-text'>枢纽</text><g class='deck-hub-labels'>"
        + "".join(labels)
        + "</g></svg><figcaption>连线表示本轮共现/映射关系，不证明因果。</figcaption></figure>"
    )


def _deck_relationship_flow(edges: List[Dict[str, Any]]) -> str:
    if not edges:
        return "<div class='deck-gap-mini'>等待 Market Mapper 交付可追溯的主题—产业关系边。</div>"
    rows = []
    max_weight = max([_as_number(edge.get("weight")) for edge in edges] or [1]) or 1
    for edge in edges[:5]:
        width = min(100, max(8, int(_as_number(edge.get("weight")) / max_weight * 100)))
        rows.append(
            "<li><span>" + _esc(str(edge.get("from") or "主题")) + "</span><i style='width:"
            + str(width)
            + "%'></i><b>"
            + _esc(str(edge.get("to") or "节点"))
            + "</b></li>"
        )
    return "<div class='deck-flow'><div class='flow-labels'><span>主题信号</span><span>研究性产业映射</span></div><ul>" + "".join(rows) + "</ul><p>标记为“推断”：需由后续一手数据或人工核验确认。</p></div>"


def _deck_risk_quadrant(risks: List[Dict[str, Any]]) -> str:
    if not risks:
        return "<div class='deck-gap-mini'>等待风险与反证队列。</div>"
    labels = []
    for index, risk in enumerate(risks[:4]):
        impact = min(4, max(1, int(_as_number(risk.get("impact"), 2))))
        likelihood = min(4, max(1, int(_as_number(risk.get("likelihood"), 2))))
        left = 12 + (likelihood - 1) / 3 * 72
        bottom = 10 + (impact - 1) / 3 * 66
        labels.append(
            f"<span class='risk-dot r{index % 4}' style='left:{left:.0f}%;bottom:{bottom:.0f}%'>"
            f"{_esc(str(risk.get('risk') or '风险'))}</span>"
        )
    return (
        "<div class='risk-quadrant'><span class='risk-axis risk-x'>发生概率 →</span><span class='risk-axis risk-y'>影响程度 ↑</span>"
        "<i class='risk-v'></i><i class='risk-h'></i>" + "".join(labels) + "</div>"
    )


def _deck_gap(gaps: List[Dict[str, Any]], default: str) -> str:
    gap = gaps[0] if gaps else {"field": "待补充数据", "reason": default, "owner": "对应 Agent"}
    return (
        "<div class='deck-gap'><b>不能用装饰性数字替代真实证据</b>"
        f"<strong>{_esc(str(gap.get('field') or '待补充数据'))}</strong>"
        f"<p>{_esc(str(gap.get('reason') or default))}</p>"
        f"<span>下一棒：{_esc(str(gap.get('owner') or '对应 Agent'))}</span></div>"
    )


def _deck_analysis(report: Union[AiNews60sReport, WorldIntelReport]) -> Dict[str, Any]:
    """Return a complete, backward-compatible input contract for all cards."""
    analysis = dict(getattr(report, "analysis", {}) or {})
    citations = list(getattr(report, "citations", []) or [])
    if not analysis.get("source_breakdown"):
        grouped: Dict[str, int] = {}
        for citation in citations:
            host = (urlparse(getattr(citation, "url", "")).netloc or "未标注来源").lower()
            grouped[host] = grouped.get(host, 0) + 1
        analysis["source_breakdown"] = [
            {"host": host, "count": count, "share": round(count / max(1, len(citations)), 2), "avg_score": 0}
            for host, count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
        ]
    analysis.setdefault("source_count", len(citations))
    analysis.setdefault("source_diversity", len(analysis.get("source_breakdown") or []))
    analysis.setdefault("freshness_ratio", 0.0)
    analysis.setdefault("evidence_score", 0.0)
    analysis.setdefault("signal_strength", "待定")
    analysis.setdefault("topic_clusters", [])
    analysis.setdefault("top_signals", [])
    analysis.setdefault("score_distribution", [])
    analysis.setdefault("timeline", [])
    analysis.setdefault("time_series", [])
    analysis.setdefault("entity_metrics", [])
    analysis.setdefault("relationship_edges", [])
    analysis.setdefault("risk_matrix", [])
    analysis.setdefault("open_questions", [])
    analysis.setdefault("business_implications", [])
    analysis.setdefault("coverage_gaps", [])
    return analysis


def _world_display_title(report: WorldIntelReport) -> str:
    """Recover a useful cover title from citations for older URL-first runs."""
    current = str(report.what_happened.text or "").strip()
    if current and not current.startswith("来源条目缺少可读标题"):
        return current
    for citation in report.citations:
        title = str(getattr(citation, "title", "") or "").strip()
        if title and not title.startswith("http") and title.lower() != "fallback":
            return title
    return "本轮世界趋势待观察"


def _ai_display_title(report: AiNews60sReport, analysis: Optional[Dict[str, Any]] = None) -> str:
    """Use the strongest observed event as the AI deck cover headline.

    The thematic report headline describes the method/run; the cover must tell
    a reader what actually happened in this collection round. Prefer the
    scored, readable signal and fall back to a citation title or the thematic
    headline when the round has no usable event title.
    """
    data = analysis or _deck_analysis(report)
    candidates: List[str] = []
    for row in data.get("top_signals") or []:
        candidates.append(str(row.get("title") or "").strip())
    for citation in report.citations:
        candidates.append(str(getattr(citation, "title", "") or "").strip())
    candidates.append(str(report.headline or "").strip())
    for candidate in candidates:
        parsed = urlparse(candidate)
        is_url_only = parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not any(ch.isspace() for ch in candidate)
        if candidate and not is_url_only and candidate not in {"暂无高分信号", "未命名证据", "fallback"}:
            return candidate
    return "等待本轮研究结论"


def _research_overview_deck(report: Union[AiNews60sReport, WorldIntelReport], *, team_name: str) -> str:
    """Render all 20 overview card grammars as a static research deck.

    The deck borrows the *visual grammar* of the reference PPT Master project
    (editorial dark canvas, KPI, ranking, comparison, flow, risk and closing),
    while each number remains tied to the current run's evidence contract.
    """
    analysis = _deck_analysis(report)
    sources = list(analysis.get("source_breakdown") or [])
    topics = list(analysis.get("topic_clusters") or [])
    signals = list(analysis.get("top_signals") or [])
    timeline = list(analysis.get("time_series") or [])
    metrics = list(analysis.get("entity_metrics") or [])
    edges = list(analysis.get("relationship_edges") or [])
    risks = list(analysis.get("risk_matrix") or [])
    gaps = list(analysis.get("coverage_gaps") or [])
    citations = list(getattr(report, "citations", []) or [])
    evidence_count = int(analysis.get("source_count") or 0)
    diversity = int(analysis.get("source_diversity") or 0)
    score = _as_number(analysis.get("evidence_score"))
    freshness = _as_number(analysis.get("freshness_ratio"))
    title = _ai_display_title(report, analysis) if isinstance(report, AiNews60sReport) else _world_display_title(report)
    title = str(title or "等待本轮研究结论")
    subtitle = f"{team_name} · {evidence_count} 条证据 · {diversity} 个来源域名 · 截止 {report.data_cutoff}"
    topic_max = max([_as_number(row.get("count")) for row in topics] or [1]) or 1
    high_confidence = sum(1 for row in signals if _as_number(row.get("score")) >= 70)
    domestic = sum(int(row.get("count") or 0) for row in sources if str(row.get("host") or "").lower().endswith(".cn"))
    outside = max(0, sum(int(row.get("count") or 0) for row in sources) - domestic)
    top_three = topics[:3]
    long_tail = sources[3:] or sources[1:]
    cards: List[str] = []

    def card(number: int, card_id: str, chapter: str, card_title: str, content: str, **kwargs: Any) -> str:
        state = str(kwargs.get("state", "observed"))
        return _deck_card(
            number, card_id, chapter, card_title, content,
            state=state, featured=bool(kwargs.get("featured", False)),
            conclusion=_card_conclusion(report, analysis, card_id=card_id, title=card_title, state=state, team_name=team_name),
        )

    cards.append(card(1, "cover", "COVER", "本轮信号档案", "<div class='deck-cover-copy'><p>" + _esc(title) + "</p><small>" + _esc(subtitle) + "</small><div class='deck-cover-rule'></div><span>研究 / 模拟用途 · 非投资建议 · 无真实券商连接</span></div>", featured=True))
    # The first cards are conclusions, not documentation about the method.  The
    # reader should see what this run found immediately after the cover.
    conf_label = "高" if score >= 0.8 else "中高" if score >= 0.6 else "中" if score >= 0.4 else "低"
    confidence_note = _confidence_explanation(score)
    evidence_mix = (
        "<div class='deck-evidence-mix'><article><h4>证据类别分布</h4>"
        + _deck_donut(topics)
        + "</article><article><h4>来源域分布</h4>"
        + _deck_donut(sources)
        + "</article></div>"
    )
    exec_kpis = (
        "<div class='deck-kpis deck-exec-kpis'>"
        f"<div><span>结论</span><b>{_esc(title[:48])}</b><small>headline</small></div>"
        f"<div><span>置信</span><b>{_esc(conf_label)}</b><small>综合 {score:.2f} · {_esc(confidence_note)}</small></div>"
        f"<div><span>证据</span><b>{evidence_count}</b><small>按主题类别分布 · as_of {_esc(str(report.data_cutoff)[:16])}</small></div>"
        f"<div><span>来源域</span><b>{diversity}</b><small>三块来源域分布</small></div>"
        "</div>"
    )
    if isinstance(report, AiNews60sReport):
        conclusion = (
            exec_kpis
            + evidence_mix
            + _claim_block(report.bullets[:4], "本轮关键发现")
            + _claim_block(report.why_it_matters[:3], "为什么重要")
            + "<details class='deck-method'><summary>方法与口径（折叠）</summary>"
            "<p>文本标准化 → 主题聚类 → 新颖性/时效/来源评分。本卡结论来自本轮 report，不是固定模板文案。</p></details>"
        )
        impact = _claim_block(report.risks_and_counterpoints[:3], "反证与限制") + "<p class='deck-card-meta'>影响映射：" + _esc("、".join(report.related_companies[:4]) or "暂无可确认产业节点") + "</p>"
    else:
        world_claims = [report.what_happened] + list(report.timeline[:2]) + list(report.market_transmission[:1])
        conclusion = (
            exec_kpis
            + evidence_mix
            + _claim_block(world_claims, "本轮多条结论")
            + _claim_block(report.drivers[:3], "关键驱动")
            + "<details class='deck-method'><summary>方法与口径（折叠）</summary>"
            "<p>事件卡、时间线与情景树均绑定本轮证据；情景为分析框架非预测保证。</p></details>"
        )
        impact = _claim_block(report.market_transmission[:3], "市场传导") + _claim_block(report.views_and_counterpoints[:3], "反证与限制")
    cards.append(card(2, "editor-note", "EXECUTIVE FINDING", "编辑结论 · 本轮核心判断", conclusion, state="observed" if evidence_count else "gap", featured=True))
    # CONTENTS: real status + one-line abstract + jump anchors for remaining deck cards
    toc_specs = [
        ("cover", "observed" if title else "gap", "封面结论"),
        ("editor-note", "observed" if evidence_count else "gap", "编辑结论"),
        ("signal-landscape", "observed" if evidence_count else "gap", "证据版图 KPI"),
        ("evidence-pulse", "observed" if sources else "gap", "来源热度"),
        ("confidence-bubble", "observed" if topics else "gap", "主题密度"),
        ("top-three", "observed" if top_three else "gap", "前三主题"),
        ("focal-signal", "observed" if signals else "pending", "焦点信号"),
        ("flow-map", "inferred" if edges else "gap", "传导路径"),
        ("risk-quadrant", "inferred" if risks else "gap", "风险矩阵"),
        ("closing", "inferred", "下一步与边界"),
    ]
    summary_html = _claim_block(
        (report.bullets[:5] if isinstance(report, AiNews60sReport) else ([report.what_happened] + list(report.drivers[:2]) + list(report.market_transmission[:2]))),
        "本轮核心结论",
    ) + impact
    cards.append(card(3, "executive-summary", "EXECUTIVE SUMMARY", "结论摘要 · 先看发生了什么", summary_html, state="observed" if evidence_count else "gap"))
    kpis = "<div class='deck-kpis'><div><span>证据</span><b>" + str(evidence_count) + "</b><small>已标准化条目</small></div><div><span>来源</span><b>" + str(diversity) + "</b><small>独立域名</small></div><div><span>综合</span><b>" + f"{score:.2f}" + "</b><small>覆盖/时效评分</small></div><div><span>时效</span><b>" + f"{freshness:.0%}" + "</b><small>7 日内证据</small></div></div>"
    cards.append(card(4, "signal-landscape", "LANDSCAPE", "证据版图：本轮四个控制面", kpis))
    cards.append(card(5, "evidence-pulse", "EVIDENCE PULSE", "来源热度与信号脉冲", _deck_bar_list(sources, label_key="host", value_key="count", suffix=" 条")))
    dumbbell = "<div class='deck-dumbbell'><div><span>已观察信号</span><b>" + str(high_confidence) + "</b></div><i></i><div><span>待验证问题</span><b>" + str(len(analysis.get("open_questions") or [])) + "</b></div><p>左侧是高分证据条目，右侧是未被证据关闭的研究问题。</p></div>"
    cards.append(card(6, "two-state-gap", "COMPARISON", "信号与反证的双端张力", dumbbell, state="inferred"))
    if topics:
        bubbles = "".join("<span class='deck-bubble b" + str(index % 5) + "' style='--size:" + str(44 + int(_as_number(row.get("count")) / topic_max * 68)) + "px'><b>" + _esc(str(row.get("name") or "主题")) + "</b><small>" + str(int(row.get("count") or 0)) + " 条</small></span>" for index, row in enumerate(topics[:5]))
        bubble_content = "<div class='deck-bubbles'>" + bubbles + "</div><p class='deck-caption'>气泡面积按证据条数缩放；它表示议题覆盖，不表示市场规模。</p>"
    else:
        bubble_content = _deck_gap(gaps, "等待主题聚类结果。")
    cards.append(card(7, "confidence-bubble", "CONFIDENCE", "主题密度气泡：看见覆盖，不夸大规模", bubble_content, state="observed" if topics else "gap"))
    cards.append(card(8, "evidence-donut", "SOURCE MIX", "来源结构：证据来自哪里", _deck_donut(sources)))
    if top_three:
        comparisons = "<div class='deck-three'>" + "".join("<article><span>#" + str(index + 1) + "</span><h4>" + _esc(str(row.get("name") or "主题")) + "</h4><strong>" + f"{_as_number(row.get('share')):.0%}" + "</strong><p>" + str(int(row.get("count") or 0)) + " 条证据</p><small>" + _esc("；".join((row.get("examples") or [])[:1])) + "</small></article>" for index, row in enumerate(top_three)) + "</div>"
    else:
        comparisons = _deck_gap(gaps, "等待可比较的主题簇。")
    cards.append(card(9, "top-three", "TOP THREE", "前三主题：证据份额与代表性样本", comparisons, state="observed" if top_three else "gap"))
    cards.append(card(10, "source-ranking", "RANKING", "来源排名：数量与质量线索", _deck_bar_list(sources, label_key="host", value_key="avg_score", suffix=" 分")))
    dual_track = "<div class='deck-dual-track'><article><span>域名 .cn</span><b>" + str(domestic) + "</b><small>条引用（域名后缀代理）</small></article><article><span>其他域名</span><b>" + str(outside) + "</b><small>条引用（不代表市场归属）</small></article><p>本卡只比较来源域名分布，不能据此判断公司、资本或市场地域。</p></div>"
    cards.append(card(11, "dual-track", "DUAL TRACK", "双轨视角：来源地域代理", dual_track, state="inferred"))
    tail_content = _deck_bar_list(long_tail, label_key="host", value_key="count", suffix=" 条") if long_tail else _deck_gap(gaps, "来源长尾尚未形成；建议增加独立 RSS 或官方一手来源。")
    cards.append(card(12, "second-tier", "LONG TAIL", "第二梯队：避免被头部来源主导", tail_content, state="observed" if long_tail else "gap"))
    focal = signals[0] if signals else {}
    focal_content = "<div class='deck-focal'><span>本轮最强线索</span><h4>" + _esc(str(focal.get("title") or title)) + "</h4><div><b>" + f"{_as_number(focal.get('score')):.0f}" + "</b><small>信号分（新颖性 / 时效 / 来源质量）</small></div><p>" + _esc("、".join(focal.get("topics") or [])) + "</p></div>"
    cards.append(card(13, "focal-signal", "FOCAL SIGNAL", "本轮信号中心", focal_content, state="observed" if focal else "pending", featured=True))
    cards.append(card(14, "flow-map", "FLOW MAP", "主题 → 产业节点：待核验的传导路径", _deck_relationship_flow(edges), state="inferred" if edges else "gap"))
    pareto_rows = []
    running = 0
    total_sources = sum(int(row.get("count") or 0) for row in sources) or 1
    for row in sources[:6]:
        running += int(row.get("count") or 0)
        pareto_rows.append({"host": row.get("host"), "count": row.get("count"), "cumulative": round(running / total_sources * 100)})
    pareto = "<ul class='deck-pareto'>" + "".join("<li><b>" + _esc(str(row.get("host") or "来源")) + "</b><i style='width:" + str(int(_as_number(row.get("cumulative")))) + "%'></i><span>累计 " + str(int(_as_number(row.get("cumulative")))) + "%</span></li>" for row in pareto_rows) + "</ul>"
    cards.append(card(15, "pareto", "PARETO", "集中度：头部来源占了多少证据", pareto if pareto_rows else _deck_gap(gaps, "等待来源分布。"), state="observed" if pareto_rows else "gap"))
    hub_nodes = (analysis.get("evidence_graph") or {}).get("nodes") or [{"label": row.get("name"), "count": row.get("count")} for row in topics]
    cards.append(card(16, "evidence-hub", "EVIDENCE HUB", "证据枢纽：主题共现关系", _deck_hub(hub_nodes), state="inferred" if hub_nodes else "gap"))
    questions = analysis.get("open_questions") or []
    uncertainty = "<div class='deck-uncertainty'><b>证据综合 {0:.2f}</b><span>已关闭的只是证据缺口，不是未来的不确定性。</span><ul>".format(score) + "".join("<li>" + _esc(str(question)) + "</li>" for question in questions[:4]) + "</ul></div>"
    cards.append(card(17, "uncertainty", "UNCERTAINTY", "泡沫问题：哪些结论还不能说", uncertainty, state="inferred"))
    proxy = _deck_sparkline(timeline) if len(timeline) >= 2 else _deck_gap(gaps, "仅有单期数据；用跨期证据量和平均信号分作为研究代理，不绘制虚构的收入或资本开支曲线。")
    cards.append(card(18, "adoption-cost-proxy", "TIME SERIES", "跨期代理：证据量与平均信号分", proxy, state="observed" if len(timeline) >= 2 else "gap"))
    cards.append(card(19, "risk-quadrant", "FOUR RISKS", "四象限：证据、时效、因果与结论风险", _deck_risk_quadrant(risks), state="inferred" if risks else "gap"))
    next_owner = " · ".join(str(gap.get("owner") or "对应 Agent") for gap in gaps[:2]) or "下一轮由 Scout / Checker / Analyst 继续补证"
    closing = "<div class='deck-closing'><p>" + _esc(title) + "</p><dl><dt>下一步</dt><dd>" + _esc(next_owner) + "</dd><dt>边界</dt><dd>研究与模拟用途，非投资建议；无真实券商连接。</dd></dl><span>本报告基于 " + str(len(citations)) + " 条可回溯引用生成</span></div>"
    cards.append(card(20, "closing", "CLOSING", "结论不是终点，而是下一轮核验的起点", closing, state="inferred", featured=True))
    return (
        "<section class='research-deck' aria-labelledby='research-deck-title'><header class='research-deck-title'>"
        "<div><span>OVERVIEW · 20 CARD RESEARCH DECK</span><h2 id='research-deck-title'>" + _esc(team_name) + " · 深度报告卡片组</h2>"
        "<p>覆盖、比较、结构、关系、风险与缺口都来自本轮可追溯证据；数值卡会标记观察、推断或待补。</p></div>"
        f"<b>{evidence_count} 条证据 / {len(citations)} 个引用</b></header><div class='research-deck-grid'>"
        + "".join(cards)
        + "</div></section>"
    )


def render_ai60(report: AiNews60sReport) -> str:
    companies = "".join(f"<li>{_esc(c)}</li>" for c in report.related_companies) or "<li>无</li>"
    body = f"""
<article class="hugohe3-doc" data-channel="ai_news_60s" data-run="{_esc(report.run_id)}">
  <header>
    <p class="kicker">60 秒 AI · 数据截止 <time datetime="{_esc(report.data_cutoff)}">{_esc(report.data_cutoff)}</time></p>
    <h1>{_esc(report.headline)}</h1>
    <p class="disclaimer" role="note">{_esc(report.disclaimer)}</p>
  </header>
  {_ai60_timeline()}
  <p class='cadence-note'>“60 秒”指播报结构，不是刷新频率；工作台默认每 30 分钟采集，实际以定时任务配置为准。</p>
  {_analysis_dashboard(report)}
  {_research_overview_deck(report, team_name="AI 60 秒 · 研判驾驶舱")}
  {_ai60_signal_map(report)}
  {_claim_block(report.bullets, "快讯")}
  {_claim_block(report.why_it_matters, "为什么重要")}
  <section aria-labelledby="h-companies">
    <h2 id="h-companies">相关公司/赛道（非投资建议）</h2>
    <ul>{companies}</ul>
  </section>
  {_claim_block(report.risks_and_counterpoints, "风险与反证")}
  {_citations_block(report.citations)}
  <footer><p>运行 ID: <code>{_esc(report.run_id)}</code></p></footer>
</article>
"""
    return _wrap(body, report.model_dump(), chart_alt="AI 快讯无额外图表")


def render_world(report: WorldIntelReport) -> str:
    scenarios = ["<section class='scenario-slide' aria-labelledby='h-scen'><div class='slide-kicker'>SCENARIO BOARD · 16:9 STORYBOARD</div><h2 id='h-scen'>三情景树</h2><div class='scenario-grid'>"]
    for s in report.scenarios:
        triggers = "; ".join(s.trigger_conditions)
        scenarios.append(
            f"<article class='scenario-card'><span class='scenario-name'>{_esc(s.name)}</span>"
            f"<strong>{_esc(s.summary)}</strong><p>触发条件：{_esc(triggers)}</p>"
            f"<em>不确定性：{_esc(s.uncertainty)}</em></article>"
        )
    scenarios.append("</div></section>")
    body = f"""
<article class="hugohe3-doc" data-channel="dufu_world_intel" data-run="{_esc(report.run_id)}">
  <header class='deck-cover'>
    <div class='slide-kicker'>WORLD INTEL · EDITORIAL BOARD</div>
    <p class="kicker">世界趋势 · 数据截止 <time datetime="{_esc(report.data_cutoff)}">{_esc(report.data_cutoff)}</time></p>
    <h1>{_esc(_world_display_title(report))}</h1>
    <p class="disclaimer" role="note">{_esc(report.disclaimer)}</p>
  </header>
  {_research_overview_deck(report, team_name="独夫之心 · 世界趋势研判")}
  <div class='deck-section-grid'><div class='deck-slide'>{_claim_block(report.timeline, "历史时间线")}</div><div class='deck-slide'>{_claim_block(report.drivers, "核心驱动因素")}</div><div class='deck-slide'>{_claim_block(report.data_trends, "数据与趋势")}</div><div class='deck-slide'>{_claim_block(report.views_and_counterpoints, "观点与反证")}</div></div>
  {"".join(scenarios)}
  <div class='deck-slide'>{_claim_block(report.market_transmission, "市场传导路径（非投资建议）")}</div>
  {_citations_block(report.citations)}
  <footer><p>运行 ID: <code>{_esc(report.run_id)}</code></p></footer>
</article>
"""
    chart = {
        "scenarios": [{"name": s.name, "triggers": s.trigger_conditions} for s in report.scenarios]
    }
    return _wrap(body, report.model_dump(), chart_data=chart, chart_alt="情景树：乐观/基准/悲观及触发条件")


def _wrap(
    body: str,
    report_data: Dict[str, Any],
    *,
    chart_data: Optional[Dict[str, Any]] = None,
    chart_alt: str = "",
) -> str:
    chart_block = ""
    if chart_data:
        chart_block = (
            f"<figure class='chart' role='img' aria-label='{_esc(chart_alt)}'>"
            f"<pre class='chart-data' data-chart='{safe_json(chart_data)}'>"
            f"{_esc(chart_alt)}</pre>"
            f"<figcaption>{_esc(chart_alt)}</figcaption></figure>"
        )
    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none';"/>
  <title>StockAgents Document</title>
  <style>
    :root {{ --fg:#0f172a; --muted:#64748b; --bg:#f8fafc; --card:#fff; --line:#e2e8f0; --acc:#0d9488; }}
    body {{ margin:0; font-family:system-ui,-apple-system,"PingFang SC","Noto Sans SC",sans-serif; background:var(--bg); color:var(--fg); line-height:1.55; }}
    .hugohe3-shell {{ max-width:920px; margin:0 auto; padding:24px 16px 48px; }}
    .hugohe3-doc {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:24px; }}
    h1 {{ font-size:1.45rem; margin:0 0 12px; }}
    h2 {{ font-size:1.1rem; margin:1.4rem 0 .6rem; color:var(--acc); }}
    .kicker,.disclaimer {{ color:var(--muted); font-size:.9rem; }}
    .claim-label {{ display:inline-block; font-size:.75rem; text-transform:uppercase; background:#ecfeff; color:#0e7490; padding:1px 6px; border-radius:4px; }}
    .uncertainty {{ color:var(--muted); font-size:.85rem; }}
    a {{ color:#0369a1; }}
    .chart {{ margin:1rem 0; padding:12px; background:#f1f5f9; border-radius:8px; }}
    .chart-data {{ white-space:pre-wrap; font-size:.8rem; margin:0; }}
    .signal-map {{ margin:1.1rem 0; padding:14px; border:1px solid #dbe4ee; border-radius:12px; background:linear-gradient(135deg,#f8fafc,#eef8f7); }}
    .signal-map-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; color:#0f766e; font-weight:700; font-size:.9rem; }}
    .legend {{ color:#64748b; font-size:.72rem; font-weight:500; display:flex; align-items:center; gap:5px; }}
    .legend-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; border:1px solid #94a3b8; }}
    .legend-dot.fact {{ background:#dbeafe; }} .legend-dot.exposure {{ background:#fef3c7; }} .legend-dot.hub {{ background:#0f766e; border-color:#115e59; }}
    .signal-map svg {{ width:100%; height:auto; display:block; margin-top:6px; }}
    .signal-edge {{ stroke:#94a3b8; stroke-width:1.5; opacity:.55; }}
    .signal-node text {{ font:600 10px system-ui,-apple-system,"PingFang SC",sans-serif; }}
    .signal-node .node-detail {{ font-size:8px; font-weight:400; }}
    .signal-map figcaption {{ color:#64748b; font-size:.76rem; margin-top:5px; }}
    .analysis-dashboard {{ margin:1.2rem 0; padding:16px; border:1px solid #c7dce8; border-radius:14px; background:linear-gradient(145deg,#f8fcff,#effaf7); box-shadow:0 10px 25px rgba(15,118,110,.07); }}
    .analysis-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }} .analysis-kicker {{ color:#0f766e; font-size:.66rem; letter-spacing:.14em; font-weight:900; }} .analysis-head h2 {{ margin:.25rem 0 .2rem; color:#0f172a; }} .analysis-head p {{ margin:0; color:#64748b; font-size:.8rem; }} .analysis-pulse {{ color:#0f766e; font-size:.68rem; font-weight:900; animation:analysis-pulse 1.8s ease-in-out infinite; white-space:nowrap; }}
    @keyframes analysis-pulse {{ 0%,100% {{ opacity:.45; transform:translateY(0); }} 50% {{ opacity:1; transform:translateY(-2px); }} }}
    .analysis-progress-wrap {{ margin:13px 0 2px; }} .analysis-progress-label {{ display:flex; justify-content:space-between; gap:8px; color:#64748b; font-size:.68rem; }} .analysis-progress-label b {{ color:#0f766e; font-size:.74rem; }} .analysis-progress-track {{ height:7px; margin-top:5px; overflow:hidden; border-radius:99px; background:#dcecef; box-shadow:inset 0 1px 2px rgba(15,118,110,.08); }} .analysis-progress-track i {{ display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#0f766e,#38bdf8,#6366f1); transition:width .5s ease; }}
    .analysis-metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:7px; margin:13px 0; }} .analysis-metric {{ padding:9px; border:1px solid #d5e8ef; border-radius:9px; background:#fff; }} .analysis-metric span,.analysis-metric strong {{ display:block; }} .analysis-metric span {{ color:#64748b; font-size:.68rem; }} .analysis-metric strong {{ margin-top:3px; color:#0f766e; font-size:1.1rem; }}
    .analysis-overview {{ margin:11px 0 9px; padding:11px; border:1px solid #d8e7ed; border-radius:10px; background:rgba(255,255,255,.62); }} .overview-heading {{ display:flex; justify-content:space-between; align-items:flex-end; gap:8px; margin-bottom:8px; }} .overview-heading h3 {{ margin:.2rem 0 0; color:#334155; font-size:.86rem; }} .overview-count {{ color:#64748b; font-size:.67rem; white-space:nowrap; }} .overview-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }} .overview-card {{ min-width:0; padding:9px; border:1px solid #e1edf1; border-radius:8px; background:#fff; }} .overview-card.overview-wide {{ grid-column:1 / -1; }} .overview-card h4 {{ margin:0 0 6px; color:#475569; font-size:.73rem; }} .overview-card ul {{ list-style:none; margin:0; padding:0; }} .overview-card li {{ min-width:0; padding:4px 0; border-bottom:1px solid #f0f4f6; }} .overview-row {{ display:flex; justify-content:space-between; align-items:baseline; gap:7px; min-width:0; font-size:.68rem; }} .overview-row b {{ min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#334155; font-weight:700; }} .overview-row span {{ color:#64748b; font-size:.64rem; white-space:nowrap; }} .overview-track {{ height:4px; margin-top:4px; overflow:hidden; border-radius:99px; background:#e7f1f4; }} .overview-track i {{ display:block; height:100%; min-width:4px; border-radius:inherit; background:linear-gradient(90deg,#0f766e,#60a5fa); }} .overview-track.score i {{ background:linear-gradient(90deg,#f59e0b,#ef4444); }} .overview-track.timeline i {{ background:linear-gradient(90deg,#6366f1,#38bdf8); }} .overview-track.signal i {{ background:linear-gradient(90deg,#10b981,#0f766e); }} .overview-tag {{ padding:1px 5px; border-radius:4px; background:#ecfeff; color:#0e7490 !important; font-size:.58rem !important; }} .overview-detail {{ margin:4px 0 0; color:#64748b; font-size:.64rem; line-height:1.4; }} .overview-expand summary {{ cursor:zoom-in; list-style:none; }} .overview-expand summary::-webkit-details-marker {{ display:none; }} .overview-expand[open] summary {{ cursor:zoom-out; }} .overview-expand[open] .overview-row b {{ overflow:visible; text-overflow:clip; white-space:normal; }} .overview-stage {{ display:flex; align-items:center; gap:6px; }} .overview-stage b {{ flex:1; color:#334155; font-size:.67rem; }} .overview-stage span:last-child {{ color:#0f766e; font-size:.6rem; }} .overview-stage-dot {{ width:7px; height:7px; flex:none; border-radius:50%; background:#cbd5e1; }} .overview-stage-dot.done {{ background:#10b981; box-shadow:0 0 0 3px #d1fae5; }} .question-mark {{ display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; margin-right:5px; border-radius:50%; background:#fff7ed; color:#c2410c; font-weight:800; font-size:.62rem; }} .overview-empty {{ color:#94a3b8; font-size:.68rem; }}
    .analysis-columns {{ display:grid; grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr); gap:9px; align-items:stretch; }} .analysis-columns > * {{ min-width:0; }} .analysis-panel {{ min-width:0; padding:11px; border:1px solid #d8e7ed; border-radius:10px; background:rgba(255,255,255,.8); overflow:hidden; }} .analysis-panel h3 {{ margin:0 0 8px; font-size:.83rem; color:#334155; }} .topic-list,.reasoning-list,.impact-panel ul {{ list-style:none; padding:0; margin:0; }} .topic-list li {{ min-width:0; padding:6px 0; border-bottom:1px solid #edf3f5; }} .topic-line {{ display:flex; justify-content:space-between; gap:8px; min-width:0; font-size:.76rem; }} .topic-line b,.topic-line span {{ min-width:0; overflow-wrap:anywhere; }} .topic-line span,.topic-list small {{ color:#64748b; font-size:.68rem; }} .topic-list small {{ display:block; margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }} .topic-track {{ height:5px; background:#e7f1f4; border-radius:9px; overflow:hidden; margin-top:4px; }} .topic-track i {{ display:block; height:100%; min-width:4px; border-radius:9px; background:linear-gradient(90deg,#0f766e,#60a5fa); }}
    .reasoning-step {{ display:flex; align-items:flex-start; gap:7px; min-width:0; padding:6px 0; border-bottom:1px solid #edf3f5; }} .step-dot {{ width:8px; height:8px; margin-top:4px; border-radius:50%; background:#0f766e; box-shadow:0 0 0 3px #d5f5ee; flex:none; }} .reasoning-step div {{ flex:1; min-width:0; overflow-wrap:anywhere; }} .reasoning-step b,.reasoning-step small {{ display:block; }} .reasoning-step b {{ font-size:.75rem; }} .reasoning-step small {{ color:#64748b; font-size:.68rem; line-height:1.4; margin-top:2px; }} .reasoning-step em {{ color:#0f766e; font-style:normal; font-size:.63rem; white-space:nowrap; }} .impact-panel {{ margin-top:9px; }} .impact-panel li {{ padding:6px 0; border-bottom:1px solid #edf3f5; font-size:.76rem; line-height:1.5; overflow-wrap:anywhere; }}
    .seconds-strip {{ display:grid; grid-template-columns:repeat(6,1fr); gap:5px; margin:1rem 0 1.2rem; }}
    .seconds-strip div {{ padding:8px 6px; border-radius:7px; background:#f1f5f9; border-top:3px solid #0f766e; }}
    .seconds-strip div:nth-child(2) {{ border-color:#38bdf8; }} .seconds-strip div:nth-child(3) {{ border-color:#6366f1; }}
    .seconds-strip div:nth-child(4) {{ border-color:#f59e0b; }} .seconds-strip div:nth-child(5) {{ border-color:#f97316; }} .seconds-strip div:nth-child(6) {{ border-color:#94a3b8; }}
    .seconds-strip b,.seconds-strip span {{ display:block; }} .seconds-strip b {{ font-size:.78rem; }} .seconds-strip span {{ color:#64748b; font-size:.72rem; margin-top:2px; }}
    .cadence-note {{ margin:-8px 0 13px; color:#64748b; font-size:.72rem; }}
    .deck-cover {{ padding:20px; margin:-24px -24px 18px; background:linear-gradient(135deg,#102a43,#0f766e); color:#fff; border-radius:12px 12px 0 0; }}
    .deck-cover .kicker,.deck-cover .disclaimer {{ color:#d7f5ef; }} .slide-kicker {{ color:#72e2d1; letter-spacing:.14em; font-size:.67rem; font-weight:800; }}
    .deck-section-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }} .deck-slide,.scenario-slide {{ border:1px solid #dbe4ee; border-radius:10px; padding:14px; background:#fff; }}
    .deck-slide section {{ border:0; padding:0; }} .deck-slide h2,.scenario-slide h2 {{ margin-top:.3rem; }} .scenario-slide {{ margin-top:12px; background:#f8fafc; }}
    .scenario-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:9px; }} .scenario-card {{ padding:12px; background:#fff; border:1px solid #e2e8f0; border-radius:9px; }}
    .scenario-card:nth-child(1) {{ border-top:3px solid #10b981; }} .scenario-card:nth-child(2) {{ border-top:3px solid #f59e0b; }} .scenario-card:nth-child(3) {{ border-top:3px solid #ef4444; }}
    .scenario-name {{ display:block; color:#0f766e; font-size:.72rem; font-weight:800; text-transform:uppercase; }} .scenario-card strong {{ display:block; margin-top:5px; font-size:.9rem; }} .scenario-card p,.scenario-card em {{ color:#64748b; font-size:.78rem; }}
    .research-deck {{ margin:20px 0; padding:16px; border:1px solid #2c3440; border-radius:15px; background:radial-gradient(circle at 94% 0%,rgba(230,57,70,.16),transparent 26%),radial-gradient(circle at 0% 32%,rgba(94,168,255,.13),transparent 30%),#0e1116; color:#e8e6e1; box-shadow:0 18px 42px rgba(15,23,42,.18); }}
    .deck-method {{ margin-top:10px; color:#9eabbc; font-size:.72rem; }} .deck-method summary {{ cursor:pointer; color:#f4a261; }}
    .deck-toc ul {{ list-style:none; margin:0; padding:0; display:grid; gap:6px; }} .deck-toc li a {{ display:grid; grid-template-columns:1fr auto; gap:4px 10px; padding:8px 9px; border:1px solid #2a313c; border-radius:8px; color:#e8e6e1; text-decoration:none; }} .deck-toc li a:hover {{ border-color:#e63946; }} .deck-toc span {{ grid-column:1/-1; color:#9eabbc; font-size:.68rem; }}
    .deck-exec-kpis b {{ font-size:.85rem; line-height:1.25; }}
    .research-deck-title {{ display:flex; align-items:flex-end; justify-content:space-between; gap:15px; padding:5px 5px 16px; border-bottom:1px solid #2c3440; }} .research-deck-title span {{ color:#e63946; font-size:.64rem; letter-spacing:.15em; font-weight:900; }} .research-deck-title h2 {{ margin:5px 0; color:#f8fafc; font-size:1.15rem; }} .research-deck-title p {{ max-width:630px; margin:0; color:#9eabbc; font-size:.75rem; }} .research-deck-title > b {{ flex:none; color:#f4a261; font-size:.68rem; white-space:nowrap; }}
    .research-deck-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:11px; margin-top:13px; }} .research-card {{ position:relative; min-width:0; min-height:205px; overflow:hidden; padding:15px; border:1px solid #2a313c; border-radius:12px; background:linear-gradient(150deg,rgba(29,34,42,.98),rgba(16,19,24,.98)); box-shadow:inset 0 1px rgba(255,255,255,.025); }} .research-card::after {{ position:absolute; right:-33px; bottom:-35px; width:110px; height:110px; border:1px solid rgba(232,230,225,.07); border-radius:50%; content:""; }} .research-card-featured {{ grid-column:span 2; min-height:235px; background:linear-gradient(135deg,#14171d 8%,#0e1116 62%,#201518); }}
    .research-card-head {{ display:flex; justify-content:space-between; align-items:center; gap:8px; margin:0 0 11px; color:#8995a8; font-size:.61rem; letter-spacing:.12em; font-weight:850; }} .deck-state {{ padding:3px 6px; border-radius:99px; font-size:.56rem; letter-spacing:.04em; font-style:normal; }} .deck-state.observed {{ color:#79d7b2; background:rgba(82,183,136,.13); }} .deck-state.inferred {{ color:#ffd293; background:rgba(244,162,97,.13); }} .deck-state.pending {{ color:#d5b5ff; background:rgba(183,148,244,.13); }} .research-card h3 {{ position:relative; z-index:1; max-width:94%; margin:0 0 12px; color:#f3f1ec; font-size:1.02rem; letter-spacing:-.01em; line-height:1.2; }} .research-card h4 {{ margin:0; color:#f8fafc; font-size:.83rem; }} .research-card p {{ color:#aeb8c6; }} .deck-caption {{ margin:10px 0 0; color:#8995a8 !important; font-size:.67rem; }} .deck-empty {{ color:#8995a8; font-size:.78rem; }}
    .card-conclusion {{ position:relative; z-index:1; display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:5px; margin:0 0 12px; padding:7px; border:1px solid #365063; border-radius:8px; background:linear-gradient(135deg,rgba(18,49,65,.9),rgba(20,27,37,.9)); }} .card-conclusion-cell {{ min-width:0; cursor:zoom-in; }} .card-conclusion-cell summary {{ list-style:none; }} .card-conclusion-cell summary::-webkit-details-marker {{ display:none; }} .card-conclusion-cell summary:focus-visible {{ outline:2px solid #78d8ca; outline-offset:2px; }} .card-conclusion span,.card-conclusion b {{ display:block; }} .card-conclusion span {{ color:#78d8ca; font-size:.55rem; font-weight:800; letter-spacing:.05em; }} .card-conclusion b {{ margin-top:2px; overflow:hidden; color:#f1f5f9; font-size:.62rem; font-weight:650; line-height:1.25; text-overflow:ellipsis; white-space:nowrap; }} .card-conclusion-cell p {{ display:none; margin:4px 0 0; color:#f1f5f9; font-size:.63rem; line-height:1.35; overflow-wrap:anywhere; }} .card-conclusion-cell[open] {{ grid-column:span 2; padding:4px; border-radius:5px; background:rgba(120,216,202,.08); cursor:zoom-out; }} .card-conclusion-cell[open] b {{ overflow:visible; text-overflow:clip; white-space:normal; overflow-wrap:anywhere; }} .card-conclusion-cell[open] p {{ display:block; }}
    .deck-cover-copy {{ display:flex; position:relative; z-index:1; flex-direction:column; justify-content:flex-end; min-height:150px; }} .deck-cover-copy p {{ max-width:850px; margin:0; color:#f8fafc; font-size:1.48rem; font-weight:820; line-height:1.2; }} .deck-cover-copy small {{ margin-top:12px; color:#b7c0cb; font-size:.75rem; }} .deck-cover-copy span {{ color:#e8a2a9; font-size:.65rem; }} .deck-cover-rule {{ width:78px; height:3px; margin:16px 0 13px; background:linear-gradient(90deg,#e63946,#f4a261); }}
    .deck-editor-note {{ position:relative; z-index:1; }} .deck-editor-note > b {{ color:#f4a261; font-size:.73rem; }} .deck-editor-note p {{ max-width:640px; margin:8px 0 13px; font-size:.8rem; line-height:1.55; }} .deck-editor-note dl {{ display:grid; grid-template-columns:82px 1fr; gap:6px 10px; margin:0; font-size:.69rem; }} .deck-editor-note dt {{ color:#e63946; font-weight:800; }} .deck-editor-note dd {{ margin:0; color:#c3cad4; }}
    .deck-contents {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin:0; padding:0; list-style:none; }} .deck-contents li {{ padding:9px; border:1px solid #313945; border-radius:8px; color:#c8d0db; font-size:.74rem; }} .deck-contents b {{ display:block; margin-bottom:3px; color:#e63946; font-size:1rem; font-family:Georgia,serif; }}
    .deck-kpis {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:7px; }} .deck-kpis div {{ min-width:0; padding:10px; border:1px solid #303945; border-top:2px solid #e63946; border-radius:8px; background:rgba(255,255,255,.025); }} .deck-kpis div:nth-child(2) {{ border-top-color:#f4a261; }} .deck-kpis div:nth-child(3) {{ border-top-color:#5ea8ff; }} .deck-kpis div:nth-child(4) {{ border-top-color:#52b788; }} .deck-kpis span,.deck-kpis small,.deck-kpis b {{ display:block; }} .deck-kpis span,.deck-kpis small {{ color:#8995a8; font-size:.62rem; }} .deck-kpis b {{ margin:4px 0; color:#f8fafc; font-size:1.3rem; }}
    .deck-exec-kpis small {{ line-height:1.35; }} .deck-evidence-mix {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin:10px 0 12px; }} .deck-evidence-mix article {{ min-width:0; padding:8px; border:1px solid #303945; border-radius:8px; background:rgba(255,255,255,.02); }} .deck-evidence-mix h4 {{ margin:0 0 5px; color:#cbd5e1; font-size:.68rem; }} .deck-evidence-mix .deck-donut-wrap {{ gap:9px; }} .deck-evidence-mix .deck-donut {{ width:82px; height:82px; }} .deck-evidence-mix .deck-donut::before {{ width:52px; height:52px; }} .deck-evidence-mix .deck-legend li {{ font-size:.58rem; }}
    .deck-bars,.deck-pareto {{ margin:0; padding:0; list-style:none; }} .deck-bars li,.deck-pareto li {{ padding:6px 0; border-bottom:1px solid #27303a; }} .deck-bars li > div {{ display:flex; justify-content:space-between; gap:8px; color:#d7dde6; font-size:.71rem; }} .deck-bars li > div b {{ min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }} .deck-bars li > div span {{ color:#f4a261; white-space:nowrap; }} .deck-bars li > i,.deck-pareto li > i {{ display:block; height:5px; margin-top:5px; border-radius:99px; background:linear-gradient(90deg,#e63946,#f4a261 52%,#5ea8ff); }}
    .deck-dumbbell {{ display:grid; grid-template-columns:1fr 70px 1fr; align-items:center; gap:8px; padding-top:14px; }} .deck-dumbbell div {{ padding:11px; border:1px solid #333d49; border-radius:9px; background:rgba(255,255,255,.03); text-align:center; }} .deck-dumbbell span,.deck-dumbbell b {{ display:block; }} .deck-dumbbell span {{ color:#93a0b0; font-size:.63rem; }} .deck-dumbbell b {{ color:#fff; font-size:1.5rem; }} .deck-dumbbell i {{ height:2px; background:linear-gradient(90deg,#52b788,#f4a261); }} .deck-dumbbell p {{ grid-column:1/-1; margin:3px 0 0; font-size:.66rem; }}
    .deck-bubbles {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:7px; min-height:128px; }} .deck-bubble {{ display:flex; width:var(--size); height:var(--size); flex-direction:column; align-items:center; justify-content:center; padding:4px; border-radius:50%; color:#fff; text-align:center; }} .deck-bubble b {{ max-width:92%; overflow:hidden; font-size:.63rem; line-height:1.1; text-overflow:ellipsis; }} .deck-bubble small {{ margin-top:3px; font-size:.58rem; }} .deck-bubble.b0 {{ background:radial-gradient(circle at 33% 28%,#ff717a,#a91e2d); }} .deck-bubble.b1 {{ background:radial-gradient(circle at 33% 28%,#ffc17c,#a85320); }} .deck-bubble.b2 {{ background:radial-gradient(circle at 33% 28%,#88dfad,#247852); }} .deck-bubble.b3 {{ background:radial-gradient(circle at 33% 28%,#8fc5ff,#285fa1); }} .deck-bubble.b4 {{ background:radial-gradient(circle at 33% 28%,#d4b7ff,#7954a9); }}
    .deck-donut-wrap {{ display:flex; align-items:center; gap:16px; }} .deck-donut {{ display:grid; width:125px; height:125px; flex:none; place-items:center; border-radius:50%; }} .deck-donut::before {{ grid-area:1/1; width:78px; height:78px; border-radius:50%; background:#151a21; content:""; }} .deck-donut span {{ z-index:1; grid-area:1/1; color:#98a5b5; font-size:.61rem; text-align:center; }} .deck-donut span b {{ color:#f8fafc; font-size:.75rem; }} .deck-legend {{ flex:1; min-width:0; margin:0; padding:0; list-style:none; }} .deck-legend li {{ display:flex; gap:5px; align-items:center; padding:3px 0; color:#bdc7d3; font-size:.66rem; }} .deck-legend i {{ width:7px; height:7px; border-radius:50%; }} .deck-legend span {{ flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }} .deck-legend b {{ color:#f4a261; }}
    .deck-three {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:7px; }} .deck-three article {{ min-width:0; padding:9px; border:1px solid #313945; border-radius:8px; background:rgba(255,255,255,.02); }} .deck-three span {{ color:#e63946; font-size:.66rem; font-weight:900; }} .deck-three strong {{ display:block; margin-top:10px; color:#f4a261; font-size:1.3rem; }} .deck-three p {{ margin:2px 0 8px; font-size:.64rem; }} .deck-three small {{ display:block; overflow:hidden; color:#8e9aac; font-size:.59rem; line-height:1.35; }}
    .deck-dual-track {{ display:grid; grid-template-columns:1fr 1fr; gap:9px; }} .deck-dual-track article {{ padding:16px 10px; border:1px solid #353e49; border-radius:8px; background:linear-gradient(145deg,rgba(94,168,255,.12),transparent); }} .deck-dual-track article+article {{ background:linear-gradient(145deg,rgba(244,162,97,.12),transparent); }} .deck-dual-track span,.deck-dual-track b,.deck-dual-track small {{ display:block; }} .deck-dual-track span,.deck-dual-track small {{ color:#a5b0bd; font-size:.62rem; }} .deck-dual-track b {{ color:#fff; font-size:1.7rem; }} .deck-dual-track p {{ grid-column:1/-1; margin:2px 0; font-size:.64rem; }}
    .deck-focal {{ padding:12px; border-left:3px solid #e63946; background:linear-gradient(90deg,rgba(230,57,70,.1),transparent); }} .deck-focal > span {{ color:#e63946; font-size:.62rem; font-weight:900; letter-spacing:.12em; }} .deck-focal h4 {{ margin:7px 0 13px; font-size:1.05rem; }} .deck-focal div {{ display:flex; gap:9px; align-items:baseline; }} .deck-focal b {{ color:#f4a261; font-size:1.8rem; }} .deck-focal small,.deck-focal p {{ color:#aeb8c6; font-size:.68rem; }} .deck-focal p {{ margin:8px 0 0; }}
    .deck-flow .flow-labels {{ display:flex; justify-content:space-between; color:#93a0b0; font-size:.62rem; }} .deck-flow ul {{ margin:8px 0 0; padding:0; list-style:none; }} .deck-flow li {{ display:grid; grid-template-columns:minmax(54px,.8fr) minmax(30px,1.2fr) minmax(74px,1fr); align-items:center; gap:6px; padding:6px 0; color:#cbd3dd; font-size:.65rem; }} .deck-flow li > span,.deck-flow li > b {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }} .deck-flow li > b {{ color:#f4a261; }} .deck-flow li > i {{ display:block; height:7px; border-radius:99px; background:linear-gradient(90deg,#e63946 0,#f4a261 43%,#52b788 100%); }} .deck-flow p {{ margin:7px 0 0; color:#8995a8; font-size:.61rem; }}
    .deck-pareto li {{ display:grid; grid-template-columns:100px 1fr 56px; align-items:center; gap:8px; }} .deck-pareto b {{ overflow:hidden; color:#cbd3dd; font-size:.66rem; text-overflow:ellipsis; white-space:nowrap; }} .deck-pareto i {{ margin:0; }} .deck-pareto span {{ color:#f4a261; font-size:.61rem; text-align:right; }}
    .deck-hub {{ margin:0; }} .deck-hub svg {{ display:block; width:100%; max-height:160px; }} .deck-hub-links line {{ stroke:#59687a; stroke-width:1; }} .deck-hub-node {{ stroke:#0e1116; stroke-width:2; }} .deck-hub-node.n0 {{ fill:#e63946; }} .deck-hub-node.n1 {{ fill:#f4a261; }} .deck-hub-node.n2 {{ fill:#52b788; }} .deck-hub-node.n3 {{ fill:#5ea8ff; }} .deck-hub-core {{ fill:#f3f1ec; }} .deck-hub-labels text {{ fill:#e8e6e1; text-anchor:middle; font:600 8px system-ui,sans-serif; }} .deck-hub-core-text {{ fill:#101419; text-anchor:middle; font:800 10px system-ui,sans-serif; }} .deck-hub figcaption {{ color:#8995a8; font-size:.61rem; }}
    .deck-uncertainty {{ padding:11px; border:1px solid rgba(183,148,244,.4); border-radius:9px; background:linear-gradient(135deg,rgba(183,148,244,.11),transparent); }} .deck-uncertainty > b,.deck-uncertainty > span {{ display:block; }} .deck-uncertainty > b {{ color:#d8c6ff; font-size:1.05rem; }} .deck-uncertainty > span {{ margin-top:3px; color:#aeb8c6; font-size:.67rem; }} .deck-uncertainty ul {{ margin:9px 0 0; padding:0; list-style:none; }} .deck-uncertainty li {{ padding:5px 0; border-top:1px solid rgba(183,148,244,.18); color:#d6dbe3; font-size:.66rem; }} .deck-uncertainty li::before {{ margin-right:5px; color:#b794f4; content:"?"; font-weight:900; }}
    .deck-sparkline {{ margin:0; }} .deck-sparkline svg {{ display:block; width:100%; }} .deck-gridline {{ stroke:#2d3742; stroke-width:1; }} .deck-line {{ fill:none; stroke-width:3; stroke-linecap:round; stroke-linejoin:round; }} .deck-line.evidence {{ stroke:#f4a261; }} .deck-line.signal {{ stroke:#5ea8ff; }} .deck-sparkline figcaption {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:3px; color:#aeb8c6; font-size:.61rem; }} .deck-sparkline figcaption i {{ display:inline-block; width:8px; height:2px; margin-right:3px; vertical-align:middle; }} .deck-sparkline figcaption i.evidence {{ background:#f4a261; }} .deck-sparkline figcaption i.signal {{ background:#5ea8ff; }} .deck-sparkline figcaption small {{ margin-left:auto; color:#8995a8; }}
    .risk-quadrant {{ position:relative; height:130px; overflow:hidden; border:1px solid #374150; border-radius:8px; background:linear-gradient(135deg,rgba(82,183,136,.07) 0 50%,rgba(230,57,70,.08) 50%); }} .risk-v,.risk-h {{ position:absolute; background:#465160; }} .risk-v {{ top:0; bottom:0; left:50%; width:1px; }} .risk-h {{ right:0; bottom:50%; left:0; height:1px; }} .risk-axis {{ position:absolute; z-index:1; color:#8d9aac; font-size:.56rem; }} .risk-x {{ right:6px; bottom:3px; }} .risk-y {{ top:3px; left:5px; }} .risk-dot {{ position:absolute; z-index:2; max-width:68px; padding:4px 5px; border-radius:99px; color:#fff; font-size:.57rem; line-height:1.1; transform:translate(-50%,50%); }} .risk-dot.r0 {{ background:#e63946; }} .risk-dot.r1 {{ background:#f4a261; color:#191b20; }} .risk-dot.r2 {{ background:#b794f4; }} .risk-dot.r3 {{ background:#5ea8ff; }}
    .deck-gap,.deck-gap-mini {{ padding:11px; border:1px dashed #826835; border-radius:8px; background:rgba(244,162,97,.06); }} .deck-gap b,.deck-gap strong,.deck-gap span {{ display:block; }} .deck-gap b {{ color:#f4a261; font-size:.66rem; }} .deck-gap strong {{ margin-top:6px; color:#f7e2c5; font-size:.84rem; }} .deck-gap p {{ margin:6px 0; color:#b7ad9d; font-size:.68rem; }} .deck-gap span,.deck-gap-mini {{ color:#d5b47a; font-size:.62rem; }}
    .deck-closing {{ padding:13px; border:1px solid #40313a; border-radius:10px; background:linear-gradient(135deg,rgba(230,57,70,.12),rgba(244,162,97,.06)); }} .deck-closing p {{ margin:0 0 12px; color:#f7f1e9; font-size:1rem; font-weight:760; }} .deck-closing dl {{ display:grid; grid-template-columns:56px 1fr; gap:7px; margin:0; font-size:.68rem; }} .deck-closing dt {{ color:#e63946; font-weight:850; }} .deck-closing dd {{ margin:0; color:#c6ced8; }} .deck-closing > span {{ display:block; margin-top:13px; color:#f4a261; font-size:.64rem; }}
    /* Dark report canvas: distinct borders separate document, analysis panels,
       evidence cards and timelines without reverting to white paper blocks. */
    .hugohe3-doc {{ background:#0d141e; border-color:#304255; color:#e7edf5; }}
    .hugohe3-doc .kicker,.hugohe3-doc .disclaimer,.hugohe3-doc .uncertainty,.hugohe3-doc .cadence-note {{ color:#9aaabd; }}
    .hugohe3-doc a {{ color:#7dd3fc; }}
    .hugohe3-doc .signal-map {{ background:linear-gradient(135deg,#101d2b,#102d32); border-color:#315a68; }}
    .hugohe3-doc .signal-map-head {{ color:#7de4d2; }} .hugohe3-doc .signal-edge {{ stroke:#547184; }} .hugohe3-doc .signal-map figcaption {{ color:#9aaabd; }}
    .hugohe3-doc .analysis-dashboard {{ background:linear-gradient(145deg,#111f2d,#102a2d); border-color:#376474; box-shadow:0 10px 25px rgba(0,0,0,.18); }}
    .hugohe3-doc .analysis-head h2 {{ color:#f3f7fb; }} .hugohe3-doc .analysis-head p,.hugohe3-doc .analysis-progress-label,.hugohe3-doc .analysis-metric span {{ color:#9aaabd; }}
    .hugohe3-doc .analysis-metric {{ background:#121d2a; border-color:#30495b; }} .hugohe3-doc .analysis-metric strong {{ color:#7de4d2; }}
    .hugohe3-doc .analysis-overview,.hugohe3-doc .analysis-panel {{ background:#101a26; border-color:#30495b; }} .hugohe3-doc .overview-card {{ background:#121e2b; border-color:#2d4657; }}
    .hugohe3-doc .overview-heading h3,.hugohe3-doc .overview-card h4,.hugohe3-doc .overview-row b,.hugohe3-doc .analysis-panel h3,.hugohe3-doc .topic-line b {{ color:#e7edf5; }}
    .hugohe3-doc .overview-count,.hugohe3-doc .overview-row span,.hugohe3-doc .overview-detail,.hugohe3-doc .overview-empty,.hugohe3-doc .topic-line span,.hugohe3-doc .topic-list small,.hugohe3-doc .reasoning-step small {{ color:#9aaabd; }}
    .hugohe3-doc .overview-card li,.hugohe3-doc .topic-list li,.hugohe3-doc .reasoning-step {{ border-color:#263b4c; }}
    .hugohe3-doc .analysis-progress-track,.hugohe3-doc .topic-track {{ background:#1c3442; }}
    .hugohe3-doc .analysis-panel {{ color:#e7edf5; }} .hugohe3-doc .reasoning-step em {{ color:#7de4d2; }}
    .hugohe3-doc .seconds-strip div {{ background:#142231; border-left:1px solid #2d4b5d; border-right:1px solid #2d4b5d; }} .hugohe3-doc .seconds-strip span {{ color:#a8bac8; }}
    .hugohe3-doc .deck-section-grid,.hugohe3-doc .scenario-slide,.hugohe3-doc .deck-slide {{ background:#0d141e; }} .hugohe3-doc .deck-slide,.hugohe3-doc .scenario-slide {{ border-color:#304255; }}
    .hugohe3-doc .scenario-card {{ background:#121e2b; border-color:#304255; }} .hugohe3-doc .scenario-card p,.hugohe3-doc .scenario-card em {{ color:#a8bac8; }}
    @media (max-width:820px) {{ .analysis-columns {{ grid-template-columns:1fr; }} }}
    @media (max-width:700px) {{ .research-deck-title {{ display:block; }} .research-deck-title > b {{ display:block; margin-top:8px; }} .research-deck-grid {{ grid-template-columns:1fr; }} .research-card-featured {{ grid-column:auto; }} .deck-kpis {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:900px) {{ .card-conclusion {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} }}
    @media (max-width:600px) {{ .deck-cover {{ margin:-16px -16px 16px; }} .deck-section-grid,.scenario-grid,.overview-grid {{ grid-template-columns:1fr; }} .overview-card.overview-wide {{ grid-column:auto; }} .analysis-metrics {{ grid-template-columns:repeat(2,1fr); }} .research-deck {{ margin-right:-3px; margin-left:-3px; padding:11px; }} .research-card {{ min-height:0; padding:12px; }} .deck-cover-copy p {{ font-size:1.15rem; }} .deck-three {{ grid-template-columns:1fr; }} .deck-donut-wrap {{ align-items:flex-start; }} .card-conclusion {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:600px) {{ .hugohe3-doc {{ padding:16px; }} h1 {{ font-size:1.2rem; }} .seconds-strip {{ grid-template-columns:repeat(3,1fr); }} .signal-map-head {{ display:block; }} .legend {{ margin-top:6px; }} }}
  </style>
</head>
<body>
  <main class="hugohe3-shell">
    {body}
    {chart_block}
    <script type="application/json" id="report-data">{safe_json(report_data)}</script>
  </main>
</body>
</html>
"""
    # CSP meta allows no script execution from inline; strip accidental script tags from body
    # but keep application/json script for data — replace with template element
    html_out = html_out.replace(
        f'<script type="application/json" id="report-data">{safe_json(report_data)}</script>',
        f'<template id="report-data">{safe_json(report_data)}</template>',
    )
    validate_csp_html(html_out)
    urls = []
    for c in report_data.get("citations") or []:
        if isinstance(c, dict) and c.get("url"):
            urls.append(c["url"])
    validate_citations_present(html_out, urls)
    return html_out


def hugohe3_render(
    payload: Union[dict, AiNews60sReport, WorldIntelReport],
    *,
    channel: Optional[str] = None,
) -> str:
    """Validate report and render immutable HTML document string."""
    if isinstance(payload, AiNews60sReport):
        return render_ai60(payload)
    if isinstance(payload, WorldIntelReport):
        return render_world(payload)
    ch = channel or payload.get("channel")
    report = validate_report(ch, payload)
    if isinstance(report, AiNews60sReport):
        return render_ai60(report)
    return render_world(report)
