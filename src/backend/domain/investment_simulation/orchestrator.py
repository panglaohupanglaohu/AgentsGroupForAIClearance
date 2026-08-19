# -*- coding: utf-8 -*-
"""T402/T403/T406 — Independent simulation orchestration + event stream."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional  # noqa: F401 — Dict used by assembly known_as_of

from integrations.tradingagents.config_mapper import map_agent_config, validate_mapped_config
from integrations.tradingagents.graph_adapter import GRAPH_NODES, StockAgentsTradingGraph
from integrations.tradingagents.report_adapter import save_reports

from .assembly import compile_assembly, modules_from_legacy_sources
from .models import InvestmentEvent, InvestmentSimulation, utc_now
from .portfolio import PaperPortfolio, apply_decision
from .store import SimulationStore, get_simulation_store

logger = logging.getLogger(__name__)

# In-process cancel flags and tasks
_cancel_flags: Dict[str, asyncio.Event] = {}
_tasks: Dict[str, asyncio.Task] = {}
_token_budget: Dict[str, int] = {}  # run_id -> remaining abstract tokens


class BudgetExceeded(Exception):
    pass


def _estimate_node_cost() -> int:
    return 1000  # abstract tokens per node for fixture mode


async def create_simulation(
    payload: Dict[str, Any],
    *,
    store: Optional[SimulationStore] = None,
    models: Optional[Dict[str, Any]] = None,
) -> InvestmentSimulation:
    store = store or get_simulation_store()
    ticker = str(payload.get("ticker") or "").upper().strip()
    if not ticker or not ticker.replace(".", "").isalnum() or len(ticker) > 12:
        raise ValueError("Invalid ticker")
    trade_date = str(payload.get("trade_date") or payload.get("date") or "")
    if not trade_date:
        raise ValueError("trade_date required (YYYY-MM-DD or ISO)")
    # Future leakage protection: trade_date is the cutoff for context

    quick = (models or {}).get("quick") or payload.get("quick_model")
    deep = (models or {}).get("deep") or payload.get("deep_model")
    mapped = map_agent_config(
        quick_model=quick,
        deep_model=deep,
        debate_rounds=int(payload.get("debate_rounds") or 1),
        risk_rounds=int(payload.get("risk_rounds") or 1),
        analysts=payload.get("analysts"),
    )
    val = validate_mapped_config(mapped)
    if not val["ok"]:
        raise ValueError(f"Invalid config: {val['errors']}")

    raw_modules = payload.get("assembly") or payload.get("modules") or payload.get("sources") or []
    modules = modules_from_legacy_sources(list(raw_modules))
    # Resolve document as_of for future-leakage filter
    known_as_of: Dict[str, str] = {}
    try:
        from domain.information_sources.documents import get_document_store

        docs_store = get_document_store()
        for m in modules:
            mid = str(m.get("module_id") or "")
            if m.get("kind") == "document" or mid.startswith("document:"):
                if mid in ("document:latest", "document:latest_ai", "document:latest_world"):
                    ch = "ai_news_60s" if "world" not in mid else "dufu_world_intel"
                    if mid == "document:latest":
                        # Prefer both channels latest if present
                        for channel in ("ai_news_60s", "dufu_world_intel"):
                            d = docs_store.get_latest(channel)
                            if d:
                                known_as_of[d.document_id] = d.as_of
                                known_as_of[mid] = d.as_of
                    else:
                        d = docs_store.get_latest(ch)
                        if d:
                            known_as_of[mid] = d.as_of
                            known_as_of[d.document_id] = d.as_of
                else:
                    d = docs_store.get_by_id(mid)
                    if d:
                        known_as_of[mid] = d.as_of
    except Exception:
        pass

    plan = compile_assembly(
        modules,
        ticker=ticker,
        cutoff=trade_date,
        known_document_as_of=known_as_of,
    )
    assembly_snapshot = plan.to_dict()
    # Freeze: never mutate after create
    assembly_snapshot["frozen_at"] = utc_now()
    assembly_snapshot["immutable"] = True

    engine_config_snapshot = {
        "ticker": ticker,
        "trade_date": trade_date,
        "sector": str(payload.get("sector") or "").strip()[:80],
        "initial_cash": float(payload.get("initial_cash") or 100_000),
        "debate_rounds": mapped["max_debate_rounds"],
        "risk_rounds": mapped["max_risk_discuss_rounds"],
        "mode": str(payload.get("mode") or "fixture"),
        "models": {
            "quick_model_id": mapped.get("quick_model_id"),
            "deep_model_id": mapped.get("deep_model_id"),
            "llm_provider": mapped.get("llm_provider"),
            "deep_think_llm": mapped.get("deep_think_llm"),
            "quick_think_llm": mapped.get("quick_think_llm"),
        },
        "adapter_version": "1.0.0",
        "assembly_hash": plan.snapshot_hash,
    }

    sim = InvestmentSimulation.create(
        ticker=ticker,
        trade_date=trade_date,
        sector=str(payload.get("sector") or "").strip()[:80],
        initial_cash=float(payload.get("initial_cash") or 100_000),
        asset_type=str(payload.get("asset_type") or "stock"),
        models=engine_config_snapshot["models"],
        analysts=list(mapped.get("selected_analysts") or []),
        debate_rounds=mapped["max_debate_rounds"],
        risk_rounds=mapped["max_risk_discuss_rounds"],
        sources=list(payload.get("sources") or modules),
        assembly_snapshot=assembly_snapshot,
        engine_config_snapshot=engine_config_snapshot,
        mode=str(payload.get("mode") or "fixture"),
        config_snapshot=mapped,
        graph_shape=list(GRAPH_NODES),
        status="queued",
    )
    store.save(sim)
    store.save_portfolio(sim.run_id, PaperPortfolio(cash=sim.initial_cash))
    return sim


async def start_simulation(run_id: str, *, store: Optional[SimulationStore] = None) -> InvestmentSimulation:
    store = store or get_simulation_store()
    sim = store.get(run_id)
    if sim is None:
        raise KeyError(run_id)
    if sim.status == "running":
        return sim
    if sim.status in ("completed", "cancelled"):
        # Recovery: only resume if checkpoint graph shape matches
        if sim.checkpoint.get("graph_shape") and sim.checkpoint["graph_shape"] != sim.graph_shape:
            raise ValueError("Cannot resume: graph_shape mismatch (prevents checkpoint cross-talk)")
    sim.status = "running"
    sim.error = ""
    store.save(sim)
    _cancel_flags[run_id] = asyncio.Event()
    budget = int((sim.config_snapshot or {}).get("token_budget") or 50_000)
    _token_budget[run_id] = budget
    task = asyncio.create_task(_run_loop(run_id))
    _tasks[run_id] = task
    return sim


async def cancel_simulation(run_id: str, *, store: Optional[SimulationStore] = None) -> InvestmentSimulation:
    store = store or get_simulation_store()
    flag = _cancel_flags.get(run_id)
    if flag:
        flag.set()
    sim = store.get(run_id)
    if sim and sim.status == "running":
        sim.status = "cancelled"
        store.save(sim)
    elif sim is None:
        raise KeyError(run_id)
    return sim  # type: ignore


async def _run_loop(run_id: str) -> None:
    store = get_simulation_store()
    sim = store.get(run_id)
    if sim is None:
        return
    cancel = _cancel_flags.get(run_id) or asyncio.Event()
    seq = sim.last_event_cursor
    try:
        graph = StockAgentsTradingGraph(
            config=sim.config_snapshot,
            force_fixture=(sim.mode == "fixture"),
        )
        # Shape lock for recovery
        sim.checkpoint = {
            "graph_shape": list(graph.graph_shape),
            "adapter_version": graph.graph_shape and "1.0.0",
            "started_at": utc_now(),
        }
        sim.graph_shape = list(graph.graph_shape)
        store.save(sim)

        result = await graph.run(
            ticker=sim.ticker,
            trade_date=sim.trade_date,
            sector=sim.sector,
            run_id=run_id,
            mode=sim.mode,
        )
        for ev in result.events:
            if cancel.is_set():
                sim.status = "cancelled"
                store.save(sim)
                return
            remaining = _token_budget.get(run_id, 50_000)
            cost = _estimate_node_cost()
            if remaining < cost:
                seq += 1
                store.append_event(
                    InvestmentEvent(
                        run_id=run_id,
                        seq=seq,
                        participant="BudgetGuard",
                        phase="budget",
                        content=f"Token budget exceeded; stopped before {ev.node}",
                        status="failed",
                        node="budget_guard",
                    )
                )
                sim.status = "failed"
                sim.error = "token budget exceeded"
                sim.last_event_cursor = seq
                sim.cost = {"abstract_tokens_used": 50_000 - remaining, "stopped": True}
                store.save(sim)
                return
            _token_budget[run_id] = remaining - cost
            seq += 1
            store.append_event(
                InvestmentEvent(
                    run_id=run_id,
                    seq=seq,
                    participant=ev.participant,
                    phase=ev.phase,
                    content=ev.content,
                    status=ev.status,
                    evidence=list(ev.evidence_refs),
                    node=ev.node,
                    structured=dict(getattr(ev, "structured", None) or {}),
                    ts=ev.ts,
                )
            )
            sim.last_event_cursor = seq
            sim.checkpoint["last_node"] = ev.node
            sim.checkpoint["last_phase"] = ev.phase
            # Never rewrite assembly_snapshot after create
            if seq % 4 == 0:
                store.save(sim)
            # Fixture mode: stage delay for live journey visibility
            await asyncio.sleep(0.12 if sim.mode == "fixture" else 0)

        index = save_reports(result)
        store.save_reports_index(run_id, index)
        sim.source_versions = result.context_versions
        portfolio = store.get_portfolio(run_id) or PaperPortfolio(cash=sim.initial_cash)
        apply_decision(
            portfolio,
            {**result.final_decision, "price": 100.0},
            ts=utc_now(),
            decision_ref=run_id,
        )
        store.save_portfolio(run_id, portfolio)
        seq += 1
        store.append_event(
            InvestmentEvent(
                run_id=run_id,
                seq=seq,
                participant="PaperPortfolio",
                phase="portfolio",
                content=f"Applied decision {result.final_decision.get('action')} for {sim.ticker}",
                status="completed",
                node="paper_portfolio",
                structured={
                    "label": "simulation",
                    "decision": result.final_decision,
                    "portfolio": portfolio.to_dict(),
                    "disclaimer": "研究/模拟用途，不构成投资建议，绝不连接真实券商。",
                },
            )
        )
        sim.status = "completed"
        sim.last_event_cursor = seq
        sim.cost = {
            "abstract_tokens_used": 50_000 - _token_budget.get(run_id, 0),
            "provider": (sim.models or {}).get("llm_provider"),
            "model": (sim.models or {}).get("deep_think_llm"),
        }
        store.save(sim)
    except Exception as exc:
        logger.exception("simulation %s failed", run_id)
        sim = store.get(run_id)
        if sim:
            sim.status = "failed"
            sim.error = str(exc)
            store.save(sim)
    finally:
        _tasks.pop(run_id, None)
