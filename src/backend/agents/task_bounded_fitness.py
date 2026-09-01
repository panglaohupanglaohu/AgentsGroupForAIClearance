"""任务界定适应度 F_i(D) — 论文 Section 5.3。

论文依据:
- Eq.(16): 使用记录 ξ_{i,t} = (y, r, l, e, ι, f, v)
  (成功标识, 归一化回报, 延迟, 成本, 人工介入, 失败码, 环境版本)
- Eq.(17): F_i(D) = w^T x_i, w >= 0, 1^T w = 1
- 六因子:
  1. schema_quality (预检/溯源质量)
  2. success_rate (执行成功率)
  3. mean_reward (平均任务回报，失败计0不可剔除)
  4. reuse_breadth (跨团队/跨任务复用度)
  5. exec_cost (负向: 执行资源与Token开销)
  6. aging_sensitivity (负向: 跨环境版本波动率)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

FACTORS = (
    "schema_quality",
    "success_rate",
    "mean_reward",
    "reuse_breadth",
    "exec_cost",
    "aging_sensitivity",
)
NEGATIVE = frozenset({"exec_cost", "aging_sensitivity"})

DEFAULT_WEIGHTS = {
    "schema_quality": 0.15,
    "success_rate": 0.25,
    "mean_reward": 0.25,
    "reuse_breadth": 0.15,
    "exec_cost": 0.10,
    "aging_sensitivity": 0.10,
}


@dataclass
class UsageRecord:
    """论文 Eq.(16) 使用记录 ξ_{i,t}."""

    success: bool                # y
    reward: float                # r 归一化任务回报 [0, 1]
    latency_ms: float            # l
    cost: float                  # e Token或工具成本
    human_intervention: bool     # ι
    failure_code: str = ""       # f
    env_version: str = ""        # v
    team_id: str = ""


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def aggregate_factors(
    records: Sequence[UsageRecord],
    *,
    schema_quality: float = 1.0,
    cost_budget: float = 1.0,
) -> Dict[str, float]:
    """把使用记录聚合为 6 个 [0, 1] 因子.

    关键点：失败执行必须保留并计 0 回报，不得从统计中剔除。
    """
    if not records:
        return {f: 0.0 for f in FACTORS}

    n = len(records)
    success_rate = sum(1 for r in records if r.success) / n
    mean_reward = sum((r.reward if r.success else 0.0) for r in records) / n
    team_ids = {r.team_id for r in records if r.team_id}
    reuse = _clamp01(len(team_ids) / 3.0)
    avg_cost = sum(r.cost for r in records) / n
    exec_cost = _clamp01(avg_cost / max(cost_budget, 1e-9))

    # 老化敏感度：跨环境版本的成功率极差
    by_env: Dict[str, List[bool]] = {}
    for r in records:
        env = r.env_version or "_"
        by_env.setdefault(env, []).append(r.success)

    rates = [sum(1 for ok in v if ok) / len(v) for v in by_env.values() if v]
    aging = 0.0 if len(rates) < 2 else _clamp01(max(rates) - min(rates))

    return {
        "schema_quality": _clamp01(schema_quality),
        "success_rate": _clamp01(success_rate),
        "mean_reward": _clamp01(mean_reward),
        "reuse_breadth": round(reuse, 4),
        "exec_cost": round(exec_cost, 4),
        "aging_sensitivity": round(aging, 4),
    }


def compute_fitness(
    factors: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """论文 Eq.(17) F = w^T x.

    负向因子取 (1 - x) 后加权。
    """
    w = dict(weights or DEFAULT_WEIGHTS)
    total = sum(w.values())
    if total <= 0:
        raise ValueError("权重和必须为正数")
    w_norm = {k: v / total for k, v in w.items()}  # 1^T w = 1

    contrib: Dict[str, float] = {}
    F = 0.0
    for f in FACTORS:
        x = factors.get(f, 0.0)
        eff = (1.0 - x) if f in NEGATIVE else x
        c = w_norm.get(f, 0.0) * eff
        contrib[f] = round(c, 6)
        F += c

    return {
        "F": round(F, 6),
        "factors": factors,
        "weights": w_norm,
        "contributions": contrib,
        "eval_config_fingerprint": _fingerprint(w_norm),
    }


def _fingerprint(w: Dict[str, float]) -> str:
    payload = json.dumps(w, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
