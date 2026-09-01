# -*- coding: utf-8 -*-
"""Plaza Consensus Measurement — 五指量表 (Fist-to-Five) + ORID 层收敛度量.

替代原有的关键词共识计数（plaza_consensus.py v1），采用：
- Fist-to-Five: 每个参与者表达 1-5 的支持程度
  - 5指 = 全力支持，愿意带头执行
  - 4指 = 支持，有小顾虑但不影响
  - 3指 = 可以接受，跟随团队决定
  - 2指 = 有保留，希望讨论修改
  - 1指（拳头）= 根本性反对，不能接受
- Consensus = 没有人给1指，且 ≥ 多数人给≥3指
- Dissent detection: 任何1指 = blocking，必须处理

文献:
- Kaner et al. (2014) *Facilitator's Guide to Participatory Decision-Making* (五指量表)
- Lippincott et al. (2025) arXiv:2503.18765 (模糊共识建模，验证关键词共识不可靠)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("plaza_consensus")

# 五指量表常量
FIST_TO_FIVE = {
    5: "全力支持 — 我愿意带头执行",
    4: "支持 — 有小顾虑但不影响整体",
    3: "可以接受 — 跟随团队决定",
    2: "有保留 — 希望讨论修改后再决定",
    1: "根本性反对 — 我不能接受这个方向",
}


@dataclass
class FistToFiveVote:
    """单个 Agent 的五指投票."""

    agent_id: str
    agent_name: str
    fingers: int  # 1-5
    reason: str = ""  # 投票理由

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "fingers": self.fingers,
            "label": FIST_TO_FIVE.get(self.fingers, ""),
            "reason": self.reason,
        }

    @property
    def is_blocking(self) -> bool:
        return self.fingers == 1

    @property
    def is_supportive(self) -> bool:
        return self.fingers >= 4

    @property
    def is_accepting(self) -> bool:
        return self.fingers >= 3


@dataclass
class FistToFiveResult:
    """五指投票的集体结果 — 论文 Eq.(5) 共识模型."""

    votes: List[FistToFiveVote] = field(default_factory=list)
    consensus_reached: bool = False
    blocking_agents: List[str] = field(default_factory=list)
    supportive_agents: List[str] = field(default_factory=list)
    mean_fingers: float = 0.0
    median_fingers: float = 0.0
    consensus_level: str = "none"  # none | weak | strong | blocked
    rho: float = 0.0               # ρ_k 支持率: 指数 >= 3 的占比
    mu: float = 0.0                # μ_k 平均支持度

    def to_dict(self) -> Dict[str, Any]:
        return {
            "votes": [v.to_dict() for v in self.votes],
            "consensus_reached": self.consensus_reached,
            "blocking_agents": self.blocking_agents,
            "supportive_agents": self.supportive_agents,
            "mean_fingers": round(self.mean_fingers, 2),
            "median_fingers": self.median_fingers,
            "consensus_level": self.consensus_level,
            "rho": round(self.rho, 4),
            "mu": round(self.mu, 4),
        }


def collect_fist_to_five(
    votes: List[FistToFiveVote],
    consensus_threshold: int = 3,
) -> FistToFiveResult:
    """从五指投票结果计算集体共识状态.

    Parameters
    ----------
    votes : 每个参与者的投票
    consensus_threshold : 被认为"可接受"的最低指数 (默认3)

    Returns
    -------
    FistToFiveResult : 共识分析结果
    """
    if not votes:
        return FistToFiveResult()

    blocking = [v.agent_id for v in votes if v.is_blocking]
    supportive = [v.agent_id for v in votes if v.is_supportive]
    fingers_list = [v.fingers for v in votes]
    mean_f = sum(fingers_list) / len(fingers_list)
    median_f = _median(fingers_list)

    # Consensus Eq.(5): min(v_a) > 1 且 ρ_k >= 0.6 且 μ_k >= 3.0
    no_blocking = len(blocking) == 0
    accepting = sum(1 for v in votes if v.is_accepting)
    rho = accepting / len(votes) if votes else 0.0
    mu = mean_f
    majority_accept = (rho >= 0.6) and (mu >= 3.0)

    consensus_reached = no_blocking and majority_accept

    if not no_blocking:
        level = "blocked"
    elif mean_f >= 4.0 and rho >= 0.8 and all(v.fingers >= 3 for v in votes):
        level = "strong"
    elif consensus_reached:
        level = "weak"
    else:
        level = "none"

    return FistToFiveResult(
        votes=votes,
        consensus_reached=consensus_reached,
        blocking_agents=blocking,
        supportive_agents=supportive,
        mean_fingers=mean_f,
        median_fingers=median_f,
        consensus_level=level,
        rho=rho,
        mu=mu,
    )


def _median(values: List[int]) -> float:
    """计算中位数."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(sorted_vals[n // 2])
    return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0


def format_fist_to_five_summary(result: FistToFiveResult) -> str:
    """生成五指投票结果的人类可读摘要."""

    if not result.votes:
        return "无投票记录"

    lines = [
        f"五指投票结果: 均值={result.mean_fingers:.1f}/5, 中位数={result.median_fingers:.0f}/5"
    ]
    lines.append(f"共识状态: {result.consensus_level}")

    for v in result.votes:
        icon = "✋" if v.fingers >= 3 else ("✊" if v.fingers == 1 else "✌️")
        lines.append(
            f"  {icon} {v.agent_name}({v.fingers}指): {FIST_TO_FIVE.get(v.fingers, '')[:30]}"
        )

    if result.blocking_agents:
        lines.append(
            f"⚠️ 根本性反对: {', '.join(result.blocking_agents)} — 必须处理后再决策"
        )

    return "\n".join(lines)


def generate_blocking_resolution_prompt(
    blocking_agents: List[str],
    proposal_summary: str,
) -> str:
    """为处理根本性反对生成Facilitator追问提示词."""

    agents_str = ", ".join(blocking_agents)
    return (
        f"以下Agent对当前方案给出了根本性反对 (✊ 1指): {agents_str}\n\n"
        f"当前方案摘要:\n{proposal_summary}\n\n"
        "请针对每个反对者追问以下问题:\n"
        "1. 具体哪些方面让你不能接受？\n"
        "2. 需要修改哪些条件，你才能至少给出3指（可以接受）？\n"
        "3. 你认为方案中是否有可行的部分可以保留，哪些部分必须修改？"
    )
