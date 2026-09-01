# -*- coding: utf-8 -*-
"""智能体广场 — 数据模型.

灵感来源：维特鲁威环形比例 + 威尔士议事厅向心结构 + 科幻美学。
广场是一个环形的多智能体讨论空间，中心为数字奇点（Digital Singularity），
座席环绕其四周，12个壁龛提供私有交互接口。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


class DiscussionStatus(str, enum.Enum):
    """讨论状态流转: open → in_progress → summarizing → closed."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    SUMMARIZING = "summarizing"
    CLOSED = "closed"


class SeatTier(str, enum.Enum):
    """座席层级 — 三层同心圆阶梯（致敬尤利亚议事堂）."""
    INNER = "inner"       # 内圈 — 核心讨论者
    MIDDLE = "middle"     # 中圈 — 积极参与者
    OUTER = "outer"       # 外圈 — 观察者/旁听


class NicheRole(str, enum.Enum):
    """壁龛角色 — 12个弧形壁龛的功能定义."""
    MODERATOR = "moderator"         # 主持人壁龛
    ANALYST = "analyst"             # 分析师壁龛
    CHALLENGER = "challenger"       # 挑战者壁龛
    SYNTHESIZER = "synthesizer"     # 综合者壁龛
    OBSERVER = "observer"           # 观察者壁龛


# 论文 Section 4.2 12-Niche 三环知识功能拓扑
NICHE_RINGS: Dict[str, List[str]] = {
    "inner": ["goal", "tool", "step", "precondition"],           # 直接执行知识
    "middle": ["detection", "failure_mode", "risk", "rollback"],  # 风险与边界
    "outer": ["provenance", "version", "audit", "change"],        # 证据与记录
}


def ring_of(niche_name: str) -> str:
    """根据壁龛功能名称获取所在三环层级."""
    clean = str(niche_name or "").lower().strip()
    for ring, names in NICHE_RINGS.items():
        if clean in names:
            return ring
    return "outer"


def role_coverage(required: Set[str], activated: Set[str]) -> float:
    """论文 7.4 C_role / role coverage 指标 (目标 1.0)."""
    if not required:
        return 1.0
    return round(len(required & activated) / len(required), 4)


@dataclass
class PlazaMessage:
    """广场讨论消息 — 在数字奇点中显示的信息流."""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    discussion_id: str = ""
    agent_id: str = ""
    agent_name: str = ""
    role: str = ""                    # agent的角色
    niche_role: str = ""              # 在本次讨论中的壁龛角色
    content: str = ""
    round_number: int = 0             # 第几轮讨论
    reply_to: Optional[str] = None    # 回复哪条消息
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)
    seq: int = -1                     # 消息序号(0-based), 引擎追加时自动分配, 用于 SSE Last-Event-ID 重放去重

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "discussion_id": self.discussion_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "niche_role": self.niche_role,
            "content": self.content,
            "round_number": self.round_number,
            "reply_to": self.reply_to,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "seq": self.seq,
        }


@dataclass
class Participant:
    """广场参与者 — 座席上的智能体."""
    agent_id: str
    agent_name: str = ""
    role: str = ""                    # 原始角色
    team_id: str = ""
    seat_tier: SeatTier = SeatTier.MIDDLE
    niche_role: NicheRole = NicheRole.OBSERVER
    niche_index: int = -1             # 壁龛编号 0-11
    joined_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "team_id": self.team_id,
            "seat_tier": self.seat_tier.value,
            "niche_role": self.niche_role.value,
            "niche_index": self.niche_index,
            "joined_at": self.joined_at,
        }


@dataclass
class Discussion:
    """广场讨论 — 在数字奇点上方投影的全息话题."""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    plaza_id: str = ""
    topic: str = ""
    description: str = ""
    status: DiscussionStatus = DiscussionStatus.OPEN
    moderator_agent_id: str = ""      # 主持人
    max_rounds: int = 5               # 最大讨论轮次
    current_round: int = 0
    messages: List[PlazaMessage] = field(default_factory=list)
    goal: str = ""                    # 讨论目标
    summary: str = ""                 # 讨论总结
    key_conclusions: List[str] = field(default_factory=list)
    plan: Dict[str, Any] = field(default_factory=dict)  # 议事长生成的执行计划
    assigned_team_id: str = ""        # 计划指派给的团队
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_messages: bool = False) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "plaza_id": self.plaza_id,
            "topic": self.topic,
            "description": self.description,
            "status": self.status.value,
            "moderator_agent_id": self.moderator_agent_id,
            "max_rounds": self.max_rounds,
            "current_round": self.current_round,
            "message_count": len(self.messages),
            "goal": self.goal,
            "summary": self.summary,
            "key_conclusions": self.key_conclusions,
            "plan": self.plan,
            "assigned_team_id": self.assigned_team_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }
        if include_messages:
            d["messages"] = [m.to_dict() for m in self.messages]
        return d


@dataclass
class Plaza:
    """智能体广场 — 维特鲁威环形议事空间.

    几何参数:
    - diameter: 广场直径 D
    - height: 穹顶高度 H = D/2 (维特鲁威声学公式)
    - oculus_diameter: 穹顶开孔直径 (万神殿 Oculus)
    - niche_count: 壁龛数量 (固定 12)
    - seat_tiers: 座席层数 (固定 3)
    """
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    name: str = ""
    description: str = ""

    # 维特鲁威几何参数
    diameter: float = 60.0            # 广场直径 D (米)
    height: float = 30.0              # H = D/2
    oculus_diameter: float = 9.0      # 穹顶开孔直径
    niche_count: int = 12             # 12 个壁龛
    seat_tiers: int = 3               # 三层座席

    # 参与者与讨论
    participants: Dict[str, Participant] = field(default_factory=dict)
    discussions: Dict[str, Discussion] = field(default_factory=dict)

    # 数字孪生层模式
    visual_mode: str = "modern"       # modern | rome_320ad | senedd

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_details: bool = False) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "diameter": self.diameter,
            "height": self.height,
            "oculus_diameter": self.oculus_diameter,
            "niche_count": self.niche_count,
            "seat_tiers": self.seat_tiers,
            "visual_mode": self.visual_mode,
            "participant_count": len(self.participants),
            "discussion_count": len(self.discussions),
            "active_discussions": sum(
                1 for d in self.discussions.values()
                if d.status in (DiscussionStatus.OPEN, DiscussionStatus.IN_PROGRESS)
            ),
            "created_at": self.created_at,
        }
        if include_details:
            d["participants"] = [p.to_dict() for p in self.participants.values()]
            d["discussions"] = [
                disc.to_dict() for disc in self.discussions.values()
            ]
        return d


# ── 预设话题模板 ──────────────────────────────────────────────

PRESET_TOPICS = [
    {
        "topic": "如何设计一个高效的智能体协作系统？",
        "description": "探讨多智能体系统中的通信协议、任务分配策略和冲突解决机制。",
    },
    {
        "topic": "构建 Agent 广场功能的技术方案讨论",
        "description": "讨论广场的后端架构、实时消息推送、讨论编排逻辑和前端可视化方案。",
    },
    {
        "topic": "代码质量保障的最佳实践",
        "description": "从单元测试、集成测试、代码审查、CI/CD 等维度讨论如何保障代码质量。",
    },
    {
        "topic": "AI 时代的软件架构演进",
        "description": "LLM 驱动的智能体如何改变传统的微服务架构？讨论 Agent-native 架构模式。",
    },
    {
        "topic": "从维特鲁威到数字孪生：建筑智慧的传承",
        "description": "古罗马建筑的比例法则如何启发现代数字空间设计？讨论物理与虚拟的融合。",
    },
]
