"""CHALLENGE 议程路由 — 论文 Eq.(3)(4) 的 Γ_k 实现.

论文 Section 4.2：来自中/外环的 CHALLENGE 会依据其 Niche 环与当前议程阶段，
把议程**回退**到需要补充或修订的 ORID 阶段，转化为事实补充、风险约束、
工具替换、流程修订或回滚规则。

    ω_{k,t+1} = Φ(ω_{k,t}, σ_{k,t}; Γ_k)

本模块只做纯函数与预算记账，不涉及 async / LLM，便于单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# 论文 ORID 四阶段顺序；索引 +1 即 plaza_engine 的 phase_num（1-4）
ORID_ORDER: Tuple[str, ...] = ("objective", "reflective", "interpretive", "decisional")

ORID_LABELS: Dict[str, str] = {
    "objective": "客观事实",
    "reflective": "风险直觉",
    "interpretive": "方案思辨",
    "decisional": "五指决策",
}

# 论文 4.2：内环持执行知识→回 O 补事实；中环持失效模式→回 R 补风险；
# 外环持溯源/版本→回 I 重议方案。
RING_TARGET: Dict[str, str] = {
    "inner": "objective",
    "middle": "reflective",
    "outer": "interpretive",
}

# 防死循环：同一 (来源阶段, 目标阶段) 对最多回退 N 次
MAX_ROUTES_PER_PAIR = 2
# 硬上限：4 个正常阶段 + 最多 6 次回退重跑
MAX_PHASE_RUNS = len(ORID_ORDER) + MAX_ROUTES_PER_PAIR * 3


def phase_name(phase_num: int) -> str:
    """phase_num(1-4) → ORID 阶段名。越界回落到首尾阶段。"""
    idx = min(max(phase_num - 1, 0), len(ORID_ORDER) - 1)
    return ORID_ORDER[idx]


def phase_number(name: str) -> int:
    """ORID 阶段名 → phase_num(1-4)。未知名字视为 objective。"""
    try:
        return ORID_ORDER.index(name) + 1
    except ValueError:
        return 1


def route_challenge(current_phase: str, niche_ring: str, signal: str) -> Optional[str]:
    """论文 Eq.(4)：CHALLENGE 按 Niche 环回退到目标阶段。

    仅 CHALLENGE 触发；且只能**向后回退**，不能向前跳（向前跳会跳过必经阶段）。
    返回 None 表示不路由。
    """
    if str(signal or "").lower() != "challenge":
        return None
    target = RING_TARGET.get(str(niche_ring or "").lower())
    if target is None:
        return None
    if phase_number(target) >= phase_number(current_phase):
        return None
    return target


@dataclass
class ChallengeRouter:
    """带预算的 Γ_k 记账器 —— 保证议程一定收敛。"""

    max_routes_per_pair: int = MAX_ROUTES_PER_PAIR
    _used: Dict[Tuple[str, str], int] = field(default_factory=dict)
    routes: List[Dict[str, Any]] = field(default_factory=list)

    def route(
        self,
        current_phase: str,
        niche_ring: str,
        signal: str,
        *,
        agent_id: str = "",
        utterance_id: str = "",
    ) -> Optional[str]:
        """尝试路由。返回目标阶段名；预算耗尽或不满足回退条件时返回 None。"""
        target = route_challenge(current_phase, niche_ring, signal)
        if target is None:
            return None

        pair = (current_phase, target)
        if self._used.get(pair, 0) >= self.max_routes_per_pair:
            self.routes.append({
                "from_phase": current_phase,
                "target_phase": target,
                "niche_ring": niche_ring,
                "agent_id": agent_id,
                "utterance_id": utterance_id,
                "applied": False,
                "reason": "budget_exhausted",
            })
            return None

        self._used[pair] = self._used.get(pair, 0) + 1
        self.routes.append({
            "from_phase": current_phase,
            "target_phase": target,
            "niche_ring": niche_ring,
            "agent_id": agent_id,
            "utterance_id": utterance_id,
            "applied": True,
            "reason": "challenge_routed",
        })
        return target

    def budget_left(self, current_phase: str, target_phase: str) -> int:
        used = self._used.get((current_phase, target_phase), 0)
        return max(self.max_routes_per_pair - used, 0)

    def applied_routes(self) -> List[Dict[str, Any]]:
        return [r for r in self.routes if r.get("applied")]


def build_revisit_notice(target_phase: str, ring: str, excerpt: str = "") -> str:
    """回退时议事长的固定引导语（确定性，不调用 LLM）。"""
    label = ORID_LABELS.get(target_phase, target_phase)
    ring_cn = {"inner": "内环", "middle": "中环", "outer": "外环"}.get(ring, ring)
    tip = {
        "objective": "请补充可验证的事实或工具前置条件。",
        "reflective": "请补充失效模式、风险约束或回滚边界。",
        "interpretive": "请重新比较候选方案与因果链。",
    }.get(target_phase, "请补充相关信息。")
    quoted = f"（质疑要点：{excerpt.strip()[:60]}）" if excerpt else ""
    return f"⟲ 收到{ring_cn}质疑{quoted}，议程回到第「{label}」层。{tip}"
