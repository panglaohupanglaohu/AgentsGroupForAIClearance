# -*- coding: utf-8 -*-
"""T405 — Lightweight paper portfolio (never connects to real brokers)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Fill:
    side: str  # BUY | SELL
    ticker: str
    qty: float
    price: float
    fees: float
    ts: str
    decision_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperPortfolio:
    cash: float
    positions: Dict[str, float] = field(default_factory=dict)  # ticker -> qty
    avg_cost: Dict[str, float] = field(default_factory=dict)
    fills: List[Fill] = field(default_factory=list)
    realized_pnl: float = 0.0
    max_position_pct: float = 0.25
    fee_bps: float = 5.0  # 5 bps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash": self.cash,
            "positions": dict(self.positions),
            "avg_cost": dict(self.avg_cost),
            "fills": [f.to_dict() for f in self.fills],
            "realized_pnl": self.realized_pnl,
            "max_position_pct": self.max_position_pct,
            "fee_bps": self.fee_bps,
            "broker": None,  # never a real broker
            "disclaimer": "Paper portfolio only — research/simulation, not investment advice.",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperPortfolio":
        fills = [Fill(**f) for f in (data.get("fills") or [])]
        return cls(
            cash=float(data.get("cash") or 0),
            positions=dict(data.get("positions") or {}),
            avg_cost=dict(data.get("avg_cost") or {}),
            fills=fills,
            realized_pnl=float(data.get("realized_pnl") or 0),
            max_position_pct=float(data.get("max_position_pct") or 0.25),
            fee_bps=float(data.get("fee_bps") or 5.0),
        )


def parse_structured_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    action = str(decision.get("action") or "HOLD").upper()
    if action not in ("BUY", "SELL", "HOLD"):
        action = "HOLD"
    return {
        "action": action,
        "ticker": str(decision.get("ticker") or "").upper(),
        "confidence": float(decision.get("confidence") or 0.5),
        "rationale": str(decision.get("rationale") or ""),
        "price": float(decision.get("price") or decision.get("ref_price") or 100.0),
    }


def size_by_risk(cash: float, price: float, confidence: float, max_position_pct: float) -> float:
    if price <= 0 or cash <= 0:
        return 0.0
    budget = cash * max_position_pct * max(0.1, min(1.0, confidence))
    qty = budget / price
    return max(0.0, round(qty, 4))


def apply_decision(
    portfolio: PaperPortfolio,
    decision: Dict[str, Any],
    *,
    ts: str,
    decision_ref: str = "",
) -> PaperPortfolio:
    d = parse_structured_decision(decision)
    ticker = d["ticker"]
    price = d["price"]
    action = d["action"]
    fee_rate = portfolio.fee_bps / 10_000.0

    if action == "BUY" and ticker:
        qty = size_by_risk(portfolio.cash, price, d["confidence"], portfolio.max_position_pct)
        if qty > 0:
            cost = qty * price
            fees = cost * fee_rate
            total = cost + fees
            if total <= portfolio.cash:
                prev_qty = portfolio.positions.get(ticker, 0.0)
                prev_cost = portfolio.avg_cost.get(ticker, 0.0)
                new_qty = prev_qty + qty
                portfolio.avg_cost[ticker] = (
                    (prev_cost * prev_qty + cost) / new_qty if new_qty else price
                )
                portfolio.positions[ticker] = new_qty
                portfolio.cash -= total
                portfolio.fills.append(
                    Fill("BUY", ticker, qty, price, fees, ts, decision_ref=decision_ref)
                )
    elif action == "SELL" and ticker:
        held = portfolio.positions.get(ticker, 0.0)
        if held > 0:
            # Sell portion based on confidence
            qty = round(held * max(0.1, min(1.0, d["confidence"])), 4)
            qty = min(qty, held)
            proceeds = qty * price
            fees = proceeds * fee_rate
            avg = portfolio.avg_cost.get(ticker, price)
            portfolio.realized_pnl += (price - avg) * qty - fees
            portfolio.cash += proceeds - fees
            portfolio.positions[ticker] = held - qty
            if portfolio.positions[ticker] <= 1e-9:
                portfolio.positions.pop(ticker, None)
                portfolio.avg_cost.pop(ticker, None)
            portfolio.fills.append(
                Fill("SELL", ticker, qty, price, fees, ts, decision_ref=decision_ref)
            )
    else:
        portfolio.fills.append(
            Fill("HOLD", ticker or "N/A", 0.0, price, 0.0, ts, decision_ref=decision_ref)
        )
    return portfolio


def mark_to_market(portfolio: PaperPortfolio, prices: Dict[str, float]) -> Dict[str, Any]:
    equity = portfolio.cash
    unrealized = 0.0
    for t, qty in portfolio.positions.items():
        px = prices.get(t, portfolio.avg_cost.get(t, 0.0))
        equity += qty * px
        unrealized += (px - portfolio.avg_cost.get(t, px)) * qty
    return {
        "equity": equity,
        "cash": portfolio.cash,
        "unrealized_pnl": unrealized,
        "realized_pnl": portfolio.realized_pnl,
        "positions": dict(portfolio.positions),
    }
