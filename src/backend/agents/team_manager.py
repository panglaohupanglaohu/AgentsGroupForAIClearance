# -*- coding: utf-8 -*-
"""AgentsGroup2026 Agent Team Framework — Team Manager.

Manages multiple AgentTeam instances and provides CRUD operations for
teams, agents, and models.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import AgentProfile, AgentState, AgentTeam, ModelConfig
from .team_store import TeamStore

logger = logging.getLogger(__name__)


class TeamManager:
    """Manages the lifecycle of agent teams."""

    def __init__(self, store: Optional[TeamStore] = None) -> None:
        self._store = store or TeamStore()
        self._teams: Dict[str, AgentTeam] = self._store.load_all()

    def _persist(self) -> None:
        """Save current state to disk."""
        self._store.save_all(self._teams)

    # ── Team CRUD ──────────────────────────────────────────────────────

    def create_team(
        self,
        name: str,
        description: str = "",
        **kwargs: Any,
    ) -> AgentTeam:
        """Create a new team and register it."""
        team = AgentTeam(name=name, description=description, **kwargs)
        if team.team_id in self._teams:
            raise ValueError(f"Team already exists: {team.team_id}")
        self._teams[team.team_id] = team
        self._persist()
        return team

    def get_team(self, team_id: str) -> Optional[AgentTeam]:
        """Get a team by ID."""
        return self._teams.get(team_id)

    def register_team(self, team: AgentTeam, overwrite: bool = False) -> AgentTeam:
        """Register a pre-built team and persist it.

        Bootstrap teams that write straight into ``_teams`` stay memory-only and
        vanish on restart; this keeps them on disk like user-created teams.
        """
        existing = self._teams.get(team.team_id)
        if existing is not None and not overwrite:
            return existing
        self._teams[team.team_id] = team
        self._persist()
        return team

    def list_teams(self) -> List[AgentTeam]:
        """Return all teams."""
        return list(self._teams.values())

    def delete_team(self, team_id: str) -> Optional[AgentTeam]:
        """Delete a team. Returns the removed team or None."""
        team = self._teams.pop(team_id, None)
        if team:
            self._persist()
        return team

    # ── Agent management ───────────────────────────────────────────────

    def add_agent_to_team(
        self,
        team_id: str,
        agent: AgentProfile,
    ) -> bool:
        """Add an agent to a team. Returns True on success."""
        team = self._teams.get(team_id)
        if team is None:
            return False
        team.add_agent(agent)
        self._persist()
        return True

    def remove_agent_from_team(
        self,
        team_id: str,
        agent_id: str,
    ) -> Optional[AgentProfile]:
        """Remove an agent from a team."""
        team = self._teams.get(team_id)
        if team is None:
            return None
        agent = team.remove_agent(agent_id)
        if agent:
            self._persist()
        return agent

    def get_agent(
        self,
        team_id: str,
        agent_id: str,
    ) -> Optional[AgentProfile]:
        """Get a specific agent from a team."""
        team = self._teams.get(team_id)
        if team is None:
            return None
        return team.get_agent(agent_id)

    def list_agents(self, team_id: str) -> List[AgentProfile]:
        """List all agents in a team."""
        team = self._teams.get(team_id)
        if team is None:
            return []
        return list(team.agents.values())

    # ── Model management ───────────────────────────────────────────────

    def add_model_to_team(
        self,
        team_id: str,
        model: ModelConfig,
    ) -> bool:
        """Add a model to a team. Returns True on success."""
        team = self._teams.get(team_id)
        if team is None:
            return False
        team.add_model(model)
        self._persist()
        return True

    def remove_model_from_team(
        self,
        team_id: str,
        model_id: str,
    ) -> Optional[ModelConfig]:
        """Remove a model from a team."""
        team = self._teams.get(team_id)
        if team is None:
            return None
        model = team.remove_model(model_id)
        if model:
            self._persist()
        return model

    # ── Overview ───────────────────────────────────────────────────────

    def get_team_overview(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Return a summary dict for a team."""
        team = self._teams.get(team_id)
        if team is None:
            return None
        return {
            "team_id": team.team_id,
            "name": team.name,
            "description": team.description,
            "agent_count": len(team.agents),
            "model_count": len(team.models),
            "tool_count": len(team.tools),
            "skill_count": len(team.skills),
            "agents": [
                {"agent_id": a.agent_id, "name": a.name, "role": a.role, "state": a.state.value}
                for a in team.agents.values()
            ],
        }


    # ── Update operations ─────────────────────────────────────

    def update_team(
        self,
        team_id: str,
        **kwargs: Any,
    ) -> Optional[AgentTeam]:
        """Update team fields. Returns updated team or None."""
        team = self._teams.get(team_id)
        if team is None:
            return None
        for key, value in kwargs.items():
            if hasattr(team, key) and key not in ("team_id", "created_at"):
                setattr(team, key, value)
        self._persist()
        return team

    def duplicate_agent(
        self,
        team_id: str,
        agent_id: str,
    ) -> Optional[AgentProfile]:
        """Deep copy an agent within a team. Returns new agent or None."""
        import copy
        team = self._teams.get(team_id)
        if team is None:
            return None
        original = team.get_agent(agent_id)
        if original is None:
            return None
        new_agent = copy.deepcopy(original)
        new_agent.agent_id = ""  # triggers __post_init__ to generate new ID
        new_agent.__post_init__()
        new_agent.name = original.name + " (副本)"
        team.add_agent(new_agent)
        self._persist()
        return new_agent

    # ── Health Ledger 事件映射（Agent仿生生态运行时 P2-2） ──────────────
    # 对应 docs/Agent仿生生态运行时plan.md §3、§8：Health 代谢是唯一选择压力，
    # dormant 事件复用已有 AgentState.STOPPED，不新增枚举值；可逆，不删除。

    def apply_health_event(
        self,
        team_id: str,
        agent_id: str,
        event: str,
    ) -> Optional[AgentProfile]:
        """把 HealthLedger 产出的代谢事件映射为 Agent 生命周期状态.

        event: "dormant" | "revived"（其他值忽略并原样返回当前 Agent，不报错）。
        """
        team = self._teams.get(team_id)
        if team is None:
            return None
        agent = team.get_agent(agent_id)
        if agent is None:
            return None

        if event == "dormant":
            agent.state = AgentState.STOPPED
        elif event == "revived":
            agent.state = AgentState.IDLE
        # 未知 event：不修改状态，只返回当前 agent（调用方可自行判断）

        self._persist()
        return agent

    def revive_agent(
        self,
        team_id: str,
        agent_id: str,
        health_ledger: Any = None,
        revive_ratio: float = 0.5,
    ) -> Optional[AgentProfile]:
        """复活一个 dormant Agent：state 改回 idle + (可选)联动 HealthLedger 恢复部分 Health.

        health_ledger 为可选依赖注入（`runtime.health_ledger.HealthLedger` 实例），
        不在本方法内部硬编码 import，方便测试用 mock 或跳过联动。
        """
        agent = self.apply_health_event(team_id, agent_id, "revived")
        if agent is None:
            return None
        if health_ledger is not None:
            try:
                health_ledger.revive(agent_id, revive_ratio=revive_ratio)
            except Exception:
                pass  # Health 联动失败不应阻断状态复活本身
        return agent

    # ── 交配门禁（Agent仿生生态运行时 P4-1） ────────────────────────────
    # 对应 docs/Agent仿生生态运行时plan.md §1、§8：交配不是随意复制，
    # 只有跨过"饱暖"门槛的个体才能繁殖，复用已有 duplicate_agent，只加门禁条件。

    def can_mate(
        self,
        health_state: Any,
        saturation_threshold: float = 0.7,
    ) -> "tuple[bool, str]":
        """判定一个 Agent 是否满足交配门禁（Health 占比达标）.

        health_state 预期为 `runtime.health_ledger.HealthState` 实例（或结构相同的
        对象/dict，鸭子类型即可），依赖注入而非硬编码 import，便于测试 mock。
        """
        if health_state is None:
            return False, "no_health_state"

        # 支持 dataclass 属性访问或 dict 访问（鸭子类型）
        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        status = _get(health_state, "status", "active")
        if status == "dormant":
            return False, "dormant_cannot_mate"

        health = float(_get(health_state, "health", 0.0))
        health_max = float(_get(health_state, "health_max", 1.0))
        if health_max <= 0:
            return False, "invalid_health_max"

        ratio = health / health_max
        if ratio < saturation_threshold:
            return False, f"insufficient_saturation: {ratio:.2f} < {saturation_threshold:.2f}"

        return True, "ok"

    def mate(
        self,
        team_id: str,
        agent_id: str,
        health_state: Any = None,
        saturation_threshold: float = 0.7,
        partner_agent_id: str = "",
    ) -> Optional[AgentProfile]:
        """交配：门禁通过后调用现有 duplicate_agent，记录血统（lineage）到 metadata.

        血统信息写入 `metadata["lineage"]`，不新增 AgentProfile dataclass 字段
        （复用已有的通用 metadata 字段，保持向后兼容）。

        ND-3: 当 partner_agent_id 非空时，进行双亲 skill 交叉遗传（复合型 Skill），
        后代 skills = 双亲 skill 的随机交叉子集，而非单亲复制。
        """
        allowed, reason = self.can_mate(health_state, saturation_threshold)
        if not allowed:
            return None

        team = self._teams.get(team_id)
        if team is None:
            return None
        original = team.get_agent(agent_id)
        if original is None:
            return None

        parent_generation = int((original.metadata or {}).get("lineage", {}).get("generation", 0))

        new_agent = self.duplicate_agent(team_id, agent_id)
        if new_agent is None:
            return None

        # ── ND-3: 双亲 skill 交叉遗传 ──
        partner_skills: list = []
        if partner_agent_id:
            partner = team.get_agent(partner_agent_id)
            if partner is not None:
                partner_skills = list(partner.skills)
                # 交叉：从双亲各取约 50%，去重
                import random as _rnd
                parent_a_skills = list(original.skills)
                take_a = max(1, len(parent_a_skills) // 2) if parent_a_skills else 0
                take_b = max(1, len(partner_skills) // 2) if partner_skills else 0
                crossed = set()
                if parent_a_skills:
                    crossed.update(_rnd.sample(parent_a_skills, min(take_a, len(parent_a_skills))))
                if partner_skills:
                    crossed.update(_rnd.sample(partner_skills, min(take_b, len(partner_skills))))
                # 确保至少有一个 skill（兜底用 parent A 全量）
                if not crossed and parent_a_skills:
                    crossed = set(parent_a_skills)
                new_agent.skills = list(crossed)

        new_agent.metadata = dict(new_agent.metadata or {})
        lineage: dict = {
            "parent_agent_id": agent_id,
            "generation": parent_generation + 1,
        }
        if partner_agent_id:
            lineage["partner_agent_id"] = partner_agent_id
            lineage["crossover"] = True
        new_agent.metadata["lineage"] = lineage
        self._persist()
        return new_agent

    # ── ND-3.2: 交叉后调 skill_evolver 提炼复合 Skill（草稿，需人工确认） ──

    async def evolve_offspring_skills(
        self,
        team_id: str,
        agent_id: str,
        skill_evolver: Any = None,
    ) -> List[Dict[str, Any]]:
        """对交叉后代的 skill 调 skill_evolver 产出改进草稿.

        只对 lineage.crossover=True 的后代生效。
        产出为草稿（status=draft），经门禁+人工确认才入库（可逆原则）。
        LLM 不可用时降级跳过，不阻断流程。
        """
        team = self._teams.get(team_id)
        if team is None:
            return []
        agent = team.get_agent(agent_id)
        if agent is None:
            return []
        lineage = (agent.metadata or {}).get("lineage", {})
        if not lineage.get("crossover"):
            return []  # 非交叉后代，跳过

        if skill_evolver is None:
            try:
                from .skill_evolver import SkillEvolver
                from .api import _skill_library, _chat_harness
                if _skill_library is None:
                    return []
                skill_evolver = SkillEvolver(_skill_library, _chat_harness)
            except Exception:
                return []

        drafts: list = []
        for skill_id in (agent.skills or []):
            try:
                result = await skill_evolver.evolve_skill(
                    team_id=team_id,
                    skill_id=skill_id,
                    user_feedback=(
                        f"交叉遗传后代(skill_genome={agent.skills})，"
                        f"双亲: {lineage.get('parent_agent_id','?')} × {lineage.get('partner_agent_id','?')}"
                    ),
                )
                if result and not result.get("error"):
                    drafts.append({
                        "skill_id": skill_id,
                        "agent_id": agent_id,
                        "version": result.get("new_version"),
                        "status": "draft",
                    })
            except Exception as e:
                logger.warning("skill_evolver evolve failed for %s: %s", skill_id, e)
        return drafts

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all teams to dict."""
        return {tid: t.to_dict() for tid, t in self._teams.items()}
