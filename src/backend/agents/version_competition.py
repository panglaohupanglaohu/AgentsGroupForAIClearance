r"""在位者 vs 挑战者版本竞争 — 论文 Section 5.4。

论文依据:
- Eq.(18): Δf_{i,t} = f(c_i; x_t) - f(v_s^i; x_t),  \overline{ΔF_i} = 1/N ∑ Δf_{i,t}
- Eq.(19): LCB_{1-α} = \overline{ΔF_i} - t_{1-α, N-1} * (s_{Δ,i} / √N)
- Eq.(20): G_r = 1[LCB >= δ_{min}] * C_i * H_i (统计下界 + 关键指标 + 硬约束全合取)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass
class EvalSuite:
    """论文 5.4 四类评估材料."""

    regression: List[Dict[str, Any]] = field(default_factory=list)  # D_reg 固定回归集
    current: List[Dict[str, Any]] = field(default_factory=list)     # D_cur 当前任务集
    failures: List[Dict[str, Any]] = field(default_factory=list)    # D_fail 历史失败集（硬约束）
    safety: List[Dict[str, Any]] = field(default_factory=list)      # D_safe 安全反例集（硬约束）

    def paired_cases(self) -> List[Dict[str, Any]]:
        """D_reg + D_cur 用于配对效用比较；使用 sample_id 去重."""
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for c in [*self.regression, *self.current]:
            sid = c.get("sample_id")
            if sid is not None and sid in seen:
                continue
            if sid is not None:
                seen.add(sid)
            out.append(c)
        return out


def student_t_quantile(p: float, df: int) -> float:
    """t_{p, df} 单侧分位数.

    使用 NormalDist 结合 Cornish-Fisher 展开，无需 scipy 依赖。
    """
    if df <= 0:
        return float("inf")
    # p <= 0 或 p >= 1 边界防护
    p_clamped = min(max(p, 1e-7), 1.0 - 1e-7)
    z = statistics.NormalDist().inv_cdf(p_clamped)
    # Cornish-Fisher 展开（Abramowitz & Stegun 26.7.5）
    g1 = (z**3 + z) / 4.0
    g2 = (5.0 * z**5 + 16.0 * z**3 + 3.0 * z) / 96.0
    g3 = (3.0 * z**7 + 19.0 * z**5 + 17.0 * z**3 - 15.0 * z) / 384.0
    return z + g1 / df + g2 / (df**2) + g3 / (df**3)


def lower_confidence_bound(diffs: Sequence[float], alpha: float = 0.05) -> Dict[str, Any]:
    """论文 Eq.(19) 单侧 Student-t 下置信界 LCB."""
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": 0.0, "sd": 0.0, "t": 0.0, "lcb": float("-inf")}
    mean = sum(diffs) / n
    if n == 1:
        return {"n": 1, "mean": mean, "sd": 0.0, "t": 0.0, "lcb": float("-inf")}
    try:
        sd = statistics.stdev(diffs)
    except statistics.StatisticsError:
        sd = 0.0
    t = student_t_quantile(1.0 - alpha, n - 1)
    lcb = mean - (t * sd / math.sqrt(n)) if sd > 0 else mean
    return {"n": n, "mean": round(mean, 6), "sd": round(sd, 6), "t": round(t, 4), "lcb": round(lcb, 6)}


def check_metric_constraints(metrics: Dict[str, float], spec: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """论文 Eq.(20) 的 C_i：按方向约束关键指标."""
    violations: List[str] = []
    for name, rule in spec.items():
        val = metrics.get(name)
        if val is None:
            continue
        direction = rule.get("direction", "higher")
        bound = float(rule.get("bound", 0.0))
        if direction == "higher" and val < bound:
            violations.append(f"{name}={val:.4f} < 下界{bound:.4f}")
        if direction == "lower" and val > bound:
            violations.append(f"{name}={val:.4f} > 上界{bound:.4f}")
    return {"ok": len(violations) == 0, "violations": violations}


def check_hard_constraints(challenger_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """论文 Eq.(20) 的 H_i：安全反例全过 + 历史严重失败不复现."""
    safety_fail = [
        str(r.get("sample_id", ""))
        for r in challenger_results
        if r.get("suite") == "safety" and not r.get("passed", False)
    ]
    regressed = [
        str(r.get("sample_id", ""))
        for r in challenger_results
        if r.get("suite") == "failures" and not r.get("passed", False)
    ]
    return {
        "ok": len(safety_fail) == 0 and len(regressed) == 0,
        "safety_failures": safety_fail,
        "reappeared_failures": regressed,
    }


def _aggregate_metrics(results: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    paired = [r for r in results if r.get("suite") == "paired"]
    if not paired:
        return {}
    passed_count = sum(1 for r in paired if r.get("passed", False))
    utilities = [float(r.get("utility", 0.0)) for r in paired]
    return {
        "success_rate": passed_count / len(paired),
        "mean_utility": sum(utilities) / len(utilities),
    }


def compete(
    incumbent_id: str,
    challenger_id: str,
    suite: EvalSuite,
    run_case: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    *,
    alpha: float = 0.05,
    delta_min: float = 0.0,
    metric_spec: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """完整版本竞争.

    delta_min=0 表示严格非退化；>0 表示要求最小显著增益。
    """
    diffs: List[float] = []
    challenger_results: List[Dict[str, Any]] = []

    # 1. 配对试验：同一任务样本
    for case in suite.paired_cases():
        rc = run_case(challenger_id, case)
        ri = run_case(incumbent_id, case)
        u_c = float(rc.get("utility", 0.0))
        u_i = float(ri.get("utility", 0.0))
        diffs.append(u_c - u_i)  # Eq.(18)
        challenger_results.append({**rc, "sample_id": case.get("sample_id", ""), "suite": "paired"})

    # 2. 硬约束子集（安全与回归）
    for name in ("failures", "safety"):
        for case in getattr(suite, name, []):
            rc = run_case(challenger_id, case)
            challenger_results.append({**rc, "sample_id": case.get("sample_id", ""), "suite": name})

    stat = lower_confidence_bound(diffs, alpha)  # Eq.(19)
    hard = check_hard_constraints(challenger_results)
    agg_metrics = _aggregate_metrics(challenger_results)
    cons = check_metric_constraints(agg_metrics, metric_spec or {})

    lcb_ok = stat["lcb"] >= delta_min
    accepted = lcb_ok and cons["ok"] and hard["ok"]  # Eq.(20)

    if not lcb_ok:
        reason = f"LCB={stat['lcb']:.4f} < delta_min={delta_min}（未证明非退化）"
    elif not hard["ok"]:
        reason = f"硬约束失败: {hard}"
    elif not cons["ok"]:
        reason = f"关键指标越界: {cons['violations']}"
    else:
        reason = "accepted"

    failed_samples = [
        str(r.get("sample_id", ""))
        for r in challenger_results
        if not r.get("passed", False)
    ]

    return {
        "accepted": accepted,
        "reason": reason,
        "lcb": stat["lcb"],
        "delta_min": delta_min,
        **stat,
        "constraints": cons,
        "hard": hard,
        "incumbent": incumbent_id,
        "challenger": challenger_id,
        "failed_samples": failed_samples,
    }
