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
    from agents.startup_health import assess_trading_runtime
    from integrations.tradingagents.version_check import check_tradingagents_release

    layer = assess_trading_runtime()
    release = await check_tradingagents_release()
    return {"layer": layer, "release_check": release, "auto_upgrade": False}


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
    from integrations.tradingagents.config_mapper import map_agent_config, validate_mapped_config

    cfg = map_agent_config(
        quick_model=body.quick_model,
        deep_model=body.deep_model,
        debate_rounds=body.debate_rounds,
        risk_rounds=body.risk_rounds,
        analysts=body.analysts,
    )
    return validate_mapped_config(cfg)


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

    if body.profile not in ("ai60", "dufu", "both"):
        _err(400, "profile must be ai60, dufu or both", code="invalid_profile")
    store = get_source_config_store()
    existing = {s.url for s in store.list() if s.url}
    created, skipped, errors = [], [], []
    target_teams = ["ai_news_60s", "dufu_world_intel"] if body.profile == "both" else ["ai_news_60s" if body.profile == "ai60" else "dufu_world_intel"]
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
        _err(400, "team_id must be ai_news_60s or dufu_world_intel", code="invalid_team")


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
    return await _schedule_service().run_once(schedule_id)


class InformationRunCreate(BaseModel):
    team_id: str
    source_ids: List[str] = Field(default_factory=list)
    wait: bool = False
    wait_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)


@router.post("/api/v1/information-runs")
async def create_information_run(body: InformationRunCreate):
    """Enqueue a background information run. Returns 202 unless wait=true."""
    if body.team_id not in ("ai_news_60s", "dufu_world_intel"):
        _err(400, "team_id must be ai_news_60s or dufu_world_intel", code="invalid_team")
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
    if team_id not in ("ai_news_60s", "dufu_world_intel"):
        _err(400, "team_id must be ai_news_60s or dufu_world_intel", code="invalid_team")
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
    for channel in ("ai_news_60s", "dufu_world_intel"):
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


# ── Investment simulations ───────────────────────────────────────

class SimCreate(BaseModel):
    ticker: str
    trade_date: str
    sector: str = ""
    initial_cash: float = 100_000
    asset_type: str = "stock"
    debate_rounds: int = 1
    risk_rounds: int = 1
    analysts: Optional[List[str]] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    assembly: Optional[List[Dict[str, Any]]] = None
    modules: Optional[List[Dict[str, Any]]] = None
    mode: str = "fixture"
    auto_start: bool = False
    quick_model: Optional[Dict[str, Any]] = None
    deep_model: Optional[Dict[str, Any]] = None


@router.get("/api/v1/investment-simulations")
async def list_simulations(limit: int = Query(50, ge=1, le=200)):
    from domain.investment_simulation.store import get_simulation_store

    return {"simulations": [s.to_dict() for s in get_simulation_store().list(limit=limit)]}


@router.post("/api/v1/investment-simulations")
async def create_sim(body: SimCreate):
    from domain.investment_simulation.orchestrator import create_simulation, start_simulation

    try:
        payload = body.model_dump()
        auto_start = bool(payload.pop("auto_start", False))
        sim = await create_simulation(payload)
        if auto_start:
            sim = await start_simulation(sim.run_id)
        return sim.to_dict()
    except ValueError as exc:
        _err(400, str(exc), code="invalid_request")


@router.get("/api/v1/investment-simulations/{run_id}")
async def get_sim(run_id: str):
    from domain.investment_simulation.store import get_simulation_store

    sim = get_simulation_store().get(run_id)
    if not sim:
        _err(404, "run not found", code="not_found")
    return sim.to_dict()


@router.post("/api/v1/investment-simulations/{run_id}/start")
async def start_sim(run_id: str):
    from domain.investment_simulation.orchestrator import start_simulation

    try:
        sim = await start_simulation(run_id)
        return sim.to_dict()
    except KeyError:
        _err(404, "run not found", code="not_found")
    except ValueError as exc:
        _err(409, str(exc), code="resume_conflict")


@router.post("/api/v1/investment-simulations/{run_id}/cancel")
async def cancel_sim(run_id: str):
    from domain.investment_simulation.orchestrator import cancel_simulation

    try:
        sim = await cancel_simulation(run_id)
        return sim.to_dict()
    except KeyError:
        _err(404, "run not found", code="not_found")


@router.get("/api/v1/investment-simulations/{run_id}/events")
async def sim_events(run_id: str, after_seq: int = Query(0, ge=0)):
    from domain.investment_simulation.store import get_simulation_store

    store = get_simulation_store()
    if not store.get(run_id):
        _err(404, "run not found", code="not_found")
    events = store.list_events(run_id, after_seq=after_seq)
    return {"run_id": run_id, "events": [e.to_dict() for e in events]}


@router.get("/api/v1/investment-simulations/{run_id}/events/stream")
async def sim_events_stream(run_id: str, after_seq: int = Query(0, ge=0)):
    """SSE stream for investment engine events (does not touch Plaza SSE)."""
    import asyncio
    import json as _json

    from fastapi.responses import StreamingResponse

    from domain.investment_simulation.store import get_simulation_store

    store = get_simulation_store()
    if not store.get(run_id):
        _err(404, "run not found", code="not_found")

    async def gen():
        cursor = after_seq
        idle_ticks = 0
        while True:
            sim = store.get(run_id)
            if sim is None:
                yield f"event: error\ndata: {_json.dumps({'error': 'missing'})}\n\n"
                break
            events = store.list_events(run_id, after_seq=cursor)
            for ev in events:
                cursor = max(cursor, ev.seq)
                yield f"data: {_json.dumps(ev.to_dict(), ensure_ascii=False)}\n\n"
                idle_ticks = 0
            if sim.status in ("completed", "failed", "cancelled") and not events:
                yield f"event: done\ndata: {_json.dumps({'status': sim.status, 'last_seq': cursor})}\n\n"
                break
            idle_ticks += 1
            if idle_ticks > 600:  # ~2 min idle safety
                yield f"event: timeout\ndata: {_json.dumps({'last_seq': cursor})}\n\n"
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/v1/investment-simulations/{run_id}/reports")
async def sim_reports(run_id: str):
    from domain.investment_simulation.store import get_simulation_store

    store = get_simulation_store()
    if not store.get(run_id):
        _err(404, "run not found", code="not_found")
    index = store.get_reports_index(run_id) or {}
    return {"run_id": run_id, "reports": index}


@router.get("/api/v1/investment-simulations/{run_id}/portfolio")
async def sim_portfolio(run_id: str):
    from domain.investment_simulation.store import get_simulation_store

    store = get_simulation_store()
    if not store.get(run_id):
        _err(404, "run not found", code="not_found")
    pf = store.get_portfolio(run_id)
    if not pf:
        return {"run_id": run_id, "portfolio": None, "empty": True}
    return {"run_id": run_id, "portfolio": pf.to_dict(), "empty": False}


# ── Model Admission Clearance APIs (T503 / T807) ──────────────────────────

class ClearanceAppCreate(BaseModel):
    model_id: str
    applicant: str = "security-admin"
    revision: str = "main"
    weights_uri: str = ""
    local_path: str = ""
    expected_signer_identity: Optional[str] = None
    auto_submit: bool = False


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
    from domain.model_clearance.models import AppStatus, ModelApplication, ModelIdentity
    from domain.model_clearance.registry import get_registry_store
    from domain.model_clearance.store import get_clearance_store

    app_id = f"app-{uuid.uuid4().hex[:10]}"
    app = ModelApplication(
        application_id=app_id,
        applicant=body.applicant,
        identity=ModelIdentity(
            model_id=body.model_id.strip(),
            revision=body.revision.strip(),
            weights_uri=body.weights_uri.strip(),
            local_path=body.local_path.strip(),
            expected_signer_identity=body.expected_signer_identity,
        ),
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

