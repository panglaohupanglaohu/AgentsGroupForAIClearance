# -*- coding: utf-8 -*-
"""AgentsGroup2026 Agent Team Framework — Core Data Models.

Inspired by Clawith platform architecture:
- AgentTeam = Company (team-level resource sharing)
- AgentProfile = Employee (individual agent with personality/skills/permissions)
- ModelConfig = Model Pool entry
- ToolDefinition = Tool catalog entry
- SkillDefinition = Skill catalog entry
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────


class AgentState(Enum):
    """Agent lifecycle states."""

    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class ToolCategory(Enum):
    """Tool classification categories."""

    GENERAL = "general"
    BROWSER = "browser"
    CODE_EXECUTION = "code_execution"
    COMMUNICATION = "communication"
    FILE_OPERATION = "file_operation"
    TRIGGERS = "triggers"
    DISCOVERY = "discovery"
    DIGITAL_TWIN = "digital_twin"
    # Hermes-style tool categories
    WEB = "web"
    VISION = "vision"
    MEMORY = "memory"
    SKILLS = "skills"
    DELEGATION = "delegation"


class SkillCategory(Enum):
    """Skill classification categories."""

    GENERAL = "general"
    DIGITAL_TWIN = "digital_twin"
    AUTOMATION = "automation"
    # Hermes-style skill categories
    RESEARCH = "research"
    DOMAIN_KNOWLEDGE = "domain_knowledge"


class SkillLifecycleStage(Enum):
    """Skill lifecycle stages — 论文 Section 5.6 完整六态与兼容别名."""

    DRAFT = "draft"
    REVISION = "revision"       # 被 revise 裁决打回修改
    READY = "ready"             # 六门通过、等待版本竞争
    PUBLISHED = "published"
    DEGRADED = "degraded"
    DEPRECATED = "deprecated"   # 退出常规检索（终态）
    # 向后兼容别名（勿删）
    TEAM_LOCAL = "team_local"
    VERIFIED = "verified"
    SOLIDIFIED = "solidified"


# 合法生命周期迁移表（论文 5.6）
LIFECYCLE_TRANSITIONS: Dict[str, Set[str]] = {
    "draft": {"revision", "ready", "team_local", "verified"},
    "revision": {"draft", "ready", "team_local"},
    "ready": {"published", "revision", "verified"},
    "published": {"degraded", "deprecated", "solidified"},
    "degraded": {"published", "deprecated", "ready"},
    "deprecated": set(),
    "team_local": {"verified", "published", "draft", "ready"},
    "verified": {"published", "solidified", "team_local", "ready"},
    "solidified": {"degraded", "deprecated", "published"},
}


class Visibility(Enum):
    """Visibility level for teams/agents."""

    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class AccessLevel(Enum):
    """Permission access levels."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class AgentTemplateType(Enum):
    """Predefined agent template types."""

    RESEARCHER = "researcher"
    DEVELOPER = "developer"
    ANALYST = "analyst"
    ENGINEER = "engineer"
    COORDINATOR = "coordinator"
    CUSTOM = "custom"
    # Hermes-style agent types
    HERMES_RESEARCHER = "hermes_researcher"
    HERMES_DEVELOPER = "hermes_developer"
    HERMES_CREATIVE = "hermes_creative"


# ── Dataclasses ────────────────────────────────────────────────────────────


class AgentCollection(dict):
    """Dict-backed agent collection with legacy list-style helpers."""

    def append(self, agent: "AgentProfile") -> None:
        self[agent.agent_id] = agent

    def __getitem__(self, key: Any) -> "AgentProfile":
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


@dataclass
class ModelConfig:
    """LLM model configuration entry."""

    model_id: str = ""
    provider: str = "anthropic"
    name: str = "claude-sonnet-4-20250514"
    max_tokens: int = 65536
    temperature: float = 0.7
    is_default: bool = False
    enabled: bool = True
    api_key: str = ""
    api_base_url: str = ""

    def __post_init__(self) -> None:
        if not self.model_id:
            self.model_id = str(uuid.uuid4())[:8]

    def to_dict(self) -> Dict[str, Any]:
        """序列化。env: 引用原样保留；真实 key 脱敏（不落盘明文）。"""
        if self.api_key.startswith("env:"):
            api_key_val = self.api_key  # 环境变量引用，原样存（非敏感）
        else:
            api_key_val = ("****" + self.api_key[-4:]) if len(self.api_key) >= 4 else ("****" if self.api_key else "")
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "name": self.name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "is_default": self.is_default,
            "enabled": self.enabled,
            "api_key": api_key_val,
            "api_base_url": self.api_base_url,
            "has_api_key": bool(self.api_key),
        }

    def get_resolved_api_key(self) -> str:
        """运行时解析 api_key：env:VAR_NAME → 从环境变量读取；否则原样返回。"""
        if self.api_key.startswith("env:"):
            var_name = self.api_key[4:]
            import os
            return os.environ.get(var_name, "")
        return self.api_key


@dataclass
class ToolDefinition:
    """Tool catalog entry."""

    tool_id: str = ""
    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.BROWSER
    enabled: bool = True
    requires_approval: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    icon: str = "🔧"
    config_schema: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    is_default: bool = False
    source: str = "builtin"

    def __post_init__(self) -> None:
        if not self.tool_id:
            self.tool_id = str(uuid.uuid4())[:8]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "enabled": self.enabled,
            "requires_approval": self.requires_approval,
            "parameters": self.parameters,
            "icon": self.icon,
            "config_schema": self.config_schema,
            "config": self.config,
            "is_default": self.is_default,
            "source": self.source,
        }


@dataclass
class SkillDefinition:
    """Skill catalog entry."""

    skill_id: str = ""
    name: str = ""
    description: str = ""
    category: SkillCategory = SkillCategory.GENERAL
    required: bool = False
    enabled: bool = True
    icon: str = "⚡"
    config_schema: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    is_default: bool = False
    source: str = "builtin"
    slug: str = ""
    required_tools: List[str] = field(default_factory=list)
    instructions: str = ""
    # Lifecycle & tracking fields
    lifecycle_stage: str = "draft"
    quality_score: float = 0.0
    visibility: str = "private"
    version: int = 1
    usage_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    effectiveness: float = 0.0
    last_used_at: str = ""
    adopted_by: List[str] = field(default_factory=list)
    origin_team_id: str = ""
    lineage: str = ""
    schema_version: int = 1
    evidence_sessions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.skill_id:
            self.skill_id = str(uuid.uuid4())[:8]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value if isinstance(self.category, Enum) else self.category,
            "required": self.required,
            "enabled": self.enabled,
            "icon": self.icon,
            "config_schema": self.config_schema,
            "config": self.config,
            "is_default": self.is_default,
            "source": self.source,
            "slug": self.slug,
            "required_tools": self.required_tools,
            "has_instructions": bool(self.instructions),
            "lifecycle_stage": self.lifecycle_stage.value if isinstance(self.lifecycle_stage, Enum) else self.lifecycle_stage,
            "quality_score": self.quality_score,
            "visibility": self.visibility.value if isinstance(self.visibility, Enum) else self.visibility,
            "version": self.version,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "effectiveness": self.effectiveness,
            "last_used_at": self.last_used_at,
            "adopted_by": self.adopted_by,
            "origin_team_id": self.origin_team_id,
            "lineage": self.lineage,
        }


@dataclass
class AgentPersonality:
    """Agent personality and behavior configuration."""

    tone: str = "professional"
    language: str = "zh-CN"
    expertise_areas: List[str] = field(default_factory=list)
    response_style: str = "concise"
    creativity: float = 0.5

    def __init__(
        self,
        tone: str = "professional",
        language: str = "zh-CN",
        expertise_areas: Optional[List[str]] = None,
        response_style: str = "concise",
        creativity: float = 0.5,
        *,
        style: Optional[str] = None,
        traits: Optional[List[str]] = None,
        **_extra: Any,
    ) -> None:
        # Aliases used by some team factories (cloud_ops etc.): style→response_style, traits→expertise
        if style is not None:
            response_style = style
        areas = list(expertise_areas or [])
        if traits:
            for t in traits:
                if t and t not in areas:
                    areas.append(t)
        self.tone = tone
        self.language = language
        self.expertise_areas = areas
        self.response_style = response_style
        self.creativity = float(creativity) if creativity is not None else 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tone": self.tone,
            "language": self.language,
            "expertise_areas": self.expertise_areas,
            "response_style": self.response_style,
            "creativity": self.creativity,
        }


@dataclass
class ToolsetDistribution:
    """Hermes-style probabilistic toolset distribution.

    Each toolset has a % probability of being available per turn.
    Inspired by NousResearch/hermes-agent toolset_distributions.py.
    """

    name: str = "default"
    description: str = ""
    toolsets: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "toolsets": self.toolsets,
        }


@dataclass
class HermesAgentConfig:
    """Hermes-style agent configuration — extends AgentProfile with
    learning loop, memory, skills, toolsets, and context management.

    Inspired by NousResearch/hermes-agent architecture:
    - Closed learning loop (skills from experience)
    - Persistent memory across sessions
    - Toolset distributions for probabilistic tool access
    - SOUL.md persona
    - Context files (AGENTS.md, HERMES.md)
    - Session search (cross-session recall)
    - Delegate/subagent parallelization
    """

    # Agent loop parameters
    max_iterations: int = 90
    iteration_budget: int = 90

    # Toolset distribution (Hermes-style probabilistic tool selection)
    toolset_distribution: ToolsetDistribution = field(
        default_factory=lambda: ToolsetDistribution(name="default")
    )
    enabled_toolsets: List[str] = field(default_factory=list)
    disabled_toolsets: List[str] = field(default_factory=list)

    # Memory & learning
    memory_enabled: bool = True
    session_search_enabled: bool = True
    skill_auto_create: bool = True
    soul_md: str = ""
    context_files: List[str] = field(default_factory=list)

    # Delegation
    can_delegate: bool = False
    max_subagents: int = 3

    # Platform
    platform: str = "cli"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "iteration_budget": self.iteration_budget,
            "toolset_distribution": self.toolset_distribution.to_dict(),
            "enabled_toolsets": self.enabled_toolsets,
            "disabled_toolsets": self.disabled_toolsets,
            "memory_enabled": self.memory_enabled,
            "session_search_enabled": self.session_search_enabled,
            "skill_auto_create": self.skill_auto_create,
            "soul_md": self.soul_md,
            "context_files": self.context_files,
            "can_delegate": self.can_delegate,
            "max_subagents": self.max_subagents,
            "platform": self.platform,
        }


@dataclass
class AgentPermission:
    """Agent access permission."""

    agent_id: str = ""
    resource: str = ""
    access_level: AccessLevel = AccessLevel.READ
    channels: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    description: str = ""  # optional human note (team factories may pass it)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "agent_id": self.agent_id,
            "resource": self.resource,
            "access_level": self.access_level.value,
            "channels": self.channels,
            "allowed_tools": self.allowed_tools,
        }
        if self.description:
            d["description"] = self.description
        return d


@dataclass
class AgentChannelConfig:
    """Channel subscription configuration for an agent."""

    channel: str = ""
    channel_name: str = ""
    endpoint: str = ""
    enabled: bool = True
    sync_interval_seconds: int = 60
    subscribe: bool = True
    publish: bool = False
    priority: int = 0
    # 物竞/审计来源（可选；团队页「物竞」chip）
    source: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.channel and not self.channel_name:
            self.channel_name = self.channel
        elif self.channel_name and not self.channel:
            self.channel = self.channel_name

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "channel": self.channel,
            "channel_name": self.channel_name,
            "endpoint": self.endpoint,
            "enabled": self.enabled,
            "sync_interval_seconds": self.sync_interval_seconds,
            "subscribe": self.subscribe,
            "publish": self.publish,
            "priority": self.priority,
        }
        if self.source:
            d["source"] = self.source
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class AgentProfile:
    """Individual agent profile — the Employee equivalent."""

    agent_id: str = ""
    name: str = ""
    role: str = ""
    description: str = ""
    template_type: AgentTemplateType = AgentTemplateType.CUSTOM
    state: AgentState = AgentState.IDLE
    model_id: str = ""
    system_prompt: str = ""
    personality: AgentPersonality = field(default_factory=AgentPersonality)
    permissions: List[AgentPermission] = field(default_factory=list)
    channels: List[AgentChannelConfig] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Hermes-style agent config (optional — non-None means Hermes mode)
    hermes_config: Optional[HermesAgentConfig] = None
    # ── AgentsGroupConfig ED-1: 组织治理参数 (Clawith 白皮书 L1-L4 / 预算 / 双模型降级) ──
    autonomy_level: int = 2          # L1 只读建议 / L2 低危执行 / L3 高危需审批 / L4 全自主
    token_budget: int = 0            # 日 token 限额，0 = 不限
    fallback_model_id: str = ""      # 主模型失败时的降级模型
    # ── 物竞天择 ND-1.1: 运行时模式 ("legacy"=现有SECS演练 / "eco"=自然选择生境) ──
    runtime: str = "legacy"
    # Optional UI / factory aliases (cloud_ops etc.)
    avatar_emoji: str = ""
    model: Any = None  # ModelConfig or id; normalized to model_id in __post_init__
    visibility: Any = None  # Visibility enum or str; stored in metadata when set

    def __post_init__(self) -> None:
        if not self.agent_id:
            self.agent_id = str(uuid.uuid4())[:8]
        if isinstance(self.state, str):
            self.state = AgentState(self.state)
        if isinstance(self.template_type, str):
            self.template_type = AgentTemplateType(self.template_type)
        if self.runtime not in ("eco", "legacy"):
            self.runtime = "legacy"
        # Accept model=ModelConfig|str from older team factories
        if self.model is not None and not self.model_id:
            m = self.model
            self.model_id = getattr(m, "model_id", None) or getattr(m, "name", None) or str(m)
        meta = dict(self.metadata or {})
        if self.avatar_emoji:
            meta.setdefault("avatar_emoji", self.avatar_emoji)
        if self.visibility is not None:
            v = self.visibility
            meta.setdefault("visibility", getattr(v, "value", v))
        self.metadata = meta

    @property
    def is_hermes_agent(self) -> bool:
        return self.hermes_config is not None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "template_type": self.template_type.value,
            "state": self.state.value,
            "model_id": self.model_id,
            "system_prompt": self.system_prompt,
            "personality": self.personality.to_dict(),
            "permissions": [p.to_dict() for p in self.permissions],
            "channels": [c.to_dict() for c in self.channels],
            "tools": self.tools,
            "skills": self.skills,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "is_hermes_agent": self.is_hermes_agent,
            # ED-1: 治理参数
            "autonomy_level": self.autonomy_level,
            "token_budget": self.token_budget,
            "fallback_model_id": self.fallback_model_id,
            # ND-1.1: 运行时模式
            "runtime": self.runtime,
        }
        if self.hermes_config is not None:
            d["hermes_config"] = self.hermes_config.to_dict()
        return d


@dataclass
class AgentTeam:
    """Agent team — the Company equivalent. Holds shared resources."""

    team_id: str = ""
    name: str = ""
    description: str = ""
    visibility: Visibility = Visibility.PRIVATE
    agents: Dict[str, AgentProfile] = field(default_factory=AgentCollection)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    tools: Dict[str, ToolDefinition] = field(default_factory=dict)
    skills: Dict[str, SkillDefinition] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # ── 物竞天择 ND-1.1: 团队级运行时模式 ("legacy"=现有SECS演练 / "eco"=自然选择生境) ──
    runtime: str = "legacy"
    # ── 团队级任务流水线模式: "single"=单步 / "auto"=智能自适应 / "xops"=云运维运营 / "dev"=研发协作 / "energy"=能效优化 / "star"=星型 / "mesh"=网状 / "custom"=自定义 ──
    workflow_mode: str = "single"

    def __post_init__(self) -> None:
        if not self.team_id:
            self.team_id = str(uuid.uuid4())[:8]
        if not isinstance(self.agents, AgentCollection):
            self.agents = AgentCollection(self.agents)
        if self.runtime not in ("eco", "legacy"):
            self.runtime = "legacy"
        if self.workflow_mode not in ("single", "auto", "full", "xops", "dev", "energy", "star", "mesh", "custom"):
            self.workflow_mode = "single"

    def add_agent(self, agent: AgentProfile) -> None:
        self.agents[agent.agent_id] = agent

    def remove_agent(self, agent_id: str) -> Optional[AgentProfile]:
        return self.agents.pop(agent_id, None)

    def get_agent(self, agent_id: str) -> Optional[AgentProfile]:
        return self.agents.get(agent_id)

    def add_model(self, model: ModelConfig) -> None:
        self.models[model.model_id] = model

    def remove_model(self, model_id: str) -> Optional[ModelConfig]:
        return self.models.pop(model_id, None)

    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        return self.models.get(model_id)

    def add_tool(self, tool: ToolDefinition) -> None:
        self.tools[tool.tool_id] = tool

    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        return self.tools.get(tool_id)

    def add_skill(self, skill: SkillDefinition) -> None:
        self.skills[skill.skill_id] = skill

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        return self.skills.get(skill_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "description": self.description,
            "visibility": self.visibility.value,
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "models": {k: v.to_dict() for k, v in self.models.items()},
            "tools": {k: v.to_dict() for k, v in self.tools.items()},
            "skills": {k: v.to_dict() for k, v in self.skills.items()},
            "metadata": self.metadata,
            "created_at": self.created_at,
            # ND-1.1: 运行时模式
            "runtime": self.runtime,
            "workflow_mode": self.workflow_mode,
        }
