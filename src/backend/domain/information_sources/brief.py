# -*- coding: utf-8 -*-
"""P13 — Executive brief / distinctive insights from published reports.

Conclusion-first structures for Data Intelligence. Never emits process chatter
or bare URLs as the primary headline/bullets.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

PROCESS_NOISE = (
    "正在",
    "清洗",
    "聚类",
    "分析中",
    "采集中",
    "加载",
    "等待",
    "处理中",
    "队列空闲",
    "fixture / 待命",
)

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_URL_IN_TEXT_RE = re.compile(r"https?://\S+", re.I)


def _is_url_like(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _URL_RE.match(t):
        return True
    if t.startswith("www.") and " " not in t:
        return True
    # Mostly a URL with little prose
    if t.lower().startswith("http") and len(t.split()) <= 2:
        return True
    return False


def _is_noise(text: str) -> bool:
    t = text or ""
    if not t.strip():
        return True
    if _is_url_like(t):
        return True
    return any(p in t for p in PROCESS_NOISE)


def _clean_prose(text: str) -> str:
    t = (text or "").strip()
    t = _URL_IN_TEXT_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" ·|-")
    return t


def _claim_text(item: Any) -> str:
    """Extract human prose from a claim/citation-like object."""
    if item is None:
        return ""
    if isinstance(item, str):
        return _clean_prose(item)
    if not isinstance(item, dict):
        return _clean_prose(str(item))
    # Prefer non-URL fields in order
    for key in ("text", "title", "summary", "name", "headline", "body"):
        val = item.get(key)
        if val is None:
            continue
        s = _clean_prose(str(val))
        if s and not _is_url_like(s) and not _is_noise(s):
            return s
    # last resort: limited string fields only (never uncertainty / label meta)
    for key in ("description", "content", "detail", "rubric"):
        val = item.get(key)
        if isinstance(val, str):
            s = _clean_prose(val)
            if s and not _is_url_like(s) and not _is_noise(s):
                return s
    return ""


def _domains(citations: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        url = str(c.get("url") or "")
        host = (urlparse(url).netloc or "").lower()
        if host and host not in out:
            out.append(host)
    return out[:8]


def _insight(
    *,
    kind: str,
    title: str,
    body: str,
    confidence: float,
    evidence_ids: List[str],
    source_domains: List[str],
    as_of: str,
    impact: str = "",
) -> Dict[str, Any]:
    return {
        "kind": kind,
        "title": (title or "")[:120],
        "body": (body or "")[:400],
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "evidence_ids": list(evidence_ids or [])[:12],
        "source_domains": list(source_domains or [])[:8],
        "as_of": as_of or "",
        "impact": (impact or "")[:200],
    }


def _unique_prose(items: List[str], *, limit: int = 6) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in items:
        text = _clean_prose(raw)
        if not text or _is_noise(text) or _is_url_like(text):
            continue
        key = re.sub(r"\s+", "", text)[:48]
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:160])
        if len(out) >= limit:
            break
    return out


def _citation_body(citation: Dict[str, Any]) -> str:
    """Return a useful news line without pretending a title is an article."""
    title = _claim_text(citation)
    detail = _claim_text({"text": citation.get("summary") or citation.get("excerpt") or citation.get("content")})
    host = (urlparse(str(citation.get("url") or "")).netloc or "未知来源").lower()
    published = str(citation.get("published_at") or citation.get("fetched_at") or "")[:16]
    if detail and detail != title:
        return f"{title}｜{detail[:180]}｜来源：{host}｜时间：{published or '未知'}"
    return f"{title}｜来源：{host}｜时间：{published or '未知'}；当前仅有标题级证据，主体、具体变化与业务影响待正文核验"


def build_run_brief(
    *,
    channel: str,
    report: Optional[Dict[str, Any]] = None,
    document: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build RunBrief from a channel report / document dict.

    Contract fields:
      headline, bullets, focus_items, hot_analysis, trending_news,
      distinctive_insights, evidence_limits, as_of, disclaimer
    """
    report = report or {}
    document = document or {}
    as_of = str(document.get("as_of") or report.get("data_cutoff") or "")
    citations = [c for c in (report.get("citations") or []) if isinstance(c, dict)]
    domains = _domains(citations)
    evidence_ids = [str(x) for x in (document.get("evidence_ids") or [])]
    multi = len(domains) >= 2 or len(evidence_ids) >= 2
    analysis = report.get("analysis") if isinstance(report.get("analysis"), dict) else {}

    if channel == "ai_news_60s":
        headline = _clean_prose(str(report.get("headline") or document.get("title") or ""))
        bullets_raw = report.get("bullets") or []
        why = report.get("why_it_matters") or []
        risks = report.get("risks_and_counterpoints") or []
        topics = analysis.get("topic_clusters") or []
        related = report.get("related_companies") or []
    else:
        what = report.get("what_happened") or {}
        headline = _claim_text(what) or _clean_prose(str(document.get("title") or ""))
        bullets_raw = report.get("timeline") or []
        why = list(report.get("drivers") or [])
        risks = report.get("views_and_counterpoints") or []
        topics = []
        related = []
        for s in report.get("scenarios") or []:
            if isinstance(s, dict) and s.get("summary"):
                why.append({"text": f"情景 {s.get('name')}: {s.get('summary')}"})

    # Topic fallback for headline
    if not headline or _is_noise(headline) or _is_url_like(headline):
        if topics:
            names = [str(t.get("name") or t) for t in topics[:3] if t]
            headline = "核心结论：" + "、".join(names) if names else "本轮证据有限，暂无强结论"
        else:
            headline = "本轮证据有限，暂无强结论"

    # Bullets: claim text first, never bare URLs
    bullet_candidates: List[str] = []
    for b in bullets_raw[:12]:
        bullet_candidates.append(_claim_text(b))
    # Enrich from citation titles when claims were empty/URL
    for c in citations[:12]:
        bullet_candidates.append(_claim_text(c))
    # Topic lines as structured conclusions
    for t in (topics or [])[:4]:
        if isinstance(t, dict) and t.get("name"):
            share = t.get("share")
            share_s = f"（占比 {float(share):.0%}）" if isinstance(share, (int, float)) else ""
            bullet_candidates.append(f"主题「{t.get('name')}」{share_s}获本轮证据支持")

    bullets = _unique_prose(bullet_candidates, limit=6)
    if not bullets:
        bullets = ["未形成可发布要点；请检查来源质量或等待下一轮采集。"]

    # Focus items from top bullets
    focus_items = [
        _insight(
            kind="fact" if multi else "inference",
            title="In Focus",
            body=b,
            confidence=0.72 if multi else 0.45,
            evidence_ids=evidence_ids,
            source_domains=domains,
            as_of=as_of,
            impact="需结合业务/宏观上下文解读",
        )
        for b in bullets[:3]
    ]

    # Hot analysis from why_it_matters / drivers + business implications
    hot_src: List[Any] = list(why or [])
    hot_src.extend(analysis.get("business_implications") or [])
    hot_analysis: List[Dict[str, Any]] = []
    for w in hot_src[:8]:
        text = _claim_text(w)
        if not text:
            if isinstance(w, dict) and w.get("detail"):
                text = _claim_text(w.get("detail"))
            if isinstance(w, dict) and w.get("stage") and w.get("detail"):
                text = f"{w.get('stage')}：{_claim_text(w.get('detail'))}"
        if not text or _is_noise(text):
            continue
        hot_analysis.append(
            _insight(
                kind="analysis",
                title="热门分析",
                body=text,
                confidence=0.65 if multi else 0.4,
                evidence_ids=evidence_ids,
                source_domains=domains,
                as_of=as_of,
                impact=text[:80],
            )
        )
    if not hot_analysis:
        for t in (topics or [])[:3]:
            if isinstance(t, dict) and t.get("name"):
                hot_analysis.append(
                    _insight(
                        kind="analysis",
                        title=str(t.get("name")),
                        body=f"主题「{t.get('name')}」在本轮证据中出现 {t.get('count') or '?'} 次。",
                        confidence=0.5,
                        evidence_ids=evidence_ids,
                        source_domains=domains,
                        as_of=as_of,
                    )
                )

    # Trending news: give each item a distinct title plus source/time and an
    # explicit title-only caveat when the connector did not return article text.
    trending_news: List[Dict[str, Any]] = []
    for c in citations[:8]:
        title = _claim_text(c)
        if not title:
            continue
        host = (urlparse(str(c.get("url") or "")).netloc or "").lower()
        trending_news.append(
            _insight(
                kind="fact",
                title=title[:48],
                body=_citation_body(c),
                confidence=0.6 if multi else 0.35,
                evidence_ids=evidence_ids,
                source_domains=[host] if host else domains[:1],
                as_of=as_of,
            )
        )
    if not trending_news:
        for b in bullets[:5]:
            trending_news.append(
                _insight(
                    kind="fact",
                    title=b[:48],
                    body=b,
                    confidence=0.5,
                    evidence_ids=evidence_ids,
                    source_domains=domains,
                    as_of=as_of,
                )
            )

    # Distinctive insights: derive one non-duplicated observation per topic.
    # Repeating "交叉印证见解" for every why_it_matters line hides the actual
    # signal, so topic name/share/examples are used as the visible thesis.
    distinctive: List[Dict[str, Any]] = []
    seen_insights = set()
    for topic in (topics or [])[:4]:
        if not isinstance(topic, dict) or not topic.get("name"):
            continue
        name = str(topic["name"])
        share = topic.get("share")
        share_text = f"占本轮证据 {float(share):.0%}" if isinstance(share, (int, float)) else "进入本轮主题簇"
        examples = _unique_prose([str(x) for x in (topic.get("examples") or [])], limit=2)
        body = f"{name}{share_text}；主要观察：{('；'.join(examples)) if examples else '尚缺少可读标题'}。下一步验证其是否转化为真实采用、成本或交付变化。"
        key = re.sub(r"\s+", "", body)[:90]
        if key in seen_insights:
            continue
        seen_insights.add(key)
        distinctive.append(_insight(kind="analysis" if multi else "inference", title=f"{name} · 观察", body=body, confidence=0.7 if multi else 0.38, evidence_ids=evidence_ids, source_domains=domains, as_of=as_of, impact="研究用途，非投资建议"))
    if not distinctive:
        for w in (why or [])[:3]:
            text = _claim_text(w)
            if not text:
                continue
            key = re.sub(r"\s+", "", text)[:90]
            if key in seen_insights:
                continue
            seen_insights.add(key)
            distinctive.append(_insight(kind="analysis" if multi else "inference", title="交叉印证见解" if multi else "单一来源推断", body=text, confidence=0.7 if multi else 0.38, evidence_ids=evidence_ids, source_domains=domains, as_of=as_of, impact="研究用途，非投资建议"))
    if related:
        distinctive.append(
            _insight(
                kind="analysis",
                title="产业映射",
                body="相关赛道/公司映射：" + "、".join(str(x) for x in related[:5]),
                confidence=0.5,
                evidence_ids=evidence_ids,
                source_domains=domains,
                as_of=as_of,
                impact="信息映射，非荐股",
            )
        )
    for r in (risks or [])[:3]:
        text = _claim_text(r)
        if text:
            distinctive.append(
                _insight(
                    kind="counter",
                    title="反证 / 不确定性",
                    body=text,
                    confidence=0.55,
                    evidence_ids=evidence_ids,
                    source_domains=domains,
                    as_of=as_of,
                )
            )
    for q in (analysis.get("open_questions") or [])[:2]:
        text = _claim_text(q)
        if text:
            distinctive.append(
                _insight(
                    kind="counter",
                    title="开放问题",
                    body=text,
                    confidence=0.5,
                    evidence_ids=evidence_ids,
                    source_domains=domains,
                    as_of=as_of,
                )
            )

    limits: List[str] = []
    if not multi:
        limits.append("独立来源不足（<2），结论置信度下调")
    if not evidence_ids:
        limits.append("无 evidence_id 追溯链")
    if not domains:
        limits.append("缺少可解析来源域名")
    signal = analysis.get("signal_strength")
    if signal == "弱":
        limits.append("信号强度弱：样本或多样性不足")
    if any(_is_url_like(_claim_text(b)) for b in (bullets_raw or [])[:3]):
        limits.append("部分快讯缺少标题，已用主题/引用来源改写")
    limits.append("研究/模拟用途，不构成投资建议")

    return {
        "channel": channel,
        "headline": headline[:200],
        "bullets": bullets[:6],
        "focus_items": focus_items,
        "hot_analysis": hot_analysis or focus_items[:2],
        "trending_news": trending_news[:6],
        "distinctive_insights": distinctive[:8],
        "evidence_limits": limits,
        "as_of": as_of,
        "document_id": document.get("document_id") or "",
        "version": document.get("version"),
        "run_id": document.get("run_id") or report.get("run_id") or "",
        "disclaimer": "研究/模拟用途，非投资建议",
        "signal_strength": analysis.get("signal_strength") or "",
        "evidence_score": analysis.get("evidence_score"),
        "source_count": analysis.get("source_count") or len(evidence_ids),
        "source_diversity": analysis.get("source_diversity") or len(domains),
    }
