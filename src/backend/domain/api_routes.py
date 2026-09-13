# -*- coding: utf-8 -*-
"""T601 — Trading runtime, information sources/documents, investment simulation APIs.

Independent route prefix; does not modify Plaza contracts.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["stockagents-domain"])


class ErrorBody(BaseModel):
    error: str
    detail: Optional[str] = None
    code: str = "error"


def _err(status: int, message: str, code: str = "error", detail: str = None):
    raise HTTPException(
        status_code=status,
        detail={"error": message, "code": code, "detail": detail},
    )


# ── Trading runtime ──────────────────────────────────────────────

@router.get("/api/v1/trading-runtime/health")
async def trading_runtime_health():
    return {
        "status": "ok",
        "engine": "model-clearance-v1",
        "layer": {"status": "ok"},
        "release_check": {"release": "1.0.0", "status": "stable"},
        "auto_upgrade": False,
    }


@router.get("/api/v1/trading-runtime/config-schema")
async def trading_config_schema():
    """Read-only schema; Agent Config models selected by id (T303)."""
    return {
        "type": "object",
        "properties": {
            "quick_model_id": {"type": "string", "description": "Agent Config Quick Think model_id"},
            "deep_model_id": {"type": "string", "description": "Agent Config Deep Think model_id"},
            "analysts": {
                "type": "array",
                "items": {"type": "string", "enum": ["market", "social", "news", "fundamentals"]},
            },
            "debate_rounds": {"type": "integer", "minimum": 0, "maximum": 5, "default": 1},
            "risk_rounds": {"type": "integer", "minimum": 0, "maximum": 5, "default": 1},
            "data_vendor": {"type": "string", "default": "yfinance"},
            "checkpoint_enabled": {"type": "boolean", "default": True},
            "output_language": {"type": "string", "default": "zh-CN"},
            "providers_supported": [
                "openai",
                "openai-compatible",
                "anthropic",
                "google",
                "xai",
                "grok",
                "deepseek",
                "qwen",
                "ollama",
            ],
        },
        "required": ["deep_model_id"],
        "note": "API keys resolve only from SecretStore/env; never from browser JSON.",
    }


class ConfigValidateRequest(BaseModel):
    quick_model: Optional[Dict[str, Any]] = None
    deep_model: Optional[Dict[str, Any]] = None
    debate_rounds: int = 1
    risk_rounds: int = 1
    analysts: Optional[List[str]] = None


@router.post("/api/v1/trading-runtime/config/validate")
async def trading_config_validate(body: ConfigValidateRequest):
    return {"valid": True, "warnings": []}


# ── Information sources ──────────────────────────────────────────

class SourceCreate(BaseModel):
    kind: str
    name: str = ""
    url: str = ""
    enabled: bool = True
    options: Dict[str, Any] = Field(default_factory=dict)
    secret_refs: Dict[str, str] = Field(default_factory=dict)
    language: str = ""
    region: str = ""
    license_note: str = ""
    reputation_score: float = 0.5
    allowed_hosts: List[str] = Field(default_factory=list)
    source_id: Optional[str] = None


class SourceDirectoryPreviewRequest(BaseModel):
    url: str
    max_items: int = Field(200, ge=1, le=500)
    check_health: bool = True


class SourceDirectoryCommitRequest(BaseModel):
    directory_url: str = ""
    profile: str = "both"
    items: List[Dict[str, Any]] = Field(default_factory=list, max_length=500)


class ScheduleCreate(BaseModel):
    name: str = Field("未命名定时任务", min_length=1, max_length=80)
    team_id: str
    interval_minutes: int = Field(30, ge=1, le=10080)
    enabled: bool = True
    source_ids: List[str] = Field(default_factory=list)
    run_immediately: bool = False


class SchedulePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    interval_minutes: Optional[int] = Field(None, ge=1, le=10080)
    enabled: Optional[bool] = None
    source_ids: Optional[List[str]] = None


@router.get("/api/v1/information-sources")
async def list_sources():
    from domain.information_sources.protocol import get_source_registry
    from domain.information_sources.source_store import get_source_config_store

    store = get_source_config_store()
    reg = get_source_registry()
    return {
        "sources": [s.to_dict() for s in store.list()],
        "kinds": [m.to_dict() for m in reg.list_manifests()],
    }


# Information/research teams that own a collection pipeline and a published channel.
INFORMATION_TEAMS = ("ai_news_60s", "dufu_world_intel", "open_weights")
_TEAM_LABELS = {
    "ai_news_60s": "60 秒 AI 信息团队",
    "dufu_world_intel": "独夫之心世界趋势团队",
    "open_weights": "开放权重资源团队",
}
_TEAM_HINT = "team_id must be one of " + ", ".join(INFORMATION_TEAMS)


@router.post("/api/v1/information-sources")
async def create_source(body: SourceCreate):
    from domain.information_sources.protocol import get_source_registry
    from domain.information_sources.source_store import get_source_config_store

    if body.kind not in get_source_registry().known_kinds():
        _err(400, f"Unknown kind: {body.kind}", code="invalid_kind")
    # Secrets only as env refs
    for k, v in (body.secret_refs or {}).items():
        if v and not str(v).startswith("env:"):
            _err(400, "secret_refs values must be env:VAR_NAME", code="secret_policy")
    cfg = get_source_config_store().create(body.model_dump())
    return cfg.to_dict()


@router.post("/api/v1/information-sources/import-directory/preview")
async def preview_source_directory(body: SourceDirectoryPreviewRequest):
    from domain.information_sources.directory_parser import preview_directory

    try:
        return await preview_directory(body.url, max_items=body.max_items, check_health=body.check_health)
    except Exception as exc:
        _err(400, f"RSS 目录解析失败: {exc}", code="directory_parse_failed")


@router.post("/api/v1/information-sources/import-directory/commit")
async def commit_source_directory(body: SourceDirectoryCommitRequest):
    from domain.information_sources.source_store import get_source_config_store
    from domain.information_sources.ssrf import assert_url_safe

    if body.profile not in ("ai60", "dufu", "openweights", "both", "all"):
        _err(400, "profile must be ai60, dufu, openweights, both or all", code="invalid_profile")
    store = get_source_config_store()
    existing = {s.url for s in store.list() if s.url}
    created, skipped, errors = [], [], []
    _PROFILE_TEAMS = {
        "ai60": ["ai_news_60s"],
        "dufu": ["dufu_world_intel"],
        "openweights": ["open_weights"],
        "both": ["ai_news_60s", "dufu_world_intel"],
        "all": list(INFORMATION_TEAMS),
    }
    target_teams = _PROFILE_TEAMS[body.profile]
    for item in body.items:
        url = str(item.get("url") or "").strip()
        name = str(item.get("name") or "RSS source").strip()[:160]
        try:
            safe = assert_url_safe(url)
            if safe in existing:
                skipped.append({"name": name, "url": safe, "reason": "already_exists"})
                continue
            cfg = store.create({
                "kind": "rss", "name": name, "url": safe, "enabled": True,
                "language": str(item.get("language") or ""), "region": str(item.get("region") or ""),
                "options": {"directory_url": body.directory_url, "collection_profile": body.profile, "target_teams": target_teams},
            })
            existing.add(safe)
            created.append(cfg.to_dict())
        except Exception as exc:
            errors.append({"name": name, "url": url, "reason": str(exc)})
    return {"created": created, "skipped": skipped, "errors": errors, "count": len(created)}


@router.get("/api/v1/information-sources/{source_id}")
async def get_source(source_id: str):
    from domain.information_sources.source_store import get_source_config_store

    s = get_source_config_store().get(source_id)
    if not s:
        _err(404, "source not found", code="not_found")
    return s.to_dict()


@router.patch("/api/v1/information-sources/{source_id}")
async def patch_source(source_id: str, body: Dict[str, Any]):
    from domain.information_sources.source_store import get_source_config_store

    if "secret_refs" in body:
        for k, v in (body.get("secret_refs") or {}).items():
            if v and not str(v).startswith("env:"):
                _err(400, "secret_refs values must be env:VAR_NAME", code="secret_policy")
    s = get_source_config_store().update(source_id, body)
    if not s:
        _err(404, "source not found", code="not_found")
    return s.to_dict()


@router.delete("/api/v1/information-sources/{source_id}")
async def delete_source(source_id: str):
    from domain.information_sources.source_store import get_source_config_store

    if not get_source_config_store().delete(source_id):
        _err(404, "source not found", code="not_found")
    return {"ok": True, "source_id": source_id}


@router.post("/api/v1/information-sources/{source_id}/test")
async def test_source(source_id: str):
    from domain.information_sources.protocol import get_source_registry
    from domain.information_sources.source_store import get_source_config_store

    cfg = get_source_config_store().get(source_id)
    if not cfg:
        _err(404, "source not found", code="not_found")
    connector = get_source_registry().create(cfg.kind, cfg)
    health = await connector.healthcheck(cfg)
    return health.to_dict()


# ── Periodic information tasks ───────────────────────────────────

def _schedule_service():
    from domain.information_sources.scheduler import get_information_scheduler
    return get_information_scheduler()


def _validate_schedule_team(team_id: str) -> None:
    from domain.information_sources.scheduler import ACTIVE_SCHEDULE_TEAMS
    if team_id not in ACTIVE_SCHEDULE_TEAMS:
        _err(400, _TEAM_HINT, code="invalid_team")


@router.get("/api/v1/information-schedules")
async def list_information_schedules():
    service = _schedule_service()
    return {"schedules": [item.to_dict() for item in service.list()]}


@router.post("/api/v1/information-schedules")
async def create_information_schedule(body: ScheduleCreate):
    _validate_schedule_team(body.team_id)
    return _schedule_service().store.create(body.model_dump()).to_dict()


@router.patch("/api/v1/information-schedules/{schedule_id}")
async def patch_information_schedule(schedule_id: str, body: SchedulePatch):
    item = _schedule_service().store.get(schedule_id)
    if not item:
        _err(404, "schedule not found", code="not_found")
    updated = _schedule_service().store.update(schedule_id, body.model_dump(exclude_none=True))
    return updated.to_dict()


@router.delete("/api/v1/information-schedules/{schedule_id}")
async def delete_information_schedule(schedule_id: str):
    if not _schedule_service().store.delete(schedule_id):
        _err(404, "schedule not found", code="not_found")
    return {"ok": True, "schedule_id": schedule_id}


@router.post("/api/v1/information-schedules/{schedule_id}/run")
async def run_information_schedule(schedule_id: str):
    if not _schedule_service().store.get(schedule_id):
        _err(404, "schedule not found", code="not_found")
    # Only the manual "run now" button reaches this endpoint; the timer calls
    # run_once directly and keeps the per-window idempotency.
    return await _schedule_service().run_once(schedule_id, force=True)


class InformationRunCreate(BaseModel):
    team_id: str
    source_ids: List[str] = Field(default_factory=list)
    wait: bool = False
    wait_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)


@router.post("/api/v1/information-runs")
async def create_information_run(body: InformationRunCreate):
    """Enqueue a background information run. Returns 202 unless wait=true."""
    if body.team_id not in INFORMATION_TEAMS:
        _err(400, _TEAM_HINT, code="invalid_team")
    from domain.information_sources.run_service import enqueue_run_async, wait_for_run

    run = await enqueue_run_async(
        team_id=body.team_id,
        source_ids=body.source_ids,
        trigger="api",
    )
    if body.wait:
        finished = await wait_for_run(run.run_id, timeout=body.wait_timeout_seconds)
        payload = finished.to_dict()
        payload["events_hint"] = f"/api/v1/information-runs/{finished.run_id}/events"
        return payload
    return JSONResponse(
        status_code=202,
        content={
            "run_id": run.run_id,
            "status": run.status,
            "team_id": run.team_id,
            "accepted": True,
            "events_url": f"/api/v1/information-runs/{run.run_id}/events",
            "stream_url": f"/api/v1/information-runs/{run.run_id}/events/stream",
        },
    )


@router.get("/api/v1/information-runs")
async def list_information_runs(limit: int = Query(30, ge=1, le=100)):
    from domain.information_sources.run_store import get_run_repository

    runs = get_run_repository().list_recent(limit)
    return {"runs": [r.to_dict() for r in runs]}


@router.get("/api/v1/information-runs/{run_id}")
async def get_information_run(run_id: str):
    from domain.information_sources.run_service import get_run

    run = get_run(run_id)
    if not run:
        _err(404, "run not found", code="not_found")
    return run.to_dict()


@router.get("/api/v1/information-runs/{run_id}/events")
async def list_information_run_events(run_id: str, after_seq: int = Query(0, ge=0)):
    from domain.information_sources.run_service import get_run, list_events

    if not get_run(run_id):
        _err(404, "run not found", code="not_found")
    events = list_events(run_id, after_seq=after_seq)
    return {
        "run_id": run_id,
        "after_seq": after_seq,
        "events": [e.to_dict() for e in events],
        "last_seq": events[-1].seq if events else after_seq,
    }


@router.get("/api/v1/information-runs/{run_id}/events/stream")
async def stream_information_run_events(run_id: str, after_seq: int = Query(0, ge=0)):
    from domain.information_sources.run_service import get_run, list_events

    if not get_run(run_id):
        _err(404, "run not found", code="not_found")

    async def gen():
        cursor = after_seq
        idle = 0
        while idle < 120:
            run = get_run(run_id)
            events = list_events(run_id, after_seq=cursor)
            for ev in events:
                cursor = ev.seq
                yield f"data: {json.dumps(ev.to_dict(), ensure_ascii=False)}\n\n"
            if run and run.status in ("completed", "failed", "cancelled", "degraded"):
                yield f"data: {json.dumps({'type': 'done', 'status': run.status, 'run_id': run_id}, ensure_ascii=False)}\n\n"
                break
            idle = 0 if events else idle + 1
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/api/v1/information-sources/teams/{team_id}/run")
async def run_team_pipeline(team_id: str, body: Optional[Dict[str, Any]] = None):
    """Start team pipeline via background queue (202) or wait when body.wait=true.

    Default is async enqueue so browser refresh does not kill the run.
    Pass ``{"wait": true}`` for legacy/fixture callers that need the final document.
    """
    if team_id not in INFORMATION_TEAMS:
        _err(400, _TEAM_HINT, code="invalid_team")
    body = body or {}
    source_ids = body.get("source_ids") or []
    wait = bool(body.get("wait", False))
    # Back-compat: tests / scripts that expect immediate document may omit wait;
    # accept query-style wait flag in body only. Default async for UI.
    from domain.information_sources.run_service import enqueue_run_async, wait_for_run

    try:
        run = await enqueue_run_async(
            team_id=team_id,
            source_ids=list(source_ids),
            trigger="manual",
        )
        if not wait:
            return JSONResponse(
                status_code=202,
                content={
                    "run_id": run.run_id,
                    "status": run.status,
                    "team_id": team_id,
                    "accepted": True,
                    "async": True,
                    "events_url": f"/api/v1/information-runs/{run.run_id}/events",
                    "poll_url": f"/api/v1/information-runs/{run.run_id}",
                },
            )
        finished = await wait_for_run(run.run_id, timeout=float(body.get("wait_timeout_seconds") or 120))
        if finished.status == "failed":
            _err(500, finished.error or "pipeline failed", code="pipeline_failed")
        # Prefer pipeline result shape for legacy consumers
        if finished.result:
            out = dict(finished.result)
            out["run_status"] = finished.status
            out["information_run_id"] = finished.run_id
            out["cards"] = [c if isinstance(c, dict) else c for c in (finished.cards or [])]
            return out
        return finished.to_dict()
    except Exception as exc:
        _err(500, str(exc), code="pipeline_failed")


# ── Information documents ────────────────────────────────────────

@router.get("/api/v1/information-documents")
async def list_documents(
    channel: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    from domain.information_sources.documents import get_document_store

    docs = get_document_store().list_documents(channel, before=before, limit=limit)
    return {"documents": [d.to_dict() for d in docs]}


_REPORT_CARD_IDS = (
    "cover", "editor-note", "contents", "signal-landscape", "evidence-pulse",
    "two-state-gap", "confidence-bubble", "evidence-donut", "top-three",
    "source-ranking", "dual-track", "second-tier", "focal-signal", "flow-map",
    "pareto", "evidence-hub", "uncertainty", "adoption-cost-proxy",
    "risk-quadrant", "closing",
)


def _document_payload(doc, *, include_html: bool = True):
    """Return reader metadata without forcing a second download of HTML."""
    payload = doc.to_dict(include_html=include_html)
    payload["render_contract"] = {
        "stable_card_anchors": all(
            f"<article id='{card_id}'" in (doc.html or "")
            for card_id in _REPORT_CARD_IDS
        ),
    }
    try:
        from domain.information_sources.brief import build_run_brief

        payload["executive_summary"] = build_run_brief(
            channel=doc.channel,
            report=doc.report or {},
            document=payload,
        )
    except Exception:
        payload["executive_summary"] = None
    return payload


@router.get("/api/v1/information-documents/latest-summary")
async def latest_summaries():
    """P13 — conclusion-first briefs for both research channels."""
    from domain.information_sources.brief import build_run_brief
    from domain.information_sources.documents import get_document_store

    store = get_document_store()
    out = {}
    for channel in INFORMATION_TEAMS:
        doc = store.get_latest(channel)
        if not doc:
            out[channel] = None
            continue
        payload = doc.to_dict(include_html=False)
        out[channel] = build_run_brief(
            channel=channel,
            report=doc.report or {},
            document=payload,
        )
    return {"summaries": out, "disclaimer": "研究/模拟用途，非投资建议"}


@router.get("/api/v1/information-documents/latest/{channel}")
async def latest_document(channel: str, include_html: bool = True):
    from domain.information_sources.documents import get_document_store

    doc = get_document_store().get_latest(channel)
    if not doc:
        _err(404, "no document", code="not_found")
    return _document_payload(doc, include_html=include_html)


@router.get("/api/v1/information-documents/{document_id}/versions/{version}")
async def document_version(document_id: str, version: int, include_html: bool = True):
    from domain.information_sources.documents import get_document_store

    # Prefer channel-less lookup by id then version
    store = get_document_store()
    doc = store.get_by_id(document_id)
    if doc and doc.version == version:
        return _document_payload(doc, include_html=include_html)
    # Fallback: treat document_id as channel name (compat)
    doc = store.get_version(document_id, version)
    if not doc:
        _err(404, "version not found", code="not_found")
    return _document_payload(doc, include_html=include_html)


@router.get("/api/v1/information-documents/{document_id}/versions/{version}/render")
async def render_document_version(document_id: str, version: int):
    """Serve one immutable, sanitized report snapshot for the reader iframe.

    The reader deliberately receives a document version rather than a channel
    latest pointer, so a newly published report cannot silently replace the
    evidence a reader opened. Revalidate the stored output before serving it:
    report HTML is a privileged rendering artifact, never arbitrary user HTML.
    """
    from domain.information_sources.documents import get_document_store
    from domain.information_sources.hugohe3 import validate_csp_html

    store = get_document_store()
    doc = store.get_by_id(document_id)
    if not (doc and doc.version == version):
        # Backward-compatible channel/version lookup remains useful for older
        # callers, but the immersive reader always sends a document id.
        doc = store.get_version(document_id, version)
    if not doc:
        _err(404, "version not found", code="not_found")
    try:
        validate_csp_html(doc.html)
    except ValueError:
        _err(500, "stored document failed safety validation", code="unsafe_document")
    return HTMLResponse(
        content=doc.html,
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


# ── Model Admission Clearance APIs (T503 / T807) ──────────────────────────

class ClearanceAppCreate(BaseModel):
    model_id: str
    applicant: str = "security-admin"
    review_scope: str = "full"
    revision: str = "main"
    weights_uri: str = ""
    local_path: str = ""
    expected_signer_identity: Optional[str] = None
    auto_submit: bool = False
    # §7/§8/§10 部署上下文；未知键由 DeploymentContext.from_dict 丢弃
    deployment: Dict[str, Any] = Field(default_factory=dict)
    # 控制台组装的情报来源：[{gate, kind, ref_id, label}]
    contributions: List[Dict[str, Any]] = Field(default_factory=list, max_length=60)


@router.get("/api/v1/model-clearance/contributors")
async def list_clearance_contributors():
    """可组装进流水线的情报来源：智能体情报团队、信息源、已发布文档。"""
    from domain.information_sources.documents import get_document_store
    from domain.information_sources.source_store import get_source_config_store
    from domain.model_clearance.standard import gate_catalog

    teams: List[Dict[str, Any]] = []
    for tid in INFORMATION_TEAMS:
        try:
            docs = get_document_store().list_documents(tid, limit=1)
        except Exception:
            docs = []
        latest = docs[0] if docs else None
        teams.append({
            "kind": "team",
            "ref_id": tid,
            "label": _TEAM_LABELS.get(tid, tid),
            "latest_document_id": latest.document_id if latest else None,
            "latest_as_of": latest.as_of if latest else None,
            "latest_title": latest.title if latest else None,
            "has_analysis": latest is not None,
        })

    try:
        sources = [
            {
                "kind": "source",
                "ref_id": s.source_id,
                "label": s.name or s.source_id,
                "source_kind": s.kind,
                "enabled": s.enabled,
            }
            for s in get_source_config_store().list()
        ]
    except Exception:
        sources = []

    try:
        documents = [
            {
                "kind": "document",
                "ref_id": d.document_id,
                "label": d.title or d.document_id,
                "channel": d.channel,
                "as_of": d.as_of,
                "version": d.version,
            }
            for d in get_document_store().list_documents(limit=20)
        ]
    except Exception:
        documents = []

    # 一次采集运行就是一个完整的「数据采集与处理过程」，可直接组装进流水线
    try:
        from domain.information_sources.run_store import get_run_repository

        runs = [
            {
                "kind": "run",
                "ref_id": r.run_id,
                "label": _TEAM_LABELS.get(r.team_id, r.team_id) + " · " + (r.finished_at or r.created_at or "")[:16],
                "team_id": r.team_id,
                "status": r.status,
                "source_count": len(r.source_ids or []),
                "finished_at": r.finished_at,
            }
            for r in get_run_repository().list_recent(limit=15)
        ]
    except Exception:
        runs = []

    return {
        "teams": teams,
        "sources": sources,
        "documents": documents,
        "runs": runs,
        "gates": [
            {"gate": g["gate"], "section": g["section"], "name": g["name"], "phase": g["phase"]}
            for g in gate_catalog()
        ],
    }


@router.get("/api/v1/model-clearance/standard")
async def get_clearance_standard():
    """标准目录：门定义、裁决结果、许可用途分级、治理角色。前端据此渲染，不再硬编码。"""
    from domain.model_clearance.standard import (
        GOVERNANCE_ROLES,
        OUTCOME_APPROVED,
        OUTCOME_APPROVED_COND,
        OUTCOME_NOT_APPROVED,
        OUTCOME_RESTRICTED,
        PERMITTED_USE_TIERS,
        gate_catalog,
    )

    return {
        "gates": gate_catalog(),
        "outcomes": [
            OUTCOME_APPROVED,
            OUTCOME_APPROVED_COND,
            OUTCOME_RESTRICTED,
            OUTCOME_NOT_APPROVED,
        ],
        "permitted_use_tiers": PERMITTED_USE_TIERS,
        "governance_roles": GOVERNANCE_ROLES,
    }


@router.get("/api/v1/model-clearance/licenses")
async def list_model_licenses():
    """T807: Knowledge base model license registry for frontend auto-complete."""
    from pathlib import Path
    lic_path = Path(__file__).resolve().parents[3] / "config" / "model_license_registry.json"
    if not lic_path.exists():
        return {"models": []}
    try:
        return json.loads(lic_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _err(500, f"Failed to load license registry: {exc}")


@router.get("/api/v1/model-clearance/applications")
async def list_clearance_applications(limit: int = Query(50, ge=1, le=200)):
    from domain.model_clearance.store import get_clearance_store
    apps = get_clearance_store().list(limit=limit)
    return {"applications": [a.to_dict() for a in apps]}


@router.post("/api/v1/model-clearance/applications")
async def create_clearance_application(body: ClearanceAppCreate):
    import uuid
    from domain.model_clearance.gate_orchestrator import GateOrchestrator
    from domain.model_clearance.models import (
        AppStatus,
        DeploymentContext,
        EvidenceContribution,
        ModelApplication,
        ModelIdentity,
    )
    from domain.model_clearance.registry import get_registry_store
    from domain.model_clearance.standard import GATE_BY_ID
    from domain.model_clearance.store import get_clearance_store

    contributions = []
    for c in body.contributions:
        gate = str(c.get("gate", ""))
        kind = str(c.get("kind", ""))
        if gate not in GATE_BY_ID:
            _err(400, f"Unknown gate in contributions: {gate}", code="invalid_gate")
        if kind not in ("team", "source", "document", "run"):
            _err(400, f"Unknown contribution kind: {kind}", code="invalid_kind")
        contributions.append(
            EvidenceContribution(
                gate=gate,
                kind=kind,
                ref_id=str(c.get("ref_id", ""))[:128],
                label=str(c.get("label", ""))[:120],
            )
        )

    if body.review_scope not in ("full", "model"):
        _err(400, "review_scope must be full or model", code="invalid_review_scope")

    app_id = f"app-{uuid.uuid4().hex[:10]}"
    app = ModelApplication(
        application_id=app_id,
        applicant=body.applicant,
        review_scope=body.review_scope,
        identity=ModelIdentity(
            model_id=body.model_id.strip(),
            revision=body.revision.strip(),
            weights_uri=body.weights_uri.strip(),
            local_path=body.local_path.strip(),
            expected_signer_identity=body.expected_signer_identity,
        ),
        deployment=(
            DeploymentContext.unknown()
            if body.review_scope == "model"
            else DeploymentContext.from_dict(body.deployment)
        ),
        contributions=contributions,
    )
    store = get_clearance_store()
    store.save(app)

    if body.auto_submit:
        orch = GateOrchestrator(store=store)
        app = orch.run_clearance(app)
        if app.status in (AppStatus.APPROVED, AppStatus.APPROVED_COND):
            from domain.model_clearance.adjudicate import adjudicate
            dec = adjudicate(app)
            get_registry_store().register(
                app=app,
                runtime_profile=dec.runtime_profile,
                scope=dec.scope,
                conditions=dec.conditions,
                expires_at=dec.expires_at,
            )

    return app.to_dict()


@router.get("/api/v1/model-clearance/applications/{app_id}")
async def get_clearance_application(app_id: str):
    from domain.model_clearance.store import get_clearance_store
    app = get_clearance_store().get(app_id)
    if not app:
        _err(404, f"Application {app_id} not found", code="not_found")
    return app.to_dict()


@router.post("/api/v1/model-clearance/applications/{app_id}/blocker-advisories")
async def generate_blocker_advisories(app_id: str):
    """为阻断项生成 LLM 分析与建议；仅作参考，不改变任何门禁判定。"""
    from domain.model_clearance.blocker_advisor import advise_blockers
    from domain.model_clearance.store import get_clearance_store

    store = get_clearance_store()
    app = store.get(app_id)
    if not app:
        _err(404, f"Application {app_id} not found", code="not_found")
    if not app.verdicts:
        _err(409, "尚未产生门禁裁决，无法生成阻断项分析", code="not_assessed")

    app.blocker_advisories = await advise_blockers(app)
    store.save(app)
    return {
        "application_id": app_id,
        "count": len(app.blocker_advisories),
        "advisories": [a.to_dict() for a in app.blocker_advisories],
    }


@router.get("/api/v1/model-clearance/applications/{app_id}/assurance-record")
async def get_clearance_assurance_record(app_id: str):
    """标准 §9 保障记录：评审报告的单一数据源。"""
    from domain.model_clearance.assurance_record import build_assurance_record
    from domain.model_clearance.store import get_clearance_store
    app = get_clearance_store().get(app_id)
    if not app:
        _err(404, f"Application {app_id} not found", code="not_found")
    return build_assurance_record(app)


@router.get("/api/v1/model-clearance/applications/{app_id}/events")
async def get_clearance_application_events(app_id: str):
    from domain.model_clearance.gate_orchestrator import generate_application_events
    from domain.model_clearance.store import get_clearance_store
    app = get_clearance_store().get(app_id)
    if not app:
        _err(404, f"Application {app_id} not found", code="not_found")
    events = generate_application_events(app)
    return {"application_id": app_id, "events": events}


@router.post("/api/v1/model-clearance/applications/{app_id}/submit")
async def submit_clearance_application(app_id: str):
    from domain.model_clearance.gate_orchestrator import GateOrchestrator
    from domain.model_clearance.models import AppStatus
    from domain.model_clearance.registry import get_registry_store
    from domain.model_clearance.store import get_clearance_store

    store = get_clearance_store()
    app = store.get(app_id)
    if not app:
        _err(404, f"Application {app_id} not found", code="not_found")

    orch = GateOrchestrator(store=store)
    app = orch.run_clearance(app)

    # If approved, register into registry with attestation
    if app.status in (AppStatus.APPROVED, AppStatus.APPROVED_COND):
        from domain.model_clearance.adjudicate import adjudicate
        dec = adjudicate(app)
        get_registry_store().register(
            app=app,
            runtime_profile=dec.runtime_profile,
            scope=dec.scope,
            conditions=dec.conditions,
            expires_at=dec.expires_at,
        )

    return app.to_dict()


@router.post("/api/v1/model-clearance/applications/{app_id}/retry")
async def retry_clearance_application(app_id: str):
    """Start a new immutable review run from the same model facts."""
    import uuid
    from domain.model_clearance.gate_orchestrator import GateOrchestrator
    from domain.model_clearance.models import (
        AppStatus,
        DeploymentContext,
        EvidenceContribution,
        ModelApplication,
        ModelIdentity,
    )
    from domain.model_clearance.registry import get_registry_store
    from domain.model_clearance.store import get_clearance_store

    store = get_clearance_store()
    previous = store.get(app_id)
    if not previous:
        _err(404, f"Application {app_id} not found", code="not_found")
    if previous.status in (AppStatus.DRAFT, AppStatus.SUBMITTED, AppStatus.GATING, AppStatus.ADJUDICATING):
        _err(409, "Application is not ready to retry", code="retry_not_ready")

    app = ModelApplication(
        application_id=f"app-{uuid.uuid4().hex[:10]}",
        applicant="",
        review_scope="model",
        identity=ModelIdentity.from_dict(previous.identity.to_dict()),
        deployment=DeploymentContext.unknown(),
        contributions=[
            EvidenceContribution.from_dict(contribution.to_dict())
            for contribution in previous.contributions
        ],
    )
    store.save(app)
    app = GateOrchestrator(store=store).run_clearance(app)

    if app.status in (AppStatus.APPROVED, AppStatus.APPROVED_COND):
        from domain.model_clearance.adjudicate import adjudicate
        decision = adjudicate(app)
        get_registry_store().register(
            app=app,
            runtime_profile=decision.runtime_profile,
            scope=decision.scope,
            conditions=decision.conditions,
            expires_at=decision.expires_at,
        )

    return app.to_dict()


@router.get("/api/v1/model-clearance/registry")
async def list_model_registry():
    from domain.model_clearance.registry import get_registry_store
    entries = get_registry_store().list_all()
    return {"registry": [e.to_dict() for e in entries]}


@router.get("/api/v1/model-clearance/registry/{entry_id}")
async def get_model_registry_entry(entry_id: str):
    from domain.model_clearance.registry import get_registry_store
    entry = get_registry_store().get(entry_id)
    if not entry:
        _err(404, f"Registry entry {entry_id} not found", code="not_found")
    return entry.to_dict()


@router.get("/api/v1/model-clearance/registry/{entry_id}/attestations")
async def get_model_registry_attestations(entry_id: str):
    from domain.model_clearance.registry import get_registry_store
    entry = get_registry_store().get(entry_id)
    if not entry:
        _err(404, f"Registry entry {entry_id} not found", code="not_found")
    return {"entry_id": entry_id, "attestations": entry.attestations}


@router.get("/api/v1/model-clearance/registry/{entry_id}/verify")
async def verify_model_registry_entry(entry_id: str):
    from domain.model_clearance.registry import get_registry_store
    res = get_registry_store().verify_entry(entry_id)
    if not res.get("found"):
        _err(404, f"Registry entry {entry_id} not found", code="not_found")
    return res


@router.post("/api/v1/model-clearance/registry/{entry_id}/revoke")
async def revoke_model_registry_entry(entry_id: str, request: Request):
    from domain.model_clearance.registry import get_registry_store
    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = str(body.get("reason", "Revoked by administrator"))
    entry = get_registry_store().revoke(entry_id, reason=reason)
    if not entry:
        _err(404, f"Registry entry {entry_id} not found", code="not_found")
    return entry.to_dict()


@router.post("/api/v1/model-clearance/registry/{entry_id}/kill-switch")
async def emergency_kill_switch(entry_id: str, request: Request):
    """T903: Emergency kill switch to instantly revoke admission and disconnect serving."""
    from domain.model_clearance.registry import get_registry_store
    try:
        body = await request.json()
    except Exception:
        body = {}
    operator = str(body.get("operator", "lenovo-secops-admin"))
    reason = str(body.get("reason", "Emergency kill-switch executed"))
    entry = get_registry_store().emergency_revoke(entry_id, operator=operator, reason=reason)
    if not entry:
        _err(404, f"Registry entry {entry_id} not found", code="not_found")
    return {
        "status": "kill_switch_triggered",
        "entry_id": entry_id,
        "operator": operator,
        "entry": entry.to_dict(),
    }


@router.post("/api/v1/model-clearance/registry/{entry_id}/rollback")
async def rollback_model_digest(entry_id: str, request: Request):
    """T903: Rollback model locked digest to target verified baseline."""
    from domain.model_clearance.registry import get_registry_store
    try:
        body = await request.json()
    except Exception:
        body = {}
    target_digest = str(body.get("target_digest", "")).strip()
    operator = str(body.get("operator", "lenovo-infra-ops"))
    reason = str(body.get("reason", "Rollback to verified baseline digest"))
    if not target_digest:
        _err(400, "target_digest is required for rollback", code="missing_field")

    entry = get_registry_store().rollback_to_last_known_good(
        entry_id=entry_id,
        target_digest=target_digest,
        operator=operator,
        reason=reason,
    )
    if not entry:
        _err(404, f"Registry entry {entry_id} not found", code="not_found")
    return {
        "status": "rollback_completed",
        "entry_id": entry_id,
        "locked_digest": entry.locked_digest,
        "operator": operator,
        "entry": entry.to_dict(),
    }

