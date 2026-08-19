# -*- coding: utf-8 -*-
"""T404 — Simulation persistence and recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import InvestmentEvent, InvestmentSimulation, utc_now
from .portfolio import PaperPortfolio

_DEFAULT = Path(__file__).resolve().parents[4] / "storage" / "investment_simulations"


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class SimulationStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else _DEFAULT
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def save(self, sim: InvestmentSimulation) -> None:
        sim.updated_at = utc_now()
        d = self._run_dir(sim.run_id)
        d.mkdir(parents=True, exist_ok=True)
        _atomic_write(d / "simulation.json", json.dumps(sim.to_dict(), ensure_ascii=False, indent=2))

    def get(self, run_id: str) -> Optional[InvestmentSimulation]:
        path = self._run_dir(run_id) / "simulation.json"
        if not path.exists():
            return None
        return InvestmentSimulation.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self, limit: int = 50) -> List[InvestmentSimulation]:
        runs = []
        for p in sorted(self.root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_dir():
                continue
            sim = self.get(p.name)
            if sim:
                runs.append(sim)
            if len(runs) >= limit:
                break
        return runs

    def append_event(self, event: InvestmentEvent) -> None:
        d = self._run_dir(event.run_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "events.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def list_events(self, run_id: str, after_seq: int = 0) -> List[InvestmentEvent]:
        path = self._run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        out: List[InvestmentEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if int(data.get("seq") or 0) > after_seq:
                out.append(InvestmentEvent.from_dict(data))
        return out

    def save_portfolio(self, run_id: str, portfolio: PaperPortfolio) -> None:
        d = self._run_dir(run_id)
        _atomic_write(d / "portfolio.json", json.dumps(portfolio.to_dict(), ensure_ascii=False, indent=2))

    def get_portfolio(self, run_id: str) -> Optional[PaperPortfolio]:
        path = self._run_dir(run_id) / "portfolio.json"
        if not path.exists():
            return None
        return PaperPortfolio.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_reports_index(self, run_id: str, index: Dict[str, Any]) -> None:
        d = self._run_dir(run_id)
        _atomic_write(d / "reports_index.json", json.dumps(index, ensure_ascii=False, indent=2))

    def get_reports_index(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self._run_dir(run_id) / "reports_index.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


_store: Optional[SimulationStore] = None


def get_simulation_store() -> SimulationStore:
    global _store
    if _store is None:
        _store = SimulationStore()
    return _store
