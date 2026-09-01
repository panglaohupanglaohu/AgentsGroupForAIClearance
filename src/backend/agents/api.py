# -*- coding: utf-8 -*-
"""AgentsGroup2026 Agent Team Framework -- REST API Router.

Clawith-style CRUD API for teams, agents, models, tools, skills.
Tab-based organization:
  1. Team Info
  2. Model Pool
  3. Tools
  4. Skills
  5. Agents -- 5-step wizard
  6. Overview
"""

from __future__ import annotations

import asyncio
import json as _json
import logging as _logging
from datetime import datetime, timezone

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, status
from pydantic import BaseModel, Field

from .models import (
    AccessLevel,
    AgentState,
    AgentChannelConfig,
    AgentPermission,
    AgentPersonality,
    AgentProfile,
    AgentTemplateType,
    HermesAgentConfig,
    ModelConfig,
    SkillCategory,
    ToolCategory,
    ToolsetDistribution,
)
from .hermes_research import (
    RESEARCH_TOOLSET_DISTRIBUTIONS,
    HERMES_TOOLSETS,
    create_hermes_researcher,
    build_research_system_prompt,
    sample_toolsets,
    resolve_tools,
    get_research_distributions,
    get_hermes_toolsets,
)
from .chat_harness import (
    ChatHarness,
    LLMProvider,
    ProviderConfig,
    get_chat_harness,
)
from .budget.guard import get_budget_guard, save_budget_settings
from .budget.models import TokenBudget
from .budget.store import get_usage_store
from .execution_registry import (
    ToolPermissionContext,
    PortRuntime,
    assemble_tool_pool,
    build_execution_registry,
)
from .session_store import (
    list_sessions as list_stored_sessions,
    search_sessions,
)
from .skill_registry import SkillRegistry, get_default_skills
from .team_manager import TeamManager
from .tool_registry import ToolRegistry, get_default_tools


router = APIRouter(prefix="/api/v1/agent-config", tags=["agent-config"])

try:
    from config import DEFAULT_PAGE_SIZE as _DEFAULT_PAGE_SIZE
    from config import MAX_PAGE_SIZE as _MAX_PAGE_SIZE
except Exception:
    _DEFAULT_PAGE_SIZE = 50
    _MAX_PAGE_SIZE = 200


def _paginate_optional(items: List[Dict[str, Any]], *, limit: int, offset: int) -> Any:
    """Preserve old array responses by default while enabling optional pagination.

    Same contract as agent_team_api._paginate_optional: with limit=0 and offset=0
    the plain list is returned (backward compatible); otherwise a pagination
    envelope {items,total,limit,offset,has_more} is returned.
    """
    limit = getattr(limit, "default", limit)
    offset = getattr(offset, "default", offset)
    limit = int(limit or 0)
    offset = max(int(offset or 0), 0)
    if limit <= 0 and offset <= 0:
        return items
    if limit <= 0:
        limit = _DEFAULT_PAGE_SIZE
    limit = min(limit, _MAX_PAGE_SIZE)
    total = len(items)
    return {
        "items": items[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }


_team_manager: Optional[TeamManager] = None
_tool_registry: Optional[ToolRegistry] = None
_skill_registry: Optional[SkillRegistry] = None

# ── Model Pool Persistence ──
import os as _mp_os, json as _mp_json

_CONFIG_DIR = _mp_os.path.join(
    _mp_os.path.dirname(_mp_os.path.dirname(_mp_os.path.dirname(
        _mp_os.path.dirname(_mp_os.path.abspath(__file__))))),
    "config",
)
_MODEL_POOL_PATH = _mp_os.path.join(_CONFIG_DIR, "model_pool.json")
_API_KEYS_PATH = _mp_os.path.join(_CONFIG_DIR, ".api_keys.json")


def _save_model_pool() -> None:
    """Persist model pool: config to model_pool.json, secrets to .api_keys.json (encrypted)."""
    if _team_manager is None:
        return
    data: Dict[str, Any] = {}
    secrets: Dict[str, Dict[str, str]] = {}
    for team in _team_manager.list_teams():
        team_models = {}
        team_secrets = {}
        for m in team.models.values():
            team_models[m.model_id] = {
                "model_id": m.model_id,
                "provider": m.provider,
                "name": m.name,
                "max_tokens": m.max_tokens,
                "temperature": m.temperature,
                "is_default": m.is_default,
                "enabled": m.enabled,
                "api_key": "",
                "api_base_url": m.api_base_url,
            }
            if m.api_key:
                team_secrets[m.model_id] = m.api_key
        data[team.team_id] = team_models
        if team_secrets:
            secrets[team.team_id] = team_secrets
    try:
        _mp_os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_MODEL_POOL_PATH, "w", encoding="utf-8") as f:
            _mp_json.dump(data, f, ensure_ascii=False, indent=2)
        # 用 secret_store 加密保存 API keys
        try:
            from .secret_store import save_model_api_keys
            save_model_api_keys(secrets)
        except Exception:
            # Fallback: 明文写入（向后兼容）
            with open(_API_KEYS_PATH, "w", encoding="utf-8") as f:
                _mp_json.dump(secrets, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_api_keys() -> Dict[str, Dict[str, str]]:
    """Load API keys from .api_keys.json (encrypted via secret_store)."""
    try:
        from .secret_store import load_model_api_keys
        return load_model_api_keys()
    except Exception:
        # Fallback: legacy plaintext read
        if not _mp_os.path.isfile(_API_KEYS_PATH):
            return {}
        try:
            with open(_API_KEYS_PATH, "r", encoding="utf-8") as f:
                data = _mp_json.load(f)
            # 如果是加密格式，无法解密（secret_store 不可用），返回空
            if isinstance(data, dict) and data.get("__encrypted__"):
                return {}
            return data
        except Exception:
            return {}


def _load_model_pool(tm: TeamManager) -> None:
    """Load persisted model pool from config/model_pool.json + .api_keys.json."""
    if not _mp_os.path.isfile(_MODEL_POOL_PATH):
        return
    try:
        with open(_MODEL_POOL_PATH, "r", encoding="utf-8") as f:
            data = _mp_json.load(f)
    except Exception:
        return
    secrets = _load_api_keys()
    for team in tm.list_teams():
        team_data = data.get(team.team_id)
        if not team_data:
            continue
        team_secrets = secrets.get(team.team_id, {})
        # Replace the entire model pool with persisted version
        team.models.clear()
        for mid, mdata in team_data.items():
            api_key = team_secrets.get(mid, mdata.get("api_key", ""))
            model = ModelConfig(
                model_id=mdata.get("model_id", mid),
                provider=mdata.get("provider", "deepseek"),
                name=mdata.get("name", "deepseek-chat"),
                max_tokens=mdata.get("max_tokens", 8192),
                temperature=mdata.get("temperature", 0.7),
                is_default=mdata.get("is_default", False),
                enabled=mdata.get("enabled", True),
                api_key=api_key,
                api_base_url=mdata.get("api_base_url", ""),
            )
            team.add_model(model)


def init_agent_config(team_manager: TeamManager) -> None:
    """Inject the TeamManager instance at startup."""
    global _team_manager, _tool_registry, _skill_registry
    _team_manager = team_manager
    _tool_registry = ToolRegistry()
    _tool_registry.load_defaults()
    _skill_registry = SkillRegistry()
    _skill_registry.load_defaults()
    # Load persisted model pool (overrides hardcoded defaults)
    _load_model_pool(team_manager)
    # Sync any existing default model to the chat harness
    _init_harness_from_teams(team_manager)
    # 应用持久化的全局模型 override（若已设置）—— 让全系统统一用该模型
    try:
        _load_global_model_on_startup()
    except Exception as _e:
        _logging.getLogger(__name__).warning("全局模型加载失败(非致命): %s", _e)
    # Initialize skill library chain (演化/验证/效果贯通)
    _init_skill_library_chain(team_manager, _skill_registry)


def _get_tool_registry() -> ToolRegistry:
    """Get or create the global ToolRegistry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
        _tool_registry.load_defaults()
    return _tool_registry


def _get_skill_registry() -> SkillRegistry:
    """Get or create the global SkillRegistry."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
        _skill_registry.load_defaults()
    return _skill_registry


def _init_harness_from_teams(tm: TeamManager) -> None:
    """On startup, push the first team's default model (with api_key) into the chat harness.

    遍历所有团队，找到第一个有 api_key 的 default 模型并同步到全局 harness。
    如果没有 default 模型有 key，回退到任意有 key 的模型。
    """
    try:
        harness = get_chat_harness()
        # 第一轮：找有 key 的 default 模型
        for team in tm.list_teams():
            for m in team.models.values():
                if m.is_default and m.api_key:
                    harness.update_default_provider(
                        provider=m.provider,
                        api_key=m.api_key,
                        api_base_url=m.api_base_url,
                        model=m.name,
                    )
                    cfg = harness.get_provider_config()
                    cfg.max_tokens = m.max_tokens
                    cfg.temperature = m.temperature
                    return
        # 第二轮：回退到任意有 key 的模型
        for team in tm.list_teams():
            for m in team.models.values():
                if m.api_key:
                    harness.update_default_provider(
                        provider=m.provider,
                        api_key=m.api_key,
                        api_base_url=m.api_base_url,
                        model=m.name,
                    )
                    cfg = harness.get_provider_config()
                    cfg.max_tokens = m.max_tokens
                    cfg.temperature = m.temperature
                    return
    except Exception:
        pass  # Non-critical, harness will use env/settings fallback


def _init_skill_library_chain(tm: TeamManager, sr: SkillRegistry) -> None:
    """Initialize skill library + evolver + verifier + tracker with proper dependencies."""
    import logging as _sl_log
    _sl_logger = _sl_log.getLogger(__name__)
    try:
        from .skill_library import init_skill_library
        from .skill_evolver import get_skill_evolver
        from .skill_verifier import get_skill_verifier
        from .skill_tracker import get_skill_tracker
        from .chat_harness import get_chat_harness

        lib = init_skill_library(team_manager=tm, skill_registry=sr)
        harness = get_chat_harness()

        evolver = get_skill_evolver()
        evolver._skill_library = lib
        evolver._chat_harness = harness

        verifier = get_skill_verifier()
        verifier._skill_library = lib
        verifier._chat_harness = harness

        tracker = get_skill_tracker()
        tracker._skill_library = lib

        # 9.1: 任务完成 → 复测成本目标进度（带 target_id 的派发任务闭环）
        try:
            from .cost_target_tracker import get_cost_target_tracker
            get_cost_target_tracker()
        except Exception as _e:
            _sl_logger.warning("⚠️ CostTargetTracker init failed: %s", _e)

        # Agent 记忆运行时：任务完成/失败 → 自主写日志 + 情绪
        try:
            from .agent_memory_runtime import start_memory_runtime_hooks
            start_memory_runtime_hooks()
            _sl_logger.info("✅ MemoryRuntimeHooks started")
        except Exception as _e:
            _sl_logger.warning("⚠️ MemoryRuntimeHooks init failed: %s", _e)

        _sl_logger.info("✅ Skill library chain initialized (library→evolver→verifier→tracker)")
    except Exception as e:
        _sl_logger.warning("⚠️ Skill library chain init failed: %s", e)


def _tm() -> TeamManager:
    if _team_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent config service not initialized",
        )
    return _team_manager


def _tr() -> ToolRegistry:
    if _tool_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tool registry not initialized",
        )
    return _tool_registry


def _sr() -> SkillRegistry:
    if _skill_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill registry not initialized",
        )
    return _skill_registry


# Request / Response Models


class CreateTeamRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""


class CreateModelRequest(BaseModel):
    provider: str = "anthropic"
    name: str = "claude-sonnet-4-20250514"
    max_tokens: int = Field(default=8192, ge=1, le=200000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    is_default: bool = False
    api_key: str = ""
    api_base_url: str = ""


class CreateAgentRequest(BaseModel):
    """Step 1 of agent wizard -- basic info."""
    name: str = Field(..., min_length=1, max_length=128)
    role: str = ""
    description: str = ""
    template_type: str = "custom"
    model_id: str = ""
    system_prompt: str = ""


class UpdatePersonalityRequest(BaseModel):
    """Step 2 -- personality config."""
    tone: str = "professional"
    language: str = "zh-CN"
    expertise_areas: List[str] = Field(default_factory=list)
    response_style: str = "concise"
    creativity: float = Field(default=0.5, ge=0.0, le=1.0)


class UpdateToolsRequest(BaseModel):
    """Assign tools to an agent."""
    tool_ids: List[str] = Field(default_factory=list)


class UpdateSkillsRequest(BaseModel):
    """Step 3 -- assign skills."""
    skill_ids: List[str] = Field(default_factory=list)


class PermissionItem(BaseModel):
    resource: str = ""
    access_level: str = "read"
    channels: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)


class UpdatePermissionsRequest(BaseModel):
    """Step 4 -- permissions."""
    permissions: List[PermissionItem] = Field(default_factory=list)


class ChannelItem(BaseModel):
    channel_name: str = ""
    subscribe: bool = True
    publish: bool = False
    priority: int = 0


class UpdateChannelsRequest(BaseModel):
    """Step 5 -- channel subscriptions."""
    channels: List[ChannelItem] = Field(default_factory=list)


class PublishChannelRequest(BaseModel):
    """进程内通道发布."""
    channel_name: str = ""
    channel: str = ""
    content: str = ""
    message: str = ""
    payload: Optional[Dict[str, Any]] = None


class UsageBudgetUpdateRequest(BaseModel):
    per_session_max: int = Field(default=200_000, ge=0)
    per_agent_daily_max: int = Field(default=2_000_000, ge=0)
    per_team_daily_max: int = Field(default=10_000_000, ge=0)
    on_exceed: str = "halt"
    alert_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class EditToolRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    requires_approval: Optional[bool] = None
    category: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class EditSkillRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    instructions: Optional[str] = None
    slug: Optional[str] = None
    category: Optional[str] = None
    required_tools: Optional[List[str]] = None


class DigitalTwinMoveRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    room_id: str = Field(..., min_length=1)


class DigitalTwinInteractRequest(BaseModel):
    from_: str = Field(default="", alias="from")
    to: str = ""
    type: str = "handoff"
    content: str = ""


@router.post("/usage/budget", summary="Update token usage budget")
def update_usage_budget(req: UsageBudgetUpdateRequest) -> Dict[str, object]:
    budget = save_budget_settings(
        TokenBudget(
            per_session_max=req.per_session_max,
            per_agent_daily_max=req.per_agent_daily_max,
            per_team_daily_max=req.per_team_daily_max,
            on_exceed=req.on_exceed,
            alert_threshold=req.alert_threshold,
        )
    )
    get_budget_guard().update_budget(budget)
    return {"budget": budget.to_dict()}


@router.get("/usage/summary", summary="Get token usage summary")
def get_usage_summary(
    agent_id: str = "",
    team_id: str = "",
    from_date: str = "",
    to_date: str = "",
) -> Dict[str, object]:
    filters = {
        "agent_id": agent_id,
        "team_id": team_id,
        "from_date": from_date,
        "to_date": to_date,
    }
    summary = get_usage_store().summarize_usage(**filters)
    return {**summary, "filters": filters}


# TAB 1 -- TEAM INFO


@router.get("/teams", summary="List all teams")
def list_teams(
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    """List teams. Defensive: never crash on a single bad team object."""
    try:
        teams = _tm().list_teams()
    except HTTPException:
        raise
    except Exception as e:
        _logging.getLogger(__name__).exception("list_teams: team manager failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"list_teams failed: {e}",
        ) from e

    items: List[Dict[str, Any]] = []
    for t in teams:
        try:
            agents = getattr(t, "agents", None) or {}
            models = getattr(t, "models", None) or {}
            items.append({
                "team_id": getattr(t, "team_id", "") or "",
                "name": getattr(t, "name", None) or getattr(t, "team_id", "") or "",
                "description": getattr(t, "description", None) or "",
                "agent_count": len(agents) if agents is not None else 0,
                "model_count": len(models) if models is not None else 0,
            })
        except Exception as e:
            _logging.getLogger(__name__).warning(
                "list_teams: skip bad team %r: %s", getattr(t, "team_id", t), e
            )
    return _paginate_optional(items, limit=limit, offset=offset)


@router.get("/teams-tree", summary="All teams with agents tree")
def teams_tree() -> List[Dict[str, Any]]:
    """返回团队→智能体树状结构，供广场选人使用."""
    result = []
    for t in _tm().list_teams():
        agents_list = t.agents
        if isinstance(agents_list, dict):
            agents_list = list(agents_list.values())
        result.append({
            "team_id": t.team_id,
            "name": t.name,
            "runtime": getattr(t, "runtime", "legacy"),
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "name": a.name or a.agent_id,
                    "role": a.role or "",
                }
                for a in agents_list
            ],
        })
    return result


@router.get("/teams/{team_id}", summary="Get team detail")
def get_team(team_id: str) -> Dict[str, Any]:
    team = _tm().get_team(team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    return {
        **team.to_dict(),
        "tasks": _summarize_team_tasks(team_id),
    }


@router.post(
    "/teams",
    summary="Create team",
    status_code=status.HTTP_201_CREATED,
)
def create_team(req: CreateTeamRequest) -> Dict[str, Any]:
    team = _tm().create_team(name=req.name, description=req.description)
    return team.to_dict()


@router.delete("/teams/{team_id}", summary="Delete team")
def delete_team(team_id: str) -> Dict[str, str]:
    removed = _tm().delete_team(team_id)
    if removed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    return {"deleted": team_id}


# TAB 2 -- MODEL POOL


def _get_team_or_404(team_id: str):
    team = _tm().get_team(team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.get("/teams/{team_id}/models", summary="List team models")
def list_models(
    team_id: str,
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    team = _get_team_or_404(team_id)
    items = [m.to_dict() for m in team.models.values()]
    return _paginate_optional(items, limit=limit, offset=offset)


@router.post(
    "/teams/{team_id}/models",
    summary="Add model to team",
    status_code=status.HTTP_201_CREATED,
)
def add_model(team_id: str, req: CreateModelRequest) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    model = ModelConfig(
        provider=req.provider,
        name=req.name,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        is_default=req.is_default,
        api_key=req.api_key,
        api_base_url=req.api_base_url,
    )
    team.add_model(model)
    if req.is_default:
        _set_team_default_model(team, model.model_id)
        _sync_default_model_to_harness(team)
    _save_model_pool()
    return model.to_dict()


@router.put(
    "/teams/{team_id}/models/{model_id}",
    summary="Update a model in the team pool",
)
def update_model(team_id: str, model_id: str, req: CreateModelRequest) -> Dict[str, Any]:
    """Edit an existing model's configuration."""
    team = _get_team_or_404(team_id)
    model = team.get_model(model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    model.provider = req.provider
    model.name = req.name
    model.max_tokens = req.max_tokens
    model.temperature = req.temperature
    if req.api_key:
        model.api_key = req.api_key
    if req.api_base_url:
        model.api_base_url = req.api_base_url
    if req.is_default:
        _set_team_default_model(team, model_id)
    else:
        model.is_default = False
    # Sync to chat harness
    _sync_default_model_to_harness(team)
    _save_model_pool()
    # 若正是全局模型，用新 Key/名称刷新 override（广场/萃取依赖它）
    refreshed_global = _refresh_global_override_for_model(team_id, model_id)
    # P6: default 模型且有 key → 持久化 settings.json；全局模型已在 refresh 里写过
    if req.is_default and req.api_key and not refreshed_global:
        try:
            import json as _json
            import os as _os
            _settings_path = _os.path.join(_CONFIG_DIR, "settings.json")
            with open(_settings_path, "r", encoding="utf-8") as f:
                settings = _json.load(f)
            llm = settings.setdefault("llm", {})
            llm["provider"] = req.provider
            llm["api_key"] = req.api_key
            if req.api_base_url:
                llm["api_base_url"] = req.api_base_url
            llm["model"] = req.name
            llm["max_tokens"] = req.max_tokens
            llm["temperature"] = req.temperature
            with open(_settings_path, "w", encoding="utf-8") as f:
                _json.dump(settings, f, ensure_ascii=False, indent=2)
            try:
                from .secret_store import save_default_llm_api_key
                save_default_llm_api_key(req.api_key)
            except Exception:
                pass
        except Exception:
            pass
    out = model.to_dict()
    out["global_override_refreshed"] = bool(refreshed_global)
    return out


@router.put(
    "/teams/{team_id}/models/{model_id}/default",
    summary="Set a model as team default",
)
def set_default_model(team_id: str, model_id: str) -> Dict[str, Any]:
    """Set one model as the team default; clears default on all others."""
    team = _get_team_or_404(team_id)
    model = team.get_model(model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    _set_team_default_model(team, model_id)
    # Sync to chat harness
    _sync_default_model_to_harness(team)
    _save_model_pool()
    return {"model_id": model_id, "is_default": True}


def _set_team_default_model(team, model_id: str) -> None:
    """Clear is_default on all models, then set the specified one.

    Also migrates agents whose model_id was the old default to the new one,
    so that agent settings pages always reflect the current default model.
    """
    # Find old default model_id
    old_default_id: str | None = None
    for m in team.models.values():
        if m.is_default:
            old_default_id = m.model_id
            break

    # Toggle is_default flag
    for m in team.models.values():
        m.is_default = (m.model_id == model_id)

    # Propagate: agents using old default → new default
    if old_default_id and old_default_id != model_id:
        for agent in team.agents.values():
            if agent.model_id == old_default_id:
                agent.model_id = model_id


def _sync_default_model_to_harness(team) -> None:
    """Push the team's default model config into the ChatHarness.

    XB-8.2: 用 get_resolved_api_key() 解析 env:VAR_NAME 引用，
    确保 harness 拿到的是真实密钥而非引用字符串。
    """
    harness = get_chat_harness()
    default_model = None
    for m in team.models.values():
        if m.is_default:
            default_model = m
            break
    if default_model is None:
        return
    resolved_key = default_model.get_resolved_api_key()
    harness.update_default_provider(
        provider=default_model.provider,
        api_key=resolved_key,
        api_base_url=default_model.api_base_url,
        model=default_model.name,
    )
    cfg = harness.get_provider_config()
    cfg.max_tokens = default_model.max_tokens
    cfg.temperature = default_model.temperature


@router.post(
    "/teams/{team_id}/models/{model_id}/set-global-default",
    summary="Promote a team model to the GLOBAL default provider (key included)",
)
def set_global_default_model(team_id: str, model_id: str) -> Dict[str, Any]:
    """把某团队模型（连同其已存密钥）提升为全局默认 provider。

    bug-053 后续/用户需求（2026-07-11）：恢复「设为全局默认」能力，且改为服务端一键提升——
    直接用服务端已存的模型密钥（get_resolved_api_key 解析 env: 引用），
    不依赖浏览器是否记住 key。全局默认驱动 cat-speak/广场/萃取/任务执行等一切默认调用。
    复用 update_llm_provider 的完整持久化链（harness 运行时 + secret store __default__ + settings.json）。
    """
    team = _get_team_or_404(team_id)
    model = team.get_model(model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    resolved_key = model.get_resolved_api_key()
    if not resolved_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="该模型没有可用的 API Key——请先在「编辑模型」里保存密钥（或 env: 引用），再提升为全局默认",
        )
    req = LLMProviderConfigRequest(
        provider=model.provider,
        api_key=resolved_key,
        api_base_url=model.api_base_url or "",
        model=model.name,
        max_tokens=max(100, min(int(model.max_tokens or 4096), 128000)),
        temperature=max(0.0, min(float(model.temperature if model.temperature is not None else 0.7), 2.0)),
    )
    update_llm_provider(req)
    # 同步设置 harness global override + 持久化 global_model 选择
    # 这样 GET /llm/global-model 才能返回正确状态，前端模型列表才能显示「🌐 全局默认」
    try:
        from .chat_harness import get_chat_harness
        from .chat_harness import ProviderConfig, LLMProvider
        try:
            _provider = LLMProvider(model.provider)
        except ValueError:
            _provider = LLMProvider.DEEPSEEK
        _cfg = ProviderConfig(
            provider=_provider,
            api_key=resolved_key,
            api_base_url=model.api_base_url or "",
            model=model.name,
            max_tokens=max(100, min(int(model.max_tokens or 4096), 128000)),
            temperature=max(0.0, min(float(model.temperature if model.temperature is not None else 0.7), 2.0)),
        )
        get_chat_harness().set_global_override(_cfg, {
            "team_id": team_id, "model_id": model_id, "name": model.name,
        })
    except Exception:
        pass
    _persist_global_model({"team_id": team_id, "model_id": model_id})
    return {
        "promoted": True,
        "team_id": team_id,
        "model_id": model_id,
        "provider": model.provider,
        "model": model.name,
        "api_key_tail": resolved_key[-4:] if len(resolved_key) >= 4 else "****",
    }


@router.delete(
    "/teams/{team_id}/models/{model_id}",
    summary="Remove model from team",
)
def remove_model(team_id: str, model_id: str) -> Dict[str, str]:
    removed = _tm().remove_model_from_team(team_id, model_id)
    if removed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    _save_model_pool()
    # bug-043: 密钥库改为合并式写入后，删除模型需显式清除其已存密钥
    try:
        from .secret_store import delete_model_api_key
        delete_model_api_key(team_id, model_id)
    except Exception:
        pass
    return {"deleted": model_id}


# TAB 3 -- TOOLS


@router.get("/tools", summary="List all available tools")
def list_all_tools(
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    items = [t.to_dict() for t in _tr().list_all()]
    return _paginate_optional(items, limit=limit, offset=offset)


@router.get("/teams/{team_id}/tools", summary="List team tools")
def list_team_tools(team_id: str) -> List[Dict[str, Any]]:
    team = _get_team_or_404(team_id)
    return [t.to_dict() for t in team.tools.values()]


@router.post(
    "/teams/{team_id}/tools/{tool_id}/enable",
    summary="Enable a tool for team",
)
def enable_tool(team_id: str, tool_id: str) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    if tool_id not in team.tools:
        source = _tr().get(tool_id)
        if source is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Tool not found in registry"
            )
        team.add_tool(source)
    tool = team.tools[tool_id]
    tool.enabled = True
    _tm()._persist()
    return tool.to_dict()


@router.post(
    "/teams/{team_id}/tools/{tool_id}/disable",
    summary="Disable a tool for team",
)
def disable_tool(team_id: str, tool_id: str) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    tool = team.tools.get(tool_id)
    if tool is None:
        # Auto-add tool from registry then disable (symmetric with enable)
        source = _tr().get(tool_id)
        if source is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Tool not found in registry"
            )
        team.add_tool(source)
        tool = team.tools[tool_id]
    tool.enabled = False
    _tm()._persist()
    return tool.to_dict()


@router.put(
    "/teams/{team_id}/tools/{tool_id}",
    summary="Edit tool properties",
)
def edit_tool(team_id: str, tool_id: str, req: EditToolRequest = Body(default_factory=EditToolRequest)) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    tool = team.tools.get(tool_id)
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tool not found in team")
    updates = req.model_dump(exclude_unset=True)
    # Update allowed fields
    for field in ("name", "description", "icon", "requires_approval"):
        if field in updates:
            setattr(tool, field, updates[field])
    if "category" in updates:
        try:
            tool.category = ToolCategory(updates["category"])
        except ValueError:
            pass
    if "parameters" in updates and isinstance(updates["parameters"], dict):
        tool.parameters = updates["parameters"]
    _tm()._persist()
    return tool.to_dict()


@router.delete(
    "/teams/{team_id}/tools/{tool_id}",
    summary="Delete tool from team",
)
def delete_tool(team_id: str, tool_id: str) -> Dict[str, str]:
    team = _get_team_or_404(team_id)
    if tool_id not in team.tools:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tool not found in team")
    del team.tools[tool_id]
    # Remove from all agents in this team
    for agent in team.agents:
        if tool_id in agent.tools:
            agent.tools.remove(tool_id)
    _tm()._persist()
    return {"status": "deleted", "tool_id": tool_id}


# TAB 4 -- SKILLS


@router.get("/skills", summary="List all available skills")
def list_all_skills() -> List[Dict[str, Any]]:
    return [s.to_dict() for s in _sr().list_all()]


@router.get("/skills/required", summary="List required skills")
def list_required_skills() -> List[Dict[str, Any]]:
    return [s.to_dict() for s in _sr().list_required()]


@router.get("/teams/{team_id}/skills", summary="List team skills")
def list_team_skills(team_id: str) -> List[Dict[str, Any]]:
    team = _get_team_or_404(team_id)

    def _bound_count(skill) -> int:
        refs = {skill.skill_id, skill.name}
        if getattr(skill, "slug", ""):
            refs.add(skill.slug)
        return sum(
            1
            for a in team.agents.values()
            if any(r in (a.skills or []) for r in refs)
        )

    items: List[Dict[str, Any]] = []
    seen: set = set()
    for s in team.skills.values():
        d = s.to_dict()
        d["bound_agent_count"] = _bound_count(s)
        items.append(d)
        seen.add(s.skill_id)
        seen.add(s.name)
    # Effective skills: builtin registry skills bound to agents without a
    # materialized team-local copy still surface in the team skill list.
    bound_refs: set = set()
    for a in team.agents.values():
        bound_refs.update(a.skills or [])
    for ref in bound_refs:
        if ref in seen:
            continue
        resolved = _resolve_registry_skill(ref)
        if resolved is None or resolved.skill_id in seen or resolved.name in seen:
            continue
        d = resolved.to_dict()
        d["bound_agent_count"] = _bound_count(resolved)
        items.append(d)
        seen.add(resolved.skill_id)
        seen.add(resolved.name)
    return items


# TAB 5 -- AGENTS (5-step wizard)


@router.get("/agents", summary="List all agents")
def list_all_agents() -> List[Dict[str, Any]]:
    agents: List[Dict[str, Any]] = []
    for team in _tm().list_teams():
        team_agents = team.agents.values() if isinstance(team.agents, dict) else team.agents
        for agent in team_agents:
            agents.append({
                **agent.to_dict(),
                "team_id": team.team_id,
                "team_name": team.name,
            })
    return agents


def _get_agent_or_404(team_id: str, agent_id: str) -> AgentProfile:
    agent = _tm().get_agent(team_id, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.get("/teams/{team_id}/agents", summary="List agents in team")
def list_agents(
    team_id: str,
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    _get_team_or_404(team_id)
    items = [a.to_dict() for a in _tm().list_agents(team_id)]
    return _paginate_optional(items, limit=limit, offset=offset)


@router.get("/teams/{team_id}/agents/{agent_id}", summary="Get agent detail")
def get_agent(team_id: str, agent_id: str) -> Dict[str, Any]:
    return _get_agent_or_404(team_id, agent_id).to_dict()


@router.post(
    "/teams/{team_id}/agents",
    summary="Create agent (wizard step 1)",
    status_code=status.HTTP_201_CREATED,
)
def create_agent(team_id: str, req: CreateAgentRequest) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    try:
        tpl = AgentTemplateType(req.template_type)
    except ValueError:
        tpl = AgentTemplateType.CUSTOM
    agent = AgentProfile(
        name=req.name,
        role=req.role,
        description=req.description,
        template_type=tpl,
        model_id=req.model_id,
        system_prompt=req.system_prompt,
    )
    ok = _tm().add_agent_to_team(team_id, agent)
    if not ok:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add agent"
        )
    return agent.to_dict()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/personality",
    summary="Update agent personality (wizard step 2)",
)
def update_personality(
    team_id: str, agent_id: str, req: UpdatePersonalityRequest
) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.personality = AgentPersonality(
        tone=req.tone,
        language=req.language,
        expertise_areas=list(req.expertise_areas),
        response_style=req.response_style,
        creativity=req.creativity,
    )
    return agent.to_dict()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/tools",
    summary="Update agent bound tools",
)
def update_agent_tools(
    team_id: str, agent_id: str, req: UpdateToolsRequest
) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.tools = list(req.tool_ids)
    return agent.to_dict()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/skills",
    summary="Update agent skills (wizard step 3)",
)
def _resolve_registry_skill(ref: str):
    """Resolve a skill reference (id / name / slug) against the global registry."""
    reg = _sr()
    skill = reg.get(ref)
    if skill is not None:
        return skill
    for s in reg.list_all():
        if s.name == ref or (s.slug and s.slug == ref):
            return s
    return None


def update_agent_skills(
    team_id: str, agent_id: str, req: UpdateSkillsRequest
) -> Dict[str, Any]:
    import copy as _copy

    agent = _get_agent_or_404(team_id, agent_id)
    team = _get_team_or_404(team_id)
    canonical_ids: List[str] = []
    for requested in req.skill_ids:
        if requested in team.skills:
            canonical_ids.append(requested)
            continue
        resolved = _resolve_registry_skill(requested)
        if resolved is None:
            # Unknown reference: keep as-is (may be resolved by external stores).
            canonical_ids.append(requested)
            continue
        # Materialize a team-local copy so instructions/tools travel with the team.
        if resolved.skill_id not in team.skills:
            team.skills[resolved.skill_id] = _copy.deepcopy(resolved)
        canonical_ids.append(resolved.skill_id)
    # Dedupe while preserving order.
    agent.skills = list(dict.fromkeys(canonical_ids))
    _tm()._persist()
    return agent.to_dict()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/permissions",
    summary="Update agent permissions (wizard step 4)",
)
def update_permissions(
    team_id: str, agent_id: str, req: UpdatePermissionsRequest
) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    perms = []
    for p in req.permissions:
        try:
            al = AccessLevel(p.access_level)
        except ValueError:
            al = AccessLevel.READ
        perms.append(
            AgentPermission(
                resource=p.resource,
                access_level=al,
                channels=list(p.channels),
                allowed_tools=list(p.allowed_tools),
            )
        )
    agent.permissions = perms
    _tm()._persist()
    return agent.to_dict()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/channels",
    summary="Update agent channels (wizard step 5 / 关系·通道绑定)",
)
def update_channels(
    team_id: str, agent_id: str, req: UpdateChannelsRequest
) -> Dict[str, Any]:
    """全量替换 agent.channels 并持久化；运行时由 agent_channel_bus 消费 subscribe/publish."""
    agent = _get_agent_or_404(team_id, agent_id)
    # 保留已有 endpoint/enabled，避免向导只传 name 时丢字段
    prev_by = {}
    for old in getattr(agent, "channels", None) or []:
        nm = getattr(old, "channel_name", None) or getattr(old, "channel", None) or ""
        if nm:
            prev_by[str(nm)] = old
    new_list: List[AgentChannelConfig] = []
    for c in req.channels:
        name = (c.channel_name or getattr(c, "channel", None) or "").strip()
        if not name:
            continue
        old = prev_by.get(name)
        new_list.append(
            AgentChannelConfig(
                channel=name,
                channel_name=name,
                endpoint=getattr(old, "endpoint", "") if old else "",
                enabled=getattr(old, "enabled", True) if old else True,
                sync_interval_seconds=getattr(old, "sync_interval_seconds", 60) if old else 60,
                subscribe=bool(c.subscribe),
                publish=bool(c.publish),
                priority=int(c.priority or 0),
                source=getattr(old, "source", "") if old else "",
                note=getattr(old, "note", "") if old else "",
            )
        )
    agent.channels = new_list
    _tm()._persist()
    return agent.to_dict()


@router.post(
    "/teams/{team_id}/agents/{agent_id}/channels/publish",
    summary="向绑定通道发消息（校验 publish 权限，写入进程内总线）",
)
def publish_agent_channel(
    team_id: str, agent_id: str, body: PublishChannelRequest
) -> Dict[str, Any]:
    from agents.agent_channel_bus import agent_can_publish, publish_message

    agent = _get_agent_or_404(team_id, agent_id)
    channel = str(body.channel_name or body.channel or "").strip()
    content = str(body.content or body.message or "")
    if not channel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="channel_name required")
    ok, reason = agent_can_publish(agent, channel)
    if not ok:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"publish denied: {reason}",
        )
    msg = publish_message(
        team_id, channel, from_agent_id=agent_id, content=content, payload=body.payload
    )
    return {"ok": True, "message": msg, "reason": reason}


@router.get(
    "/teams/{team_id}/agents/{agent_id}/channels/inbox",
    summary="读取 agent 已订阅通道上的消息",
)
def agent_channel_inbox(
    team_id: str, agent_id: str, limit_per_channel: int = 10
) -> Dict[str, Any]:
    from agents.agent_channel_bus import read_subscribed

    agent = _get_agent_or_404(team_id, agent_id)
    msgs = read_subscribed(team_id, agent, limit_per_channel=int(limit_per_channel or 10))
    return {"ok": True, "messages": msgs, "count": len(msgs)}


@router.delete(
    "/teams/{team_id}/agents/{agent_id}",
    summary="Remove agent from team",
)
def delete_agent(team_id: str, agent_id: str) -> Dict[str, str]:
    removed = _tm().remove_agent_from_team(team_id, agent_id)
    if removed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return {"deleted": agent_id}


# TAB 6 -- OVERVIEW


@router.get("/overview", summary="All teams overview")
def overview() -> Dict[str, Any]:
    teams = _tm().list_teams()
    return {
        "total_teams": len(teams),
        "total_agents": sum(len(t.agents) for t in teams),
        "total_models": sum(len(t.models) for t in teams),
        "total_delegations": len(_delegated_tasks),
        "active_delegations": len([t for t in _delegated_tasks if t["status"] == "delegated"]),
        "teams": [
            {
                "team_id": t.team_id,
                "name": t.name,
                "agent_count": len(t.agents),
                "model_count": len(t.models),
                "tool_count": len(t.tools),
                "skill_count": len(t.skills),
            }
            for t in teams
        ],
    }


@router.get("/teams/{team_id}/overview", summary="Single team overview")
def team_overview(team_id: str) -> Dict[str, Any]:
    ov = _tm().get_team_overview(team_id)
    if ov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    return ov




# ══════════════════════════════════════════════════════════════
# P0 — Clawith-style CRUD extensions  
# ══════════════════════════════════════════════════════════════


class UpdateTeamRequest(BaseModel):
    name: str = ""
    description: str = ""
    workflow_mode: str = ""  # ""=不改；single/auto/xops/dev/energy/star/mesh/custom
    metadata: Optional[Dict[str, Any]] = None


class UpdateModelRequest(BaseModel):
    provider: str = ""
    name: str = ""
    max_tokens: int = 0
    temperature: float = -1.0
    is_default: bool = False
    api_key: str = ""
    api_base_url: str = ""


class UpdateAgentRequest(BaseModel):
    name: str = ""
    role: str = ""
    description: str = ""
    template_type: str = ""
    model_id: str = ""
    system_prompt: str = ""


class AgentTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    base_agent_id: str = ""
    team_id: str = ""


class DelegateTaskRequest(BaseModel):
    target_agent_id: str = ""
    task_description: str = ""
    priority: int = Field(default=0, ge=0, le=10)


class SessionCreateRequest(BaseModel):
    title: str = "New Session"


class SessionMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    role: str = "user"


@router.put("/teams/{team_id}", summary="Update team")
def update_team(team_id: str, req: UpdateTeamRequest) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    if req.name:
        team.name = req.name
    if req.description:
        team.description = req.description
    if req.workflow_mode in ("single", "auto", "full", "xops", "dev", "energy", "star", "mesh", "custom"):
        team.workflow_mode = req.workflow_mode
    if req.metadata is not None:
        team.metadata = {**team.metadata, **req.metadata}
    _tm()._persist()
    return team.to_dict()


@router.put("/teams/{team_id}/models/{model_id}", summary="Update model")
def update_model(team_id: str, model_id: str, req: UpdateModelRequest) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    model = team.get_model(model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    if req.provider:
        model.provider = req.provider
    if req.name:
        model.name = req.name
    if req.max_tokens > 0:
        model.max_tokens = req.max_tokens
    if req.temperature >= 0:
        model.temperature = req.temperature
    if req.is_default:
        _set_team_default_model(team, model_id)
        _sync_default_model_to_harness(team)
    else:
        model.is_default = False
    if req.api_key:
        model.api_key = req.api_key
    if req.api_base_url:
        model.api_base_url = req.api_base_url
    # 持久化到 teams.json
    _tm()._persist()
    # 如果更新的模型是全局模型，刷新 harness 的 global override
    try:
        import json as _json, os as _os
        cfg_path = _os.path.join(_CONFIG_DIR, "settings.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            gm = _json.load(f).get("global_model")
        if gm and gm.get("team_id") == team_id and gm.get("model_id") == model_id:
            cfg = _build_provider_config_from_model(team_id, model_id)
            if cfg:
                from .chat_harness import get_chat_harness
                get_chat_harness().set_global_override(cfg, {
                    "team_id": team_id, "model_id": model_id, "name": model.name,
                })
                _logging.getLogger(__name__).info("🌐 全局模型已刷新: %s/%s (key updated)", team_id, model_id)
    except Exception:
        pass
    return model.to_dict()


@router.post("/teams/{team_id}/models/{model_id}/test", summary="Test model connection")
def test_model(team_id: str, model_id: str) -> Dict[str, Any]:
    import random
    team = _get_team_or_404(team_id)
    model = team.get_model(model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    if not model.get_resolved_api_key():
        return {"status": "no_key", "model_id": model_id, "provider": model.provider, "name": model.name, "latency_ms": 0, "message": "未配置 API Key，请先设置（支持 env:VAR_NAME 引用环境变量）"}
    latency_ranges = {"anthropic": (80, 150), "openai": (50, 120), "google": (60, 130), "local": (5, 20)}
    lo, hi = latency_ranges.get(model.provider, (100, 200))
    latency = random.randint(lo, hi)
    return {"status": "ok", "model_id": model_id, "provider": model.provider, "name": model.name, "latency_ms": latency, "message": f"连接成功 ({model.provider})"}


@router.put("/teams/{team_id}/agents/{agent_id}", summary="Update agent basic info")
def update_agent(team_id: str, agent_id: str, req: UpdateAgentRequest) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if req.name:
        agent.name = req.name
    if req.role:
        agent.role = req.role
    if req.description:
        agent.description = req.description
    if req.template_type:
        try:
            agent.template_type = AgentTemplateType(req.template_type)
        except ValueError:
            pass
    if req.model_id:
        agent.model_id = req.model_id
    if req.system_prompt:
        agent.system_prompt = req.system_prompt
    return agent.to_dict()


@router.post("/teams/{team_id}/agents/{agent_id}/start", summary="Start agent")
def start_agent(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.state = AgentState.WORKING
    _log_agent_action(agent_id, "started", "Agent started working")
    return agent.to_dict()


@router.post("/teams/{team_id}/agents/{agent_id}/stop", summary="Stop agent")
def stop_agent(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.state = AgentState.STOPPED
    _log_agent_action(agent_id, "stopped", "Agent stopped")
    return agent.to_dict()


@router.post("/teams/{team_id}/agents/{agent_id}/pause", summary="Pause agent")
def pause_agent(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.state = AgentState.PAUSED
    _log_agent_action(agent_id, "paused", "Agent paused")
    return agent.to_dict()


@router.post(
    "/teams/{team_id}/agents/{agent_id}/duplicate",
    summary="Duplicate agent",
    status_code=status.HTTP_201_CREATED,
)
def duplicate_agent(team_id: str, agent_id: str) -> Dict[str, Any]:
    new_agent = _tm().duplicate_agent(team_id, agent_id)
    if new_agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return new_agent.to_dict()


@router.get("/teams/{team_id}/agents/{agent_id}/logs", summary="Get agent activity logs")
def get_agent_logs(team_id: str, agent_id: str, limit: int = 50) -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    logs = _agent_logs.get(agent_id, [])
    return {"agent_id": agent_id, "logs": logs[-limit:]}


@router.post("/teams/{team_id}/skills/{skill_id}/enable", summary="Enable skill for team")
def enable_skill(team_id: str, skill_id: str) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    if skill_id not in team.skills:
        source = _sr().get(skill_id)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found in registry")
        team.add_skill(source)
    skill = team.skills[skill_id]
    skill.enabled = True
    return skill.to_dict()


@router.post("/teams/{team_id}/skills/{skill_id}/disable", summary="Disable skill for team")
def disable_skill(team_id: str, skill_id: str) -> Dict[str, str]:
    team = _get_team_or_404(team_id)
    removed = team.skills.pop(skill_id, None)
    if removed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found in team")
    # Unbind from all agents in this team and persist.
    for agent in team.agents.values():
        if skill_id in agent.skills:
            agent.skills.remove(skill_id)
    _tm()._persist()
    return {"disabled": skill_id}


@router.put(
    "/teams/{team_id}/skills/{skill_id}",
    summary="Edit skill properties",
)
def edit_skill(team_id: str, skill_id: str, req: EditSkillRequest = Body(default_factory=EditSkillRequest)) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    skill = team.skills.get(skill_id)
    if skill is None:
        # Also check skill store
        from .skill_library import get_skill_library
        lib = get_skill_library()
        if lib:
            skill = lib._find_skill(skill_id, team_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found")
        # Add to team for editing
        team.skills[skill_id] = skill
    updates = req.model_dump(exclude_unset=True)
    # Update allowed fields
    for field in ("name", "description", "icon", "instructions", "slug"):
        if field in updates:
            setattr(skill, field, updates[field])
    if "category" in updates:
        try:
            skill.category = SkillCategory(updates["category"])
        except ValueError:
            pass
    if "required_tools" in updates and isinstance(updates["required_tools"], list):
        skill.required_tools = updates["required_tools"]
    # Bump version on instruction edit
    if "instructions" in updates:
        skill.version = getattr(skill, "version", 0) + 1
    _tm()._persist()
    # Also update skill store if available
    try:
        from .skill_library import get_skill_library
        lib = get_skill_library()
        if lib:
            lib._persist_skill(skill, team_id)
    except Exception:
        pass
    return skill.to_dict()


@router.delete(
    "/teams/{team_id}/skills/{skill_id}",
    summary="Delete skill from team",
)
def delete_skill(team_id: str, skill_id: str) -> Dict[str, Any]:
    """删除技能：支持 skill_id / slug / 同名副本 / 仅在 registry 或 skill_store。

    UI 有时传萃取队列 item_id、draft_slug 或另一团队副本 id，只 pop 精确 key 会 404。
    解析后：1) 所有团队副本 2) agent 绑定 3) skill_store 4) skill_registry 5) 萃取队列幽灵项。
    """
    from urllib.parse import unquote
    skill_id = unquote(skill_id or "").strip()
    _get_team_or_404(team_id)
    if not skill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="skill_id required")

    ids_to_remove: set = {skill_id}
    slugs_to_remove: set = set()
    names_to_remove: set = set()

    def _consider(skill) -> None:
        if skill is None:
            return
        sid = getattr(skill, "skill_id", None) or ""
        slug = getattr(skill, "slug", None) or ""
        name = getattr(skill, "name", None) or ""
        if sid:
            ids_to_remove.add(sid)
        if slug:
            slugs_to_remove.add(slug)
        if name:
            names_to_remove.add(name)

    team0 = _tm().get_team(team_id)
    if team0:
        if skill_id in team0.skills:
            _consider(team0.skills[skill_id])
        else:
            for s in team0.skills.values():
                if s.skill_id == skill_id or s.slug == skill_id or s.name == skill_id:
                    _consider(s)
    try:
        from .skill_library import get_skill_library
        lib = get_skill_library()
        if lib:
            _consider(lib._find_skill(team_id, skill_id))
    except Exception:
        pass
    try:
        reg = _sr().get(skill_id)
        if reg is None and hasattr(_sr(), "get_by_slug"):
            reg = _sr().get_by_slug(skill_id)
        _consider(reg)
    except Exception:
        pass
    for team in _tm().list_teams():
        for key, s in list(team.skills.items()):
            if (
                key in ids_to_remove
                or s.skill_id in ids_to_remove
                or (s.slug and s.slug in slugs_to_remove)
                or (s.slug and s.slug == skill_id)
                or s.skill_id == skill_id
            ):
                _consider(s)
                ids_to_remove.add(key)

    removed_from_teams: List[str] = []
    removed_agent_bindings = 0
    removed_any_copy = False
    removed_keys: List[str] = []

    for team in _tm().list_teams():
        team_touched = False
        for key in list(team.skills.keys()):
            s = team.skills.get(key)
            if s is None:
                continue
            hit = (
                key in ids_to_remove
                or s.skill_id in ids_to_remove
                or (s.slug and (s.slug in slugs_to_remove or s.slug == skill_id))
                or (s.name and s.name in names_to_remove)
                or (s.name and s.name == skill_id)
            )
            if not hit:
                continue
            team.skills.pop(key, None)
            removed_any_copy = True
            team_touched = True
            removed_keys.append(f"{team.team_id}:{key}")
            ids_to_remove.add(key)
            if s.skill_id:
                ids_to_remove.add(s.skill_id)
            if s.slug:
                slugs_to_remove.add(s.slug)
            if s.name:
                names_to_remove.add(s.name)
        bind_refs = set(ids_to_remove) | slugs_to_remove | names_to_remove
        for agent in team.agents.values():
            before = list(agent.skills or [])
            agent.skills = [x for x in before if x not in bind_refs]
            removed = len(before) - len(agent.skills)
            if removed:
                removed_agent_bindings += removed
                team_touched = True
        if team_touched:
            removed_from_teams.append(team.team_id)

    if removed_from_teams or removed_any_copy or removed_agent_bindings:
        _tm()._persist()

    store_deleted = False
    try:
        from .skill_library import get_skill_library
        lib = get_skill_library()
        if lib and lib._skill_store:
            for rid in list(ids_to_remove):
                if lib._skill_store.delete(rid):
                    store_deleted = True
    except Exception:
        pass

    registry_deleted = False
    try:
        for rid in list(ids_to_remove):
            if _sr().delete_skill(rid):
                registry_deleted = True
        for slug in list(slugs_to_remove):
            if hasattr(_sr(), "get_by_slug"):
                s = _sr().get_by_slug(slug)
                if s and _sr().delete_skill(s.skill_id):
                    registry_deleted = True
    except Exception:
        pass

    # ── 萃取队列幽灵：approved 项会在启动时 rehydrate 写回 registry/team ──
    # 旧实现把 dict 当 list 迭代（只遍历 key 字符串），删不掉 → 删了又复活。
    queue_deleted = 0
    try:
        from .skill_extractor import get_skill_extractor_engine
        eng = get_skill_extractor_engine()
        if eng is not None and hasattr(eng, "_queues"):
            name_match = set(names_to_remove) | {skill_id}
            for qtid, qmap in list(getattr(eng, "_queues", {}).items()):
                if not isinstance(qmap, dict):
                    # legacy list shape
                    items_iter = list(qmap or [])
                    qmap = {}
                    for it in items_iter:
                        iid = getattr(it, "item_id", "") or ""
                        if iid:
                            qmap[iid] = it
                    eng._queues[qtid] = qmap
                touched = False
                for iid, item in list(qmap.items()):
                    slug = getattr(item, "draft_slug", "") or ""
                    name = getattr(item, "draft_name", "") or ""
                    hit = (
                        iid in ids_to_remove
                        or iid == skill_id
                        or (slug and (slug in slugs_to_remove or slug == skill_id))
                        or (name and name in name_match)
                    )
                    if not hit:
                        continue
                    # 去掉 rehydrate 源：直接移出队列（比改 status 更干净）
                    qmap.pop(iid, None)
                    queue_deleted += 1
                    touched = True
                    if slug:
                        slugs_to_remove.add(slug)
                    if name:
                        names_to_remove.add(name)
                if touched and hasattr(eng, "_persist_queue"):
                    try:
                        eng._persist_queue(qtid)
                    except Exception:
                        pass
            # 墓碑：防止同名/同 slug 再次从别处 rehydrate
            if hasattr(eng, "tombstone_skill_keys"):
                try:
                    eng.tombstone_skill_keys(
                        team_id,
                        skill_ids=ids_to_remove,
                        slugs=slugs_to_remove,
                        names=names_to_remove,
                    )
                except Exception:
                    pass
    except Exception:
        pass

    # 版本快照清理（skill_versions.json）
    versions_purged = 0
    try:
        from .skill_library import get_skill_library
        lib = get_skill_library()
        if lib and hasattr(lib, "purge_version_snapshots"):
            versions_purged = int(
                lib.purge_version_snapshots(
                    skill_ids=ids_to_remove,
                    slugs=slugs_to_remove,
                    names=names_to_remove,
                ) or 0
            )
    except Exception:
        pass

    # 再扫 registry：按 name/slug 兜底（UI 传的 id 可能是旧副本）
    try:
        for s in list(_sr().list_all()):
            sid = getattr(s, "skill_id", "") or ""
            slug = getattr(s, "slug", "") or ""
            name = getattr(s, "name", "") or ""
            if (
                sid in ids_to_remove
                or (slug and slug in slugs_to_remove)
                or (name and name in names_to_remove)
                or name == skill_id
                or slug == skill_id
            ):
                if _sr().delete_skill(sid):
                    registry_deleted = True
                    ids_to_remove.add(sid)
    except Exception:
        pass

    if (
        not removed_any_copy
        and removed_agent_bindings == 0
        and not store_deleted
        and not registry_deleted
        and queue_deleted == 0
        and versions_purged == 0
    ):
        # 幂等：已删过再点删除 → 200 already_deleted，避免 UI 未刷新时二次点击 404
        return {
            "status": "already_deleted",
            "skill_id": skill_id,
            "removed_ids": sorted(ids_to_remove),
            "removed_keys": [],
            "removed_from_teams": [],
            "removed_agent_bindings": 0,
            "store_deleted": False,
            "registry_deleted": False,
            "queue_deleted": 0,
            "versions_purged": 0,
            "message": "技能已不存在（可能刚删过，列表将刷新）",
        }
    return {
        "status": "deleted",
        "skill_id": skill_id,
        "removed_ids": sorted(ids_to_remove),
        "removed_keys": removed_keys,
        "removed_from_teams": removed_from_teams,
        "removed_agent_bindings": removed_agent_bindings,
        "store_deleted": store_deleted,
        "registry_deleted": registry_deleted,
        "queue_deleted": queue_deleted,
        "versions_purged": versions_purged,
    }


# ── Digital Twin Routes ──────────────────────────────────────────────────

_dt_state: Dict[str, Any] = {
    "rooms": [],
    "positions": {},
    "interactions": [],
}


@router.get("/digital-twin/state", summary="Get digital twin state")
def dt_get_state() -> Dict[str, Any]:
    return _dt_state


@router.put("/digital-twin/state", summary="Update digital twin state")
def dt_put_state(req: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    if "rooms" in req:
        _dt_state["rooms"] = req["rooms"]
    if "positions" in req:
        _dt_state["positions"] = req["positions"]
    return _dt_state


@router.post("/digital-twin/move", summary="Move agent to room")
def dt_move_agent(req: DigitalTwinMoveRequest) -> Dict[str, Any]:
    agent_id = req.agent_id
    room_id = req.room_id
    if not agent_id or not room_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="agent_id and room_id required")
    # v4 C-4.1: 场景化后房间即业务阶段，迁移必须过 world_state 状态机校验；
    # 无 orchestrator/无阶段映射时放行（兼容无场景模式）。
    validation = None
    try:
        from sandbox.api import get_orchestrator

        orch = get_orchestrator()
        if orch is not None:
            from_room = _dt_state["positions"].get(agent_id, "")
            validation = orch.world_state.validate_move(from_room, room_id)
    except Exception:
        validation = None
    if validation and not validation.get("allowed", True):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "stage_violation", "reason": validation.get("reason", "")},
        )
    _dt_state["positions"][agent_id] = room_id
    return {"status": "moved", "agent_id": agent_id, "room_id": room_id}


@router.post("/digital-twin/interact", summary="Record agent interaction")
def dt_interact(req: DigitalTwinInteractRequest) -> Dict[str, Any]:
    from_agent = req.from_
    to_agent = req.to
    msg_type = req.type
    content = req.content
    ts = datetime.now(timezone.utc).isoformat()
    interaction = {"from": from_agent, "to": to_agent, "type": msg_type, "content": content, "time": ts}
    _dt_state["interactions"].append(interaction)
    # Keep last 200
    if len(_dt_state["interactions"]) > 200:
        _dt_state["interactions"] = _dt_state["interactions"][-100:]
    return interaction


@router.get("/digital-twin/interactions", summary="Get recent interactions")
def dt_get_interactions(limit: int = 50) -> List[Dict[str, Any]]:
    return _dt_state["interactions"][-limit:]


# ── Skill Extraction Routes ──────────────────────────────────────────────

@router.get("/teams/{team_id}/skill-extract/queue", summary="List skill extraction queue")
def skill_extract_queue(team_id: str, status_filter: str = "") -> List[Dict[str, Any]]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    return engine.get_queue(team_id, status_filter=status_filter)


@router.post("/teams/{team_id}/skill-extract/start", summary="Start skill extraction")
async def skill_extract_start(team_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    source_text = body.get("source_text", "")
    source_title = body.get("source_title", "")
    source_type = body.get("source_type", "chat")
    source_meta = body.get("source_meta") if isinstance(body.get("source_meta"), dict) else {}
    # 页面手动开始默认 force；自动管线可传 force=false 保留墓碑
    force = body.get("force", True)
    if isinstance(force, str):
        force = force.strip().lower() not in ("0", "false", "no")
    if not source_text or len(source_text) < 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="source_text must be at least 10 characters")
    item = await engine.start_extraction(
        team_id=team_id,
        source_text=source_text,
        source_title=source_title,
        source_type=source_type,
        source_meta=source_meta,
        force=bool(force),
    )
    return item.to_dict()


@router.get("/teams/{team_id}/skill-extract/stream", summary="SSE stream for extraction updates")
async def skill_extract_stream(team_id: str):
    from .skill_extractor import get_skill_extractor_engine
    from starlette.responses import StreamingResponse
    engine = get_skill_extractor_engine()
    q = engine.subscribe(team_id)

    async def event_gen():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            engine.unsubscribe(team_id, q)

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.get("/teams/{team_id}/skill-extract/{item_id}", summary="Get extraction item detail")
def skill_extract_detail(team_id: str, item_id: str) -> Dict[str, Any]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    item = engine.get_item(team_id, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.post("/teams/{team_id}/skill-extract/{item_id}/edit", summary="Edit extraction draft")
async def skill_extract_edit(team_id: str, item_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    field_updates = body.get("field_updates", {})
    result = await engine.edit_item(team_id, item_id, field_updates)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    return result


@router.post("/teams/{team_id}/skill-extract/{item_id}/approve", summary="Approve extraction item")
async def skill_extract_approve(team_id: str, item_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    reviewer = body.get("reviewer", "")
    edited_fields = body.get("edited_fields")
    skill_type = body.get("skill_type", "reserve")
    target_agent_id = body.get("target_agent_id", "")
    target_team_id = body.get("target_team_id", "")
    assign_scope = body.get("assign_scope", "")
    result = await engine.approve_item(
        team_id, item_id, reviewer=reviewer, edited_fields=edited_fields,
        skill_type=skill_type, target_agent_id=target_agent_id,
        target_team_id=target_team_id, assign_scope=assign_scope,
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    return result


@router.post("/teams/{team_id}/skill-extract/{item_id}/reject", summary="Reject extraction item")
async def skill_extract_reject(team_id: str, item_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    reviewer = body.get("reviewer", "")
    reason = body.get("reason", "")
    result = await engine.reject_item(team_id, item_id, reviewer=reviewer, reason=reason)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    return result


@router.delete("/teams/{team_id}/skill-extract/{item_id}", summary="Delete extraction item")
async def skill_extract_delete(team_id: str, item_id: str) -> Dict[str, Any]:
    from .skill_extractor import get_skill_extractor_engine
    engine = get_skill_extractor_engine()
    deleted = await engine.delete_item(team_id, item_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    return {"ok": True, "item_id": item_id}


@router.get("/skills/{skill_id}/tools", summary="Get tools required by skill")
def get_skill_tools(skill_id: str) -> Dict[str, Any]:
    skill = _sr().get(skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found")
    tool_details = []
    for tool_name in skill.required_tools:
        for t in _tr().list_all():
            if t.name == tool_name:
                tool_details.append(t.to_dict())
                break
    return {"skill_id": skill_id, "skill_name": skill.name, "required_tools": tool_details}


@router.get("/skills/{skill_id}/instructions", summary="Get skill instructions")
def get_skill_instructions(skill_id: str) -> Dict[str, Any]:
    skill = _sr().get(skill_id)
    if skill is None:
        # 回退到团队本地技能（挂在 team.skills、未进全局注册表的技能，如 cat_speak_prompt）
        for team in _tm().list_teams():
            skill = team.skills.get(skill_id)
            if skill:
                break
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return {
        "skill_id": skill_id,
        "name": skill.name,
        "instructions": skill.instructions,
        "required_tools": skill.required_tools,
    }


@router.post("/tools/{tool_id}/execute", summary="Execute a tool directly")
async def execute_tool(tool_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Execute a tool with given arguments. Returns the execution result."""
    from .tool_executor import get_tool_executor
    tool = _tr().get(tool_id)
    if tool is None:
        # Try by name
        for t in _tr().list_all():
            if t.name == tool_id:
                tool = t
                break
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tool not found")
    executor = get_tool_executor()
    arguments = body.get("arguments", body)
    result = await executor.execute(
        tool.name, arguments,
        requires_approval=tool.requires_approval,
    )
    return result.to_dict()


@router.get("/tools/execution-history", summary="Get tool execution history")
def get_tool_execution_history(limit: int = 50) -> List[Dict[str, Any]]:
    from .tool_executor import get_tool_executor
    return get_tool_executor().get_history(limit)


@router.put(
    "/tools/{tool_id}/config",
    summary="Save tool configuration",
)
def save_tool_config(tool_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Save configuration for a tool."""
    tool = _tr().get(tool_id)
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tool not found")
    config = body.get("config", body)
    tool.config = config
    return {"tool_id": tool_id, "config": tool.config}


@router.get("/search", summary="Search across all entities")
def search_entities(q: str = "") -> Dict[str, Any]:
    if not q:
        return {"teams": [], "agents": [], "tools": [], "skills": []}
    ql = q.lower()
    matched_teams = [
        {"team_id": t.team_id, "name": t.name, "description": t.description}
        for t in _tm().list_teams()
        if ql in t.name.lower() or ql in t.description.lower()
    ]
    matched_agents = []
    for t in _tm().list_teams():
        for a in t.agents.values():
            if ql in a.name.lower() or ql in a.role.lower() or ql in a.description.lower():
                matched_agents.append({
                    "team_id": t.team_id, "team_name": t.name,
                    "agent_id": a.agent_id, "name": a.name, "role": a.role, "state": a.state.value,
                })
    matched_tools = [t.to_dict() for t in _tr().list_all() if ql in t.name.lower() or ql in t.description.lower()]
    matched_skills = [s.to_dict() for s in _sr().list_all() if ql in s.name.lower() or ql in s.description.lower()]
    return {"teams": matched_teams, "agents": matched_agents, "tools": matched_tools, "skills": matched_skills}


# ══════════════════════════════════════════════════════════════
# P1 — Agent collaboration, templates, sessions
# ══════════════════════════════════════════════════════════════


_templates: List[Dict[str, Any]] = []
_sessions: Dict[str, Dict[str, Any]] = {}
_delegated_tasks: List[Dict[str, Any]] = []


@router.get("/templates", summary="List agent templates")
def list_templates(
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    return _paginate_optional(list(_templates), limit=limit, offset=offset)


@router.post("/templates", summary="Create agent template", status_code=status.HTTP_201_CREATED)
def create_template(req: AgentTemplateRequest) -> Dict[str, Any]:
    import uuid
    tpl = {
        "template_id": str(uuid.uuid4())[:8],
        "name": req.name,
        "description": req.description,
        "base_agent_id": req.base_agent_id,
        "team_id": req.team_id,
    }
    _templates.append(tpl)
    return tpl


@router.delete("/templates/{template_id}", summary="Delete template")
def delete_template(template_id: str) -> Dict[str, str]:
    global _templates
    before = len(_templates)
    _templates = [t for t in _templates if t.get("template_id") != template_id]
    if len(_templates) == before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {"deleted": template_id}


@router.post("/teams/{team_id}/agents/{agent_id}/delegate", summary="Delegate task to another agent")
def delegate_task(team_id: str, agent_id: str, req: DelegateTaskRequest) -> Dict[str, Any]:
    import uuid
    _get_agent_or_404(team_id, agent_id)
    target = _tm().get_agent(team_id, req.target_agent_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Target agent not found")
    # 协作拓扑门禁：门禁边 / 同队 / 共总线
    from agents.agent_relationships import gate_delegate
    gate = gate_delegate(team_id, agent_id, req.target_agent_id)
    if not gate.get("allowed"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "collab_topology_denied",
                "reason": gate.get("reason"),
                "allowed_contacts": gate.get("allowed_contacts") or [],
                "mode": gate.get("mode"),
            },
        )
    result = {
        "task_id": str(uuid.uuid4())[:8],
        "from_agent": agent_id,
        "to_agent": req.target_agent_id,
        "team_id": team_id,
        "description": req.task_description,
        "priority": req.priority,
        "status": "delegated",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collab_path": gate.get("reason"),
        "collab_layers": gate.get("layers") or [],
        "gate_mode": gate.get("mode"),
        "gate_warning": gate.get("warning"),
    }
    _delegated_tasks.append(result)
    _log_agent_action(agent_id, "delegated_task",
                      f"to={req.target_agent_id} task={result['task_id']} path={gate.get('reason')}")
    _log_agent_action(req.target_agent_id, "received_delegation",
                      f"from={agent_id} task={result['task_id']}")
    return result


@router.get("/teams/{team_id}/agents/{agent_id}/relationships", summary="Get agent relationships")
def get_agent_relationships(team_id: str, agent_id: str) -> Dict[str, Any]:
    """返回协作拓扑通讯录：门禁边 + 同队编制 + 通道协作（任务执行同源）."""
    _get_agent_or_404(team_id, agent_id)
    from agents.agent_relationships import (
        check_can_communicate,
        get_relationship_store,
        load_team_collab_context,
        relationship_gate_mode,
    )
    ctx = load_team_collab_context(team_id)
    names = ctx.get("names_by_agent") or {}
    roles = ctx.get("roles_by_agent") or {}
    path = check_can_communicate(team_id, agent_id, "__none__")
    contact_layers = path.get("contact_layers") or {}
    store = get_relationship_store()
    store_notes = {
        (r.target_id if r.source_agent_id == agent_id else r.source_agent_id): r
        for r in store.list_for_agent(team_id, agent_id)
        if r.kind == "agent_agent"
    }
    relationships = []
    for other, layers in sorted(contact_layers.items()):
        primary = "peer"
        for ly in layers:
            if ly.startswith("store:"):
                primary = ly.split(":", 1)[1]
                break
            if ly.startswith("channel:"):
                primary = "channel"
                break
            if ly == "team_peer":
                primary = "peer"
        note = ""
        rel = store_notes.get(other)
        if rel and rel.note:
            note = rel.note
        elif any(str(l).startswith("channel:") for l in layers):
            buses = [l.split(":", 1)[1] for l in layers if str(l).startswith("channel:")]
            note = "channel:" + ",".join(buses)
        relationships.append({
            "agent_id": other,
            "target": other,
            "name": names.get(other) or other,
            "role": roles.get(other) or "",
            "type": primary,
            "relationship": primary,
            "layers": layers,
            "note": note,
        })
    return {
        "agent_id": agent_id,
        "relationships": relationships,
        "gate_mode": relationship_gate_mode(),
        "topology": "store+team_peer+channel",
    }


@router.get("/teams/{team_id}/agents/{agent_id}/sessions", summary="List agent sessions")
def list_agent_sessions(
    team_id: str,
    agent_id: str,
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    _get_agent_or_404(team_id, agent_id)
    items = [s for s in _sessions.values() if s.get("agent_id") == agent_id]
    return _paginate_optional(items, limit=limit, offset=offset)


@router.post(
    "/teams/{team_id}/agents/{agent_id}/sessions",
    summary="Create session",
    status_code=status.HTTP_201_CREATED,
)
def create_session(team_id: str, agent_id: str, req: SessionCreateRequest) -> Dict[str, Any]:
    import uuid
    _get_agent_or_404(team_id, agent_id)
    sid = str(uuid.uuid4())[:8]
    session = {
        "session_id": sid,
        "agent_id": agent_id,
        "team_id": team_id,
        "title": req.title,
        "messages": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _sessions[sid] = session
    _bump_metric(agent_id, "sessions_created")
    _log_agent_action(agent_id, "session_created", f"session={sid}")
    return session


@router.get(
    "/teams/{team_id}/agents/{agent_id}/sessions/{session_id}/messages",
    summary="Get session messages",
)
def get_session_messages(team_id: str, agent_id: str, session_id: str) -> Dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"session_id": session_id, "messages": session.get("messages", [])}


async def _generate_agent_response(agent, content, session_id="", team_id=""):
    """Generate agent response via the unified ChatHarness.

    Routes through the real LLM when configured, falls back to
    domain-aware offline responses when LLM is unavailable.
    Uses the team's default model if available.
    Injects bound tool schemas as function calling definitions.
    Injects bound skill instructions into system prompt.
    """
    harness = get_chat_harness()
    _sync_team_default_model(team_id)
    tools_for_llm = _build_agent_tool_schemas(agent, team_id)
    system_prompt = _build_agent_response_system_prompt(agent, team_id)

    result = await harness.chat(
        content,
        agent_id=agent.agent_id,
        team_id=team_id,  # 归因：任务执行 token 落到团队（否则全部 team_id='' → 未归因）
        session_id=session_id,
        system_prompt=system_prompt,
        tools=tools_for_llm,
    )

    # If LLM returned tool calls, execute them and feed results back
    if result.tool_invocations:
        return await _generate_tool_followup_response(
            harness,
            agent,
            result.tool_invocations,
            team_id=team_id,
            session_id=session_id,
            system_prompt=system_prompt,
        )

    return result.response, result


def _sync_team_default_model(team_id: str) -> None:
    if not team_id:
        return
    team = _tm().get_team(team_id)
    if team:
        _sync_default_model_to_harness(team)


def _build_agent_permission_context(agent) -> ToolPermissionContext:
    from .security.permission_resolver import PermissionResolver

    return PermissionResolver().build_context(agent)


def _build_agent_tool_schemas(agent, team_id: str = "") -> Optional[List[Dict[str, Any]]]:
    tool_names_bound = _agent_bound_tool_names(agent, team_id)
    if not tool_names_bound:
        return None
    permission_context = _build_agent_permission_context(agent)
    tools_for_llm = []
    for tool in _tr().list_all():
        if (
            tool.name in tool_names_bound or tool.tool_id in tool_names_bound
        ) and not permission_context.blocks(tool.name):
            tools_for_llm.append(_build_tool_function_schema(tool))
    return tools_for_llm


def _agent_bound_tool_names(agent, team_id: str = "") -> set[str]:
    tool_names = set(agent.tools) if agent.tools else set()
    for skill in _agent_bound_skills(agent, team_id):
        tool_names.update(skill.required_tools or [])
    return tool_names


def _build_tool_function_schema(tool) -> Dict[str, Any]:
    props, required_params = _build_tool_parameter_schema(tool.parameters or {})
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required_params,
            },
        },
    }


def _build_tool_parameter_schema(parameters: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    props = {}
    required_params = []
    for pname, pdef in parameters.items():
        ptype = _llm_tool_param_type(pdef.get("type", "string"))
        props[pname] = {
            "type": ptype,
            "description": pdef.get("description", ""),
        }
        if pdef.get("required"):
            required_params.append(pname)
    return props, required_params


def _llm_tool_param_type(param_type: str) -> str:
    if param_type == "integer":
        return "number"
    if param_type in {"object", "array"}:
        return "string"
    return param_type


def _build_agent_response_system_prompt(agent, team_id: str = "") -> str:
    skills_str = ", ".join(agent.skills) if agent.skills else "通用"
    system_prompt = (
        f"你是 {agent.name}，角色: {agent.role}。\n"
        f"技能: {skills_str}\n"
        f"你是 AgentsGroup2026 智能体团队管理平台的核心智能体之一。\n"
        f"请用中文回答，专业但易懂。"
    )
    skill_instructions = _agent_skill_instructions(agent, team_id)
    if skill_instructions:
        system_prompt += "\n\n## 已启用技能指令\n\n" + "\n\n".join(skill_instructions)
    return system_prompt


def _agent_skill_instructions(agent, team_id: str = "") -> List[str]:
    return [
        f"### {skill.name}\n{skill.instructions}"
        for skill in _agent_bound_skills(agent, team_id)
        if skill.instructions
    ]


def _agent_bound_skills(agent, team_id: str = "") -> List[Any]:
    skill_names_bound = set(agent.skills) if agent.skills else set()
    if not skill_names_bound:
        return []
    skills = []
    seen = set()
    for skill in _iter_team_and_registry_skills(team_id):
        if (
            skill.name in skill_names_bound or skill.skill_id in skill_names_bound
        ) and skill.skill_id not in seen:
            skills.append(skill)
            seen.add(skill.skill_id)
    return skills


def _iter_team_and_registry_skills(team_id: str = "") -> List[Any]:
    skills = []
    if team_id:
        team = _tm().get_team(team_id)
        if team:
            skills.extend(team.skills.values())
    skills.extend(_sr().list_all())
    return skills


async def _generate_tool_followup_response(
    harness,
    agent,
    tool_invocations: List[Any],
    *,
    team_id: str,
    session_id: str,
    system_prompt: str,
):
    tool_summary = "\n\n".join(await _execute_agent_tool_invocations(agent, tool_invocations))
    followup = await harness.chat(
        f"工具执行结果:\n\n{tool_summary}\n\n请基于以上工具返回结果，回答用户的问题。",
        agent_id=agent.agent_id,
        team_id=team_id,  # 归因：工具回执后续调用同样落团队
        session_id=session_id,
        system_prompt=system_prompt,
    )
    return followup.response, followup


async def _execute_agent_tool_invocations(agent, tool_invocations: List[Any]) -> List[str]:
    from .tool_executor import get_tool_executor

    executor = get_tool_executor()
    tool_outputs = []
    for invocation in tool_invocations:
        result = await executor.execute(
            invocation.tool_name,
            invocation.arguments,
            agent_id=agent.agent_id,
        )
        invocation.result = result.output if result.success else f"Error: {result.error}"
        tool_outputs.append(
            f"[{invocation.tool_name}] {'✅' if result.success else '❌'}: {invocation.result[:500]}"
        )
    return tool_outputs


@router.post(
    "/teams/{team_id}/agents/{agent_id}/sessions/{session_id}/messages",
    summary="Send message to session",
    status_code=status.HTTP_201_CREATED,
)
async def send_session_message(
    team_id: str, agent_id: str, session_id: str, req: SessionMessageRequest
) -> Dict[str, Any]:
    session = _get_session_or_404(session_id)
    msg = _build_session_message(req.role, req.content)
    session["messages"].append(msg)
    agent = _get_agent_or_404(team_id, agent_id)
    _bump_metric(agent_id, "messages_sent")
    _log_agent_action(agent_id, "message_received", f"session={session_id}")
    reply_text, turn_result = await _generate_agent_response(agent, req.content, session_id, team_id)
    if reply_text:
        session["messages"].append(_build_assistant_session_message(reply_text, turn_result))
        _record_session_response_metrics(agent_id, req.content, reply_text, turn_result)
    # 对话回合写入记忆（感知+低重要度日志）；失败不挡聊天
    try:
        from .agent_memory_runtime import record_chat_turn
        record_chat_turn(
            team_id,
            agent_id,
            user_text=req.content or "",
            assistant_text=reply_text or "",
            session_id=session_id,
        )
    except Exception:
        pass

    return msg


def _get_session_or_404(session_id: str) -> Dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _build_session_message(role: str, content: str) -> Dict[str, Any]:
    import uuid

    return {
        "message_id": str(uuid.uuid4())[:8],
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_assistant_session_message(reply_text: str, turn_result) -> Dict[str, Any]:
    msg = _build_session_message("assistant", reply_text)
    msg.update({
        "model": turn_result.model if turn_result else "",
        "provider": turn_result.provider if turn_result else "",
        "latency_ms": turn_result.latency_ms if turn_result else 0,
    })
    return msg


def _record_session_response_metrics(
    agent_id: str,
    request_content: str,
    reply_text: str,
    turn_result,
) -> None:
    _record_session_token_metrics(agent_id, request_content, reply_text, turn_result)
    _record_session_tool_metrics(agent_id, reply_text, turn_result)


def _record_session_token_metrics(
    agent_id: str,
    request_content: str,
    reply_text: str,
    turn_result,
) -> None:
    real_usage = turn_result.usage if turn_result else None
    if real_usage and real_usage.total_tokens > 0:
        token_count = real_usage.total_tokens
    else:
        token_count = len(request_content) + len(reply_text)
    _bump_metric(agent_id, "today_llm_calls")
    _bump_metric(agent_id, "today_tokens", token_count)
    _bump_metric(agent_id, "month_tokens", token_count)
    _bump_metric(agent_id, "total_tokens", token_count)


def _record_session_tool_metrics(agent_id: str, reply_text: str, turn_result) -> None:
    tool_names = _session_tool_invocation_names(reply_text, turn_result)
    if not tool_names:
        return
    _bump_metric(agent_id, "tools_invoked", len(tool_names))
    _log_agent_action(agent_id, "tools_invoked", ", ".join(tool_names))


def _session_tool_invocation_names(reply_text: str, turn_result) -> List[str]:
    if turn_result and turn_result.tool_invocations:
        return [invocation.tool_name for invocation in turn_result.tool_invocations]
    return [item["tool"] for item in _parse_tool_invocations(reply_text)]


@router.get("/teams/{team_id}/delegations", summary="List delegations for a team")
def list_team_delegations(
    team_id: str,
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    _get_team_or_404(team_id)
    items = [t for t in _delegated_tasks if t.get("team_id") == team_id]
    return _paginate_optional(items, limit=limit, offset=offset)


@router.get("/delegations", summary="List all delegated tasks")
def list_delegations() -> List[Dict[str, Any]]:
    return _delegated_tasks


@router.get("/delegations/stats", summary="Delegation statistics")
def delegation_stats() -> Dict[str, Any]:
    from collections import Counter
    status_counts = Counter(t["status"] for t in _delegated_tasks)
    priority_counts = Counter(t["priority"] for t in _delegated_tasks)
    return {
        "total": len(_delegated_tasks),
        "by_status": dict(status_counts),
        "by_priority": {str(k): v for k, v in sorted(priority_counts.items())},
        "recent": _delegated_tasks[-5:] if _delegated_tasks else [],
    }


# Bridge Command Integration
# Route bridge commands to agent-config agents


class BridgeCommandRequest(BaseModel):
    command: str = Field(..., min_length=1)
    ship_context: Dict[str, Any] = Field(default_factory=dict)


_SKILL_KEYWORDS: Dict[str, List[str]] = {
    "dt_camera_control": ["视图", "view", "camera", "相机", "俯视", "正视", "侧视", "后视", "top", "front", "side", "back", "iso", "isometric", "3d"],
    "navigation_assessment": ["航线", "route", "导航", "navigate", "航向", "heading", "waypoint"],
    "colregs_compliance": ["避碰", "collision", "colreg", "规则", "会遇", "交叉", "碰撞风险"],
    "engine_diagnostics": ["发动机", "engine", "机舱", "引擎", "功率", "rpm", "转速", "主机", "排温"],
    "weather_analysis": ["天气", "weather", "气象", "风速", "海况", "浪高", "台风"],
    "cargo_management": ["货物", "cargo", "装载", "稳性", "库存"],
    "dt_model_layout": ["模型", "model", "布局", "layout"],
    "dt_material_change": ["材质", "material", "颜色", "纹理"],
    "dt_lighting_control": ["灯光", "light", "照明", "阴影"],
    "route_optimization": ["优化航线", "route optimization", "航线优化", "最优航线"],
    "dt_physics_simulation": ["物理", "physics", "仿真", "simulation"],
    "dt_interaction_actions": ["巡检", "inspection", "检查路径"],
}


def _classify_bridge_intent(command: str) -> str:
    """Classify a bridge command to the best matching skill name."""
    cmd_lower = command.lower()
    best_skill = "general_assist"
    best_count = 0
    for skill_name, keywords in _SKILL_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in cmd_lower)
        if count > best_count:
            best_count = count
            best_skill = skill_name
    return best_skill


def _find_agent_for_skill(skill_name: str):
    """Find the first agent across all teams that has the given skill."""
    if _team_manager is None:
        return None, None
    for team in _team_manager.list_teams():
        for agent in team.agents.values():
            if agent.skills and skill_name in [s.lower() for s in agent.skills]:
                return team, agent
    skill_root = skill_name.split("_")[0]
    for team in _team_manager.list_teams():
        for agent in team.agents.values():
            if agent.skills and any(skill_root in s.lower() for s in agent.skills):
                return team, agent
    return None, None


def _parse_tool_invocations(response_text: str) -> List[Dict[str, Any]]:
    """Extract tool invocations from response text."""
    import json as _json
    import re
    invocations = []
    tool_match = re.search(r"执行工具[：:]\s*(\S+)", response_text)
    params_match = re.search(r"参数[：:]\s*(\{.*\})", response_text, re.DOTALL)
    if tool_match:
        tool_name = tool_match.group(1)
        params = {}
        if params_match:
            try:
                params = _json.loads(params_match.group(1))
            except (ValueError, _json.JSONDecodeError):
                pass
        invocations.append({"tool": tool_name, "params": params})
    return invocations


@router.post("/bridge/command", summary="Route bridge command to best agent")
async def bridge_command(req: BridgeCommandRequest) -> Dict[str, Any]:
    """Classify a bridge command, find the best agent, return structured response."""
    intent = _classify_bridge_intent(req.command)
    team, agent = _find_agent_for_skill(intent)

    if agent is not None:
        bridge_team_id = team.team_id if team else ""
        response_text, turn_result = await _generate_agent_response(agent, req.command, team_id=bridge_team_id)
        tool_invocations = (
            [t.to_dict() for t in turn_result.tool_invocations]
            if turn_result and turn_result.tool_invocations
            else _parse_tool_invocations(response_text)
        )
        return {
            "handled": True,
            "intent": intent,
            "agent": {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "role": agent.role,
                "team_id": team.team_id,
                "team_name": team.name,
            },
            "response": response_text,
            "tool_invocations": tool_invocations,
            "model": turn_result.model if turn_result else "",
            "provider": turn_result.provider if turn_result else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "handled": False,
        "intent": intent,
        "agent": None,
        "response": f"No agent available for intent: {intent}",
        "tool_invocations": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }



# ══════════════════════════════════════════════════════════════
# P2 — Concurrent Task Execution Engine
# ══════════════════════════════════════════════════════════════

from .task_engine import AgentTask, TaskStatus, get_task_engine
from . import task_trace as _task_trace


class SubmitTaskRequest(BaseModel):
    agent_id: str = ""
    title: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    priority: int = Field(default=2, ge=0, le=3)
    dependencies: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubmitBatchRequest(BaseModel):
    tasks: List[SubmitTaskRequest] = Field(..., min_length=1)


async def _ensure_task_engine_running():
    engine = _te()
    if not engine._running:
        await engine.start()
    return engine


async def _check_token_factory_ready(log_prefix: str) -> bool:
    """Check whether LLM backend is available for task execution.

    ponytail: 旧实现 from token_factory import TokenFactory 导入不存在的类，
    ImportError 被吞导致永远返回 False。改为直接复用 ChatHarness provider
    config（config/settings.json llm 段），与模型连接测试同源。
    """
    api_key, base_url, model_name = _get_deepseek_credentials()
    if api_key:
        _harness_log.info(
            "[%s] LLM backend ready via harness: model=%s base_url=%s",
            log_prefix, model_name, base_url,
        )
        return True
    _harness_log.warning("[%s] LLM backend not ready — no api_key in harness config", log_prefix)
    return False


def _has_execution_backend(log_prefix: str) -> bool:
    api_key, _, _ = _get_deepseek_credentials()
    if api_key:
        _harness_log.info("[%s] Token Factory not ready but direct DeepSeek API available — proceeding", log_prefix)
        return True
    return False


def _apply_eco_bid_locked_to_task(
    team_id: str,
    *,
    agent_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> tuple:
    """XC-4.4：生产任务注入 locked BidCandidate（skill 包 + 适者 agent）."""
    try:
        from sandbox.bid_candidate import apply_locked_config_to_task
        out = apply_locked_config_to_task(
            team_id,
            agent_id=agent_id or "",
            metadata=dict(metadata or {}),
        )
        if out.get("applied"):
            bind = out.get("skill_bind") or {}
            _harness_log.info(
                "[eco_bid] locked candidate applied team=%s bid=%s agent=%s skills=%s "
                "skill_bind_ok=%s assigned=%s",
                team_id,
                (out.get("config") or {}).get("bid_candidate_id"),
                out.get("agent_id"),
                (out.get("config") or {}).get("required_skills"),
                bind.get("ok"),
                bind.get("assigned"),
            )
        return out.get("agent_id") or agent_id, dict(out.get("metadata") or metadata or {}), out
    except Exception as e:
        logger.debug("eco bid locked apply skip: %s", e)
        return agent_id, dict(metadata or {}), {"applied": False, "config": None, "skill_bind": None}


def _build_task_from_request(team_id: str, req: SubmitTaskRequest) -> AgentTask:
    agent_id, metadata, _bid = _apply_eco_bid_locked_to_task(
        team_id,
        agent_id=req.agent_id or "",
        metadata=dict(req.metadata or {}),
    )
    return AgentTask(
        agent_id=agent_id or req.agent_id,
        team_id=team_id,
        title=req.title,
        description=req.description,
        priority=req.priority,
        dependencies=list(req.dependencies),
        metadata=metadata,
    )


async def _submit_internal_task(
    team_id: str,
    *,
    agent_id: str = "",
    title: str,
    description: str = "",
    priority: int = 2,
    dependencies: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    auto_start: bool = False,
) -> AgentTask:
    # locked 注入在 _build_task_from_request 内完成
    task = _build_task_from_request(
        team_id,
        SubmitTaskRequest(
            agent_id=agent_id,
            title=title,
            description=description,
            priority=priority,
            dependencies=list(dependencies or []),
            metadata=dict(metadata or {}),
        ),
    )
    workflow = _initialize_task_workflow(task, team_id)
    await _ensure_task_engine_running()
    _seed_task_pipeline(task)
    await _te().submit_task(task)
    if auto_start and workflow:
        _start_first_workflow_step(task, team_id, workflow)
        await _te().start_task(task.task_id)
        _start_harness_monitor(task.task_id, team_id)
    return task


def _initialize_task_workflow(task: AgentTask, team_id: str) -> List[Dict[str, Any]]:
    workflow = _generate_workflow(task, team_id)
    if workflow:
        task.metadata["workflow"] = workflow
    return workflow


def _seed_task_pipeline(task: AgentTask) -> None:
    try:
        _seed_project_context(task.task_id, task.title, task.description or "")
        task.metadata["pipeline_dir"] = _pipeline_dir(task.task_id)
    except Exception as exc:
        _harness_log.warning("[submit_task] Context seeding failed: %s", exc)


def _write_task_init_handoff(
    task: AgentTask,
    *,
    team_id: str,
    requested_agent_id: str,
    token_ready: bool,
    workflow: List[Dict[str, Any]],
) -> None:
    _write_handoff(task.task_id, "task_init", {
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "team_id": team_id,
        "agent_id": requested_agent_id,
        "token_factory_ready": token_ready,
        "workflow_steps": [s["key"] for s in workflow] if workflow else [],
    })


def _mark_task_backend_unavailable(task: AgentTask) -> None:
    _harness_log.warning(
        "[submit_task] Token Factory NOT ready — task %s queued but NOT started. "
        "请先确保 Ollama / LLM 推理后端可用。",
        task.task_id,
    )
    task.metadata["token_factory_error"] = "LLM 推理后端不可用，任务已创建但未启动执行"


def _start_first_workflow_step(task: AgentTask, team_id: str, workflow: List[Dict[str, Any]]) -> None:
    if not workflow:
        return
    first_step = workflow[0]
    if first_step.get("status") != "active" or not first_step.get("agent_id"):
        return

    import uuid as _uuid

    sr = _sr()
    skill = sr.get_by_slug("code_implementation")
    cfg = dict(skill.config or {}) if skill else {}
    agent = _tm().get_agent(team_id, first_step["agent_id"])
    if not agent:
        return

    sid = str(_uuid.uuid4())[:12]
    step_prompt = _build_step_prompt(task, first_step, workflow)
    _harness_log.info(
        "[submit_task] Starting Claude session %s for step '%s' (agent: %s)",
        sid,
        first_step["key"],
        agent.name,
    )
    _start_claude_session(sid, step_prompt, cfg, agent, task.task_id, team_id=team_id)
    first_step["session_id"] = sid
    task.metadata["workflow"] = workflow
    _emit_pipeline_event(task.task_id, "step_started", {
        "step": first_step["key"],
        "label": first_step.get("label", ""),
        "agent": agent.name,
    })


def _active_workflow_step(workflow: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for step in workflow:
        if step.get("status") == "active":
            return step
    return None


def _code_implementation_skill_config() -> Dict[str, Any]:
    skill = _sr().get_by_slug("code_implementation")
    return dict(skill.config or {}) if skill else {}


def _start_workflow_step_session(
    *,
    task: AgentTask,
    team_id: str,
    step: Dict[str, Any],
    workflow: List[Dict[str, Any]],
    log_prefix: str,
) -> Optional[str]:
    import uuid as _uuid

    agent = _tm().get_agent(team_id, step.get("agent_id", ""))
    if not agent:
        return None
    sid = str(_uuid.uuid4())[:12]
    step_prompt = _build_step_prompt(task, step, workflow)
    _harness_log.info(
        "[%s] Starting Claude session %s for step '%s' (agent: %s)",
        log_prefix,
        sid,
        step["key"],
        agent.name,
    )
    _start_claude_session(
        sid, step_prompt, _code_implementation_skill_config(), agent, task.task_id, team_id=team_id,
    )
    step["session_id"] = sid
    task.metadata["workflow"] = workflow
    return sid


def _persist_workflow_and_monitor(task: AgentTask, team_id: str, workflow: List[Dict[str, Any]]) -> None:
    task.metadata["workflow"] = workflow
    _start_harness_monitor(task.task_id, team_id)


def _te():
    """Return the TaskEngine singleton, registering the real executor on first call."""
    engine = get_task_engine()
    if engine._executor is None:
        engine.set_executor(_real_task_executor)
    return engine


async def _real_task_executor(task) -> Any:
    """Real executor callback — invoked by TaskEngine._execute() for queued tasks.

    This bridges the TaskEngine's internal queue with the Claude Code workflow
    pipeline.  When a task is submitted via submit_batch() or directly enqueued,
    the executor generates a workflow, starts a Claude session for step 1, and
    launches the harness monitor for auto-advancement.

    For tasks submitted via the REST API, the submit_task endpoint handles this
    directly (so the executor won't be triggered for those).
    """
    import uuid as _uuid

    # Skip if workflow already started (e.g., via the REST endpoint)
    if task.metadata.get("workflow") and any(
        s.get("session_id") for s in task.metadata["workflow"]
    ):
        return {"message": "Workflow already running via REST endpoint"}

    # LLM backend preflight — use ChatHarness provider config (authoritative)
    api_key, _, _ = _get_deepseek_credentials()
    if api_key:
        _harness_log.info("[Executor] LLM backend available via harness config — proceeding")
    else:
        _harness_log.error("[Executor] LLM backend not available for task %s — aborting", task.task_id)
        raise RuntimeError("LLM 推理后端不可用，无法执行任务。"
                           "请在 config/settings.json llm 段配置 api_key。")

    # Generate workflow if none exists
    wf = task.metadata.get("workflow")
    if not wf:
        wf = _generate_workflow(task, task.team_id)
        task.metadata["workflow"] = wf

    if not wf:
        return {"message": "No workflow generated"}

    # Pre-seed pipeline workspace with project context
    try:
        _seed_project_context(task.task_id, task.title, task.description or "")
        task.metadata["pipeline_dir"] = _pipeline_dir(task.task_id)
    except Exception as _ctx_err:
        _harness_log.warning("[Executor] Context seeding failed: %s", _ctx_err)

    # Start first step
    first_step = wf[0]
    if first_step.get("status") != "active":
        first_step["status"] = "active"

    if first_step.get("agent_id"):
        sr = _sr()
        skill = sr.get_by_slug("code_implementation")
        cfg = dict(skill.config or {}) if skill else {}
        tm = _tm()
        agent = tm.get_agent(task.team_id, first_step["agent_id"])
        if agent:
            sid = str(_uuid.uuid4())[:12]
            step_prompt = _build_step_prompt(task, first_step, wf)
            _harness_log.info("[Executor] Starting Claude session %s for task %s step '%s'",
                              sid, task.task_id, first_step["key"])
            _start_claude_session(
                sid, step_prompt, cfg, agent, task.task_id, team_id=task.team_id,
            )
            first_step["session_id"] = sid
            task.metadata["workflow"] = wf

    # Start harness monitor
    _start_harness_monitor(task.task_id, task.team_id)

    _write_handoff(task.task_id, "executor_started", {
        "task_id": task.task_id,
        "title": task.title,
        "first_step": first_step.get("key", ""),
        "executor": "real_task_executor",
    })

    return {"message": f"Workflow started with {len(wf)} steps", "first_session": first_step.get("session_id")}


@router.post(
    "/teams/{team_id}/tasks",
    summary="Submit a task for execution",
    status_code=status.HTTP_201_CREATED,
)
async def submit_task(team_id: str, req: SubmitTaskRequest) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    if req.agent_id:
        _get_agent_or_404(team_id, req.agent_id)
    # TG-5：预算 halt 硬门禁（提交前预检；metadata.skip_token_budget 可关）
    _meta0 = dict(req.metadata or {})
    if not _meta0.get("skip_token_budget"):
        _est = _estimate_prompt_tokens(
            f"{req.title or ''}\n{req.description or ''}"
        ) + 2000  # 预留首轮上下文
        _pre = _precheck_team_token_budget(
            team_id, estimated_tokens=_est, agent_id=req.agent_id or "",
        )
        if not _pre.get("allowed"):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "token_budget_exceeded",
                    "message": "团队/Agent token 预算已触顶（BudgetGuard halt）",
                    "budget": _pre.get("budget"),
                    "events": _pre.get("events"),
                    "hint": "打开 cost-dashboard「任务 Token 工作台 → 预算与门禁」调高限额，或 metadata.skip_token_budget=true",
                    "workbench": "/cost-dashboard.html#tg-hub",
                },
            )
    engine = await _ensure_task_engine_running()
    token_ready = await _check_token_factory_ready("submit_task")
    task = _build_task_from_request(team_id, req)
    workflow = _initialize_task_workflow(task, team_id)
    _seed_task_pipeline(task)
    _write_task_init_handoff(
        task,
        team_id=team_id,
        requested_agent_id=req.agent_id,
        token_ready=token_ready,
        workflow=workflow,
    )

    await engine.submit_task(task)

    if not token_ready and not _has_execution_backend("submit_task"):
        _mark_task_backend_unavailable(task)
        return task.to_dict()

    if workflow:
        _start_first_workflow_step(task, team_id, workflow)
        await engine.start_task(task.task_id)
        _start_harness_monitor(task.task_id, team_id)
    return task.to_dict()


@router.post(
    "/teams/{team_id}/tasks/batch",
    summary="Submit batch tasks with dependencies",
    status_code=status.HTTP_201_CREATED,
)
async def submit_batch_tasks(
    team_id: str, req: SubmitBatchRequest
) -> List[Dict[str, Any]]:
    _get_team_or_404(team_id)
    engine = _te()
    if not engine._running:
        await engine.start()
    tasks = []
    for item in req.tasks:
        agent_id, metadata, _bid = _apply_eco_bid_locked_to_task(
            team_id,
            agent_id=item.agent_id or "",
            metadata=dict(item.metadata or {}),
        )
        if agent_id:
            try:
                _get_agent_or_404(team_id, agent_id)
            except Exception:
                if item.agent_id:
                    _get_agent_or_404(team_id, item.agent_id)
                    agent_id = item.agent_id
        t = AgentTask(
            agent_id=agent_id or item.agent_id,
            team_id=team_id,
            title=item.title,
            description=item.description,
            priority=item.priority,
            dependencies=list(item.dependencies),
            metadata=metadata,
        )
        tasks.append(t)
    await engine.submit_batch(tasks)
    return [t.to_dict() for t in tasks]


@router.get("/teams/{team_id}/tasks", summary="List all tasks for a team")
def list_team_tasks(
    team_id: str,
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    _get_team_or_404(team_id)
    items = [t.to_dict() for t in _te().get_team_tasks(team_id)]
    return _paginate_optional(items, limit=limit, offset=offset)


@router.get(
    "/teams/{team_id}/tasks/{task_id}",
    summary="Get task detail",
)
def get_task_detail(team_id: str, task_id: str) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task.to_dict()


@router.delete(
    "/teams/{team_id}/tasks/{task_id}",
    summary="Cancel a task",
)
async def cancel_task(team_id: str, task_id: str) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    task = await _te().cancel_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task.to_dict()


@router.delete(
    "/teams/{team_id}/tasks/{task_id}/remove",
    summary="Permanently delete a task",
)
async def remove_task(team_id: str, task_id: str) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    task = await _te().delete_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {"deleted": True, "task_id": task_id}


@router.post(
    "/teams/{team_id}/tasks/{task_id}/start",
    summary="Start a pending task (mark as running)",
)
async def start_task_endpoint(team_id: str, task_id: str) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    task = await _te().start_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Manual start from UI should launch the same workflow executor path used by
    # auto-start on submit, not just flip the task status to running.
    try:
        await _real_task_executor(task)
    except RuntimeError as exc:
        task.metadata["token_factory_error"] = str(exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        _harness_log.exception("[start_task_endpoint] Failed to launch workflow for task %s", task_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"任务已标记为运行，但工作流启动失败: {exc}")

    return task.to_dict()


@router.post(
    "/teams/{team_id}/tasks/{task_id}/complete",
    summary="Mark a task as completed",
)
async def complete_task_endpoint(team_id: str, task_id: str) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    task = await _te().complete_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task.to_dict()


@router.post(
    "/teams/{team_id}/tasks/{task_id}/fail",
    summary="Mark a task as failed",
)
async def fail_task_endpoint(team_id: str, task_id: str) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    task = await _te().fail_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task.to_dict()


# ── Workflow Steps (per-task execution pipeline visualization) ──────


# Role → workflow step definitions
_ROLE_WORKFLOW_MAP: Dict[str, list] = {
    "project_manager": [
        {"key": "pm_decompose", "label": "PM分解", "agent_role": "project_manager"},
        {"key": "research", "label": "研究分析", "agent_role": "researcher"},
        {"key": "architecture", "label": "架构设计", "agent_role": "architect"},
        {"key": "develop", "label": "代码开发", "agent_role": "developer"},
        {"key": "test", "label": "测试验证", "agent_role": "qa_engineer"},
        {"key": "deploy", "label": "部署上线", "agent_role": "devops"},
        {"key": "document", "label": "文档更新", "agent_role": "documentation"},
    ],
    "researcher": [
        {"key": "research", "label": "研究分析", "agent_role": "researcher"},
        {"key": "architecture", "label": "架构设计", "agent_role": "architect"},
        {"key": "develop", "label": "代码开发", "agent_role": "developer"},
        {"key": "test", "label": "测试验证", "agent_role": "qa_engineer"},
    ],
    "architect": [
        {"key": "architecture", "label": "架构设计", "agent_role": "architect"},
        {"key": "develop", "label": "代码开发", "agent_role": "developer"},
        {"key": "test", "label": "测试验证", "agent_role": "qa_engineer"},
    ],
    "developer": [
        {"key": "develop", "label": "代码开发", "agent_role": "developer"},
        {"key": "test", "label": "测试验证", "agent_role": "qa_engineer"},
    ],
    "qa_engineer": [
        {"key": "test", "label": "测试验证", "agent_role": "qa_engineer"},
    ],
    "devops": [
        {"key": "develop", "label": "代码开发", "agent_role": "developer"},
        {"key": "test", "label": "测试验证", "agent_role": "qa_engineer"},
        {"key": "deploy", "label": "部署上线", "agent_role": "devops"},
    ],
    "documentation": [
        {"key": "document", "label": "文档更新", "agent_role": "documentation"},
    ],
}

# ── 领域专属流水线模板定义 ──────────────────────────────────────────
_PIPELINE_TEMPLATES: Dict[str, list] = {
    # 1. 研发全流程流水线 (适用于 Build System、AI 编程等研发团队)
    "dev": [
        {"key": "pm_decompose", "label": "PM需求分解", "agent_role": "project_manager"},
        {"key": "research", "label": "技术研究分析", "agent_role": "researcher"},
        {"key": "architecture", "label": "系统架构设计", "agent_role": "architect"},
        {"key": "develop", "label": "核心代码开发", "agent_role": "developer"},
        {"key": "test", "label": "质量测试验证", "agent_role": "qa_engineer"},
        {"key": "deploy", "label": "部署构建上线", "agent_role": "devops"},
        {"key": "document", "label": "项目文档更新", "agent_role": "documentation"},
    ],
    # 2. xOPs 云运维与SRE运营流水线 (适用于 公有云xOPs、AWS运维、公有云平台运维运营 等运维团队)
    "xops": [
        {"key": "ops_triage", "label": "事件响应与调度", "agent_role": "incident_commander"},
        {"key": "sre_design", "label": "SRE方案设计", "agent_role": "platform_sre_architect"},
        {"key": "automation_exec", "label": "自动化作业实施", "agent_role": "automation_platform_engineer"},
        {"key": "cloud_delivery", "label": "多云服务落地", "agent_role": "cloud_service_owner"},
        {"key": "security_audit", "label": "安全合规审计", "agent_role": "security_compliance_engineer"},
        {"key": "finops_review", "label": "FinOps成本复盘", "agent_role": "finops_analyst"},
        {"key": "sop_postmortem", "label": "运营归档与SOP", "agent_role": "domestic_cloud_service_owner"},
    ],
    # 3. 绿色数据中心与能效调优流水线 (适用于 Energy First Principle 等能效治理团队)
    "energy": [
        {"key": "anomaly_sensing", "label": "异常功耗感知", "agent_role": "anomaly_detector"},
        {"key": "thermal_analysis", "label": "热力分布分析", "agent_role": "thermal_engineer"},
        {"key": "pue_opt", "label": "PUE能效调优", "agent_role": "energy_optimizer"},
        {"key": "evolution_verify", "label": "达尔文演化验证", "agent_role": "evolution_engineer"},
        {"key": "policy_audit", "label": "政策合规审计", "agent_role": "policy_analyst"},
        {"key": "forecast_archive", "label": "负荷预测与归档", "agent_role": "forecast_analyst"},
    ],
}

# Default full pipeline (backward compatibility alias for dev)
_FULL_PIPELINE = _PIPELINE_TEMPLATES["dev"]

# Candidate aliases for pipeline step roles across all team domains
_ROLE_FALLBACK_CANDIDATES: Dict[str, list] = {
    # 研发类角色候选别名
    "project_manager": [
        "project_manager", "cloud_ops_finops_owner", "运维Leader", "incident_commander",
        "leader", "owner", "manager", "pm", "负责人", "指挥官",
    ],
    "researcher": [
        "researcher", "finops_analyst", "anomaly_detector", "巡检监控员", "成本优化成员",
        "analyst", "sentinel", "watchdog", "分析", "巡检", "研究",
    ],
    "architect": [
        "architect", "platform_sre_architect", "上云架构师", "sre", "架构",
    ],
    "developer": [
        "developer", "automation_platform_engineer", "运维操作员", "engineer",
        "automation", "operator", "开发", "工程师", "操作",
    ],
    "qa_engineer": [
        "qa_engineer", "security_compliance_engineer", "tester", "qa", "security",
        "compliance", "verifier", "安全", "合规", "测试",
    ],
    "devops": [
        "devops", "aws_service_owner", "azure_service_owner", "aliyun_service_owner",
        "gcp_service_owner", "domestic_cloud_service_owner", "deployer", "运维操作员",
        "运维", "部署",
    ],
    "documentation": [
        "documentation", "domestic_cloud_service_owner", "doc_writer", "文档", "writer", "doc",
    ],

    # xOPs / 云运维 / SRE 类角色候选别名
    "incident_commander": [
        "incident_commander", "cloud_ops_finops_owner", "运维Leader", "operations_lead",
        "project_manager", "leader", "指挥官", "值班", "调度", "负责人",
    ],
    "platform_sre_architect": [
        "platform_sre_architect", "上云架构师", "cloud_architect", "architect", "sre", "架构",
    ],
    "automation_platform_engineer": [
        "automation_platform_engineer", "运维操作员", "operations_operator", "developer",
        "automation", "自动化", "操作", "平台", "工程师",
    ],
    "cloud_service_owner": [
        "aws_service_owner", "azure_service_owner", "aliyun_service_owner", "gcp_service_owner",
        "domestic_cloud_service_owner", "北美AI项目运维员", "devops", "云服务", "实施", "运维",
    ],
    "security_compliance_engineer": [
        "security_compliance_engineer", "regional_compliance", "qa_engineer", "tester",
        "security", "compliance", "安全", "合规", "风控",
    ],
    "finops_analyst": [
        "finops_analyst", "cost_optimizer", "成本优化成员", "cloud-finops", "finops", "成本", "财务", "分析",
    ],
    "domestic_cloud_service_owner": [
        "domestic_cloud_service_owner", "cloud_ops_finops_owner", "doc_writer", "documentation",
        "ccoe", "云卓越中心治理", "文档", "归档", "复盘", "SOP",
    ],

    # 能效治理类角色候选别名
    "anomaly_detector": [
        "anomaly_detector", "anomaly_watchdog", "巡检监控员", "monitoring", "watchdog", "巡检", "异常",
    ],
    "thermal_engineer": [
        "thermal_engineer", "thermal_sentinel", "sentinel", "热力", "温控",
    ],
    "energy_optimizer": [
        "energy_optimizer", "pue_optimizer", "optimizer", "能效", "pue",
    ],
    "evolution_engineer": [
        "evolution_engineer", "darwin_ratchet", "ratchet", "演化", "棘轮",
    ],
    "policy_analyst": [
        "policy_analyst", "policy_engine", "合规", "政策", "审计",
    ],
    "forecast_analyst": [
        "forecast_analyst", "forecast_planner", "planner", "预测", "调度",
    ],
}


def _infer_team_pipeline_type(team: Optional[Any], team_id: str) -> str:
    """Infer the domain-specific pipeline template ('xops', 'dev', or 'energy') for a team."""
    t_id = (getattr(team, "team_id", "") if team else "") or team_id or ""
    t_name = (getattr(team, "name", "") if team else "") or ""
    combined = f"{t_id} {t_name}".lower()

    # 1. Check Energy domain
    if any(k in combined for k in ("energy", "pue", "thermal", "节能", "能效")):
        return "energy"
    # 2. Check xOPs / Cloud Ops domain
    if any(k in combined for k in ("ops", "cloud", "aws", "sre", "运维", "云平台", "finops")):
        return "xops"

    # 3. Check agent roles inside team
    agents_list = []
    if team:
        agents_val = getattr(team, "agents", None)
        if isinstance(agents_val, dict):
            agents_list = list(agents_val.values())
        elif isinstance(agents_val, list):
            agents_list = agents_val

    ops_role_markers = (
        "cloud_ops", "sre", "finops", "incident", "aws_", "azure_", "aliyun_", "gcp_",
        "domestic_cloud", "运维", "巡检", "上云"
    )
    for a in agents_list:
        a_role = (getattr(a, "role", "") or "").lower()
        if any(m in a_role for m in ops_role_markers):
            return "xops"

    energy_role_markers = ("energy", "pue", "thermal", "ratchet")
    for a in agents_list:
        a_role = (getattr(a, "role", "") or "").lower()
        if any(m in a_role for m in energy_role_markers):
            return "energy"

    return "dev"


def _find_agent_for_pipeline_role(
    role_needed: str,
    agents_list: list,
    default_agent_id: str = "",
) -> str:
    """Find the best matching agent in team for a pipeline role, with semantic fallbacks."""
    if not agents_list:
        return default_agent_id
    # 1. Exact role match
    for a in agents_list:
        a_role = a.get("role", "") if isinstance(a, dict) else getattr(a, "role", "")
        a_id = a.get("agent_id", "") if isinstance(a, dict) else getattr(a, "agent_id", "")
        if a_role == role_needed and a_id:
            return a_id
    # 2. Candidate role list / substring match on role or name
    candidates = _ROLE_FALLBACK_CANDIDATES.get(role_needed, [role_needed])
    for cand in candidates:
        for a in agents_list:
            a_role = (a.get("role", "") if isinstance(a, dict) else getattr(a, "role", "")) or ""
            a_name = (a.get("name", "") if isinstance(a, dict) else getattr(a, "name", "")) or ""
            a_id = a.get("agent_id", "") if isinstance(a, dict) else getattr(a, "agent_id", "")
            if not a_id:
                continue
            if cand.lower() in a_role.lower() or cand.lower() in a_name.lower():
                return a_id
    # 3. Fallback: default_agent_id or first agent in team
    if default_agent_id:
        return default_agent_id
    first = agents_list[0]
    return first.get("agent_id", "") if isinstance(first, dict) else getattr(first, "agent_id", "")


def _generate_workflow(task: "AgentTask", team_id: str) -> list:
    """Generate workflow steps for a task based on its agent role and team pipeline mode."""
    tm = _tm()
    agent = tm.get_agent(team_id, task.agent_id) if task.agent_id else None
    team = tm.get_team(team_id)

    # Resolve agent list in team
    agents_list = []
    if team:
        agents_val = team.get("agents", []) if isinstance(team, dict) else getattr(team, "agents", [])
        if isinstance(agents_val, dict):
            agents_list = list(agents_val.values())
        elif isinstance(agents_val, list):
            agents_list = agents_val

    # Determine role
    role = ""
    if agent:
        role = getattr(agent, "role", "")
    is_cross = task.metadata.get("cross_team", False)

    wf_mode = getattr(team, "workflow_mode", "single") if team else "single"
    if wf_mode == "full":
        # "full" is normalized to "auto"
        wf_mode = "auto"

    steps_template = []
    if wf_mode == "single":
        # Check if individual agent role has a mapped workflow
        steps_template = _ROLE_WORKFLOW_MAP.get(role, [])
        if not steps_template:
            label = (agent.name if agent else task.agent_id) or "执行"
            steps_template = [{"key": "execute", "label": label, "agent_role": role or "unknown"}]
    elif wf_mode in _PIPELINE_TEMPLATES:
        steps_template = _PIPELINE_TEMPLATES[wf_mode]
    elif wf_mode == "star":
        leader_id = _find_agent_for_pipeline_role("incident_commander", agents_list, default_agent_id=task.agent_id or "")
        leader_agent = next((a for a in agents_list if (a.get("agent_id") if isinstance(a, dict) else getattr(a, "agent_id", "")) == leader_id), None)
        leader_name = (leader_agent.get("name") if isinstance(leader_agent, dict) else getattr(leader_agent, "name", "")) if leader_agent else "中枢总控"
        steps_template = [{"key": "star_dispatch", "label": f"{leader_name}·总控分发", "agent_role": "incident_commander"}]
        for a in agents_list:
            aid = a.get("agent_id") if isinstance(a, dict) else getattr(a, "agent_id", "")
            aname = a.get("name") if isinstance(a, dict) else getattr(a, "name", "")
            arole = a.get("role") if isinstance(a, dict) else getattr(a, "role", "")
            if aid and aid != leader_id:
                steps_template.append({"key": f"star_{aid}", "label": f"{aname}·专项协同", "agent_role": arole or "developer"})
        steps_template.append({"key": "star_aggregate", "label": f"{leader_name}·汇总验收", "agent_role": "incident_commander"})
    elif wf_mode == "mesh":
        steps_template = []
        for i, a in enumerate(agents_list):
            aid = a.get("agent_id") if isinstance(a, dict) else getattr(a, "agent_id", "")
            aname = a.get("name") if isinstance(a, dict) else getattr(a, "name", "")
            arole = a.get("role") if isinstance(a, dict) else getattr(a, "role", "")
            if aid:
                steps_template.append({"key": f"mesh_step_{i+1}", "label": f"{aname}·对等协同", "agent_role": arole or "developer"})
        if not steps_template:
            steps_template = [{"key": "execute", "label": "全员协同执行", "agent_role": "collaborator"}]
    elif wf_mode == "custom":
        custom_links = (team.metadata or {}).get("custom_topology", []) if team else []
        if custom_links:
            seen_steps = set()
            steps_template = []
            for link in custom_links:
                src = link.get("source")
                tgt = link.get("target")
                for node_id in (src, tgt):
                    if node_id and node_id not in seen_steps:
                        seen_steps.add(node_id)
                        node_agent = next((a for a in agents_list if (a.get("agent_id") if isinstance(a, dict) else getattr(a, "agent_id", "")) == node_id), None)
                        node_name = (node_agent.get("name") if isinstance(node_agent, dict) else getattr(node_agent, "name", "")) if node_agent else node_id
                        node_role = (node_agent.get("role") if isinstance(node_agent, dict) else getattr(node_agent, "role", "")) if node_agent else "developer"
                        steps_template.append({
                            "key": f"custom_{node_id}",
                            "label": f"{node_name}·作业阶段",
                            "agent_role": node_role or "developer",
                        })
        if not steps_template:
            inferred_domain = _infer_team_pipeline_type(team, team_id)
            steps_template = _PIPELINE_TEMPLATES.get(inferred_domain, _PIPELINE_TEMPLATES["dev"])
    else:
        # "auto" or cross-team or fallback: infer domain pipeline for the team
        inferred_domain = _infer_team_pipeline_type(team, team_id)
        steps_template = _PIPELINE_TEMPLATES.get(inferred_domain, _PIPELINE_TEMPLATES["dev"])

    steps = []
    for i, tmpl in enumerate(steps_template):
        resolved_agent = _find_agent_for_pipeline_role(
            tmpl["agent_role"], agents_list, default_agent_id=task.agent_id or ""
        )
        steps.append({
            "index": i,
            "key": tmpl["key"],
            "label": tmpl["label"],
            "agent_id": resolved_agent,
            "agent_role": tmpl["agent_role"],
            "status": "pending",  # pending | active | completed | skipped
        })
    # First step is active if task is pending/running
    if steps and task.status.value in ("pending", "running"):
        steps[0]["status"] = "active"
    return steps


def _workflow_handoff_gate(
    team_id: str,
    from_agent_id: str,
    to_agent_id: str,
    *,
    log_prefix: str = "workflow_handoff",
) -> Dict[str, Any]:
    """步骤交接协作拓扑检查。hard 且无路径时返回 allowed=False."""
    if not from_agent_id or not to_agent_id or from_agent_id == to_agent_id:
        return {"allowed": True, "reason": "same_or_empty", "layers": []}
    try:
        from agents.agent_relationships import gate_workflow_handoff
        gate = gate_workflow_handoff(team_id, from_agent_id, to_agent_id)
        if gate.get("warning"):
            logger.warning("[%s] %s", log_prefix, gate.get("warning"))
        return gate
    except Exception as e:
        logger.debug("[%s] gate error: %s", log_prefix, e)
        return {"allowed": True, "reason": f"gate_error:{e}", "layers": [], "mode": "soft"}


@router.post(
    "/teams/{team_id}/tasks/{task_id}/workflow/advance",
    summary="Advance task workflow to next step",
)
async def advance_workflow(team_id: str, task_id: str) -> Dict[str, Any]:
    """Mark current active step as completed, activate and auto-start Claude Code on next step."""
    _get_team_or_404(team_id)
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    wf = task.metadata.get("workflow", [])
    if not wf:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No workflow steps")
    # Find active step
    active_idx = -1
    for s in wf:
        if s["status"] == "active":
            active_idx = s["index"]
            break
    if active_idx < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No active step")

    # Collect artifact from completed step's Claude session (if any)
    completed_step = wf[active_idx]
    _collect_step_artifact(task, completed_step)

    # Complete current, activate next
    wf[active_idx]["status"] = "completed"
    if active_idx + 1 < len(wf):
        next_step = wf[active_idx + 1]
        from_aid = str(completed_step.get("agent_id") or "")
        to_aid = str(next_step.get("agent_id") or "")
        gate = _workflow_handoff_gate(team_id, from_aid, to_aid, log_prefix="advance_workflow")
        if not gate.get("allowed"):
            wf[active_idx]["status"] = "active"  # 回滚完成态
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "collab_topology_handoff_denied",
                    "from_agent": from_aid,
                    "to_agent": to_aid,
                    "reason": gate.get("reason"),
                    "allowed_contacts": gate.get("allowed_contacts") or [],
                },
            )
        next_step["status"] = "active"
        next_step["collab_handoff"] = {
            "from": from_aid,
            "to": to_aid,
            "path": gate.get("reason"),
            "layers": gate.get("layers") or [],
        }
        # Auto-start Claude Code for EVERY step
        if next_step.get("agent_id"):
            _start_workflow_step_session(
                task=task,
                team_id=team_id,
                step=next_step,
                workflow=wf,
                log_prefix="advance_workflow",
            )
    # Ensure harness monitor is running
    _persist_workflow_and_monitor(task, team_id, wf)
    # Check if all completed
    all_done = all(s["status"] in ("completed", "skipped") for s in wf)
    # Auto-complete the task when all workflow steps are done
    if all_done and task.status.value in ("pending", "running"):
        await _te().complete_task(task_id)
    return {"workflow": wf, "all_completed": all_done, "task_id": task_id}


@router.post(
    "/teams/{team_id}/tasks/{task_id}/workflow/{step_index}/status",
    summary="Set a specific workflow step status",
)
async def set_workflow_step_status(
    team_id: str, task_id: str, step_index: int, req: Dict[str, str]
) -> Dict[str, Any]:
    """Set status of a specific workflow step (completed/active/skipped/pending)."""
    _get_team_or_404(team_id)
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    wf = task.metadata.get("workflow", [])
    new_status = req.get("status", "")
    if new_status not in ("pending", "active", "completed", "skipped"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    if step_index < 0 or step_index >= len(wf):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid step index")
    wf[step_index]["status"] = new_status
    task.metadata["workflow"] = wf
    return {"workflow": wf, "task_id": task_id}


@router.post(
    "/teams/{team_id}/tasks/{task_id}/workflow/run-claude",
    summary="Start Claude Code for the current active step",
)
async def run_claude_for_task(team_id: str, task_id: str) -> Dict[str, Any]:
    """Manually start a Claude Code session for the current active step.

    XC-1.2: 旧路由保留转发，实际已去 CLI 化——走配置模型 provider。
    """
    _get_team_or_404(team_id)
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    wf = task.metadata.get("workflow", [])
    # Find any active step
    active_step = _active_workflow_step(wf)
    if not active_step:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No active step")
    if active_step.get("session_id"):
        return {"session_id": active_step["session_id"], "status": "already_running"}

    sid = _start_workflow_step_session(
        task=task,
        team_id=team_id,
        step=active_step,
        workflow=wf,
        log_prefix="run_claude_for_task",
    )
    if not sid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agent not found for this step")

    # Ensure harness monitor is running
    _persist_workflow_and_monitor(task, team_id, wf)
    return {"session_id": sid, "status": "started"}


# XC-1.2: 新别名路由——语义更准确，旧路由保留转发
@router.post(
    "/teams/{team_id}/tasks/{task_id}/workflow/run-step",
    summary="Run the current active step via configured model",
)
async def run_step_for_task(team_id: str, task_id: str) -> Dict[str, Any]:
    """XC-1.2: run-claude 的去_cli 化别名——走配置模型 provider."""
    return await run_claude_for_task(team_id, task_id)


# XC-4.1: 工作区浏览 API（只读，路径限定工作区内）
@router.get(
    "/teams/{team_id}/tasks/{task_id}/workspace",
    summary="Browse task pipeline workspace files",
)
async def browse_task_workspace(team_id: str, task_id: str,
                                subpath: str = "") -> Dict[str, Any]:
    """XC-4.1: 列出/预览任务工作区文件（只读）."""
    _get_team_or_404(team_id)
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")

    pdir = _pipeline_dir(task_id)
    # 安全：只允许在工作区内浏览
    target = pdir
    if subpath:
        target = _os.path.normpath(_os.path.join(pdir, subpath))
        # 防止路径逃逸
        if not target.startswith(pdir):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="path outside workspace")

    if _os.path.isfile(target):
        # 预览文本文件
        try:
            size = _os.path.getsize(target)
            if size > 256 * 1024:
                return {"type": "file", "path": subpath, "size": size,
                        "content": "(file too large, >256KB)", "truncated": True}
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {"type": "file", "path": subpath, "size": size,
                    "content": content, "truncated": False}
        except Exception as e:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not _os.path.isdir(target):
        return {"type": "empty", "path": subpath, "entries": []}

    # 列目录
    entries = []
    try:
        for name in sorted(_os.listdir(target)):
            full = _os.path.join(target, name)
            rel = _os.path.relpath(full, pdir) if subpath else name
            if _os.path.isdir(full):
                entries.append({"name": name, "type": "dir", "path": rel})
            else:
                entries.append({"name": name, "type": "file", "path": rel,
                                "size": _os.path.getsize(full)})
    except Exception:
        pass
    return {"type": "dir", "path": subpath, "entries": entries}


@router.post(
    "/teams/{team_id}/tasks/{task_id}/workflow/resume",
    summary="Resume a blocked task after Token Factory becomes ready",
)
async def resume_blocked_task(team_id: str, task_id: str) -> Dict[str, Any]:
    """Resume a task pipeline that was blocked due to Token Factory unavailability.

    Re-checks Token Factory, then starts the first pending/blocked step.
    """
    _get_team_or_404(team_id)
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")

    # LLM backend preflight — use ChatHarness provider config
    if not _has_execution_backend("resume_blocked_task"):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 推理后端不可用，请在 config/settings.json llm 段配置 api_key。"
        )

    wf = task.metadata.get("workflow", [])
    if not wf:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No workflow")

    # Find first pending or blocked step
    resume_step = None
    for s in wf:
        if s.get("status") in ("pending", "active") or s.get("_blocked_reason"):
            resume_step = s
            break
    if not resume_step:
        return {"status": "all_done", "task_id": task_id}

    resume_step["status"] = "active"
    resume_step.pop("_blocked_reason", None)

    # Clear token factory error
    task.metadata.pop("token_factory_error", None)

    _start_workflow_step_session(
        task=task,
        team_id=team_id,
        step=resume_step,
        workflow=wf,
        log_prefix="Resume",
    )

    # Ensure running state
    if task.status.value == "pending":
        await _te().start_task(task_id)
    _persist_workflow_and_monitor(task, team_id, wf)

    _write_handoff(task_id, "pipeline_resumed", {
        "step": resume_step["key"],
        "agent": resume_step.get("agent_id", ""),
        "reason": "Token Factory now available, pipeline resumed",
    })

    return {"status": "resumed", "step": resume_step["key"], "session_id": resume_step.get("session_id")}


class ExecuteSkillRequest(BaseModel):
    """Execute a skill on a task, optionally with a specific executor."""
    task_id: str = ""
    prompt: str = ""
    config_overrides: Dict[str, Any] = Field(default_factory=dict)


# ── Claude Code streaming session store ──
import subprocess
import threading
import time as _time
import os as _os
import logging as _logging
from collections import deque

_harness_log = _logging.getLogger("workflow_harness")
# Ensure harness messages reach stdout (uvicorn captures root logger)
if not _harness_log.handlers:
    _h = _logging.StreamHandler()
    _h.setFormatter(_logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    _harness_log.addHandler(_h)
    _harness_log.setLevel(_logging.INFO)
    _harness_log.propagate = False

_claude_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> {proc, lines, status, ...}

# ── Harness config ──
_HARNESS_POLL_SEC = 5        # Check session status every N seconds
_HARNESS_MAX_RETRIES = 2     # Retry failed steps up to N times
_HARNESS_RETRY_DELAY = 3     # Seconds between retries
_HARNESS_STALL_SEC = 300     # Mark stalled if no output for N seconds (large models need time)
_HARNESS_AUTO_ADVANCE = True # Auto-advance on step completion
_PIPELINE_MAX_REWINDS = 2    # Max times to rewind develop→test→deploy with QA feedback
_SESSION_GC_TTL_SEC = 1800   # Remove completed sessions after 30 min

# ── Pipeline event bus (per-task SSE subscribers) ──
import collections as _collections
_pipeline_events: Dict[str, list] = {}  # task_id -> list of event dicts
_pipeline_subscribers: Dict[str, list] = {}  # task_id -> list of asyncio.Queue


def _emit_pipeline_event(task_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """Push an event to all SSE subscribers of a task and persist it."""
    evt = {"type": event_type, "ts": _time.time(), **data}
    _pipeline_events.setdefault(task_id, []).append(evt)
    # Keep last 200 events per task
    if len(_pipeline_events[task_id]) > 200:
        _pipeline_events[task_id] = _pipeline_events[task_id][-200:]
    task = _te().get_task(task_id)
    if task is not None:
        task.metadata.setdefault("trace_events", []).append(_trace_event_payload(task_id, evt))
        if len(task.metadata["trace_events"]) > 200:
            task.metadata["trace_events"] = task.metadata["trace_events"][-200:]
    _persist_trace_event(task_id, evt)
    # Push to SSE subscribers
    for q in _pipeline_subscribers.get(task_id, []):
        try:
            q.put_nowait(evt)
        except Exception:
            pass


def _gc_sessions() -> int:
    """Remove completed/failed sessions older than _SESSION_GC_TTL_SEC. Returns count removed."""
    now = _time.time()
    to_remove = []
    for sid, s in _claude_sessions.items():
        if s.get("status") in ("completed", "failed", "stopped"):
            age = now - s.get("started_at", now)
            if age > _SESSION_GC_TTL_SEC:
                to_remove.append(sid)
    for sid in to_remove:
        _claude_sessions.pop(sid, None)
    if to_remove:
        _harness_log.info(f"[GC] Cleaned up {len(to_remove)} expired sessions")
    return len(to_remove)


def _rewind_pipeline_to_develop(task, wf: list, qa_reason: str, qa_report: str) -> bool:
    """Rewind workflow back to the develop step with structured QA feedback.

    Resets develop/test/deploy steps to 'pending', stores feedback in task.metadata,
    so the next harness tick will re-run develop with the QA report visible in its prompt.

    Enhanced: extracts structured failure data (file paths, line numbers, error types)
    from the QA report so the developer gets actionable fix instructions.

    Returns True if rewind succeeded, False if rewind cap exhausted.
    """
    md = task.metadata or {}
    rewind_count = int(md.get("pipeline_rewinds", 0))
    if rewind_count >= _PIPELINE_MAX_REWINDS:
        _harness_log.warning(
            f"[Harness] Rewind cap reached ({rewind_count}/{_PIPELINE_MAX_REWINDS}) "
            f"for task {task.task_id} — giving up"
        )
        # G7 fix: explicitly fail the task so it doesn't stay "running" forever
        _emit_pipeline_event(task.task_id, "pipeline_failed", {
            "reason": f"QA rewind cap exhausted ({_PIPELINE_MAX_REWINDS}): {qa_reason}",
        })
        for s in wf:
            if s.get("status") in ("active", "pending"):
                s["status"] = "failed"
                s["error"] = f"pipeline halted: rewind cap ({_PIPELINE_MAX_REWINDS}) exhausted"
        task.metadata["workflow"] = wf
        task.metadata["pipeline_failed_reason"] = qa_reason
        try:
            task.status = task.status.__class__("failed")
        except Exception:
            pass
        return False

    rewind_count += 1

    # ── Extract structured failure data from QA report ──
    structured_failures = []
    if qa_report:
        import re as _re_rw
        # Parse file-specific errors: patterns like "src/backend/foo.py: ImportError ..."
        file_error_re = _re_rw.compile(
            r"(?:❌|FAIL|BLOCKER|失败|错误)\s*[：:]*\s*"
            r"(?:`?([^\s`]+\.\w{1,6})`?)"
            r"(?:\s*(?:L|line|行)\s*(\d+))?"
            r"[：:\s]+(.+?)(?:\n|$)",
            _re_rw.MULTILINE | _re_rw.IGNORECASE,
        )
        for m in file_error_re.finditer(qa_report):
            structured_failures.append({
                "file": m.group(1),
                "line": int(m.group(2)) if m.group(2) else None,
                "error": m.group(3).strip()[:300],
            })

        # Parse pytest-style failures: "FAILED tests/unit/test_foo.py::test_bar - reason"
        pytest_fail_re = _re_rw.compile(
            r"FAILED\s+([\w/._]+)::(\w+)\s*[-–]\s*(.+?)(?:\n|$)",
            _re_rw.MULTILINE,
        )
        for m in pytest_fail_re.finditer(qa_report):
            structured_failures.append({
                "file": m.group(1),
                "test": m.group(2),
                "error": m.group(3).strip()[:300],
            })

        # Parse SyntaxError / ImportError lines
        syntax_re = _re_rw.compile(
            r"(SyntaxError|ImportError|ModuleNotFoundError|NameError|AttributeError)"
            r"[：:\s]+(.+?)(?:\n|$)",
            _re_rw.MULTILINE,
        )
        for m in syntax_re.finditer(qa_report):
            err = {"error_type": m.group(1), "detail": m.group(2).strip()[:300]}
            # Avoid duplicates
            if not any(sf.get("error", "").startswith(m.group(1)) for sf in structured_failures):
                structured_failures.append(err)

    md["pipeline_rewinds"] = rewind_count
    md["qa_feedback"] = {
        "iteration": rewind_count,
        "reason": qa_reason,
        "report": qa_report[:5000] if qa_report else "",
        "structured_failures": structured_failures[:15],
        "at": _time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Also try to include the test step's structured summary
    test_step = next((s for s in wf if s.get("key") == "test"), None)
    if test_step and test_step.get("_summary"):
        ts = test_step["_summary"]
        md["qa_feedback"]["verdict"] = ts.get("verdict", "FAIL")
        md["qa_feedback"]["qa_checklist"] = ts.get("checklist", [])

    # Reset develop / test / deploy steps so harness will re-execute them
    rewindable = {"develop", "test", "deploy"}
    for s in wf:
        if s.get("key") in rewindable:
            s["status"] = "pending"
            s["session_id"] = None
            s["_retries"] = 0
            s["artifact"] = ""
            s.pop("error", None)
            s.pop("deploy_blocked", None)
            s.pop("deploy_result", None)
            s.pop("files_applied", None)
            s.pop("smoke", None)
            s.pop("deliverable_count", None)
            s.pop("deliverable_paths", None)
            s.pop("_summary", None)

    # Re-activate develop step
    for s in wf:
        if s.get("key") == "develop":
            s["status"] = "active"
            break

    task.metadata = md
    task.metadata["workflow"] = wf
    _harness_log.info(
        f"[Harness] 🔁 Pipeline rewound to develop (iter {rewind_count}/{_PIPELINE_MAX_REWINDS}) "
        f"for task {task.task_id}: {qa_reason} "
        f"({len(structured_failures)} structured failure(s))"
    )
    _emit_pipeline_event(task.task_id, "pipeline_rewind", {
        "iteration": rewind_count,
        "max": _PIPELINE_MAX_REWINDS,
        "reason": qa_reason[:200],
        "failures": len(structured_failures),
    })
    return True




# ── Workflow harness: monitors sessions and auto-advances steps ──
_harness_threads: Dict[str, threading.Thread] = {}  # task_id -> monitor thread


def _harness_monitor(task_id: str, team_id: str) -> None:
    """Background thread that monitors a task's active step and auto-advances on completion.
    Inspired by Claude Code's stall watchdog and task notification flow."""
    _harness_log.info(f"[Harness] Monitoring task {task_id}")
    _gc_counter = 0
    _emit_pipeline_event(task_id, "pipeline_started", {"team_id": team_id})
    while True:
        _time.sleep(_HARNESS_POLL_SEC)
        _gc_counter += 1
        if _gc_counter % 50 == 0:
            _gc_sessions()
        try:
            engine = _te()
            task = engine.get_task(task_id)
            if task is None:
                _harness_log.info(f"[Harness] Task {task_id} not found, stopping monitor")
                break

            # Check if task is terminal
            if task.status.value in ("completed", "failed", "cancelled"):
                _harness_log.info(f"[Harness] Task {task_id} is {task.status.value}, stopping monitor")
                break

            wf = task.metadata.get("workflow", [])
            if not wf:
                break

            # Find active step
            active_step = None
            for s in wf:
                if s.get("status") == "active":
                    active_step = s
                    break

            if not active_step:
                # Check if all done (completed, failed, or skipped — no pending/active left)
                if all(s["status"] in ("completed", "skipped", "failed") for s in wf):
                    _harness_log.info(f"[Harness] All steps done for task {task_id}")
                    # Trigger pipeline completion
                    completed_count = sum(1 for s in wf if s["status"] == "completed")
                    failed_count = sum(1 for s in wf if s["status"] == "failed")
                    task.metadata["workflow"] = wf
                    _write_handoff(task_id, "pipeline_complete", {
                        "total_steps": len(wf),
                        "completed": completed_count,
                        "failed": failed_count,
                        "steps": [{"key": s["key"], "status": s["status"]} for s in wf],
                    })
                    _emit_pipeline_event(task_id, "pipeline_complete", {
                        "completed": completed_count, "failed": failed_count,
                        "steps": [{"key": s["key"], "status": s["status"]} for s in wf],
                    })
                    _harness_log.info(
                        f"[Harness] Pipeline complete for task {task_id}: "
                        f"{completed_count}/{len(wf)} succeeded, {failed_count} failed"
                    )
                    try:
                        import http.client
                        hconn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=10)
                        hconn.request("POST",
                            f"/api/v1/agent-config/teams/{team_id}/tasks/{task_id}/complete")
                        hresp = hconn.getresponse()
                        hresp.read()
                        hconn.close()
                        _harness_log.info(f"[Harness] Task {task_id} auto-completed via HTTP ({hresp.status})")
                    except Exception as ex:
                        _harness_log.warning(f"[Harness] Could not auto-complete task: {ex}")
                        task.status = task.status.__class__("completed")
                    break  # All done → exit harness loop
                else:
                    # No active step but pending steps remain → promote the first pending one.
                    # This recovers from cases where a step's status got reset (rewind / race)
                    # but no follow-up activation happened.
                    pending = [s for s in wf if s.get("status") == "pending"]
                    if pending:
                        promoted = pending[0]
                        promoted["status"] = "active"
                        promoted["_active_since"] = _time.time()
                        promoted["session_id"] = None
                        task.metadata["workflow"] = wf
                        _harness_log.warning(
                            f"[Harness] No active step but {len(pending)} pending — "
                            f"auto-promoting '{promoted.get('key')}' to active"
                        )
                    continue  # next poll cycle will pick it up

            sid = active_step.get("session_id")
            if not sid:
                # Step is active but no session was ever started
                # Check how long it's been waiting
                wait_start = active_step.get("_active_since", 0)
                if not wait_start:
                    active_step["_active_since"] = _time.time()
                    continue
                elif _time.time() - wait_start > 30:
                    # Been waiting 30s with no session — try to start one, or skip
                    _harness_log.warning(
                        "[Harness] Step %s has no session after 30s — attempting to start",
                        active_step["key"])
                    aid = active_step.get("agent_id")
                    if aid:
                        try:
                            import uuid as _uuid
                            tm = _tm()
                            agent = tm.get_agent(team_id, aid)
                            if agent:
                                new_sid = str(_uuid.uuid4())[:12]
                                sr = _sr()
                                skill = sr.get_by_slug("code_implementation")
                                cfg = dict(skill.config or {}) if skill else {}
                                step_prompt = _build_step_prompt(task, active_step, wf)
                                _start_claude_session(
                                    new_sid, step_prompt, cfg, agent, task_id, team_id=team_id,
                                )
                                active_step["session_id"] = new_sid
                                task.metadata["workflow"] = wf
                                _harness_log.info("[Harness] Late-started session %s for step %s",
                                                  new_sid, active_step["key"])
                            else:
                                _harness_log.warning("[Harness] Agent %s not found — skipping step %s",
                                                     aid, active_step["key"])
                                active_step["status"] = "failed"
                                active_step["error"] = f"Agent {aid} not found"
                                task.metadata["workflow"] = wf
                        except Exception as ex:
                            _harness_log.exception(
                                "[Harness] Failed to late-start step %s: %s",
                                active_step["key"], ex,
                            )
                            active_step["status"] = "failed"
                            active_step["error"] = f"late-start failed: {ex}"
                            task.metadata["workflow"] = wf
                    else:
                        _harness_log.warning("[Harness] Step %s has no agent_id — skipping",
                                             active_step["key"])
                        active_step["status"] = "skipped"
                        task.metadata["workflow"] = wf
                continue

            session = _claude_sessions.get(sid)
            if not session:
                continue

            # Check session status
            sess_status = session.get("status", "running")

            if sess_status == "running":
                # Stall detection: check if output stopped growing
                # Skip stall detection if Ollama is loading the model (waiting for first token)
                if session.get("_ollama_waiting"):
                    # Keep session alive — Ollama model loading can take minutes
                    session["_last_activity"] = _time.time()
                    continue

                last_activity = session.get("_last_activity", session.get("started_at", 0))
                now = _time.time()
                lines = session.get("lines")
                current_count = len(lines) if lines else 0
                prev_count = session.get("_prev_line_count", 0)

                if current_count > prev_count:
                    session["_last_activity"] = now
                    session["_prev_line_count"] = current_count
                elif now - last_activity > _HARNESS_STALL_SEC:
                    _harness_log.warning(f"[Harness] Session {sid} stalled ({_HARNESS_STALL_SEC}s no output)")
                    session["lines"].append(f"\n⚠️ 会话停滞 ({_HARNESS_STALL_SEC}s 无输出)\n")
                    session["status"] = "failed"
                    session["exit_code"] = -1
                    sess_status = "failed"  # Fall through to retry/advance

                if sess_status == "running":
                    continue

            # Session completed or failed — handle it
            retry_count = active_step.get("_retries", 0)

            if sess_status == "failed" and retry_count < _HARNESS_MAX_RETRIES:
                # RETRY: restart the session
                active_step["_retries"] = retry_count + 1
                _harness_log.info(
                    f"[Harness] Retry {retry_count + 1}/{_HARNESS_MAX_RETRIES} "
                    f"for step {active_step['key']} of task {task_id}"
                )
                session["lines"].append(
                    f"\n🔄 自动重试 ({retry_count + 1}/{_HARNESS_MAX_RETRIES})...\n\n"
                )
                _time.sleep(_HARNESS_RETRY_DELAY)

                # Create new session for retry
                import uuid as _uuid
                new_sid = str(_uuid.uuid4())[:12]
                sr = _sr()
                skill = sr.get_by_slug("code_implementation")
                cfg = dict(skill.config or {}) if skill else {}
                tm = _tm()
                agent = tm.get_agent(team_id, active_step["agent_id"]) if active_step.get("agent_id") else None
                if agent:
                    step_prompt = _build_step_prompt(task, active_step, wf)
                    _start_claude_session(
                        new_sid, step_prompt, cfg, agent, task_id, team_id=team_id,
                    )
                    active_step["session_id"] = new_sid
                    task.metadata["workflow"] = wf
                    _harness_log.info(f"[Harness] Retry started with session {new_sid}")
                continue

            if sess_status in ("completed", "failed"):
                # Validate that session produced real output
                has_content = _validate_session_output(session)

                # Collect artifact (legacy: docs/workflow_artifacts/)
                _collect_step_artifact(task, active_step)

                # ── Save step output to pipeline workspace (shared) ──
                step_key = active_step.get("key", "")
                if has_content:
                    try:
                        art_path = active_step.get("artifact", "")
                        art_text = ""
                        if art_path and _os.path.isfile(art_path):
                            with open(art_path, "r", encoding="utf-8") as _af:
                                art_text = _af.read()
                        else:
                            art_text = "".join(list(session.get("lines", [])))

                        # Extract code deliverables for code-producing steps
                        deliverables = []
                        if step_key in _CODE_STEPS:
                            deliverables = _extract_code_deliverables(art_text)

                        # Save to pipeline workspace
                        _save_step_to_pipeline(
                            task_id, step_key, art_text, deliverables or None,
                        )

                        # ── Persist tool-call trace if this step ran in tool-loop mode ──
                        if session.get("tool_loop_log") is not None:
                            try:
                                pdir_tt = _pipeline_dir(task_id)
                                _os.makedirs(pdir_tt, exist_ok=True)
                                idx_tt = _STEP_INDEX.get(step_key, "00")
                                trace_path = _os.path.join(
                                    pdir_tt, f"{idx_tt}_{step_key}_tool_trace.json",
                                )
                                import json as _json_tt
                                with open(trace_path, "w", encoding="utf-8") as _tf:
                                    _json_tt.dump({
                                        "task_id": task_id, "step": step_key,
                                        "role": active_step.get("agent_role", ""),
                                        "ok": bool(session.get("loop_ok")),
                                        "iterations": session.get("loop_iterations", 0),
                                        "files_changed": session.get("files_changed", []),
                                        "summary": session.get("loop_summary", ""),
                                        "log": session.get("tool_loop_log", []),
                                    }, _tf, ensure_ascii=False, indent=2)
                                _harness_log.info(
                                    f"[Harness] Tool-trace persisted: {trace_path}"
                                )
                            except Exception as _terr:
                                _harness_log.debug(f"[Harness] tool-trace save skipped: {_terr}")

                        if deliverables:
                            active_step["deliverable_count"] = len(deliverables)
                            active_step["deliverable_paths"] = [d["path"] for d in deliverables]
                            _harness_log.info(
                                f"[Harness] Step {step_key}: {len(deliverables)} code deliverables saved"
                            )

                            # Per-agent workspace isolation: also drop a copy in
                            # the agent's private deliverables dir for traceability
                            try:
                                agent_id = active_step.get("agent_id") or active_step.get("assignee") or ""
                                if team_id and agent_id:
                                    _save_deliverables_to_workspace(
                                        task_id, team_id, agent_id, deliverables,
                                    )
                            except Exception as ws_err:
                                _harness_log.debug(f"[Harness] per-agent ws save skipped: {ws_err}")

                            # Pre-deploy smoke check (so QA step sees real signal)
                            if step_key == "develop":
                                try:
                                    smoke = _smoke_check_pipeline_code(task_id, step_key)
                                    active_step["smoke"] = smoke
                                    n_fail = sum(1 for s in smoke if not s.get("syntax_ok"))
                                    if n_fail:
                                        session["lines"].append(
                                            f"\n🔥 冒烟测试: {n_fail}/{len(smoke)} 文件存在语法/导入问题 (详见 apply_report.json)\n"
                                        )
                                    _harness_log.info(
                                        f"[Harness] Smoke: {len(smoke)-n_fail}/{len(smoke)} OK"
                                    )
                                except Exception as smoke_err:
                                    _harness_log.warning(f"[Harness] smoke check failed: {smoke_err}")
                        else:
                            # Explicitly mark 0 deliverables so deploy step can detect no-op
                            active_step["deliverable_count"] = 0
                    except Exception as pipe_err:
                        _harness_log.error(f"[Harness] Pipeline save error: {pipe_err}")

                # ── Extract structured summary for downstream agents ──
                if has_content and step_key:
                    try:
                        art_path_s = active_step.get("artifact", "")
                        summary_text = ""
                        if art_path_s and _os.path.isfile(art_path_s):
                            with open(art_path_s, "r", encoding="utf-8") as _sf:
                                summary_text = _sf.read()
                        else:
                            summary_text = "".join(list(session.get("lines", [])))
                        _step_deliverables = active_step.get("deliverable_paths", [])
                        _step_smoke = active_step.get("smoke")
                        _step_summary = _extract_step_summary(
                            task_id, step_key, summary_text,
                            deliverables=[{"path": p} for p in _step_deliverables] if _step_deliverables else None,
                            smoke_results=_step_smoke,
                        )
                        active_step["_summary"] = _step_summary
                        _harness_log.info(
                            f"[Harness] Step summary extracted for {step_key}: "
                            f"{len(_step_summary.get('decisions', []))} decisions, "
                            f"{len(_step_summary.get('files_changed', []))} files"
                        )
                    except Exception as sum_err:
                        _harness_log.debug(f"[Harness] Summary extraction skipped: {sum_err}")

                # ── Deploy step: apply code from developer's pipeline output ──
                if step_key == "deploy":
                    try:
                        # ── Check if developer produced zero changes (no-op task) ──
                        dev_step_obj = next((s for s in wf if s.get("key") == "develop"), None)
                        dev_deliverables = dev_step_obj.get("deliverable_count", 0) if dev_step_obj else 0
                        dev_no_op = (dev_deliverables == 0 and dev_step_obj
                                     and dev_step_obj.get("status") == "completed")

                        # ── QA Gate: refuse to apply if test step verdict is FAIL ──
                        gate_blocked = False
                        gate_reason = ""
                        try:
                            # Check the test step's status in workflow first
                            test_step_obj = next((s for s in wf if s.get("key") == "test"), None)
                            if test_step_obj and test_step_obj.get("status") == "failed":
                                gate_blocked = True
                                gate_reason = (
                                    f"Test 步骤失败 ({test_step_obj.get('error','no session/output')})"
                                )

                            pdir_g = _pipeline_dir(task_id)
                            test_idx = _STEP_INDEX.get("test", "05")
                            test_md = _os.path.join(pdir_g, f"{test_idx}_test.md")
                            if _os.path.isfile(test_md):
                                test_text = open(test_md, "r", encoding="utf-8").read()
                                # Block if QA explicitly said FAIL or BLOCKER
                                tl = test_text.lower()
                                # Look for "## 验证结论" then "FAIL"
                                import re as _re_g
                                verdict_m = _re_g.search(
                                    r"##\s*验证结论[\s\S]{0,200}?\b(fail|失败|blocked)\b",
                                    test_text, _re_g.IGNORECASE,
                                )
                                blocker_m = _re_g.search(r"\bblocker\b", test_text, _re_g.IGNORECASE)
                                if verdict_m and not gate_blocked:
                                    gate_blocked = True
                                    gate_reason = "QA 验证结论 = FAIL"
                                elif blocker_m and "blocker" not in tl.split("##")[0] and not gate_blocked:
                                    # only treat BLOCKER as gate if it's in body (not echo of the prompt)
                                    gate_blocked = True
                                    gate_reason = "QA 报告含 BLOCKER 级别问题"
                        except Exception as gerr:
                            _harness_log.debug(f"[Harness] QA gate check skipped: {gerr}")

                        if gate_blocked:
                            active_step["files_applied"] = 0
                            active_step["deploy_blocked"] = gate_reason
                            session["lines"].append(
                                f"\n🛑 部署已被 QA 阻断: {gate_reason}\n"
                            )
                            _harness_log.warning(
                                f"[Harness] Deploy BLOCKED by QA gate for task {task_id}: {gate_reason}"
                            )

                            # ── Phase 4: try to rewind to develop with QA feedback ──
                            qa_report_text = ""
                            try:
                                pdir_g2 = _pipeline_dir(task_id)
                                test_idx2 = _STEP_INDEX.get("test", "05")
                                test_md2 = _os.path.join(pdir_g2, f"{test_idx2}_test.md")
                                if _os.path.isfile(test_md2):
                                    qa_report_text = open(test_md2, "r", encoding="utf-8").read()
                            except Exception:
                                pass

                            if _rewind_pipeline_to_develop(task, wf, gate_reason, qa_report_text):
                                session["lines"].append(
                                    f"\n🔁 自动回滚到 develop 步骤，附带 QA 反馈，重新开发...\n"
                                )
                                # Skip rest of deploy handling — pipeline is now back at develop
                                continue
                            else:
                                session["lines"].append(
                                    f"   重试上限已达 ({_PIPELINE_MAX_REWINDS})，停止管线。\n"
                                    f"   代码保留在管线工作区，不会写入项目代码库。\n"
                                )
                                # Mark as failed so workflow stops cleanly
                                sess_status = "failed"
                                session["status"] = "failed"
                                session["error"] = f"QA gate: {gate_reason}"
                        else:
                            # Apply developer step's code to project
                            dev_result = _apply_code_from_pipeline(task_id, "develop")
                            dev_applied = len(dev_result.get("applied", []))

                            # Also apply deployer's own code (blue-green new files)
                            deploy_result = _apply_code_from_pipeline(task_id, "deploy")
                            deploy_applied = len(deploy_result.get("applied", []))

                            total_applied = dev_applied + deploy_applied
                            total_skipped = (len(dev_result.get("skipped", []))
                                            + len(deploy_result.get("skipped", [])))
                            total_failed = (len(dev_result.get("failed", []))
                                           + len(deploy_result.get("failed", [])))

                            active_step["files_applied"] = total_applied
                            active_step["deploy_result"] = {
                                "developer": dev_result,
                                "deployer": deploy_result,
                            }

                            # ── No-op deploy: developer found no changes needed ──
                            if dev_no_op and total_applied == 0:
                                active_step["deploy_no_op"] = True
                                session["lines"].append(
                                    "\n✅ 开发者判定无需代码变更，部署步骤跳过 (no-op)\n"
                                )
                                _harness_log.info(
                                    f"[Harness] Deploy no-op: developer had 0 deliverables, "
                                    f"treating as successful no-op deploy"
                                )
                            else:
                                session["lines"].append(
                                    f"\n📦 部署结果: {total_applied} 文件已应用 "
                                    f"(开发: {dev_applied}, 蓝绿: {deploy_applied}), "
                                    f"{total_skipped} 跳过, {total_failed} 失败\n"
                                )
                            _harness_log.info(
                                f"[Harness] Deploy: {total_applied} applied "
                                f"(dev={dev_applied}, deploy={deploy_applied})"
                            )
                    except Exception as dpex:
                        _harness_log.error(f"[Harness] Deploy apply error: {dpex}")

                task.metadata["workflow"] = wf

                if sess_status == "completed" and not has_content:
                    # No-op deploy is still valid — developer found nothing to change
                    is_no_op_deploy = (step_key == "deploy"
                                       and active_step.get("deploy_no_op"))
                    if is_no_op_deploy:
                        _harness_log.info(
                            f"[Harness] Step {active_step['key']} is a no-op deploy — "
                            f"treating as completed despite minimal output"
                        )
                    else:
                        # Session "completed" but produced no real output — treat as failed
                        _harness_log.warning(
                            f"[Harness] Step {active_step['key']} session completed but has NO meaningful output — "
                            f"treating as failed (LLM may have returned empty/error response)"
                        )
                        sess_status = "failed"
                        session["status"] = "failed"

                if sess_status == "failed":
                    active_step["status"] = "failed"
                    _harness_log.warning(
                        f"[Harness] Step {active_step['key']} failed after "
                        f"{retry_count + 1} attempts, skipping to next"
                    )
                    # Write failure handoff
                    _write_handoff(task_id, f"{active_step['key']}_FAILED", {
                        "step": active_step["key"],
                        "retries": retry_count + 1,
                        "error": session.get("error", "unknown"),
                        "output_lines": len(list(session.get("lines", []))),
                    }, from_agent=active_step.get("agent_id", ""),
                       to_agent="(next step)")
                    _emit_pipeline_event(task_id, "step_failed", {
                        "step": active_step["key"],
                        "label": active_step.get("label", ""),
                        "error": str(session.get("error", "unknown"))[:200],
                    })

                if sess_status == "completed":
                    active_step["status"] = "completed"
                    _emit_pipeline_event(task_id, "step_completed", {
                        "step": active_step["key"],
                        "label": active_step.get("label", ""),
                    })
                    # Build structured handoff payload with summary data
                    _handoff_payload = {
                        "step": active_step["key"],
                        "label": active_step.get("label", ""),
                        "agent_role": active_step.get("agent_role", ""),
                        "status": "completed",
                        "artifact": active_step.get("artifact", ""),
                    }
                    # Include structured summary if available
                    _step_sum = active_step.get("_summary", {})
                    if _step_sum:
                        _handoff_payload["decisions"] = _step_sum.get("decisions", [])
                        _handoff_payload["files_changed"] = _step_sum.get("files_changed", [])
                        # develop→test: include verification checklist
                        if active_step["key"] == "develop":
                            _handoff_payload["verify_checklist"] = _step_sum.get("verify_checklist", [])
                            _handoff_payload["smoke"] = _step_sum.get("smoke", {})
                        # test→deploy: include verdict and blockers
                        elif active_step["key"] == "test":
                            _handoff_payload["verdict"] = _step_sum.get("verdict", "UNKNOWN")
                            _handoff_payload["checklist"] = _step_sum.get("checklist", [])
                    else:
                        _handoff_payload["output_summary"] = "".join(
                            list(session.get("lines", []))[-20:]
                        )[:2000]
                    _write_handoff(task_id, active_step["key"], _handoff_payload,
                        from_agent=active_step.get("agent_id", ""),
                       to_agent=wf[active_step["index"] + 1]["agent_id"] if active_step["index"] + 1 < len(wf) else "(end)")

                # Auto-advance to next step
                active_idx = active_step["index"]
                if active_idx + 1 < len(wf):
                    next_step = wf[active_idx + 1]
                    next_step["status"] = "active"

                    # Token Factory check before starting next Claude session
                    # If direct DeepSeek API is available, skip TF entirely
                    _ds_key, _, _ = _get_deepseek_credentials()
                    if _ds_key:
                        tf_ok = True
                        _harness_log.info("[Harness] Direct DeepSeek API available — skipping Token Factory check")
                    else:
                        tf_ok = False
                        try:
                            import http.client
                            hconn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=10)
                            hconn.request("GET", "/api/v1/token-factory/health")
                            hresp = hconn.getresponse()
                            import json as _jj
                            hdata = _jj.loads(hresp.read().decode())
                            hconn.close()
                            tf_ok = hdata.get("ready", False)
                        except Exception as e:
                            _harness_log.warning(f"[Harness] Token Factory check failed: {e}")
                            tf_ok = True  # Optimistic fallback
                            _harness_log.info("[Harness] Proceeding optimistically")

                    if not tf_ok:
                        _harness_log.warning(
                            f"[Harness] Token Factory NOT ready for step "
                            f"{next_step['key']} — will retry next poll cycle"
                        )
                        next_step["status"] = "pending"
                        next_step["_blocked_reason"] = "Token Factory not ready"
                        task.metadata["workflow"] = wf
                        continue  # Retry on next poll instead of killing the monitor

                    # 协作拓扑：步骤交接门禁（同队/共总线/门禁边）
                    _from_aid = str(active_step.get("agent_id") or "")
                    _to_aid = str(next_step.get("agent_id") or "")
                    _hgate = _workflow_handoff_gate(
                        team_id, _from_aid, _to_aid, log_prefix="harness_handoff",
                    )
                    if not _hgate.get("allowed"):
                        _harness_log.warning(
                            f"[Harness] Handoff denied {_from_aid}→{_to_aid}: "
                            f"{_hgate.get('reason')} — step {next_step['key']} blocked"
                        )
                        next_step["status"] = "failed"
                        next_step["error"] = f"collab_handoff_denied:{_hgate.get('reason')}"
                        next_step["_blocked_reason"] = "collab_topology"
                        task.metadata["workflow"] = wf
                        continue
                    next_step["collab_handoff"] = {
                        "from": _from_aid,
                        "to": _to_aid,
                        "path": _hgate.get("reason"),
                        "layers": _hgate.get("layers") or [],
                        "warning": _hgate.get("warning"),
                    }

                    # Start Claude for next step
                    if next_step.get("agent_id"):
                        import uuid as _uuid
                        sr = _sr()
                        skill = sr.get_by_slug("code_implementation")
                        cfg = dict(skill.config or {}) if skill else {}
                        tm = _tm()
                        agent = tm.get_agent(team_id, next_step["agent_id"])
                        if agent:
                            new_sid = str(_uuid.uuid4())[:12]
                            try:
                                step_prompt = _build_step_prompt(task, next_step, wf)
                                _harness_log.info(
                                    f"[Harness] Auto-advancing: step {active_step['key']} → "
                                    f"{next_step['key']} (agent: {agent.name}, session: {new_sid}, "
                                    f"collab={_hgate.get('reason')})"
                                )
                                _emit_pipeline_event(task_id, "step_started", {
                                    "step": next_step["key"],
                                    "label": next_step.get("label", ""),
                                    "agent": agent.name,
                                    "prev_step": active_step["key"],
                                    "collab_path": _hgate.get("reason"),
                                })
                                _start_claude_session(
                                    new_sid, step_prompt, cfg, agent, task_id, team_id=team_id,
                                )
                                next_step["session_id"] = new_sid
                            except Exception as start_err:
                                _harness_log.exception(
                                    f"[Harness] Failed to start session for step "
                                    f"{next_step['key']}: {start_err}"
                                )
                                next_step["status"] = "failed"
                                next_step["error"] = f"session start failed: {start_err}"
                        else:
                            _harness_log.warning(
                                f"[Harness] Agent '{next_step['agent_id']}' not found in team "
                                f"'{team_id}' — skipping step {next_step['key']}"
                            )
                            next_step["status"] = "failed"
                            next_step["error"] = f"Agent {next_step['agent_id']} not found"
                    else:
                        _harness_log.warning(
                            f"[Harness] Step {next_step['key']} has no agent_id — skipping"
                        )
                        next_step["status"] = "skipped"

                    task.metadata["workflow"] = wf
                else:
                    # All steps done — validate before marking task complete
                    completed_count = sum(1 for s in wf if s["status"] == "completed")
                    failed_count = sum(1 for s in wf if s["status"] == "failed")
                    task.metadata["workflow"] = wf

                    # Write final summary handoff
                    _write_handoff(task_id, "pipeline_complete", {
                        "total_steps": len(wf),
                        "completed": completed_count,
                        "failed": failed_count,
                        "steps": [{
                            "key": s["key"],
                            "status": s["status"],
                            "artifact": s.get("artifact", ""),
                        } for s in wf],
                    })
                    _emit_pipeline_event(task_id, "pipeline_complete", {
                        "completed": completed_count, "failed": failed_count,
                        "steps": [{"key": s["key"], "status": s["status"]} for s in wf],
                    })

                    _harness_log.info(
                        f"[Harness] Pipeline complete for task {task_id}: "
                        f"{completed_count}/{len(wf)} succeeded, {failed_count} failed"
                    )
                    # Auto-complete the task (from sync thread, schedule on event loop)
                    try:
                        import asyncio
                        engine = _te()
                        # Try to find a running event loop for async completion
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            loop = None
                        if loop and loop.is_running():
                            future = asyncio.run_coroutine_threadsafe(
                                engine.complete_task(task_id), loop
                            )
                            future.result(timeout=5)
                            _harness_log.info(f"[Harness] Task {task_id} auto-completed")
                        else:
                            # Background thread — try HTTP self-call as fallback
                            import http.client
                            hconn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=10)
                            hconn.request("POST",
                                f"/api/v1/agent-config/teams/{team_id}/tasks/{task_id}/complete")
                            hresp = hconn.getresponse()
                            hresp.read()
                            hconn.close()
                            _harness_log.info(f"[Harness] Task {task_id} auto-completed via HTTP ({hresp.status})")
                    except Exception as ex:
                        _harness_log.warning(f"[Harness] Could not auto-complete task: {ex}")
                        # Fallback: directly set status
                        task.status = task.status.__class__("completed")
                    break

        except Exception as ex:
            _harness_log.exception(f"[Harness] Error monitoring task {task_id}: {ex}")
            continue

    # Cleanup
    _harness_threads.pop(task_id, None)
    _harness_log.info(f"[Harness] Monitor stopped for task {task_id}")


def _start_harness_monitor(task_id: str, team_id: str) -> None:
    """Start a harness monitor thread for a task (if not already running)."""
    if task_id in _harness_threads:
        return
    t = threading.Thread(target=_harness_monitor, args=(task_id, team_id), daemon=True)
    _harness_threads[task_id] = t
    t.start()

# ── Artifact directory for inter-step .md handoffs ──
_ARTIFACT_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "docs", "workflow_artifacts"
)
_os.makedirs(_ARTIFACT_DIR, exist_ok=True)

# ── Handoff directory for inter-agent communication ──
_HANDOFF_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "docs", "agent_handoffs"
)
_os.makedirs(_HANDOFF_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# Pipeline Workspace — Shared directory for inter-agent deliverables
# ══════════════════════════════════════════════════════════════════
#
# Architecture: FULL-TEAM SHARED per pipeline run
#
#   storage/pipeline_runs/{task_id}/
#   ├── _context/                    # Pre-seeded project context
#   │   ├── file_tree.txt           # `find src/ -type f` listing
#   │   └── target_files/           # Actual file contents matching task
#   ├── 01_pm_decompose.md          # Step artifacts (numbered for order)
#   ├── 02_research.md
#   ├── ...
#   ├── 04_develop/
#   │   ├── summary.md              # LLM prose output
#   │   └── code/                   # Extracted code files
#   │       └── src/frontend/...    # Mirrors project tree
#   └── 06_deploy/
#       ├── summary.md
#       └── code/                   # Blue-green new files
#
# Why full-team shared (not upstream-only):
#   - Deployer needs Developer's code + PM's plan
#   - Tester needs Architecture spec + Developer code
#   - Simpler, fewer failure modes
#   - _context/ pre-seeds project knowledge for text-only LLMs

_PIPELINE_RUNS_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.abspath(__file__))))),
    "storage", "pipeline_runs"
)
_os.makedirs(_PIPELINE_RUNS_DIR, exist_ok=True)

_STEP_INDEX = {
    "pm_decompose": "01", "research": "02", "architecture": "03",
    "develop": "04", "test": "05", "deploy": "06", "document": "07",
}

# Steps whose output may contain code deliverables
_CODE_STEPS = frozenset({"develop", "deploy"})


def _pipeline_dir(task_id: str) -> str:
    """Return (and create) the shared pipeline workspace directory for a task."""
    safe_tid = task_id.replace("/", "_")[:60]
    d = _os.path.join(_PIPELINE_RUNS_DIR, safe_tid)
    _os.makedirs(d, exist_ok=True)
    return d


def _pipeline_context_dir(task_id: str) -> str:
    """Return _context/ subdir inside the pipeline workspace."""
    d = _os.path.join(_pipeline_dir(task_id), "_context")
    _os.makedirs(d, exist_ok=True)
    return d


def _seed_project_context(task_id: str, task_title: str, task_description: str) -> str:
    """Pre-seed the pipeline workspace with project context.

    Since DeepSeek text-only agents CANNOT read the filesystem, we proactively
    scan the project for files relevant to the task and include their contents.

    Returns the path to the context directory.
    """
    ctx_dir = _pipeline_context_dir(task_id)
    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.abspath(__file__)))))

    # ── 1. Generate file tree ──
    tree_path = _os.path.join(ctx_dir, "file_tree.txt")
    if not _os.path.exists(tree_path):
        tree_lines = []
        for dirpath, dirnames, filenames in _os.walk(project_root):
            # Skip non-source directories
            rel_dir = _os.path.relpath(dirpath, project_root)
            skip_prefixes = ("venv", "node_modules", ".git", "__pycache__",
                             "storage", ".pytest_cache", "logs", "reports")
            if any(rel_dir == s or rel_dir.startswith(s + _os.sep) for s in skip_prefixes):
                dirnames.clear()
                continue
            for fn in sorted(filenames):
                if fn.startswith(".") or fn.endswith((".pyc", ".pyo")):
                    continue
                rel = _os.path.join(rel_dir, fn) if rel_dir != "." else fn
                tree_lines.append(rel)
        with open(tree_path, "w", encoding="utf-8") as f:
            f.write("\n".join(tree_lines[:5000]) + "\n")
        _harness_log.info("[Pipeline] File tree: %d entries → %s", len(tree_lines), tree_path)

    # ── 2. Search for task-relevant files ──
    target_dir = _os.path.join(ctx_dir, "target_files")
    _os.makedirs(target_dir, exist_ok=True)

    # Extract keywords from task title + description
    search_text = f"{task_title} {task_description or ''}"
    # Common keyword extraction (Chinese + English significant words)
    import re as _re
    # Chinese: extract meaningful 2+ char segments between punctuation
    cn_words = _re.findall(r'[\u4e00-\u9fff]{2,6}', search_text)
    # English: extract words 3+ chars
    en_words = _re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', search_text)
    keywords = set(w.lower() for w in en_words if w.lower() not in {
        "the", "and", "for", "from", "with", "that", "this", "html", "page",
        "system", "build", "team", "task", "please", "file",
    })
    keywords.update(cn_words)

    # Also look for file path hints in the task text
    path_hints = _re.findall(r'[a-zA-Z0-9_/-]+\.\w{1,6}', search_text)
    for ph in path_hints:
        keywords.add(ph)

    # Chinese concept → filename mapping (common domain-specific translations)
    _CN_FILE_MAP = {
        "健康": ["health", "cms-health", "cms"],
        "设备": ["device", "cms", "equipment"],
        "推进": ["thruster", "propulsion", "tcs"],
        "导航": ["navigation", "nav"],
        "舵": ["rudder", "steering"],
        "数字孪生": ["digital-twin", "twin"],
        "驾驶台": ["bridge", "hmi", "openbridge"],
        "报警": ["alarm", "alert"],
        "机舱": ["engine", "intelligent-engine", "machinery"],
        "避碰": ["colreg", "collision"],
        "海图": ["chart", "map", "worldmonitor"],
        "货物": ["cargo"],
        "消防": ["fire"],
        "压载": ["ballast"],
        "通信": ["comm", "vdes"],
        "气象": ["weather", "meteo"],
        "状态": ["status", "health", "monitor"],
        "控制": ["control"],
    }
    for cn_kw in cn_words:
        for cn_key, en_vals in _CN_FILE_MAP.items():
            if cn_key in cn_kw:
                keywords.update(en_vals)

    _harness_log.info("[Pipeline] Context seeding keywords: %s", keywords)

    # Search source files for keyword matches
    _SEARCH_DIRS = ["src/frontend", "src/backend/channels", "src/backend"]
    _MAX_FILES = 10  # Don't overload the prompt
    _MAX_FILE_SIZE = 30_000  # chars per file
    _CONTENT_SCAN_SIZE = 15_000  # chars to scan for content matching

    matched_files: list = []
    for search_dir in _SEARCH_DIRS:
        abs_dir = _os.path.join(project_root, search_dir)
        if not _os.path.isdir(abs_dir):
            continue
        for dirpath, _, filenames in _os.walk(abs_dir):
            for fn in filenames:
                if not fn.endswith((".html", ".py", ".js", ".css", ".json", ".mjs")):
                    continue
                rel = _os.path.relpath(_os.path.join(dirpath, fn), project_root)
                abs_path = _os.path.join(dirpath, fn)

                # Score: how many keywords match the filename or path?
                score = 0
                lower_rel = rel.lower().replace("-", " ").replace("_", " ")
                lower_fn = fn.lower().replace("-", " ").replace("_", " ")
                for kw in keywords:
                    kw_lower = kw.lower().replace("-", " ").replace("_", " ")
                    if kw_lower in lower_rel or kw_lower in lower_fn:
                        score += 3  # Path match is strong signal
                # Also check file content for keyword matches
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        head = f.read(_CONTENT_SCAN_SIZE)
                    for kw in keywords:
                        if kw in head or kw.lower() in head.lower():
                            score += 1
                except Exception:
                    pass

                if score > 0:
                    matched_files.append((score, rel, abs_path))

    # Sort by relevance, take top N
    matched_files.sort(key=lambda x: -x[0])
    seeded_files = []
    for score, rel, abs_path in matched_files[:_MAX_FILES]:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(_MAX_FILE_SIZE)
            # Save to target_files/ preserving relative path
            dest = _os.path.join(target_dir, rel)
            _os.makedirs(_os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content)
            seeded_files.append(rel)
            _harness_log.info("[Pipeline] Seeded: %s (score=%d, %d chars)", rel, score, len(content))
        except Exception as e:
            _harness_log.warning("[Pipeline] Failed to seed %s: %s", rel, e)

    # Write a manifest
    manifest_path = _os.path.join(ctx_dir, "_manifest.md")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(f"# Pipeline Context — {task_title}\n\n")
        f.write(f"Task ID: {task_id}\n")
        f.write(f"Keywords: {', '.join(sorted(keywords))}\n")
        f.write(f"Seeded files: {len(seeded_files)}\n\n")
        for sf in seeded_files:
            f.write(f"- `{sf}`\n")

    _harness_log.info("[Pipeline] Context seeded: %d files for task %s", len(seeded_files), task_id)
    return ctx_dir


def _get_pipeline_context_for_prompt(task_id: str) -> str:
    """Build a context string from the pipeline's _context/ dir for inclusion in prompts.

    Returns a formatted string with file tree + relevant file contents.
    Budget: ~60K chars max to leave room for task prompt + prior steps.
    """
    _MAX_CONTEXT_CHARS = 60_000
    _MAX_PER_FILE = 15_000

    ctx_dir = _pipeline_context_dir(task_id)
    parts = []
    total = 0

    # File tree (truncated)
    tree_path = _os.path.join(ctx_dir, "file_tree.txt")
    if _os.path.isfile(tree_path):
        with open(tree_path, "r", encoding="utf-8") as f:
            tree = f.read()
        lines = tree.strip().split("\n")
        # Filter to src/ only for relevance
        src_lines = [l for l in lines if l.startswith("src/")]
        if len(src_lines) > 150:
            tree = "\n".join(src_lines[:150]) + f"\n... (共 {len(src_lines)} 个 src/ 文件)\n"
        else:
            tree = "\n".join(src_lines)
        chunk = f"### 项目文件结构 (src/ 目录)\n```\n{tree}\n```\n"
        parts.append(chunk)
        total += len(chunk)

    # Target files
    target_dir = _os.path.join(ctx_dir, "target_files")
    if _os.path.isdir(target_dir):
        for dirpath, _, filenames in _os.walk(target_dir):
            if total >= _MAX_CONTEXT_CHARS:
                parts.append("(后续文件因 token 预算已省略)\n")
                break
            for fn in sorted(filenames):
                if total >= _MAX_CONTEXT_CHARS:
                    break
                abs_path = _os.path.join(dirpath, fn)
                rel = _os.path.relpath(abs_path, target_dir)
                try:
                    remaining = _MAX_CONTEXT_CHARS - total
                    read_limit = min(_MAX_PER_FILE, remaining - 200)
                    if read_limit < 500:
                        parts.append("(后续文件因 token 预算已省略)\n")
                        break
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(read_limit)
                    ext = _os.path.splitext(fn)[1].lstrip(".")
                    chunk = f"### 文件: `{rel}`\n```{ext}\n{content}\n```\n"
                    parts.append(chunk)
                    total += len(chunk)
                except Exception:
                    pass

    if not parts:
        return ""
    return "## 📂 项目上下文 (系统自动预加载)\n\n" + "\n".join(parts) + "\n"


def _save_step_to_pipeline(task_id: str, step_key: str, content: str,
                            deliverables: list = None) -> str:
    """Save a step's output to the shared pipeline workspace.

    For regular steps: saves as NN_stepkey.md
    For code steps: also saves extracted code under NN_stepkey/code/

    Returns the path of the saved summary file.
    """
    pdir = _pipeline_dir(task_id)
    idx = _STEP_INDEX.get(step_key, "99")

    if step_key in _CODE_STEPS and deliverables:
        # Code step: create subdirectory with summary + code files
        step_dir = _os.path.join(pdir, f"{idx}_{step_key}")
        _os.makedirs(step_dir, exist_ok=True)

        summary_path = _os.path.join(step_dir, "summary.md")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Save extracted code files
        code_dir = _os.path.join(step_dir, "code")
        _os.makedirs(code_dir, exist_ok=True)
        for d in deliverables:
            file_path = _os.path.join(code_dir, d["path"])
            _os.makedirs(_os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(d["content"])
            _harness_log.info("[Pipeline] Code saved: %s (%d chars)", d["path"], len(d["content"]))

        _auto_ingest_step_to_kb(task_id, step_key, content, deliverables)
        return summary_path
    else:
        # Text-only step: save as single .md file
        out_path = _os.path.join(pdir, f"{idx}_{step_key}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        _harness_log.info("[Pipeline] Step artifact: %s (%d chars)", out_path, len(content))
        _auto_ingest_step_to_kb(task_id, step_key, content, deliverables)
        return out_path


# ── Step Summary Extraction ─────────────────────────────────────
# After each step completes, extract a structured summary (decisions,
# conclusions, file changes, checklist) so downstream agents receive
# compressed context instead of raw LLM dumps.

def _extract_step_summary(task_id: str, step_key: str, raw_text: str,
                           deliverables: list = None,
                           smoke_results: list = None) -> Dict[str, Any]:
    """Extract a structured summary from a completed step's raw output.

    Produces a JSON summary saved as NN_stepkey_summary.json in the pipeline
    workspace. Downstream agents read these summaries instead of raw artifacts,
    keeping the context window compact and signal-rich.

    Returns the summary dict.
    """
    import re as _re_s
    import json as _json_s

    summary: Dict[str, Any] = {
        "step": step_key,
        "task_id": task_id,
        "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "char_count": len(raw_text),
    }

    # ── Extract key decisions / conclusions ──
    # Look for markdown headings containing decision/conclusion keywords
    decisions = []
    conclusion_patterns = [
        _re_s.compile(r"^#{1,3}\s*(?:结论|决定|方案|建议|结果|验证结论|总结|Summary|Conclusion|Decision|Result)[^\n]*\n([\s\S]*?)(?=^#{1,3}\s|\Z)", _re_s.MULTILINE),
        _re_s.compile(r"^(?:[-*]\s*)?(?:结论|决策|方案选择|最终方案)[：:]\s*(.+)$", _re_s.MULTILINE),
    ]
    for pat in conclusion_patterns:
        for m in pat.finditer(raw_text):
            text = m.group(1).strip()[:1500]
            if text and len(text) > 10:
                decisions.append(text)
    summary["decisions"] = decisions[:5]  # Cap at 5 key decisions

    # ── Extract file change list (for develop/deploy steps) ──
    files_changed = []
    if deliverables:
        files_changed = [d["path"] for d in deliverables]
    else:
        # Try to parse from text: look for file paths in bullet lists
        file_path_re = _re_s.compile(
            r"[-*]\s*`?(src/[^\s`]+\.\w{1,6})`?", _re_s.MULTILINE
        )
        files_changed = list(set(m.group(1) for m in file_path_re.finditer(raw_text)))
    summary["files_changed"] = files_changed[:30]

    # ── Extract verification checklist (for test/QA steps) ──
    if step_key == "test":
        checklist = []
        # Parse PASS/FAIL verdict
        verdict_match = _re_s.search(
            r"验证结论\s*(PASS|FAIL|pass|fail)", raw_text, _re_s.IGNORECASE
        )
        summary["verdict"] = verdict_match.group(1).upper() if verdict_match else "UNKNOWN"

        # Parse BLOCKER items
        blocker_re = _re_s.compile(
            r"(?:BLOCKER|blocker|阻塞)[：:\s]+(.+?)(?:\n|$)", _re_s.MULTILINE
        )
        for m in blocker_re.finditer(raw_text):
            checklist.append({"severity": "BLOCKER", "detail": m.group(1).strip()[:300]})

        # Parse import/test failures
        fail_re = _re_s.compile(
            r"(?:❌|FAILED|FAIL|失败)[：:\s]+(.+?)(?:\n|$)", _re_s.MULTILINE
        )
        for m in fail_re.finditer(raw_text):
            detail = m.group(1).strip()[:300]
            if detail and detail not in [c["detail"] for c in checklist]:
                checklist.append({"severity": "FAIL", "detail": detail})

        summary["checklist"] = checklist[:20]

    # ── Smoke test results ──
    if smoke_results:
        smoke_fails = [s for s in smoke_results if not s.get("syntax_ok")]
        summary["smoke"] = {
            "total": len(smoke_results),
            "passed": len(smoke_results) - len(smoke_fails),
            "failed": len(smoke_fails),
            "failures": [
                {"path": s["path"], "errors": s.get("errors", [])}
                for s in smoke_fails
            ],
        }

    # ── Role-specific summaries ──
    if step_key == "pm_decompose":
        # Extract task decomposition items
        task_items = _re_s.findall(
            r"^(?:[-*]|\d+[.)]\s)\s*(.{10,200})$", raw_text, _re_s.MULTILINE
        )
        summary["subtasks"] = task_items[:15]

    elif step_key == "research":
        # Extract key findings
        findings = _re_s.findall(
            r"^(?:[-*])\s*(?:发现|建议|注意|关键|Finding|Key)[：:\s]+(.+)$",
            raw_text, _re_s.MULTILINE
        )
        summary["findings"] = [f.strip()[:300] for f in findings[:10]]

    elif step_key == "architecture":
        # Extract interface definitions / API specs
        api_specs = _re_s.findall(
            r"(?:接口|API|endpoint|路由)[：:\s]+(.+?)(?:\n|$)",
            raw_text, _re_s.MULTILINE
        )
        summary["api_specs"] = [a.strip()[:300] for a in api_specs[:10]]

    elif step_key in ("develop", "deploy"):
        # Build a verification checklist for QA
        verify_items = []
        for fp in files_changed:
            if fp.endswith(".py"):
                verify_items.append(f"import check: `{fp}`")
            elif fp.endswith((".html", ".js", ".mjs")):
                verify_items.append(f"load check: `{fp}`")
        summary["verify_checklist"] = verify_items[:20]

    # ── Compact prose summary (first meaningful paragraph, capped) ──
    # Skip code blocks and take first 800 chars of prose
    prose_text = _re_s.sub(r"```[\s\S]*?```", "", raw_text)
    prose_text = _re_s.sub(r"^#+\s.*$", "", prose_text, flags=_re_s.MULTILINE)
    prose_lines = [l.strip() for l in prose_text.split("\n")
                   if l.strip() and len(l.strip()) > 15]
    summary["prose_summary"] = "\n".join(prose_lines[:15])[:2000]

    # ── Persist summary to pipeline workspace ──
    pdir = _pipeline_dir(task_id)
    idx = _STEP_INDEX.get(step_key, "99")
    summary_path = _os.path.join(pdir, f"{idx}_{step_key}_summary.json")
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            _json_s.dump(summary, f, ensure_ascii=False, indent=2)
        _harness_log.info(
            "[Pipeline] Step summary saved: %s (%d decisions, %d files)",
            summary_path, len(summary.get("decisions", [])),
            len(summary.get("files_changed", [])),
        )
    except Exception as e:
        _harness_log.warning("[Pipeline] Summary save failed: %s", e)

    return summary


def _format_step_summary_for_prompt(summary: Dict[str, Any], step_name: str,
                                      step_idx: str) -> str:
    """Format a step summary JSON into a concise prompt section."""
    parts = [f"### 步骤 {step_idx}: {step_name}\n"]

    # Prose summary (compact)
    prose = summary.get("prose_summary", "")
    if prose:
        # Truncate to 1000 chars for non-adjacent steps
        parts.append(prose[:1500] + "\n")

    # Key decisions
    decisions = summary.get("decisions", [])
    if decisions:
        parts.append("**关键决策:**\n")
        for d in decisions[:3]:
            parts.append(f"  - {d[:300]}\n")

    # Files changed
    files = summary.get("files_changed", [])
    if files:
        parts.append(f"**变更文件 ({len(files)}):**\n")
        for fp in files[:15]:
            parts.append(f"  - `{fp}`\n")

    # Subtasks (PM step)
    subtasks = summary.get("subtasks", [])
    if subtasks:
        parts.append("**子任务拆解:**\n")
        for st in subtasks[:8]:
            parts.append(f"  - {st}\n")

    # Findings (research step)
    findings = summary.get("findings", [])
    if findings:
        parts.append("**关键发现:**\n")
        for f in findings[:5]:
            parts.append(f"  - {f}\n")

    # API specs (architecture step)
    specs = summary.get("api_specs", [])
    if specs:
        parts.append("**接口规范:**\n")
        for s in specs[:5]:
            parts.append(f"  - {s}\n")

    # Verify checklist (develop step → for QA)
    verify = summary.get("verify_checklist", [])
    if verify:
        parts.append("**待验证清单 (QA 必检):**\n")
        for v in verify[:15]:
            parts.append(f"  - [ ] {v}\n")

    # QA verdict + checklist (test step)
    verdict = summary.get("verdict")
    if verdict:
        parts.append(f"**QA 验证结论: {verdict}**\n")
    checklist = summary.get("checklist", [])
    if checklist:
        for c in checklist[:10]:
            parts.append(f"  - [{c['severity']}] {c['detail']}\n")

    # Smoke results
    smoke = summary.get("smoke")
    if smoke:
        parts.append(
            f"**冒烟测试:** {smoke['passed']}/{smoke['total']} 通过\n"
        )
        for sf in smoke.get("failures", [])[:5]:
            parts.append(f"  🔥 `{sf['path']}`: {'; '.join(sf['errors'][:2])}\n")

    parts.append("\n")
    return "".join(parts)


def _get_prior_steps_from_pipeline(task_id: str, current_step_key: str) -> str:
    """Build context from prior steps using incremental summaries.

    Strategy:
    - For N-1 (immediately prior step): include FULL raw output (up to budget)
    - For N-2 and earlier: use compressed summaries from _summary.json
    - This ensures the immediately relevant context is rich while older context
      is compact, keeping total token usage manageable.

    XC-2.2: 优先注入 MANIFEST 摘要 + 文件路径清单，Agent 通过 read_file 按需读取。
    MANIFEST 缺失时回退到现行全文/摘要交接（灰度可逆）。
    """
    pdir = _pipeline_dir(task_id)
    current_idx = _STEP_INDEX.get(current_step_key, "99")

    # XC-2.2: MANIFEST 摘要注入（优先）
    manifest_path = _os.path.join(pdir, "MANIFEST.json")
    if _os.path.isfile(manifest_path):
        try:
            import json as _json_m
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = _json_m.load(f)
            if isinstance(manifest, list) and manifest:
                parts_mf = [
                    "## 📁 工作区产物清单（MANIFEST）\n",
                    "上游步骤产物已落盘到工作区，请用 `read_file` / `list_files` 按需读取：\n\n",
                ]
                for entry in manifest:
                    step = entry.get("step", "?")
                    summary = entry.get("summary", "")
                    files = entry.get("files", [])
                    parts_mf.append(f"### {step} — {summary}\n")
                    for finfo in files:
                        fpath = finfo.get("path", "")
                        fsummary = finfo.get("summary", "")
                        # 显示相对工作区的路径
                        rel = _os.path.relpath(fpath, pdir) if _os.path.isabs(fpath) else fpath
                        parts_mf.append(f"- `{rel}` ({fsummary})\n")
                    parts_mf.append("\n")
                parts_mf.append(
                    "提示：直接读取上述文件获取完整内容，避免上下文过载。\n\n"
                )
                return "".join(parts_mf)
        except Exception:
            pass  # MANIFEST 读取失败，回退到全文交接

    parts = []
    _MAX_FULL_STEP = 40_000    # Budget for the immediately prior step (full text)
    _MAX_SUMMARY_STEP = 4_000  # Budget per older step (summary only)
    _MAX_TOTAL = 80_000        # Total budget (down from 150K raw dumps)
    total_chars = 0

    # Collect all prior step entries
    entries = sorted(_os.listdir(pdir))
    prior_entries = []
    for entry in entries:
        if entry.startswith("_") or entry.endswith("_summary.json") or entry.endswith("_tool_trace.json"):
            continue
        entry_idx = entry[:2] if len(entry) > 2 and entry[2] == "_" else ""
        if not entry_idx or entry_idx >= current_idx:
            continue
        prior_entries.append((entry_idx, entry))

    if not prior_entries:
        return ""

    # The last entry is the immediately prior step — gets full text
    immediately_prior_idx = prior_entries[-1][0]

    for entry_idx, entry in prior_entries:
        if total_chars >= _MAX_TOTAL:
            parts.append("(后续步骤产出因 token 预算已省略)\n")
            break

        abs_entry = _os.path.join(pdir, entry)
        step_name = entry[3:] if len(entry) > 3 else entry
        # Strip .md extension from step_name for display
        if step_name.endswith(".md"):
            step_name = step_name[:-3]

        is_immediately_prior = (entry_idx == immediately_prior_idx)

        # ── Try summary first (for non-adjacent steps) ──
        if not is_immediately_prior:
            summary_path = _os.path.join(pdir, f"{entry_idx}_{step_name}_summary.json")
            if _os.path.isfile(summary_path):
                try:
                    import json as _json_r
                    with open(summary_path, "r", encoding="utf-8") as f:
                        summary = _json_r.load(f)
                    chunk = _format_step_summary_for_prompt(summary, step_name, entry_idx)
                    if len(chunk) > _MAX_SUMMARY_STEP:
                        chunk = chunk[:_MAX_SUMMARY_STEP] + "\n...(摘要截断)\n"
                    total_chars += len(chunk)
                    parts.append(chunk)
                    continue  # Summary found, skip raw text
                except Exception:
                    pass  # Fall through to raw text

        # ── Full text for immediately prior step, or fallback for older steps ──
        budget = _MAX_FULL_STEP if is_immediately_prior else _MAX_SUMMARY_STEP
        remaining = _MAX_TOTAL - total_chars
        budget = min(budget, remaining)
        if budget < 200:
            parts.append("(后续步骤产出因 token 预算已省略)\n")
            break

        if _os.path.isfile(abs_entry) and entry.endswith(".md"):
            try:
                with open(abs_entry, "r", encoding="utf-8") as f:
                    content = f.read(budget)
                if len(content) >= budget:
                    content = content[:budget] + "\n...(截断)\n"
                total_chars += len(content)
                label = "(完整产出)" if is_immediately_prior else "(摘要不可用，使用原文)"
                parts.append(f"### 步骤 {entry_idx}: {step_name} {label}\n\n{content}\n")
            except Exception:
                pass

        elif _os.path.isdir(abs_entry):
            # Code step with subdirectory
            step_parts = []

            # Summary.md (the LLM prose)
            summary_md = _os.path.join(abs_entry, "summary.md")
            if _os.path.isfile(summary_md):
                try:
                    with open(summary_md, "r", encoding="utf-8") as f:
                        summary = f.read(budget)
                    if len(summary) >= budget:
                        summary = summary[:budget] + "\n...(截断)\n"
                    label = "(完整产出)" if is_immediately_prior else ""
                    step_parts.append(f"### 步骤 {entry_idx}: {step_name} {label}\n\n{summary}\n")
                    total_chars += len(summary)
                except Exception:
                    pass

            # Code deliverables list (always include, compact)
            code_dir = _os.path.join(abs_entry, "code")
            if _os.path.isdir(code_dir):
                code_files = []
                for dp, _, fns in _os.walk(code_dir):
                    for fn in fns:
                        rel = _os.path.relpath(_os.path.join(dp, fn), code_dir)
                        code_files.append(rel)
                if code_files:
                    chunk = f"📦 代码交付物 ({len(code_files)} 文件):\n"
                    for cf in code_files:
                        chunk += f"  - `{cf}`\n"
                    chunk += "\n"
                    step_parts.append(chunk)
                    total_chars += len(chunk)

            # Apply / smoke-test report (always include, compact and actionable)
            apply_report = _os.path.join(abs_entry, "apply_report.json")
            if _os.path.isfile(apply_report):
                try:
                    import json as _json_ar
                    with open(apply_report, "r", encoding="utf-8") as f:
                        rep = _json_ar.load(f)
                    chunk = "🔬 自动落地与冒烟测试结果:\n"
                    chunk += (f"  applied: {len(rep.get('applied', []))} / "
                              f"skipped: {len(rep.get('skipped', []))} / "
                              f"failed: {len(rep.get('failed', []))}\n")
                    for sk in rep.get("skipped", []):
                        chunk += f"  ⚠️ skipped {sk['path']}: {sk.get('reason','')}\n"
                    for fl in rep.get("failed", []):
                        chunk += f"  ❌ failed {fl['path']}: {fl.get('error','')}\n"
                    for sm in rep.get("smoke", []):
                        if not sm.get("syntax_ok"):
                            chunk += (f"  🔥 smoke FAIL {sm['path']}: "
                                      f"{'; '.join(sm.get('errors', []))}\n")
                    chunk += "\n"
                    step_parts.append(chunk)
                    total_chars += len(chunk)
                except Exception:
                    pass

            parts.extend(step_parts)

    if not parts:
        return ""
    return "## 前序步骤的产出 (递进式摘要)\n\n" + "".join(parts)


def _smoke_check_pipeline_code(task_id: str, step_key: str) -> List[Dict[str, Any]]:
    """Run syntax & basic import checks on staged code in the pipeline workspace.

    Operates on storage/pipeline_runs/{task_id}/{idx}_{step_key}/code/ WITHOUT
    copying into the project. Used after develop saves so QA gets concrete signal.

    Also persists apply_report.json (just the smoke section) for prompt context.
    """
    pdir = _pipeline_dir(task_id)
    idx = _STEP_INDEX.get(step_key, "99")
    step_dir = _os.path.join(pdir, f"{idx}_{step_key}")
    code_dir = _os.path.join(step_dir, "code")
    smoke: List[Dict[str, Any]] = []
    if not _os.path.isdir(code_dir):
        return smoke

    for dirpath, _, filenames in _os.walk(code_dir):
        for fn in filenames:
            abs_src = _os.path.join(dirpath, fn)
            rel = _os.path.relpath(abs_src, code_dir)
            check = {"path": rel, "syntax_ok": True, "errors": []}

            try:
                src = open(abs_src, "r", encoding="utf-8").read()
            except Exception as e:
                check["syntax_ok"] = False
                check["errors"].append(f"read error: {e}")
                smoke.append(check)
                continue

            if rel.endswith(".py"):
                import ast as _ast
                try:
                    _ast.parse(src, filename=abs_src)
                except SyntaxError as e:
                    check["syntax_ok"] = False
                    check["errors"].append(f"SyntaxError L{e.lineno}: {e.msg}")
                if check["syntax_ok"] and "/channels/" in rel:
                    import importlib.util as _ilu
                    mod_name = "_smoke_" + _os.path.splitext(_os.path.basename(rel))[0]
                    try:
                        spec = _ilu.spec_from_file_location(mod_name, abs_src)
                        if spec and spec.loader:
                            mod = _ilu.module_from_spec(spec)
                            spec.loader.exec_module(mod)
                    except Exception as e:
                        check["syntax_ok"] = False
                        check["errors"].append(
                            f"ImportError: {type(e).__name__}: {str(e)[:200]}"
                        )

            elif rel.endswith((".js", ".mjs")):
                if src.count("{") != src.count("}"):
                    check["syntax_ok"] = False
                    check["errors"].append(
                        f"brace mismatch: {{{src.count('{')} vs }}{src.count('}')}"
                    )
                if src.count("(") != src.count(")"):
                    check["syntax_ok"] = False
                    check["errors"].append(
                        f"paren mismatch: ({src.count('(')} vs ){src.count(')')}"
                    )

            if not check["syntax_ok"]:
                _harness_log.warning("[Smoke] FAIL %s: %s", rel, "; ".join(check["errors"]))
            smoke.append(check)

    # Persist as apply_report.json (so prompt context picks it up)
    try:
        report_path = _os.path.join(step_dir, "apply_report.json")
        # If file already exists (e.g. deploy already ran), merge smoke section
        existing = {}
        if _os.path.isfile(report_path):
            try:
                import json as _json
                with open(report_path, "r", encoding="utf-8") as f:
                    existing = _json.load(f)
            except Exception:
                existing = {}
        existing.setdefault("applied", [])
        existing.setdefault("skipped", [])
        existing.setdefault("failed", [])
        existing["smoke"] = smoke
        import json as _json
        with open(report_path, "w", encoding="utf-8") as f:
            _json.dump(existing, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return smoke


def _apply_code_from_pipeline(task_id: str, step_key: str) -> Dict[str, Any]:
    """Apply code deliverables from a pipeline step to the actual project.

    Reads from: storage/pipeline_runs/{task_id}/{idx}_{step_key}/code/
    Writes to:  project root (with backup + safety checks)

    Returns summary dict.
    """
    pdir = _pipeline_dir(task_id)
    idx = _STEP_INDEX.get(step_key, "99")
    code_dir = _os.path.join(pdir, f"{idx}_{step_key}", "code")
    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.abspath(__file__)))))

    result = {"applied": [], "skipped": [], "failed": [], "backup": []}

    if not _os.path.isdir(code_dir):
        _harness_log.info("[Pipeline] No code dir for %s step %s", task_id, step_key)
        return result

    _ALLOWED_PREFIXES = ("src/", "tests/", "docs/", "config/", "public/")

    for dirpath, _, filenames in _os.walk(code_dir):
        for fn in filenames:
            abs_src = _os.path.join(dirpath, fn)
            rel = _os.path.relpath(abs_src, code_dir)

            # Safety check
            if not any(rel.startswith(p) for p in _ALLOWED_PREFIXES):
                result["skipped"].append({"path": rel, "reason": "Outside allowed dirs"})
                continue
            if ".." in rel:
                result["skipped"].append({"path": rel, "reason": "Path traversal"})
                continue

            target = _os.path.join(project_root, rel)
            try:
                new_content = open(abs_src, "r", encoding="utf-8").read()

                # Shrink-replace guard: refuse to overwrite an existing file
                # with content that is dramatically smaller (likely an LLM
                # "from scratch" rewrite that drops most of the original).
                # Threshold: new < 50% of existing AND existing > 2KB.
                if _os.path.isfile(target):
                    try:
                        existing_size = _os.path.getsize(target)
                    except OSError:
                        existing_size = 0
                    if existing_size > 2048 and len(new_content) < existing_size * 0.5:
                        result["skipped"].append({
                            "path": rel,
                            "reason": (
                                f"shrink-replace guard: new {len(new_content)}B "
                                f"< 50% of existing {existing_size}B "
                                f"(LLM likely emitted a stub rewrite)"
                            ),
                        })
                        _harness_log.warning(
                            "[Pipeline] SKIP shrink-replace: %s "
                            "(new=%dB existing=%dB)",
                            rel, len(new_content), existing_size,
                        )
                        continue

                # Backup existing file
                if _os.path.isfile(target):
                    import shutil
                    backup = target + ".bak"
                    shutil.copy2(target, backup)
                    result["backup"].append({"path": rel, "backup": backup})

                _os.makedirs(_os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(new_content)
                result["applied"].append({"path": rel, "size": len(new_content)})
                _harness_log.info("[Pipeline] Applied: %s (%d chars)", rel, len(new_content))

            except Exception as e:
                result["failed"].append({"path": rel, "error": str(e)[:200]})
                _harness_log.error("[Pipeline] Failed: %s — %s", rel, e)

    _harness_log.info(
        "[Pipeline] Apply result: %d applied, %d skipped, %d failed",
        len(result["applied"]), len(result["skipped"]), len(result["failed"]),
    )

    # ── Post-apply smoke checks: syntax + import probe ──
    # Provides concrete signal for the QA step instead of LLM rubber-stamping.
    smoke = []
    for entry in result["applied"]:
        rel = entry["path"]
        target = _os.path.join(project_root, rel)
        check = {"path": rel, "syntax_ok": True, "errors": []}

        if rel.endswith(".py"):
            import ast as _ast
            try:
                src = open(target, "r", encoding="utf-8").read()
                _ast.parse(src, filename=target)
            except SyntaxError as e:
                check["syntax_ok"] = False
                check["errors"].append(f"SyntaxError L{e.lineno}: {e.msg}")
            # Best-effort import probe (channels/* only)
            if check["syntax_ok"] and "/channels/" in rel:
                import importlib.util as _ilu
                mod_name = "_smoke_" + _os.path.splitext(_os.path.basename(rel))[0]
                try:
                    spec = _ilu.spec_from_file_location(mod_name, target)
                    if spec and spec.loader:
                        mod = _ilu.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                except Exception as e:
                    check["errors"].append(f"ImportError: {type(e).__name__}: {str(e)[:200]}")

        elif rel.endswith((".js", ".mjs")):
            # Minimal sanity: braces & parens balance
            try:
                src = open(target, "r", encoding="utf-8").read()
                if src.count("{") != src.count("}"):
                    check["errors"].append(
                        f"brace mismatch: {{{src.count('{')} vs }}{src.count('}')}"
                    )
                if src.count("(") != src.count(")"):
                    check["errors"].append(
                        f"paren mismatch: ({src.count('(')} vs ){src.count(')')}"
                    )
            except Exception as e:
                check["errors"].append(f"read error: {e}")

        if check["errors"]:
            check["syntax_ok"] = False
            _harness_log.warning("[Pipeline] Smoke FAIL %s: %s", rel, "; ".join(check["errors"]))
        smoke.append(check)
    result["smoke"] = smoke

    # Persist smoke report next to the code/ dir for QA to consume
    try:
        report_path = _os.path.join(pdir, f"{idx}_{step_key}", "apply_report.json")
        import json as _json
        with open(report_path, "w", encoding="utf-8") as f:
            _json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return result


def _write_handoff(task_id: str, step_key: str, payload: Dict[str, Any],
                    *, from_agent: str = "", to_agent: str = "") -> str:
    """Write a structured handoff Markdown file for inter-agent communication.

    Each pipeline step writes a handoff file when it completes, which the next
    agent reads as context.  The file is stored in docs/agent_handoffs/.

    XC-2.1: 同时写入工作区 handoffs/ 目录（兼容旧位置读）。

    Returns the path of the written file.
    """
    import json as _json
    safe_tid = task_id.replace("/", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    fname = f"{safe_tid}_{step_key}_{ts}.md"
    fpath = _os.path.join(_HANDOFF_DIR, fname)

    lines = [
        f"# Agent Handoff — {step_key}",
        f"",
        f"| 字段 | 值 |",
        f"|------|------|",
        f"| 任务 ID | `{task_id}` |",
        f"| 步骤 | `{step_key}` |",
        f"| 来源 Agent | {from_agent or '(system)'} |",
        f"| 目标 Agent | {to_agent or '(next step)'} |",
        f"| 时间 | {ts} |",
        f"",
        f"## 传递内容",
        f"",
    ]
    for k, v in payload.items():
        if isinstance(v, (dict, list)):
            lines.append(f"### {k}")
            lines.append(f"```json")
            lines.append(_json.dumps(v, ensure_ascii=False, indent=2))
            lines.append(f"```")
            lines.append(f"")
        else:
            lines.append(f"- **{k}**: {v}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"*Auto-generated by AgentsGroup2026 Workflow Harness*")

    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    _harness_log.info(f"[Handoff] Written: {fpath} ({from_agent} → {to_agent})")
    # XC-2.1: 同步写入工作区 handoffs/（兼容旧位置读）
    try:
        ws_handoff = _os.path.join(_pipeline_handoffs_dir(task_id), fname)
        with open(ws_handoff, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
    return fpath


def _validate_session_output(session: Dict[str, Any]) -> bool:
    """Check if a completed session produced meaningful output (not just errors).

    Returns True if the session has real content, False if it's empty/error-only.
    """
    lines = list(session.get("lines", []))
    if not lines:
        return False
    # Filter out framework lines (headers, status markers)
    _NOISE = ("─", "📋", "🤖", "📂", "⏱️", "📝", "⏳", "🔄", "⚠️", "❌", "🔗", "✅")
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(m) for m in _NOISE):
            continue
        if stripped.startswith("  "):  # Prompt echo
            continue
        content_lines.append(stripped)
    # Need at least a few lines of real content
    min_content_lines = 3
    min_content_chars = 50
    total_chars = sum(len(l) for l in content_lines)
    if len(content_lines) < min_content_lines or total_chars < min_content_chars:
        _harness_log.warning("[Validate] Session %s has insufficient output: %d lines, %d chars",
                             session.get("session_id"), len(content_lines), total_chars)
        return False
    return True


def _artifact_path(task_id: str, step_key: str) -> str:
    """Return the .md artifact file path for a given task step."""
    safe_tid = task_id.replace("/", "_")
    return _os.path.join(_ARTIFACT_DIR, f"{safe_tid}_{step_key}.md")


# XC-2.1: 工作区产物目录 + MANIFEST
def _pipeline_steps_dir(task_id: str, step_key: str = "") -> str:
    """Return (and create) the per-step workspace directory."""
    d = _os.path.join(_pipeline_dir(task_id), "steps")
    if step_key:
        d = _os.path.join(d, step_key)
    _os.makedirs(d, exist_ok=True)
    return d


def _pipeline_handoffs_dir(task_id: str) -> str:
    """Return (and create) the handoffs/ directory."""
    d = _os.path.join(_pipeline_dir(task_id), "handoffs")
    _os.makedirs(d, exist_ok=True)
    return d


def _update_workspace_manifest(task_id: str, step_key: str, files: list,
                                summary: str = "") -> None:
    """Append-update MANIFEST.json with step artifacts.

    files: [{path, size, sha1, summary}]
    """
    import hashlib as _hashlib
    import json as _json
    manifest_path = _os.path.join(_pipeline_dir(task_id), "MANIFEST.json")
    manifest: list = []
    try:
        if _os.path.isfile(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = _json.load(f)
            if not isinstance(manifest, list):
                manifest = []
    except Exception:
        manifest = []

    # Compute sha1 for each file if not provided
    for entry in files:
        fpath = entry.get("path", "")
        if not entry.get("sha1") and _os.path.isfile(fpath):
            try:
                with open(fpath, "rb") as bf:
                    entry["sha1"] = _hashlib.sha1(bf.read()).hexdigest()[:12]
            except Exception:
                entry["sha1"] = ""
        if not entry.get("size") and _os.path.isfile(fpath):
            try:
                entry["size"] = _os.path.getsize(fpath)
            except Exception:
                entry["size"] = 0

    from datetime import datetime, timezone
    manifest.append({
        "step": step_key,
        "files": files,
        "summary": summary,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            _json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _harness_log.warning("[Workspace] MANIFEST update failed: %s", e)


def _collect_step_artifact(task, completed_step: Dict) -> None:
    """Extract output from a completed step's Claude session and save as .md artifact.
    Works for both CLI mode and Ollama direct mode."""
    sid = completed_step.get("session_id")
    if not sid or sid not in _claude_sessions:
        return
    session = _claude_sessions[sid]
    lines = list(session.get("lines", []))
    # Skip header lines (the prompt echo), find actual model output
    # XC-1.2: 去_cli 化文案标记——用于分离 header 和实际 LLM 输出
    _HEADER_MARKERS = ("正在调用配置模型", "正在启动 Claude Code CLI",
                       "使用 Ollama 直连模式", "Ollama 直连",
                       "使用 DeepSeek V4 工具循环", "使用 DeepSeek V4 直连",
                       "─" * 10)
    output_lines = []
    past_header = False
    for line in lines:
        if not past_header:
            if any(m in line for m in _HEADER_MARKERS):
                past_header = True
            continue
        output_lines.append(line)
    # Fallback: if no header marker found, take everything after first 3 lines
    if not output_lines and len(lines) > 3:
        output_lines = lines[3:]
    if not output_lines:
        return
    content = "".join(output_lines).strip()
    if not content:
        return
    # Save as .md artifact
    art_path = _artifact_path(task.task_id, completed_step["key"])
    header = (
        f"# {completed_step['label']} — {completed_step.get('agent_role', '')}\n\n"
        f"任务: {task.title}\n"
        f"步骤: {completed_step['key']}\n"
        f"Agent: {completed_step.get('agent_id', '')}\n\n---\n\n"
    )
    with open(art_path, "w", encoding="utf-8") as f:
        f.write(header + content + "\n")
    # Store the artifact path in step metadata
    completed_step["artifact"] = art_path
    _harness_log.info(f"[Harness] Artifact saved: {art_path} ({len(content)} chars)")

    # XC-2.1: 同步产物到工作区 steps/{step_key}/ 并更新 MANIFEST
    try:
        step_dir = _pipeline_steps_dir(task.task_id, completed_step["key"])
        ws_artifact = _os.path.join(step_dir, "output.md")
        with open(ws_artifact, "w", encoding="utf-8") as f:
            f.write(header + content + "\n")
        # self_report.json: 步骤元信息摘要
        import json as _json
        report_path = _os.path.join(step_dir, "self_report.json")
        report = {
            "step": completed_step["key"],
            "agent_id": completed_step.get("agent_id", ""),
            "agent_role": completed_step.get("agent_role", ""),
            "output_chars": len(content),
            "session_id": sid,
            "status": "completed",
        }
        with open(report_path, "w", encoding="utf-8") as f:
            _json.dump(report, f, ensure_ascii=False, indent=2)
        # 更新 MANIFEST
        _update_workspace_manifest(
            task.task_id, completed_step["key"],
            files=[
                {"path": ws_artifact, "summary": "LLM 输出主文档"},
                {"path": report_path, "summary": "步骤自报告"},
            ],
            summary=completed_step.get("label", completed_step["key"]),
        )
    except Exception as e:
        _harness_log.warning("[Workspace] step artifact sync failed: %s", e)


# ── Code Deliverable Extraction ──────────────────────────────────
import re as _re_mod

# Pattern: ```lang  // filepath: <path>  OR  ```lang filename=<path>
# Also matches: <!-- file: path --> or # File: path before code blocks
_FILE_PATH_PATTERNS = [
    # Inline in fence: ```python  // src/backend/foo.py
    _re_mod.compile(r"```\w*\s+//\s*(?:filepath:\s*)?(.+)"),
    # Inline in fence: ```python filename=src/backend/foo.py
    _re_mod.compile(r"```\w*\s+filename=(.+)"),
    # Comment above fence: <!-- file: src/frontend/bar.html -->
    _re_mod.compile(r"<!--\s*file:\s*(.+?)\s*-->"),
    # Header above fence: # File: src/frontend/bar.html  OR  ## `src/backend/foo.py`
    _re_mod.compile(r"^#+\s+(?:File:\s*)?`?([^\s`]+\.\w+)`?\s*$", _re_mod.MULTILINE),
    # Bold path: **src/frontend/cms-health.html**
    _re_mod.compile(r"\*\*([^\s*]+\.\w{1,10})\*\*"),
    # Path in backticks on its own line: `src/frontend/foo.html`
    _re_mod.compile(r"^`([^\s`]+\.\w{1,10})`\s*$", _re_mod.MULTILINE),
]

# Valid source file extensions we care about
_CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".html", ".htm", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml",
    ".md", ".sql", ".sh",
})


def _extract_code_deliverables(text: str) -> List[Dict[str, str]]:
    """Extract code blocks with file paths from LLM output.

    Returns a list of {path: str, content: str, language: str} dicts.
    Handles various formats LLMs use to indicate file paths.
    """
    deliverables: List[Dict[str, str]] = []

    # Split into segments around fenced code blocks
    # Match: ```lang ... ``` with content.
    # CRITICAL: anchor opening AND closing fence to start-of-line so indented
    # code blocks inside echoed prompts (e.g. "  ```js" in a quoted prompt) do
    # not swallow real code fences across hundreds of lines.
    fence_pattern = _re_mod.compile(
        r"^```(\w*)([ \t]+[^\n]*)?\n"     # Opening fence at line start
        r"(.*?)"                           # Code content (non-greedy)
        r"\n^```\s*$",                     # Closing fence at line start
        _re_mod.DOTALL | _re_mod.MULTILINE,
    )

    for m in fence_pattern.finditer(text):
        lang = (m.group(1) or "").strip()
        fence_meta = (m.group(2) or "").strip()
        code = m.group(3) or ""

        # Get pre-context: up to 3 lines before the opening fence
        pre_start = max(0, m.start() - 500)
        pre_text = text[pre_start:m.start()]
        pre_lines = pre_text.split("\n")
        pre_context = "\n".join(pre_lines[-4:]) if len(pre_lines) > 4 else pre_text

        if not code.strip():
            continue
        # Skip shell/terminal output blocks
        if lang in ("bash", "sh", "shell", "console", "terminal", "zsh", "log", "text", "output"):
            # But allow if explicitly marked with a file path
            if not fence_meta:
                continue

        # Try to find file path
        filepath = ""

        # 1. Check fence metadata: ```python // src/backend/foo.py
        if fence_meta:
            for pat in _FILE_PATH_PATTERNS[:2]:
                pm = pat.match(f"```{lang} {fence_meta}")
                if pm:
                    filepath = pm.group(1).strip()
                    break
            if not filepath:
                # Plain path after language: ```python src/backend/foo.py
                candidate = fence_meta.strip().strip("`").strip("'").strip('"')
                if "/" in candidate and _os.path.splitext(candidate)[1] in _CODE_EXTENSIONS:
                    filepath = candidate

        # 2. Check pre-context (lines before the code block)
        if not filepath:
            for line in reversed(pre_context.strip().split("\n")):
                line = line.strip()
                if not line:
                    continue
                for pat in _FILE_PATH_PATTERNS:
                    pm = pat.search(line)
                    if pm:
                        candidate = pm.group(1).strip().strip("`").strip("'").strip('"')
                        if _os.path.splitext(candidate)[1] in _CODE_EXTENSIONS:
                            filepath = candidate
                            break
                if filepath:
                    break

        # 3. Infer from code content (first line comment: # src/backend/foo.py)
        if not filepath:
            first_lines = code.strip().split("\n")[:3]
            for fl in first_lines:
                fl = fl.strip()
                # # file: src/backend/foo.py  or  // src/frontend/bar.js
                fm = _re_mod.match(r"(?:#|//|/\*|<!--)\s*(?:file:\s*)?(\S+\.\w+)", fl)
                if fm:
                    candidate = fm.group(1).strip()
                    if _os.path.splitext(candidate)[1] in _CODE_EXTENSIONS:
                        filepath = candidate
                        break

        if not filepath:
            continue

        # Normalize: strip leading project root prefixes
        for prefix in ("/Users/panglaohu/Downloads/DoubleBoatClawSystem/", "./"):
            if filepath.startswith(prefix):
                filepath = filepath[len(prefix):]

        # Validate: must look like a real project path
        if filepath.startswith("/") or ".." in filepath:
            continue

        deliverables.append({
            "path": filepath,
            "content": code,
            "language": lang or _os.path.splitext(filepath)[1].lstrip("."),
        })

    return deliverables


def _save_deliverables_to_workspace(
    task_id: str, team_id: str, agent_id: str,
    deliverables: List[Dict[str, str]],
) -> List[str]:
    """Save extracted code deliverables to agent workspace.

    Files are saved under: storage/agent_workspaces/{team_id}/{agent_id}/deliverables/{task_id}/
    Returns list of saved file paths (relative to workspace root).
    """
    if not deliverables:
        return []

    safe_tid = task_id.replace("/", "_")[:50]
    root = _agent_ws_root(team_id, agent_id)
    deliverable_dir = root / "deliverables" / safe_tid
    deliverable_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    # Also write a manifest
    manifest_lines = [
        f"# Deliverables for task {task_id}",
        f"",
        f"Agent: {agent_id}",
        f"Time: {datetime.now(timezone.utc).isoformat()}",
        f"Files: {len(deliverables)}",
        f"",
    ]

    for i, d in enumerate(deliverables):
        rel_path = d["path"]
        content = d["content"]

        # Preserve directory structure from the path
        file_target = deliverable_dir / rel_path
        file_target.parent.mkdir(parents=True, exist_ok=True)
        file_target.write_text(content, encoding="utf-8")
        saved.append(str(file_target.relative_to(root)))
        manifest_lines.append(f"- `{rel_path}` ({len(content)} chars, {d.get('language', '')})")
        _harness_log.info(
            f"[Deliverable] Saved: {file_target} ({len(content)} chars)"
        )

    # Write manifest
    manifest_path = deliverable_dir / "_manifest.md"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    _harness_log.info(
        f"[Deliverable] {len(saved)} files saved to workspace for agent {agent_id}, task {task_id}"
    )
    return saved


def _apply_deliverables_to_codebase(
    task_id: str, team_id: str, developer_agent_id: str,
) -> Dict[str, Any]:
    """Read deliverables from developer's workspace and apply them to the project codebase.

    This is called by the deploy step. It reads files from the developer's
    deliverables directory and copies them to the actual project locations.

    Returns a summary dict with applied/skipped/failed counts.
    """
    safe_tid = task_id.replace("/", "_")[:50]
    root = _agent_ws_root(team_id, developer_agent_id)
    deliverable_dir = root / "deliverables" / safe_tid
    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.abspath(__file__)))))

    result = {"applied": [], "skipped": [], "failed": [], "backup": []}

    if not deliverable_dir.exists():
        _harness_log.warning(f"[Deploy] No deliverables dir: {deliverable_dir}")
        return result

    # Read manifest to get file list
    for fpath in deliverable_dir.rglob("*"):
        if fpath.is_dir() or fpath.name.startswith("_"):
            continue

        # The relative path inside deliverables mirrors the project structure
        rel_in_deliverable = fpath.relative_to(deliverable_dir)
        target_path = _os.path.join(project_root, str(rel_in_deliverable))

        # Safety: only allow writes within src/, tests/, docs/, config/
        _ALLOWED_PREFIXES = ("src/", "tests/", "docs/", "config/", "public/")
        rel_str = str(rel_in_deliverable)
        if not any(rel_str.startswith(p) for p in _ALLOWED_PREFIXES):
            result["skipped"].append({
                "path": rel_str,
                "reason": f"Outside allowed directories: {_ALLOWED_PREFIXES}",
            })
            _harness_log.warning(f"[Deploy] Skipped (outside allowed dirs): {rel_str}")
            continue

        try:
            new_content = fpath.read_text(encoding="utf-8")

            # Backup existing file if it exists
            if _os.path.isfile(target_path):
                backup_path = target_path + ".bak"
                import shutil
                shutil.copy2(target_path, backup_path)
                result["backup"].append({"path": rel_str, "backup": backup_path})

            # Create parent directories
            _os.makedirs(_os.path.dirname(target_path), exist_ok=True)

            # Write the file
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            result["applied"].append({"path": rel_str, "size": len(new_content)})
            _harness_log.info(f"[Deploy] Applied: {target_path} ({len(new_content)} chars)")

        except Exception as e:
            result["failed"].append({"path": rel_str, "error": str(e)[:200]})
            _harness_log.error(f"[Deploy] Failed to apply {rel_str}: {e}")

    _harness_log.info(
        f"[Deploy] Summary: {len(result['applied'])} applied, "
        f"{len(result['skipped'])} skipped, {len(result['failed'])} failed"
    )
    return result


def _find_developer_agent(team_id: str, workflow: list) -> str:
    """Find the developer agent_id from a workflow's develop step."""
    for s in workflow:
        if s.get("key") == "develop" and s.get("agent_id"):
            return s["agent_id"]
    return ""


# ── Per-step prompt templates ──
_STEP_PROMPTS: Dict[str, str] = {
    "pm_decompose": (
        "你是项目经理 (PM)。请对以下任务进行分解和规划:\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## 要求\n"
        "1. 分析任务需求，拆解为可执行的子步骤\n"
        "2. 识别技术风险和依赖关系\n"
        "3. 为后续研究人员、架构师、开发者提供清晰的指导\n"
        "4. 输出一份结构化的任务分解文档 (Markdown 格式)\n\n"
        "## ⚠️ 重要提示\n"
        "系统已自动预加载项目文件结构和相关源文件（见下方 📂 项目上下文）。\n"
        "请基于**实际存在的文件**进行分析，不要猜测文件名。\n\n"
        "项目根目录: {working_dir}\n"
        "后端: src/backend/ (Python FastAPI)\n"
        "前端: src/frontend/ (HTML + JS)\n"
    ),
    "research": (
        "你是技术研究员。请对以下任务进行技术调研:\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## ⚠️ 最重要的规则\n"
        "系统已自动预加载项目文件结构和相关源文件（见上方 📂 项目上下文）。\n"
        "**你必须只引用上方提供的实际文件**，严禁凭想象编造文件名或路径。\n"
        "如果上下文中没有某个文件，说明该文件不存在。\n\n"
        "## 要求\n"
        "1. 仔细阅读上方提供的项目文件结构和源文件内容\n"
        "2. 根据**实际存在的文件**分析哪些需要修改\n"
        "3. 列出需要修改的文件的**完整路径** (必须是项目上下文中出现的路径)\n"
        "4. 分析实现方案的可行性\n"
        "5. 引用具体代码行号说明修改点\n\n"
        "项目根目录: {working_dir}\n"
        "后端: src/backend/ (Python FastAPI)\n"
        "前端: src/frontend/ (HTML + JS)\n"
    ),
    "architecture": (
        "你是系统架构师。请为以下任务设计技术方案:\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## ⚠️ 重要提示\n"
        "上方 📂 项目上下文 包含了任务相关的实际源文件。\n"
        "请基于这些文件设计方案，不要引用不存在的文件。\n\n"
        "## 要求\n"
        "1. 基于调研结果和实际源码，设计详细技术方案\n"
        "2. 明确指出需要修改的文件和具体修改内容\n"
        "3. 定义接口规范（如有新增 API）\n"
        "4. 为开发工程师提供逐步实施指南\n\n"
        "项目根目录: {working_dir}\n"
        "后端: src/backend/ (Python FastAPI)\n"
        "前端: src/frontend/ (HTML + JS)\n"
    ),
    "develop": (
        "你是开发工程师 (DeepSeek V4 + 工具循环模式)。\n"
        "你**已经被赋予真正的工具能力**: read_file / grep / list_files / write_file / patch_file / run_python。\n"
        "禁止凭空想象 — 所有写代码前必须先用工具读真实代码。\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## 推荐工作流（严格遵守）\n"
        "**Step 1 · 侦察**: \n"
        "  - 用 `list_files(path='src/backend/channels')` 看现有 Channel 模块\n"
        "  - 用 `grep(pattern='class MarineChannel', include='src/backend/**/*.py')` 找基类定义\n"
        "  - 用 `read_file(path='src/backend/channels/marine_base.py')` 读完整接口规范\n"
        "  - 找到任何要继承的基类 / 要调用的函数，**先 grep 再 read**，不要靠记忆\n\n"
        "**Step 2 · 验证假设**: 用 `run_python` 跑一段 import 代码，确认 import 路径正确\n"
        "  示例: `run_python(code='from channels.marine_base import ChannelPriority; print(list(ChannelPriority))')`\n\n"
        "**Step 3 · 编码**: \n"
        "  - 新功能 → `write_file` 创建新模块（推荐放在 src/backend/channels/ 或 src/frontend/digital-twin/）\n"
        "  - 改现有大文件 → 用 `patch_file(path, search, replace)` 精准修改\n"
        "  - **禁止** write_file 覆盖 >200 行的现有文件 (会被 shrink-guard 拒绝)\n\n"
        "**Step 4 · 自检**: \n"
        "  - Python: `run_python(code='from channels.your_new_module import YourClass; YourClass()')`\n"
        "  - 通过则继续；失败则修复后再次验证\n\n"
        "**Step 5 · 完成**: 调用 `finish(summary='...', files_changed=[...])`\n\n"
        "## 工程规范\n"
        "- 所有 Channel 必须 `from channels.marine_base import MarineChannel, ChannelPriority, ChannelStatus` 然后 `class X(MarineChannel)`\n"
        "- ChannelPriority 只有 P0 / P1 / P2，**没有 P3**\n"
        "- 必须实现 `process_event()` 和 `get_status()`\n"
        "- 新参数必须有默认值（向后兼容）\n\n"
        "项目根目录: {working_dir}\n"
    ),
    "test": (
        "你是 QA 测试工程师 (DeepSeek V4 + 工具循环模式)。\n"
        "你**已经被赋予真正的测试工具能力**: read_file / grep / run_python / run_pytest。\n"
        "禁止凭空判定 — 所有结论必须来自工具的真实输出。\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## 推荐工作流（严格遵守）\n"
        "**Step 1**: 用 grep / read_file 检查 Developer 写的新文件\n"
        "**Step 2**: 对每个新 .py 文件，跑 `run_python(code='from <module> import <name>')` 验证 import 通\n"
        "**Step 3**: 对涉及到的 channel，跑 `run_python(code='from channels.X import Y; obj=Y(); print(obj.process_event({{}}))')` 测试核心方法\n"
        "**Step 4**: 跑 `run_pytest(target='-k <module-name>')` 看相关测试是否通过\n"
        "**Step 5**: 调用 finish 给出结论：\n"
        "  - summary 必须以 `## 验证结论 PASS` 或 `## 验证结论 FAIL` 结尾\n"
        "  - files_changed 通常为空（QA 不写代码）\n\n"
        "## 判定标准\n"
        "- import 失败 → BLOCKER → FAIL\n"
        "- 单元测试失败 → BLOCKER → FAIL\n"
        "- 仅 lint/style 问题 → MINOR → PASS\n\n"
        "项目根目录: {working_dir}\n"
    ),
    "document": (
        "你是文档工程师。请更新以下任务的相关文档:\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## 要求\n"
        "1. 根据开发和部署步骤产出，总结变更内容\n"
        "2. 更新相关文档说明\n"
        "3. 输出文档变更清单 (Markdown 格式)\n\n"
        "项目根目录: {working_dir}\n"
        "后端: src/backend/ (Python FastAPI)\n"
        "前端: src/frontend/ (HTML + JS)\n"
    ),
    "deploy": (
        "你是 DevOps 部署工程师。\n"
        "开发者的代码交付物已自动保存到管线共享工作区。\n"
        "部署步骤完成后，系统会自动将代码文件应用到项目代码库。\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "## 自动部署机制\n"
        "- 开发步骤的代码块已提取到: `storage/pipeline_runs/<task_id>/04_develop/code/`\n"
        "- 本步骤完成时系统自动执行: 开发文件 → 项目代码库 (含 .bak 备份)\n"
        "- 你只需审查变更合理性并输出部署报告\n\n"
        "## 部署策略要求\n"
        "1. **变更分析**: 分析代码变更的范围和影响\n"
        "   - 小改动 (hotfix/patch): 就地更新\n"
        "   - 较大功能变更: 蓝绿部署\n"
        "2. **蓝绿部署判断**: 新增/大幅修改 HTML 页面、API 签名变更、核心 Channel 逻辑变更\n"
        "3. **⚠️ Captain 安全拒绝规则**:\n"
        "   如果 Captain/PM 在前序步骤中拒绝了删除/移除操作:\n"
        "   - **不得直接修改原始页面**\n"
        "   - **创建新版本**: `<文件名>-v2.<ext>` (如 cms-health-v2.html)\n"
        "   - 新版本包含所请求的修改内容，用代码块格式输出:\n"
        "     ```html // src/frontend/cms-health-v2.html\n"
        "     <!-- 完整文件内容 -->\n"
        "     ```\n"
        "4. **产出**: 输出部署清单 (Markdown 格式) 包含: 部署类型, 影响文件, 回滚方案\n\n"
        "项目根目录: {working_dir}\n"
        "后端: src/backend/ (Python FastAPI)\n"
        "前端: src/frontend/ (HTML + JS)\n"
    ),
}


def _build_step_prompt(task, step: Dict, workflow: list) -> str:
    """Build a role-specific prompt for a workflow step.

    Includes:
    1. Pre-seeded project context (_context/ from pipeline workspace)
    2. All prior step outputs from pipeline workspace (full-team shared)
    3. Handoff files for inter-agent state
    4. QA feedback (if pipeline was rewound after a failed test step)
    """
    working_dir = "/Users/panglaohu/Downloads/DoubleBoatClawSystem"
    key = step.get("key", "execute")
    template = _STEP_PROMPTS.get(key, (
        "请执行以下任务步骤 ({label}):\n\n"
        "## 任务\n{title}\n{description}\n\n"
        "{prev_artifacts}"
        "项目根目录: {working_dir}\n"
    ))

    prev_parts = []

    # ── 0. QA feedback from previous failed iteration (highest priority) ──
    try:
        qa_fb = (task.metadata or {}).get("qa_feedback") if hasattr(task, "metadata") else None
        if qa_fb and key in ("develop", "test"):
            iteration = qa_fb.get("iteration", 1)
            fb_parts = [
                f"## 🔁 上一轮 QA 反馈 (第 {iteration} 次重试)\n\n"
                f"上一次开发产出**未通过 QA**，原因：\n\n"
                f"> {qa_fb.get('reason', 'unspecified')}\n\n"
            ]

            # ── Structured failures: actionable file+line+error list ──
            structured = qa_fb.get("structured_failures", [])
            if structured:
                fb_parts.append("### 🎯 具体失败清单 (必须逐条修复)\n\n")
                for i, sf in enumerate(structured[:10], 1):
                    if "file" in sf:
                        line_str = f" L{sf['line']}" if sf.get("line") else ""
                        test_str = f" :: {sf['test']}" if sf.get("test") else ""
                        fb_parts.append(
                            f"{i}. `{sf['file']}`{line_str}{test_str} — {sf.get('error', sf.get('detail', ''))}\n"
                        )
                    elif "error_type" in sf:
                        fb_parts.append(
                            f"{i}. **{sf['error_type']}**: {sf.get('detail', '')}\n"
                        )
                fb_parts.append("\n")

            # QA checklist from structured summary
            qa_checklist = qa_fb.get("qa_checklist", [])
            if qa_checklist:
                fb_parts.append("### QA 检查清单\n\n")
                for item in qa_checklist[:10]:
                    fb_parts.append(f"- [{item.get('severity', '?')}] {item.get('detail', '')}\n")
                fb_parts.append("\n")

            # Raw report as fallback (truncated)
            report_text = qa_fb.get("report", "")
            if report_text and not structured:
                fb_parts.append(f"### QA 报告摘要\n\n```\n{report_text[:3000]}\n```\n\n")

            fb_parts.append(
                "### 必须修复\n"
                "1. 仔细阅读上方失败清单，**逐条**修复列出的 BLOCKER\n"
                "2. 不要重新发明轮子 — 用 read_file 看你之前写的代码，**只改坏的地方**\n"
                "3. 修完后用 run_python / run_pytest **当场验证**\n"
                "4. 验证通过再调用 finish\n\n"
            )
            prev_parts.append("".join(fb_parts))
    except Exception:
        pass

    # ── 1. Project context (pre-seeded file tree + relevant source files) ──
    try:
        project_ctx = _get_pipeline_context_for_prompt(task.task_id)
        if project_ctx:
            prev_parts.append(project_ctx)
    except Exception:
        pass

    # ── 2. Prior step outputs from pipeline workspace ──
    try:
        prior_steps = _get_prior_steps_from_pipeline(task.task_id, key)
        if prior_steps:
            prev_parts.append(prior_steps)
    except Exception:
        pass

    # ── 3. Fallback: old artifact system (for in-flight tasks without pipeline dir) ──
    if not prev_parts:
        _MAX_TOTAL_CHARS = 200_000
        _MAX_PER_ARTIFACT = 60_000
        prior_completed = [s for s in workflow
                          if s["index"] < step["index"] and s.get("status") == "completed"]
        for s in prior_completed[-3:]:
            art_path = s.get("artifact")
            if not art_path or not _os.path.isfile(art_path):
                if s.get("session_id") and s["session_id"] in _claude_sessions:
                    _collect_step_artifact(task, s)
                    art_path = s.get("artifact")
            if art_path and _os.path.isfile(art_path):
                try:
                    with open(art_path, "r", encoding="utf-8") as f:
                        content = f.read(_MAX_PER_ARTIFACT)
                    prev_parts.append(
                        f"## 上一步产出 — {s['label']} ({s.get('agent_role', '')})\n\n"
                        f"{content}\n\n"
                    )
                except Exception:
                    pass

    # ── 协作拓扑：可委派/交接/发消息的对象（同队/共总线/门禁边）──
    try:
        team_id = getattr(task, "team_id", "") or ""
        agent_id = str(step.get("agent_id") or getattr(task, "agent_id", "") or "")
        if team_id and agent_id:
            from agents.agent_relationships import collab_topology_for_prompt
            topo_md = collab_topology_for_prompt(team_id, agent_id)
            if topo_md:
                handoff = step.get("collab_handoff") or {}
                handoff_line = ""
                if handoff.get("path"):
                    handoff_line = (
                        f"\n本步由 `{handoff.get('from')}` 交接而来，"
                        f"路径={handoff.get('path')} layers={handoff.get('layers')}\n"
                    )
                prev_parts.append(
                    f"## 协作拓扑（执行时生效）\n\n{topo_md}\n{handoff_line}\n"
                    "委派/发消息请使用 list_agents 与上述名单内对象；"
                    "broadcast 须绑定通道 publish 权限。\n"
                )
    except Exception:
        pass

    # ── XC-4.4 物竞成本锁定构型（先适者后省钱）──
    try:
        meta = getattr(task, "metadata", None) or {}
        if meta.get("eco_bid_locked") or meta.get("bid_candidate_id"):
            skills = meta.get("required_skills") or meta.get("skill_genome") or []
            sk_line = ", ".join(str(s) for s in skills[:16]) if skills else "（无 dominant 列表）"
            bind = meta.get("eco_bid_skill_bind") or {}
            bind_line = ""
            if bind:
                bind_line = (
                    f"- SkillRouter 静默绑定: ok={bind.get('ok')} "
                    f"新增={bind.get('assigned') or []} 已有={bind.get('already_has') or []}\n"
                )
            prev_parts.insert(0,
                "## 物竞成本锁定构型（生产优先）\n\n"
                f"- bid: `{meta.get('bid_candidate_id') or '—'}`\n"
                f"- 适者 agent: `{meta.get('champion_agent_id') or getattr(task, 'agent_id', '') or '—'}`\n"
                f"- 优先 skill 包: {sk_line}\n"
                f"{bind_line}"
                f"- T={meta.get('eco_best_T', '—')} · fp=`{str(meta.get('eco_fp') or '')[:16]}`\n"
                "- 原则：先适者后省钱；locked skill 已写入 agent.skills（幂等）；勿随意换无 skill 构型。\n"
            )
    except Exception:
        pass

    prev_artifacts = "\n".join(prev_parts) if prev_parts else ""

    try:
        return template.format(
            title=task.title,
            description=task.description or "(无详细描述)",
            working_dir=working_dir,
            prev_artifacts=prev_artifacts,
            label=step.get("label", key),
        )
    except (IndexError, KeyError) as fmt_err:
        # Literal `{` / `}` in template that wasn't escaped → log and fall back
        _harness_log.exception(
            "[Harness] _build_step_prompt template format error for step '%s': %s",
            key, fmt_err,
        )
        # Fallback: return a minimal prompt so the pipeline doesn't deadlock
        return (
            f"# {step.get('label', key)}\n\n"
            f"## 任务\n{task.title}\n{task.description or ''}\n\n"
            f"{prev_artifacts}\n\n"
            f"⚠️ 模板渲染失败 ({fmt_err}); 使用降级 prompt。\n"
            f"项目根目录: {working_dir}\n"
        )


def _resolve_claude_path(configured: str) -> str:
    """Resolve Claude CLI path, checking common locations.

    XC-6.3②: escape 舱专用——仅在 AG_ENABLE_LOCAL_CLI=1 时被 _run_claude_cli_direct 调用。
    正常执行路径不经过此函数。
    """
    import shutil
    if configured and configured != "claude":
        return configured
    # Try PATH first
    found = shutil.which("claude")
    if found:
        return found
    # Common install locations
    for p in [
        _os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        _os.path.expanduser("~/.npm-global/bin/claude"),
    ]:
        if _os.path.isfile(p) and _os.access(p, _os.X_OK):
            return p
    return configured  # fallback


def _is_ollama_backend() -> bool:
    """Check if Claude settings point to Ollama (not official Anthropic API)."""
    import json as _json
    try:
        settings_path = _os.path.expanduser("~/.claude/settings.json")
        if _os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = _json.load(f)
            base_url = settings.get("env", {}).get("ANTHROPIC_BASE_URL", "")
            # Ollama typically uses non-Anthropic URLs
            if base_url and "anthropic.com" not in base_url:
                return True
    except Exception:
        pass
    return False


def _harness_provider_credentials() -> tuple:
    """Global provider credentials from ChatHarness (authoritative source).

    XC-1.1: 不再读 ~/.claude/settings.json，改用 get_chat_harness().get_provider_config()。
    Returns (api_key, base_url, model, provider); (None, None, None, provider)
    when unavailable.
    """
    try:
        from agents.chat_harness import get_chat_harness
        harness = get_chat_harness()
        pc = harness.get_provider_config()
        if pc and pc.api_key:
            return pc.api_key, pc.resolve_base_url(), pc.model, pc.provider.value
    except Exception:
        pass
    return None, None, None, "deepseek"


def _get_deepseek_credentials(agent=None, team_id: str = "") -> tuple:
    """Resolve LLM credentials, preferring the agent's bound team model.

    优先级: agent.model_id 指向的团队模型 → 团队默认模型 → 全局 harness 凭据。
    Returns (api_key, base_url, model_name)。
    """
    if agent is not None and team_id:
        team = None
        try:
            team = _tm().get_team(team_id)
        except Exception:
            team = None
        model = None
        if team is not None:
            model_id = getattr(agent, "model_id", "") or ""
            model = team.models.get(model_id)
            if model is None:
                model = next(
                    (m for m in team.models.values() if getattr(m, "is_default", False)),
                    None,
                )
        if model is not None and model.get_resolved_api_key():
            base_url = (getattr(model, "api_base_url", "") or "").strip().rstrip("/")
            return model.get_resolved_api_key(), base_url, model.name
    api_key, base_url, model_name, _provider = _harness_provider_credentials()
    return api_key, base_url, model_name


def _complete_session_with_llm_degraded_output(
    session: Dict[str, Any], task_title: str, error: str
) -> None:
    """LLM 认证/连接失败时，以降级草稿收尾会话，避免任务卡死在 running。

    契约: session 标记 completed + exit_code 0 + llm_degraded=True，
    输出行包含「降级执行草稿」供前端与审计辨识。
    """
    lines = session.setdefault("lines", [])
    lines.append(f"⚠️ LLM 调用失败: {error}\n")
    lines.append("— 降级执行草稿 —\n")
    lines.append(f"任务: {task_title}\n")
    lines.append("LLM 暂不可用，以下为基于任务描述的离线执行草稿，请人工复核后落地。\n")
    session["status"] = "completed"
    session["exit_code"] = 0
    session["llm_degraded"] = True
    session["completed_at"] = datetime.now(timezone.utc).isoformat()


# 领域内多义缩写消歧：按 agent 角色/技能上下文把易混缩写钉死在团队语义上。
_ACRONYM_DISAMBIGUATION = (
    {
        "token": "ri",
        "context_keywords": (
            "成本", "账单", "aws", "reserved", "savings plan", "ri/savings", "预算", "预留",
        ),
        "expansion": "AWS Reserved Instance（预留实例）",
        "prompt_note": "（这里的 RI 指 AWS Reserved Instance 预留实例）",
        "system_note": (
            "术语约定: 本团队语境中 RI 一律指 AWS Reserved Instance（预留实例），"
            "不要解释成编程领域的 RI（如 RuntimeIdentifier、ReactiveX 等）。"
        ),
    },
)


def _build_agent_loop_prompt_and_system(
    *, prompt: str = "", team_id: str = "", agent=None, system_prompt: str = ""
) -> tuple:
    """构建 agent loop 的有效 prompt 与 system prompt。

    - system prompt = 显式传入 or agent.system_prompt，附加角色与绑定技能说明。
    - 依据角色/技能上下文对 prompt 中的多义缩写做消歧（如成本域的 RI）。
    Returns (effective_prompt, system_prompt)。
    """
    sys_parts: List[str] = []
    base_system = system_prompt or (getattr(agent, "system_prompt", "") if agent else "")
    if base_system:
        sys_parts.append(base_system)
    role = getattr(agent, "role", "") if agent else ""
    if role:
        sys_parts.append(f"角色: {role}")
    # 绑定技能: team-local 优先，注册表可用时兜底（不可用时静默跳过）。
    skills: List[Any] = []
    if agent is not None:
        refs = set(agent.skills or [])
        pools: List[Any] = []
        try:
            team = _tm().get_team(team_id) if team_id else None
            if team is not None:
                pools.extend(team.skills.values())
        except Exception:
            pass
        try:
            pools.extend(_sr().list_all())
        except Exception:
            pass
        seen: set = set()
        for s in pools:
            if s.skill_id in seen:
                continue
            if s.skill_id in refs or s.name in refs or (getattr(s, "slug", "") and s.slug in refs):
                skills.append(s)
                seen.add(s.skill_id)
    for s in skills:
        entry = f"技能[{s.name}]"
        if getattr(s, "instructions", ""):
            entry += f": {s.instructions}"
        sys_parts.append(entry)
    # 缩写消歧: prompt 含多义缩写且上下文命中团队领域时，展开写入双端。
    effective_prompt = prompt
    context_text = " ".join(
        [role]
        + [f"{s.name} {getattr(s, 'description', '')} {getattr(s, 'instructions', '')}" for s in skills]
    ).lower()
    prompt_lower = (prompt or "").lower()
    for rule in _ACRONYM_DISAMBIGUATION:
        if rule["token"] in prompt_lower and any(
            kw in context_text for kw in rule["context_keywords"]
        ):
            effective_prompt = f"{prompt}\n{rule['prompt_note']}"
            sys_parts.append(rule["system_note"])
            sys_parts.append(f"缩写展开: {rule['token'].upper()} = {rule['expansion']}")
    return effective_prompt, "\n\n".join(p for p in sys_parts if p)


# When using DeepSeek as backend, Claude CLI has NO tool access (no file
# editing, no shell), so direct API is always faster and equally capable.
# Claude CLI is only beneficial with real Anthropic API (tool use support).
# Check at runtime whether we're on DeepSeek → always use direct API.
_TEXT_ONLY_ROLES = frozenset({
    "project_manager", "researcher", "documentation", "architect",
})

def _should_use_direct_api(role: str) -> bool:
    """XC-1.1: 决策不再依赖 ~/.claude/settings.json。

    文本角色走直连 API；其余角色走 tool_loop（含 devops/deployer）。
    CLI 逃生舱由 AG_ENABLE_LOCAL_CLI=1 控制，不由此函数决定。
    """
    return role in _TEXT_ONLY_ROLES


def _estimate_prompt_tokens(text: str) -> int:
    """粗估 prompt tokens（与 prompt_cache 一致：~2 chars/token）."""
    if not text:
        return 0
    return max(1, (len(text) + 1) // 2)


def _precheck_team_token_budget(team_id: str, *, estimated_tokens: int = 0, agent_id: str = "") -> Dict[str, Any]:
    """任务提交前预算预检。halt 且超限 → allowed=False。"""
    try:
        guard = get_budget_guard()
        check = guard.check(
            session_id=f"submit:{team_id}",
            agent_id=agent_id or f"team:{team_id}",
            team_id=team_id,
            estimated_tokens=max(0, int(estimated_tokens or 0)),
        )
        return {
            "allowed": bool(check.allowed),
            "events": [
                {
                    "scope": e.scope,
                    "scope_id": e.scope_id,
                    "level": e.level,
                    "value": e.value,
                    "limit": e.limit,
                    "message": e.message,
                }
                for e in (check.events or [])
            ],
            "budget": guard.budget.to_dict(),
        }
    except Exception as exc:
        _harness_log.warning("budget precheck failed: %s", exc)
        return {"allowed": True, "events": [], "error": str(exc)}


def _record_session_token_usage(
    session: Dict[str, Any],
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    """任务会话记账：强制 phase=task + scenario_id=task_id + team_id。"""
    tot = int(total_tokens or (input_tokens + output_tokens))
    if tot <= 0:
        return
    try:
        from .budget import UsageRecord, get_budget_guard
        from .chat_harness import ChatHarness
        from .token_context import get_token_ctx
        ctx = get_token_ctx() or {}
        task_id = str(
            session.get("task_id")
            or ctx.get("task_id")
            or ctx.get("scenario_id")
            or _os.environ.get("AG_TASK_ID")
            or ""
        )
        agent = session.get("_agent")
        agent_id = str(
            getattr(agent, "agent_id", "")
            or session.get("agent_id")
            or ctx.get("agent_id")
            or ""
        )
        team_id = str(
            session.get("team_id")
            or getattr(agent, "team_id", "")
            or getattr(agent, "origin_team_id", "")
            or ctx.get("team_id")
            or _os.environ.get("AG_TEAM_ID")
            or ""
        )
        if not team_id:
            _harness_log.warning(
                "task token record missing team_id task=%s session=%s — 分析台 by_team 将看不到",
                task_id, session.get("session_id"),
            )
        get_budget_guard().record_usage(UsageRecord(
            session_id=str(session.get("session_id") or ""),
            agent_id=agent_id,
            team_id=team_id,
            model=model or "",
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            total_tokens=tot,
            cost_usd=ChatHarness._estimate_cost_usd(model or "", tot),
            phase="task",
            scenario_id=task_id,
            run_id=str(session.get("session_id") or ""),
        ))
    except Exception as exc:
        _harness_log.debug("session token record skip: %s", exc)


def _start_claude_session(
    session_id: str, prompt: str, cfg: Dict, agent, task_id: str, team_id: str = "",
) -> None:
    """Start a session for build team tasks.

    Text-only roles (PM, researcher, docs) use DeepSeek API directly for
    fast streaming responses. Code-editing roles (developer, QA, architect)
    use Claude Code CLI which provides tool access.
    """
    _harness_log.info(
        "[Claude] Starting session %s — task: %s, agent: %s (%s)",
        session_id, task_id, agent.name, agent.role,
    )
    working_dir = cfg.get("working_directory", "") or "/Users/panglaohu/Downloads/AgentsGroup2026"
    auto_test = cfg.get("auto_test", True)
    use_direct_api = _should_use_direct_api(agent.role)
    # Direct API streams 64K tokens — needs much longer than the old 300s
    # CLI tool use can be slower still
    default_timeout = 1200 if use_direct_api else 1800
    timeout_sec = cfg.get("session_timeout", default_timeout)

    full_prompt = (
        f"你是 AgentsGroup2026 系统的 {agent.name} ({agent.role})。\n"
        f"请执行以下开发任务:\n\n{prompt}\n\n"
        f"项目根目录: {working_dir}\n"
        f"后端: src/backend/ (Python FastAPI)\n"
        f"前端: src/frontend/ (HTML + JS)\n"
    )
    # Only add test instruction for code-editing roles
    if auto_test and not use_direct_api:
        full_prompt += "完成后运行: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q --tb=short\n"

    _tid = str(team_id or getattr(agent, "team_id", "") or getattr(agent, "origin_team_id", "") or "")
    session: Dict[str, Any] = {
        "session_id": session_id,
        "task_id": task_id,
        "agent_id": str(getattr(agent, "agent_id", "") or ""),
        "team_id": _tid,
        "_agent": agent,
        "status": "running",
        "lines": deque(maxlen=20000),
        "started_at": _time.time(),
        "exit_code": None,
        "error": "",
        "proc": None,
    }
    # TG：线程内归因（contextvar 不跨线程，用 env + session + token_scope）
    # 任务维优化要求：team_id + task_id 必须进入 usage_log，分析台才认
    if task_id:
        _os.environ["AG_TASK_ID"] = str(task_id)
    if _tid:
        _os.environ["AG_TEAM_ID"] = _tid
    _claude_sessions[session_id] = session

    # Echo the prompt to the terminal buffer so users can see what was sent
    # XC-1.2: 文案去 CLI 化——显示真实 provider/model
    _api_key, _api_base, _model_name, _provider_name = _harness_provider_credentials()
    method_label = "配置模型 ({} / {})".format(_provider_name or "?", _model_name or "?")
    session["lines"].append(f"{'─'*60}\n")
    session["lines"].append(f"📋 任务: {task_id}\n")
    session["lines"].append(f"🏷 团队: {_tid or '（未传 team_id — 将无法进分析台 by_team）'}\n")
    session["lines"].append(f"🤖 Agent: {agent.name} ({agent.role})\n")
    session["lines"].append(f"📂 工作目录: {working_dir}\n")
    session["lines"].append(f"🔧 执行方式: {method_label}\n")
    session["lines"].append(f"⏱️ 超时: {timeout_sec}s\n")
    session["lines"].append(f"{'─'*60}\n")
    session["lines"].append(f"📝 提示词:\n")
    for pline in full_prompt.split("\n"):
        session["lines"].append(f"  {pline}\n")
    session["lines"].append(f"{'─'*60}\n")

    def _run():
        # 工作线程内再注 env + token_scope（contextvar 不跨线程）
        if task_id:
            _os.environ["AG_TASK_ID"] = str(task_id)
        if _tid:
            _os.environ["AG_TEAM_ID"] = str(_tid)
        _agent_id = str(getattr(agent, "agent_id", "") or session.get("agent_id") or "")
        try:
            from .token_context import token_scope as _token_scope
        except Exception:
            _token_scope = None  # type: ignore

        def _run_body() -> None:
            # XC-1.1: CLI 逃生舱——仅 AG_ENABLE_LOCAL_CLI=1 时可达
            _cli_escape = _os.getenv("AG_ENABLE_LOCAL_CLI") == "1"
            if _cli_escape and not use_direct_api:
                session["lines"].append(f"⚠️ CLI 逃生舱已启用 (AG_ENABLE_LOCAL_CLI=1)...\n\n")
                _run_claude_cli_direct(session, full_prompt, working_dir, timeout_sec, cfg)
                return

            # XC-1.1: 统一执行引擎——文本角色走直连 API，其余全部走 tool_loop
            if use_direct_api:
                api_key, api_base_url, model = _get_deepseek_credentials()
                if api_key:
                    session["lines"].append(f"⚡ 正在调用配置模型 ({model})...\n\n")
                    _max_tok = int(cfg.get("max_tokens", 65536))
                    _temp = float(cfg.get("temperature", 0.2))
                    _run_openai_compatible(
                        session, full_prompt, timeout_sec,
                        api_key=api_key, api_base_url=api_base_url, model=model,
                        max_tokens=_max_tok, temperature=_temp,
                    )
                else:
                    session["lines"].append(f"⚠️ 未找到配置模型凭据，请检查「模型与连接」页配置。\n\n")
                    _complete_session_with_llm_degraded_output(session, task_id, "No LLM credentials configured")
                return

            api_key, api_base_url, model = _get_deepseek_credentials()
            if api_key:
                session["lines"].append(
                    f"🛠 正在调用配置模型 ({model}) — 工具循环模式 (read/grep/write/exec)...\n\n"
                )
                _os.environ["AG_TASK_ID"] = str(task_id or "")
                if _tid:
                    _os.environ["AG_TEAM_ID"] = str(_tid)
                try:
                    import json as _json_env
                    _os.environ["AG_TASK_METADATA"] = _json_env.dumps(
                        cfg.get("task_metadata", {}), ensure_ascii=False
                    )
                except Exception:
                    _os.environ["AG_TASK_METADATA"] = "{}"
                _run_tool_loop(
                    session, full_prompt, agent.role,
                    api_key=api_key, api_base_url=api_base_url, model=model,
                    max_tokens=int(cfg.get("max_tokens", 65536)),
                    temperature=float(cfg.get("temperature", 0.2)),
                    max_iterations=int(cfg.get("max_iterations", 25)),
                )
                return
            session["lines"].append(f"⚠️ 未找到配置模型凭据，请检查「模型与连接」页配置。\n\n")
            _complete_session_with_llm_degraded_output(session, task_id, "No LLM credentials configured")

        try:
            if _token_scope is not None:
                with _token_scope(
                    task_id=str(task_id or ""),
                    team_id=str(_tid or ""),
                    agent_id=_agent_id,
                    phase="task",
                    run_id=str(session_id or ""),
                    scenario_id=str(task_id or ""),
                ):
                    _run_body()
            else:
                _run_body()
        except Exception as run_err:
            import traceback as _tb
            err_text = f"{run_err.__class__.__name__}: {run_err}"
            session["status"] = "failed"
            session["exit_code"] = 1
            session["error"] = err_text
            session["lines"].append(
                f"\n💥 _run 抛出未捕获异常: {err_text}\n"
                f"{_tb.format_exc()[:2000]}\n"
            )
            _harness_log.exception(
                "[Session] %s _run() crashed for role=%s: %s",
                session_id, agent.role, run_err,
            )
            return

        # Final validation: ensure session is properly marked
        final_status = session.get("status", "running")
        if final_status == "running":
            session["status"] = "failed"
            session["exit_code"] = 1
            session["error"] = "Session ended without producing a result"
            session["lines"].append(f"\n❌ 会话结束但未产生结果\n")
            _harness_log.error("[Session] %s ended in 'running' state — forced to failed", session_id)
        elif final_status == "failed":
            _harness_log.warning("[Session] %s ended as FAILED: %s", session_id, session.get("error", ""))
        else:
            _harness_log.info("[Session] %s completed successfully", session_id)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


_CLI_INITIAL_TIMEOUT = 120  # seconds to wait for first output from Claude CLI


def _build_claude_env() -> dict:
    """Build env for Claude CLI subprocess from ~/.claude/settings.json.

    The settings.json env block is authoritative — it overrides any
    inherited ANTHROPIC_* vars from the parent process.
    """
    cli_env = _os.environ.copy()
    # Remove stale ANTHROPIC_* vars that may point to Ollama proxy
    for k in list(cli_env.keys()):
        if k.startswith("ANTHROPIC_"):
            del cli_env[k]
    # Load from settings.json (authoritative source)
    try:
        import json as _json
        settings_path = _os.path.expanduser("~/.claude/settings.json")
        if _os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = _json.load(f)
            for k, v in settings.get("env", {}).items():
                cli_env[k] = v
    except Exception:
        pass
    return cli_env


def _run_claude_cli_direct(session: Dict[str, Any], prompt: str, working_dir: str,
                            timeout_sec: int, cfg: Dict) -> None:
    """Run Claude Code CLI directly via ``communicate()``.

    Claude CLI buffers its entire response and writes it on exit,
    so line-by-line ``readline()`` with ``select()`` will appear to hang.
    We use ``communicate(timeout=...)`` instead and stream a progress
    indicator so the UI knows the session is alive.
    """
    claude_path = _resolve_claude_path(cfg.get("claude_code_path", "claude"))
    cli_env = _build_claude_env()

    model = cli_env.get("ANTHROPIC_MODEL", "deepseek-chat")
    base_url = cli_env.get("ANTHROPIC_BASE_URL", "")
    session["lines"].append(f"⚠️ CLI 逃生舱 → {base_url or 'default'} | 模型: {model}\n")
    session["lines"].append(f"⏳ 等待响应...\n\n")

    try:
        proc = subprocess.Popen(
            [claude_path, "-p", prompt, "--bare"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=working_dir, env=cli_env,
        )
        session["proc"] = proc

        # Progress heartbeat: periodically append a dot so the UI
        # knows the session is alive while Claude/DeepSeek is thinking.
        import threading
        stop_heartbeat = threading.Event()

        def _heartbeat():
            tick = 0
            while not stop_heartbeat.wait(10):
                tick += 1
                session["lines"].append(f"⏳ 等待 DeepSeek 响应... ({tick * 10}s)\n")

        hb = threading.Thread(target=_heartbeat, daemon=True)
        hb.start()

        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            session["lines"].append(f"\n⏱️ 会话超时 ({timeout_sec}s)，已自动终止\n")
            session["status"] = "failed"
            session["exit_code"] = 1
            session["error"] = f"Timeout after {timeout_sec}s"
            stop_heartbeat.set()
            hb.join(timeout=2)
            return
        finally:
            stop_heartbeat.set()
            hb.join(timeout=2)

        session["exit_code"] = proc.returncode

        # Append output to session lines
        if stdout:
            for line in stdout.split("\n"):
                session["lines"].append(line + "\n")

        if stderr:
            for line in stderr.strip().split("\n"):
                if line.strip():
                    session["lines"].append(f"⚠️ {line}\n")

        # Validate output
        real_lines_count = 0
        for sline in (stdout or "").split("\n"):
            stripped = sline.strip()
            if stripped:
                real_lines_count += 1

        if real_lines_count < 1:
            session["lines"].append(f"\n❌ Claude 未返回任何内容\n")
            session["status"] = "failed"
            session["exit_code"] = 1
            session["error"] = "Empty response from Claude CLI"
        elif proc.returncode == 0:
            session["status"] = "completed"
        else:
            session["status"] = "failed"

        if proc.returncode != 0 and proc.returncode is not None:
            session["lines"].append(f"\n⚠️ Claude Code 退出码: {proc.returncode}\n")

    except FileNotFoundError:
        session["lines"].append(f"❌ Claude Code CLI not found: {claude_path}\n")
        session["status"] = "failed"
        session["exit_code"] = 1
        session["error"] = "Claude CLI not found"
    except Exception as e:
        session["lines"].append(f"❌ Claude CLI error: {e}\n")
        session["status"] = "failed"
        session["exit_code"] = 1
        session["error"] = str(e)[:200]


def _run_tool_loop(
    session: Dict[str, Any], prompt: str, role: str,
    *, api_key: str, api_base_url: str, model: str,
    max_tokens: int = 65536, temperature: float = 0.2,
    max_iterations: int = 25,
) -> None:
    """Drive a function-calling agent loop. Lets Developer/QA agents read, write,
    and execute the codebase via tool calls instead of single-shot text completion.
    """
    try:
        from agents.runtime import run_tool_loop_sync_with_provider
    except ImportError:
        from .runtime import run_tool_loop_sync_with_provider  # type: ignore

    session["lines"].append(f"🔗 API: {api_base_url}\n模型: {model}\n角色: {role}\n")
    session["lines"].append(f"{'─'*60}\n\n")

    def on_event(kind: str, payload: Dict[str, Any]):
        if kind == "tool_call":
            session["lines"].append(
                f"🔧 调用工具: {payload['name']}({payload['args'][:160]})\n"
            )
        elif kind == "tool_result":
            ok = "✅" if payload.get("ok") else "❌"
            session["lines"].append(
                f"   {ok} {payload['name']}: {payload['summary']}\n"
            )
        elif kind == "model_turn":
            session["lines"].append(
                f"\n🧠 turn#{payload['iteration']} "
                f"({payload['elapsed']}s, {payload['content_chars']}字, "
                f"{payload['tool_call_count']}个工具调用)\n"
            )
        elif kind == "loop_end":
            session["lines"].append(
                f"\n🏁 循环结束: {payload.get('reason')} (turn #{payload.get('iteration')})\n"
            )
        elif kind == "loop_start":
            session["lines"].append(
                f"🚀 工具集: {', '.join(payload['tools'])}\n\n"
            )
        elif kind == "error":
            session["lines"].append(f"💥 错误: {payload.get('error','')}\n")

    system = (
        f"你是 AgentsGroup2026 的 {role} agent。你拥有工具调用能力，"
        f"必须使用工具读真实代码、写真实文件、跑真实测试。"
        "禁止凭空想象 import 路径、类名、属性。"
        "工作流程：\n"
        "1. 先用 list_files / grep / read_file 探索项目结构和现有 API\n"
        "2. 用 run_python 验证你的设想（如导入是否能成功）\n"
        "3. 用 write_file 创建新文件，或 patch_file 修改现有文件\n"
        "4. 修改后用 run_python 或 run_pytest 验证\n"
        "5. 全部完成后调用 finish 工具，附上 summary 和 files_changed\n"
        "重要：禁止整文件覆盖大文件（>200行），改用新建模块或 patch_file。"
    )

    # TG：任务维归因 + 预算作用域（agent/team/session）
    _agent_id = str(getattr(session.get("_agent"), "agent_id", "") or session.get("agent_id") or "")
    _team_id = str(session.get("team_id") or "")
    _task_id = str(session.get("task_id") or _os.environ.get("AG_TASK_ID") or "")
    # 保证 env 中有 task_id，供 tool_loop 归因
    if _task_id:
        _os.environ["AG_TASK_ID"] = _task_id
    result = run_tool_loop_sync_with_provider(
        prompt=prompt,
        api_key=api_key,
        api_base_url=api_base_url,
        model=model,
        role=role, system_prompt=system,
        max_iterations=max_iterations,
        max_tokens=max_tokens, temperature=temperature,
        agent_id=_agent_id,
        team_id=_team_id,
        session_id=str(session.get("session_id") or ""),
        on_event=on_event,
    )

    session["tool_loop_log"] = result.get("log", [])
    session["files_changed"] = result.get("files_changed", [])
    session["loop_summary"] = result.get("summary", "")
    session["loop_ok"] = bool(result.get("ok"))
    session["loop_iterations"] = result.get("iterations", 0)

    if result.get("ok"):
        session["lines"].append(
            f"\n✅ 完成 ({result['iterations']} 轮迭代)\n"
            f"修改文件 {len(result['files_changed'])} 个: "
            f"{', '.join(result['files_changed'])[:200]}\n"
            f"\n📋 总结:\n{result.get('summary', '')[:1500]}\n"
        )
        session["status"] = "completed"
        session["exit_code"] = 0
    else:
        session["lines"].append(
            f"\n❌ 失败: {result.get('error','')}\n"
            f"已完成 {result['iterations']} 轮迭代\n"
        )
        session["status"] = "failed"
        session["exit_code"] = 1
        session["error"] = result.get("error", "")


def _run_openai_compatible(
    session: Dict[str, Any], prompt: str, timeout_sec: int,
    *, api_key: str, api_base_url: str, model: str,
    max_tokens: int = 65536, temperature: float = 0.2,
) -> None:
    """Call any OpenAI-compatible API (DeepSeek V4, OpenAI, etc.) with streaming + retry.

    DeepSeek V4 supports 64K output tokens / 128K context. We default to 64K so
    Developer/Architect agents can emit complete files without truncation.
    """
    import json as _json
    import http.client
    import ssl
    from urllib.parse import urlparse

    parsed = urlparse(api_base_url)
    host = parsed.hostname or "api.deepseek.com"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    use_ssl = parsed.scheme == "https"
    base_path = (parsed.path or "").rstrip("/")

    session["lines"].append(f"🔗 API: {host} | 模型: {model}\n")
    session["lines"].append(f"{'─'*60}\n\n")

    last_error = None
    for attempt in range(_HARNESS_MAX_RETRIES + 1):
        if attempt > 0:
            session["lines"].append(
                f"\n🔄 连接重试 ({attempt}/{_HARNESS_MAX_RETRIES})...\n\n")
            _time.sleep(_HARNESS_RETRY_DELAY * attempt)

        try:
            body = _json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            })
            if use_ssl:
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, port, timeout=timeout_sec, context=ctx)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=timeout_sec)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            conn.request("POST", f"{base_path}/chat/completions", body=body, headers=headers)
            resp = conn.getresponse()

            if resp.status != 200:
                err_body = resp.read().decode("utf-8", errors="replace")[:500]
                last_error = f"API 错误: {resp.status} {resp.reason}\n{err_body}"
                session["lines"].append(f"⚠️ {last_error}\n")
                conn.close()
                continue

            # Stream SSE response
            deadline = _time.time() + timeout_sec
            buffer = ""
            chunk_count = 0
            last_chunk_time = _time.time()
            done = False
            out_chars = 0
            usage_from_api: Dict[str, int] = {}
            while True:
                now = _time.time()
                if now > deadline:
                    session["lines"].append(f"\n\n⏱️ 超时 ({timeout_sec}s)\n")
                    break
                if chunk_count > 0 and (now - last_chunk_time) > _HARNESS_STALL_SEC:
                    session["lines"].append(
                        f"\n\n⚠️ 流式响应停滞 ({_HARNESS_STALL_SEC}s)\n")
                    break
                chunk = resp.read(4096)
                if not chunk:
                    break
                last_chunk_time = _time.time()
                chunk_count += 1
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        done = True
                        break
                    if line.startswith("data: "):
                        try:
                            obj = _json.loads(line[6:])
                            delta = obj.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                out_chars += len(content)
                                session["lines"].append(content)
                            # 部分兼容流在最终 chunk 带 usage
                            u = obj.get("usage") or {}
                            if u:
                                usage_from_api = {
                                    "prompt_tokens": int(u.get("prompt_tokens") or 0),
                                    "completion_tokens": int(u.get("completion_tokens") or 0),
                                    "total_tokens": int(u.get("total_tokens") or 0),
                                }
                        except _json.JSONDecodeError:
                            pass
                if done:
                    break

            session["status"] = "completed"
            session["exit_code"] = 0
            session["lines"].append(f"\n\n{'─'*60}\n")
            session["lines"].append(f"✅ {model} 完成\n")
            # TG：任务维 token 记账（流式 API 无 usage 时用字符粗估）
            if usage_from_api.get("total_tokens"):
                _record_session_token_usage(
                    session, model=model,
                    input_tokens=usage_from_api.get("prompt_tokens", 0),
                    output_tokens=usage_from_api.get("completion_tokens", 0),
                    total_tokens=usage_from_api.get("total_tokens", 0),
                )
            else:
                _inp = _estimate_prompt_tokens(prompt)
                _out = max(1, (out_chars + 1) // 2) if out_chars else 0
                _record_session_token_usage(
                    session, model=model,
                    input_tokens=_inp, output_tokens=_out, total_tokens=_inp + _out,
                )
            conn.close()
            return

        except (ConnectionError, OSError, http.client.HTTPException) as e:
            last_error = str(e)
            session["lines"].append(f"⚠️ 连接错误: {e}\n")
            continue
        except Exception as e:
            session["status"] = "failed"
            session["exit_code"] = 1
            session["error"] = str(e)
            session["lines"].append(f"\n❌ API 错误: {e}\n")
            return

    session["status"] = "failed"
    session["exit_code"] = 1
    session["error"] = last_error or "All retries exhausted"
    session["lines"].append(f"\n❌ 所有重试已耗尽: {last_error}\n")


def _run_ollama_direct(session: Dict[str, Any], prompt: str, timeout_sec: int) -> None:
    """Call Ollama API directly with streaming, retry on transient failures."""
    import json as _json
    import http.client

    # Read config from Claude settings (same source Claude CLI uses)
    ollama_url = "localhost"
    ollama_port = 11434
    model = "qwen3.5-35b-claude"
    try:
        settings_path = _os.path.expanduser("~/.claude/settings.json")
        if _os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = _json.load(f)
            env = settings.get("env", {})
            base_url = env.get("ANTHROPIC_BASE_URL", "")
            if base_url:
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                ollama_url = parsed.hostname or "localhost"
                ollama_port = parsed.port or 11434
            model = env.get("ANTHROPIC_MODEL", "") or settings.get("defaultModel", "") or model
    except Exception:
        pass

    session["lines"].append(f"🔗 Ollama 直连: {ollama_url}:{ollama_port} | 模型: {model}\n")
    session["lines"].append(f"{'─'*60}\n\n")

    # Mark waiting state so harness stall detector knows we're alive
    session["_ollama_waiting"] = True

    last_error = None
    for attempt in range(_HARNESS_MAX_RETRIES + 1):
        if attempt > 0:
            session["lines"].append(
                f"\n🔄 连接重试 ({attempt}/{_HARNESS_MAX_RETRIES})...\n\n")
            _time.sleep(_HARNESS_RETRY_DELAY * attempt)  # Exponential-ish backoff

        try:
            body = _json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            })
            conn = http.client.HTTPConnection(ollama_url, ollama_port, timeout=timeout_sec)
            conn.request("POST", "/v1/chat/completions", body=body,
                          headers={"Content-Type": "application/json"})
            resp = conn.getresponse()

            if resp.status != 200:
                err_body = resp.read().decode("utf-8", errors="replace")[:500]
                # Detect model runner crash specifically
                if "model runner has unexpectedly stopped" in err_body:
                    last_error = f"Ollama model runner 崩溃 — 远程 GPU 服务器需要重启 Ollama"
                    session["lines"].append(f"❌ {last_error}\n")
                    session["lines"].append(f"⚠️ 可能原因: GPU 内存不足或远程服务器资源耗尽\n")
                    # Don't retry — model runner crash won't self-heal
                    session["status"] = "failed"
                    session["exit_code"] = 1
                    session["error"] = last_error
                    conn.close()
                    return
                last_error = f"Ollama API 错误: {resp.status} {resp.reason}\n{err_body}"
                session["lines"].append(f"⚠️ {last_error}\n")
                conn.close()
                continue  # Retry

            # First chunk received — harness stall detector should not kill us
            session.pop("_ollama_waiting", None)

            # Stream SSE response
            deadline = _time.time() + timeout_sec
            buffer = ""
            chunk_count = 0
            last_chunk_time = _time.time()
            done = False
            while True:
                now = _time.time()
                if now > deadline:
                    session["lines"].append(f"\n\n⏱️ 超时 ({timeout_sec}s)\n")
                    break
                # Stall detection within stream (only after first real content chunk)
                if chunk_count > 0 and (now - last_chunk_time) > _HARNESS_STALL_SEC:
                    session["lines"].append(
                        f"\n\n⚠️ 流式响应停滞 ({_HARNESS_STALL_SEC}s)\n")
                    break
                chunk = resp.read(4096)
                if not chunk:
                    break
                last_chunk_time = _time.time()
                chunk_count += 1
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        done = True
                        break
                    if line.startswith("data: "):
                        try:
                            obj = _json.loads(line[6:])
                            delta = obj.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                session["lines"].append(content)
                        except _json.JSONDecodeError:
                            pass
                if done:
                    break

            # Validate: check if stream produced real content
            all_content = "".join(list(session.get("lines", [])))
            _OLLAMA_ERROR_MARKERS = (
                "model runner has unexpectedly stopped",
                "no_proxy",
                "connection refused",
            )
            for marker in _OLLAMA_ERROR_MARKERS:
                if marker in all_content.lower():
                    session["status"] = "failed"
                    session["exit_code"] = 1
                    session["error"] = f"Ollama error detected: {marker}"
                    session["lines"].append(f"\n\n{'─'*60}\n")
                    session["lines"].append(f"❌ Ollama 响应包含错误: {marker}\n")
                    _harness_log.error("[Ollama] Error in response: %s", marker)
                    conn.close()
                    return

            # Count real content characters (exclude framework noise)
            content_chars = sum(len(l) for l in session["lines"]
                                if not any(l.strip().startswith(m) for m in
                                           ("─", "📋", "🤖", "📂", "⏱️", "📝", "⏳", "🔗", "✅", "❌", "⚠️", "🔄")))
            if content_chars < 50:
                session["status"] = "failed"
                session["exit_code"] = 1
                session["error"] = f"Ollama returned insufficient content ({content_chars} chars)"
                session["lines"].append(f"\n\n{'─'*60}\n")
                session["lines"].append(f"❌ Ollama 响应内容不足 ({content_chars} 字符)\n")
                _harness_log.warning("[Ollama] Insufficient content: %d chars", content_chars)
                conn.close()
                return

            session["status"] = "completed"
            session["exit_code"] = 0
            session["lines"].append(f"\n\n{'─'*60}\n")
            session["lines"].append(f"✅ Ollama 直连完成 ({content_chars} 字符)\n")
            conn.close()
            return  # Success — exit retry loop

        except (ConnectionError, OSError, http.client.HTTPException) as e:
            last_error = str(e)
            session["lines"].append(f"⚠️ 连接错误: {e}\n")
            continue  # Retry
        except Exception as e:
            # Non-retryable error
            session["status"] = "failed"
            session["exit_code"] = 1
            session["error"] = str(e)
            session["lines"].append(f"\n❌ Ollama 直连错误: {e}\n")
            return

    # All retries exhausted
    session["status"] = "failed"
    session["exit_code"] = 1
    session["error"] = last_error or "All retries exhausted"
    session["lines"].append(f"\n❌ 所有重试已耗尽: {last_error}\n")


@router.post(
    "/teams/{team_id}/agents/{agent_id}/skills/{skill_name}/execute",
    summary="Execute a skill (e.g. code_implementation via Claude Code)",
)
async def execute_skill(
    team_id: str, agent_id: str, skill_name: str, req: ExecuteSkillRequest
) -> Dict[str, Any]:
    """Invoke a skill execution. For code_implementation, can call Claude Code CLI."""
    agent = _get_agent_or_404(team_id, agent_id)
    sr = _sr()
    skill = sr.get_by_slug(skill_name)
    if skill is None:
        # 回退到团队本地技能（挂在 team.skills、未进全局注册表的技能，如 cat_speak_prompt）
        team = _tm().get_team(team_id)
        if team:
            skill = team.skills.get(skill_name) or next(
                (s for s in team.skills.values()
                 if skill_name in (s.name, s.skill_id, s.slug)),
                None,
            )
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")

    # Merge config
    cfg = dict(skill.config or {})
    cfg.update(req.config_overrides)

    result: Dict[str, Any] = {
        "skill": skill_name,
        "agent_id": agent_id,
        "task_id": req.task_id,
        "executor": cfg.get("executor", "manual"),
        "status": "pending",
    }

    if skill_name == "code_implementation":
        executor = cfg.get("executor", "claude_code")
        if executor == "claude_code":
            # Start streaming session instead of blocking
            import uuid
            session_id = str(uuid.uuid4())[:12]
            _start_claude_session(
                session_id, req.prompt, cfg, agent, req.task_id, team_id=team_id,
            )
            result["status"] = "streaming"
            result["session_id"] = session_id
            result["stream_url"] = f"/api/v1/agent-config/claude-sessions/{session_id}/stream"
        elif executor == "llm_chat":
            result = await _execute_llm_chat(req.prompt, agent, req.task_id)
        else:
            result["status"] = "manual"
            result["instructions"] = skill.instructions
            result["prompt"] = req.prompt
    elif skill_name == "task_decomposition":
        result = await _execute_task_decomposition(req.prompt, agent, team_id, req.task_id)
    else:
        # Generic skill: return instructions for LLM-based execution
        result["status"] = "ready"
        result["instructions"] = skill.instructions
        result["prompt"] = req.prompt

    return result


from starlette.responses import StreamingResponse


@router.get(
    "/claude-sessions/{session_id}/stream",
    summary="SSE stream of Claude Code CLI output",
)
async def stream_claude_session(session_id: str):
    """Server-Sent Events endpoint for live Claude Code output."""
    if session_id not in _claude_sessions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    async def event_gen():
        session = _claude_sessions[session_id]
        sent = 0
        while True:
            lines = list(session["lines"])
            if sent < len(lines):
                for line in lines[sent:]:
                    # SSE format: each line prefixed with "data: "
                    escaped = line.replace("\n", "")
                    yield f"data: {escaped}\n\n"
                sent = len(lines)
            if session["status"] in ("completed", "failed", "error"):
                yield f"event: done\ndata: {{\"status\":\"{session['status']}\",\"exit_code\":{session.get('exit_code', -1)}}}\n\n"
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.get(
    "/claude-sessions/{session_id}",
    summary="Get Claude Code session status and output",
)
async def get_claude_session(session_id: str) -> Dict[str, Any]:
    """Get current session status + all buffered output."""
    if session_id not in _claude_sessions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    s = _claude_sessions[session_id]
    # Check if process died but status wasn't updated
    if s["status"] == "running" and s["proc"] is not None:
        rc = s["proc"].poll()
        if rc is not None:
            s["exit_code"] = rc
            s["status"] = "completed" if rc == 0 else "failed"
            if rc != 0:
                s["lines"].append(f"\n⚠️ Claude Code 退出码: {rc}\n")
    # Sanitize output: strip control chars (keep \n, \t)
    import re
    _ctrl_re = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
    clean_lines = [_ctrl_re.sub('', l) for l in s["lines"]]
    return {
        "session_id": session_id,
        "status": s["status"],
        "task_id": s["task_id"],
        "exit_code": s["exit_code"],
        "error": s["error"],
        "output": clean_lines,
        "line_count": len(clean_lines),
        "elapsed": round(_time.time() - s["started_at"], 1),
    }


@router.get(
    "/tasks/{task_id}/tool-trace",
    summary="Get all tool-call traces for a task pipeline",
)
async def get_task_tool_traces(task_id: str) -> Dict[str, Any]:
    """Return persisted tool-call traces (one JSON per step that ran in tool-loop mode)."""
    pdir = _pipeline_dir(task_id)
    if not _os.path.isdir(pdir):
        return {"task_id": task_id, "traces": [], "count": 0}
    import json as _json_tt
    traces = []
    try:
        for name in sorted(_os.listdir(pdir)):
            if not name.endswith("_tool_trace.json"):
                continue
            fp = _os.path.join(pdir, name)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = _json_tt.load(f)
                traces.append(data)
            except Exception:
                continue
    except Exception:
        pass
    return {"task_id": task_id, "traces": traces, "count": len(traces)}


# ══════════════════════════════════════════════════════════════════
# Trace Summaries & Events (任务追踪面板数据源)
# ══════════════════════════════════════════════════════════════════


def _project_root_path() -> str:
    return _task_trace.project_root_path(__file__)


def _global_trace_events_path() -> str:
    return _task_trace.global_trace_events_path(_project_root_path())


def _build_trace_context(task) -> Dict[str, Any]:
    """从 task metadata 提取 trace_context。"""
    return _task_trace.build_trace_context(task)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    _task_trace.append_jsonl(path, payload)


def _trace_event_payload(task_id: str, evt: Dict[str, Any]) -> Dict[str, Any]:
    task = _te().get_task(task_id)
    return _task_trace.trace_event_payload(task_id, evt, task)


def _persist_trace_event(task_id: str, evt: Dict[str, Any]) -> None:
    task = _te().get_task(task_id)
    _task_trace.persist_trace_event(
        task_id,
        evt,
        task=task,
        global_path=_global_trace_events_path(),
    )


def _workflow_summary(workflow: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _task_trace.workflow_summary(workflow)


def _collect_changed_files(workflow: List[Dict[str, Any]]) -> List[str]:
    return _task_trace.collect_changed_files(workflow)


def _extract_test_result(workflow: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _task_trace.extract_test_result(workflow)


def _build_diff_preview(workflow: List[Dict[str, Any]]) -> tuple[Dict[str, List[str]], str]:
    return _task_trace.build_diff_preview(workflow, repo_root=_project_root_path())


def _attach_task_execution_artifacts(task: AgentTask) -> Dict[str, Any]:
    meta = task.metadata or {}
    artifact_dir = str(meta.get("pipeline_dir") or _pipeline_dir(task.task_id))
    return _task_trace.attach_task_execution_artifacts(
        task,
        artifact_dir=artifact_dir,
        repo_root=_project_root_path(),
    )


def _linked_evolution_items(task: AgentTask) -> List[Dict[str, Any]]:
    try:
        from agent_team_api import _evolution_engine
    except Exception:
        _evolution_engine = None
    if not _evolution_engine:
        return []
    items = []
    for item in _evolution_engine.evolution_items.values():
        if task.task_id not in item.source_task_ids:
            continue
        items.append({
            "id": item.id,
            "status": item.status,
            "title": item.title,
            "verify_test_name": item.verify_test_name,
            "verify_result": item.verify_result,
            "verify_detail": item.verify_detail,
            "retry_count": item.retry_count,
            "max_retries": item.max_retries,
        })
    return items


async def _broadcast_task_verification_state(task: AgentTask, synced_item_ids: List[str]) -> None:
    meta = task.metadata or {}
    discussion_id = meta.get("discussion_id", "")
    if not discussion_id:
        return
    try:
        from agent_team_api import _evolution_engine
        from .plaza_routes import _build_discussion_verification_state_payload
        from .plaza_engine import get_plaza_engine

        if not _evolution_engine:
            return
        payload = _build_discussion_verification_state_payload(
            _evolution_engine,
            plaza_id=meta.get("plaza_id", ""),
            discussion_id=discussion_id,
            trigger="task_finalized",
            synced_item_ids=synced_item_ids,
        )
        await get_plaza_engine()._broadcast(discussion_id, payload)
        _emit_pipeline_event(task.task_id, "verification_state_broadcasted", {
            "discussion_id": discussion_id,
            "synced_item_ids": synced_item_ids,
        })
    except Exception:
        return


async def _finalize_task_terminal_state(task: AgentTask) -> Optional[AgentTask]:
    artifacts = _attach_task_execution_artifacts(task)
    terminal_state = _task_trace.terminal_sync_state(artifacts)
    if terminal_state["task_status"] == "failed":
        task.status = TaskStatus.FAILED
    else:
        task.status = TaskStatus.COMPLETED
    task.error = terminal_state["task_error"]
    task.completed_at = datetime.now(timezone.utc).isoformat()
    task.result = artifacts

    synced_item_ids: List[str] = []
    try:
        from agent_team_api import _evolution_engine

        if _evolution_engine:
            sync_kwargs = _task_trace.evolution_sync_kwargs(
                task,
                artifacts,
                sync_status=terminal_state["sync_status"],
            )
            synced_item_ids = _evolution_engine.sync_task_outcome(
                sync_kwargs.pop("task_id"),
                **sync_kwargs,
            )
            if synced_item_ids:
                task.metadata["evolution_item_ids"] = synced_item_ids
    except Exception:
        synced_item_ids = []

    _emit_pipeline_event(task.task_id, "task_finalized", {
        "status": task.status.value,
        "changed_files": artifacts["changed_files"],
        "synced_item_ids": synced_item_ids,
    })
    if synced_item_ids:
        _emit_pipeline_event(task.task_id, "evolution_synced", {"synced_item_ids": synced_item_ids})
        await _broadcast_task_verification_state(task, synced_item_ids)
    _te()._store.save_task(task)
    return task


def _task_trace_summary(task: AgentTask) -> Dict[str, Any]:
    events = [_trace_event_payload(task.task_id, evt) for evt in _pipeline_events.get(task.task_id, [])]
    return _task_trace.task_trace_summary(task, events, _linked_evolution_items(task))


def _get_team_task_or_404(team_id: str, task_id: str) -> AgentTask:
    task = _te().get_task(task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("/teams/{team_id}/tasks/{task_id}/trace-summary", summary="Task trace summary")
def get_task_trace_summary(team_id: str, task_id: str) -> Dict[str, Any]:
    return _task_trace_summary(_get_team_task_or_404(team_id, task_id))


@router.get("/teams/{team_id}/tasks/{task_id}/trace-events", summary="Task trace events")
def get_task_trace_events(team_id: str, task_id: str) -> Dict[str, Any]:
    task = _get_team_task_or_404(team_id, task_id)
    events = [_trace_event_payload(task_id, evt) for evt in _pipeline_events.get(task_id, [])]
    return _task_trace.task_trace_events_payload(task, events)


@router.get("/teams/{team_id}/discussions/{discussion_id}/trace-summary", summary="Discussion trace summary")
def get_discussion_trace_summary(team_id: str, discussion_id: str) -> Dict[str, Any]:
    tasks = [
        task
        for task in _te().list_tasks()
        if task.team_id == team_id and (task.metadata or {}).get("discussion_id") == discussion_id
    ]
    return _task_trace.discussion_trace_summary_payload(
        team_id=team_id,
        discussion_id=discussion_id,
        task_summaries=[_task_trace_summary(task) for task in tasks],
    )


@router.get("/traces/recent", summary="Recent trace summaries")
def get_recent_trace_summaries(
    limit: int = Query(default=20, ge=1, le=500),
    team_id: str = Query(default=""),
    source: str = Query(default=""),
) -> Dict[str, Any]:
    """返回最近的任务追踪摘要（按时间倒序）。"""
    engine = _te()
    all_tasks = engine.list_tasks() if hasattr(engine, "list_tasks") else []
    return _task_trace.recent_trace_summaries(
        all_tasks,
        limit=limit,
        team_id=team_id,
        source=source,
    )


@router.get("/traces/recent-events", summary="Recent trace events")
def get_recent_trace_events(
    limit: int = Query(default=50, ge=1, le=500),
    team_id: str = Query(default=""),
    source: str = Query(default=""),
    event_type: str = Query(default=""),
) -> Dict[str, Any]:
    """返回最近的管道事件（按时间倒序）。"""
    return _task_trace.recent_trace_events(
        _pipeline_events,
        _te().get_task,
        limit=limit,
        team_id=team_id,
        source=source,
        event_type=event_type,
    )


@router.get("/traces/log-tail", summary="Tail persisted trace event log")
def get_trace_log_tail(
    limit: int = Query(default=100, ge=1, le=5000),
    event_type: str = Query(default=""),
) -> Dict[str, Any]:
    return _task_trace.trace_log_tail(
        _global_trace_events_path(),
        limit=limit,
        event_type=event_type,
    )


@router.get("/traces/export", summary="Export trace data as NDJSON")
def export_traces(
    team_id: str = Query(default=""),
    source: str = Query(default=""),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """导出追踪数据为 NDJSON 流。"""
    from fastapi.responses import StreamingResponse

    def gen():
        summaries = get_recent_trace_summaries(limit=limit, team_id=team_id, source=source)
        events = get_recent_trace_events(limit=limit * 5, team_id=team_id, source=source)
        yield from _task_trace.iter_trace_export_lines(summaries, events)

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Content-Disposition": "attachment; filename=traces.ndjson"})


@router.get("/traces/events/export", summary="Export trace events as NDJSON")
def export_trace_events(
    limit: int = Query(default=500, ge=1, le=5000),
    team_id: str = Query(default=""),
    source: str = Query(default=""),
    event_type: str = Query(default=""),
):
    from fastapi.responses import StreamingResponse

    def gen():
        events = get_recent_trace_events(
            limit=limit,
            team_id=team_id,
            source=source,
            event_type=event_type,
        )
        yield from _task_trace.iter_trace_event_export_lines(events)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post(
    "/claude-sessions/{session_id}/stop",
    summary="Stop a running Claude Code session",
)
async def stop_claude_session(session_id: str) -> Dict[str, Any]:
    """Kill the Claude Code subprocess."""
    if session_id not in _claude_sessions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    s = _claude_sessions[session_id]
    if s["proc"] and s["status"] == "running":
        try:
            s["proc"].kill()
        except Exception:
            pass
        s["status"] = "stopped"
        s["lines"].append("\n⛔ 会话已手动停止\n")
    return {"session_id": session_id, "status": s["status"]}


@router.get(
    "/harness/status",
    summary="Get workflow harness status",
)
async def harness_status() -> Dict[str, Any]:
    """Show active harness monitors and session summary."""
    monitors = {}
    for tid, thr in _harness_threads.items():
        monitors[tid] = {"alive": thr.is_alive()}
    sessions = {}
    for sid, s in _claude_sessions.items():
        sessions[sid] = {
            "status": s["status"],
            "task_id": s["task_id"],
            "line_count": len(s["lines"]),
            "elapsed": round(_time.time() - s["started_at"], 1),
        }
    return {
        "monitors": monitors,
        "sessions": sessions,
        "config": {
            "poll_sec": _HARNESS_POLL_SEC,
            "max_retries": _HARNESS_MAX_RETRIES,
            "stall_sec": _HARNESS_STALL_SEC,
            "auto_advance": _HARNESS_AUTO_ADVANCE,
        },
    }


# ── Pipeline status + SSE endpoints ──────────────────────────────────────


@router.get(
    "/tasks/{task_id}/pipeline/status",
    summary="Get pipeline execution status (lightweight, for bridge chat polling)",
)
def get_pipeline_status(task_id: str) -> Dict[str, Any]:
    """Return current pipeline status: steps with their statuses, active step, rewind count.
    Designed for the bridge chat widget to poll cheaply."""
    engine = _te()
    task = engine.get_task(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    wf = (task.metadata or {}).get("workflow", [])
    steps = []
    active_step = None
    for s in wf:
        step_info = {
            "key": s.get("key", ""),
            "label": s.get("label", ""),
            "status": s.get("status", "pending"),
        }
        if s.get("error"):
            step_info["error"] = str(s["error"])[:200]
        if s.get("deliverable_count"):
            step_info["files"] = s["deliverable_count"]
        steps.append(step_info)
        if s.get("status") == "active":
            active_step = s.get("key")
    md = task.metadata or {}
    return {
        "task_id": task_id,
        "task_status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "title": task.title,
        "steps": steps,
        "active_step": active_step,
        "rewinds": int(md.get("pipeline_rewinds", 0)),
        "max_rewinds": _PIPELINE_MAX_REWINDS,
        "pipeline_failed_reason": md.get("pipeline_failed_reason"),
        "events": _pipeline_events.get(task_id, [])[-20:],
    }


@router.get(
    "/tasks/{task_id}/pipeline/events",
    summary="SSE stream of pipeline events for a task",
)
async def pipeline_events_sse(task_id: str):
    """Server-Sent Events stream for real-time pipeline progress.
    The bridge chat subscribes to this after dispatching a task."""
    from starlette.responses import StreamingResponse
    import json as _sse_json

    engine = _te()
    task = engine.get_task(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _pipeline_subscribers.setdefault(task_id, []).append(queue)

    async def event_generator():
        try:
            # Send current state as first event
            wf = (task.metadata or {}).get("workflow", [])
            init = {
                "type": "init",
                "task_status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "steps": [{"key": s.get("key"), "label": s.get("label"), "status": s.get("status")} for s in wf],
            }
            yield f"data: {_sse_json.dumps(init, ensure_ascii=False)}\n\n"

            # Also replay recent events
            for evt in _pipeline_events.get(task_id, [])[-10:]:
                yield f"data: {_sse_json.dumps(evt, ensure_ascii=False)}\n\n"

            # Stream new events
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {_sse_json.dumps(evt, ensure_ascii=False)}\n\n"
                    # Terminal events
                    if evt.get("type") in ("pipeline_complete", "pipeline_failed"):
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
                    # Check if task is terminal
                    t = engine.get_task(task_id)
                    if t and hasattr(t.status, "value") and t.status.value in ("completed", "failed", "cancelled"):
                        final = {"type": "pipeline_complete", "task_status": t.status.value}
                        yield f"data: {_sse_json.dumps(final, ensure_ascii=False)}\n\n"
                        break
        finally:
            # Unsubscribe
            subs = _pipeline_subscribers.get(task_id, [])
            if queue in subs:
                subs.remove(queue)
            if not subs:
                _pipeline_subscribers.pop(task_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/harness/gc",
    summary="Run session garbage collection",
)
async def run_session_gc() -> Dict[str, Any]:
    """Manually trigger GC of expired sessions."""
    removed = _gc_sessions()
    return {"removed": removed, "remaining": len(_claude_sessions)}


async def _execute_llm_chat(prompt: str, agent, task_id: str) -> Dict[str, Any]:
    """Execute code_implementation via LLM chat."""
    from .chat_harness import get_chat_harness
    harness = get_chat_harness()
    try:
        result = await harness.chat(
            prompt,
            agent_id=agent.agent_id,
            session_id=f"skill_code_{task_id}",
            system_prompt=f"你是 {agent.name}，负责代码实现。根据需求编写代码，给出文件路径和完整代码。",
        )
        return {
            "skill": "code_implementation",
            "executor": "llm_chat",
            "task_id": task_id,
            "status": "completed" if not result.error else "failed",
            "output": result.response[:3000] if result.response else "",
            "error": result.error or "",
            "model": result.model,
        }
    except Exception as e:
        return {"skill": "code_implementation", "executor": "llm_chat", "task_id": task_id, "status": "error", "error": str(e)}


async def _execute_task_decomposition(prompt: str, agent, team_id: str, parent_task_id: str) -> Dict[str, Any]:
    """PM decomposes a task into subtasks and submits them to TaskEngine."""
    from .chat_harness import get_chat_harness
    harness = get_chat_harness()

    decompose_prompt = (
        f"你是项目经理 {agent.name}。请将以下任务分解为可执行的子任务。\n\n"
        f"任务: {prompt}\n\n"
        f"请以 JSON 数组格式返回子任务，每个子任务包含:\n"
        f'  {{"title": "子任务标题", "agent_id": "目标agent_id", "priority": 2, "description": "描述"}}\n\n'
        f"可用 Agent: build_pm, build_researcher, build_architect, build_developer, build_tester, build_deployer, build_doc_writer\n"
        f"只返回 JSON 数组，不要其他内容。"
    )

    subtasks_created = []
    try:
        result = await harness.chat(
            decompose_prompt,
            agent_id=agent.agent_id,
            session_id=f"skill_decompose_{parent_task_id}",
            system_prompt="你是任务分解专家。只返回 JSON 数组。",
        )
        if result.response:
            import json, re
            # Extract JSON array from response
            match = re.search(r'\[.*\]', result.response, re.DOTALL)
            if match:
                items = json.loads(match.group())
                engine = _te()
                if not engine._running:
                    await engine.start()
                for item in items[:10]:
                    task = AgentTask(
                        agent_id=item.get("agent_id", ""),
                        team_id=team_id,
                        title=item.get("title", "子任务"),
                        description=item.get("description", ""),
                        priority=item.get("priority", 2),
                        metadata={"parent_task": parent_task_id, "auto_decomposed": True},
                    )
                    await engine.submit_task(task)
                    subtasks_created.append(task.to_dict())
    except Exception:
        pass

    return {
        "skill": "task_decomposition",
        "task_id": parent_task_id,
        "status": "completed" if subtasks_created else "no_subtasks",
        "subtasks": subtasks_created,
        "count": len(subtasks_created),
    }


@router.get(
    "/skills/{skill_name}/config-schema",
    summary="Get skill config schema for UI rendering",
)
def get_skill_config_schema(skill_name: str) -> Dict[str, Any]:
    """Return the config schema and current config for a skill."""
    sr = _sr()
    skill = sr.get_by_slug(skill_name)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return {
        "skill_name": skill.name,
        "config_schema": skill.config_schema,
        "config": skill.config,
        "instructions": skill.instructions,
    }


@router.put(
    "/skills/{skill_name}/config",
    summary="Update skill configuration",
)
def update_skill_config(skill_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Update a skill's runtime configuration."""
    sr = _sr()
    skill = sr.get_by_slug(skill_name)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found")
    skill.config.update(config)
    return {"skill_name": skill.name, "config": skill.config}


@router.get(
    "/teams/{team_id}/agents/{agent_id}/tasks",
    summary="List tasks assigned to an agent",
)
def list_agent_tasks(team_id: str, agent_id: str) -> List[Dict[str, Any]]:
    _get_team_or_404(team_id)
    _get_agent_or_404(team_id, agent_id)
    return [
        t.to_dict()
        for t in _te().get_agent_tasks(agent_id)
        if t.team_id == team_id
    ]


@router.get("/tasks/stats", summary="Task engine statistics")
def task_engine_stats() -> Dict[str, Any]:
    return _te().stats()


class CrossTeamTaskRequest(BaseModel):
    """Submit a task from one team to another."""
    target_team_id: str = Field(..., min_length=1)
    target_agent_id: str = ""
    source_team_id: str = ""
    source_agent_id: str = ""
    title: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    priority: int = Field(default=2, ge=0, le=3)
    original_message: str = ""


@router.post(
    "/cross-team/tasks",
    summary="Submit a cross-team task (e.g. execution→build)",
    status_code=status.HTTP_201_CREATED,
)
async def submit_cross_team_task(req: CrossTeamTaskRequest) -> Dict[str, Any]:
    """Create a task in the target team, recording the source team/agent."""
    _get_team_or_404(req.target_team_id)
    if req.target_agent_id:
        target = _tm().get_agent(req.target_team_id, req.target_agent_id)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Target agent not found")

    engine = _te()
    if not engine._running:
        await engine.start()

    task = AgentTask(
        agent_id=req.target_agent_id or "",
        team_id=req.target_team_id,
        title=req.title,
        description=req.description or f"[跨团队任务] 来源: {req.source_agent_id or req.source_team_id}\n原始消息: {req.original_message}",
        priority=req.priority,
        metadata={
            "cross_team": True,
            "source_team": req.source_team_id,
            "source_agent": req.source_agent_id,
            "original_message": req.original_message,
        },
    )
    # Auto-generate workflow steps for cross-team tasks
    wf = _generate_workflow(task, req.target_team_id)
    if wf:
        task.metadata["workflow"] = wf
    await engine.submit_task(task)
    return task.to_dict()


# =========================================================================
# Memory Files & Soul.md  (Clawith-style persistent memory)
# =========================================================================


class MemoryFileRequest(BaseModel):
    filename: str = Field(..., max_length=128)
    content: str = Field(default="")


class SoulUpdateRequest(BaseModel):
    content: str = Field(default="")


@router.get(
    "/teams/{team_id}/agents/{agent_id}/memory",
    summary="List agent memory files",
)
def list_memory_files(team_id: str, agent_id: str) -> List[Dict[str, Any]]:
    agent = _get_agent_or_404(team_id, agent_id)
    files = agent.metadata.get("memory_files", {})
    return [
        {"filename": k, "size": len(v), "size_display": _fmt_size(len(v))}
        for k, v in files.items()
    ]


@router.get(
    "/teams/{team_id}/agents/{agent_id}/memory/{filename}",
    summary="Read a memory file",
)
def read_memory_file(team_id: str, agent_id: str, filename: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    files = agent.metadata.get("memory_files", {})
    if filename not in files:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Memory file not found")
    return {"filename": filename, "content": files[filename], "size": len(files[filename])}


@router.put(
    "/teams/{team_id}/agents/{agent_id}/memory/{filename}",
    summary="Create or update a memory file",
)
def write_memory_file(
    team_id: str, agent_id: str, filename: str, req: SoulUpdateRequest
) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if "memory_files" not in agent.metadata:
        agent.metadata["memory_files"] = {}
    agent.metadata["memory_files"][filename] = req.content
    return {"filename": filename, "size": len(req.content), "status": "saved"}


@router.delete(
    "/teams/{team_id}/agents/{agent_id}/memory/{filename}",
    summary="Delete a memory file",
)
def delete_memory_file(team_id: str, agent_id: str, filename: str) -> Dict[str, str]:
    agent = _get_agent_or_404(team_id, agent_id)
    files = agent.metadata.get("memory_files", {})
    if filename not in files:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Memory file not found")
    del files[filename]
    return {"status": "deleted", "filename": filename}


@router.get(
    "/teams/{team_id}/agents/{agent_id}/soul",
    summary="Get agent Soul.md content",
)
def get_soul(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    soul = agent.metadata.get("soul_md", "")
    return {"content": soul, "size": len(soul)}


@router.put(
    "/teams/{team_id}/agents/{agent_id}/soul",
    summary="Update agent Soul.md content",
)
def update_soul(team_id: str, agent_id: str, req: SoulUpdateRequest) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.metadata["soul_md"] = req.content
    return {"status": "saved", "size": len(req.content)}


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


# ══════════════════════════════════════════════════════════════
# OpenClaw Agent Import
# ══════════════════════════════════════════════════════════════


class ImportOpenClawRequest(BaseModel):
    name: str = Field(..., min_length=1)
    role: str = ""
    openclaw_url: str = ""
    openclaw_token: str = ""
    openclaw_agent_id: str = ""
    visibility: str = "public"
    soul_content: str = ""
    model_id: str = ""


@router.post(
    "/teams/{team_id}/agents/import-openclaw",
    summary="Import an OpenClaw Agent",
    status_code=status.HTTP_201_CREATED,
)
def import_openclaw_agent(team_id: str, req: ImportOpenClawRequest) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    agent = AgentProfile(
        name=req.name,
        role=req.role,
        model_id=req.model_id,
    )
    agent.metadata["openclaw"] = {
        "url": req.openclaw_url,
        "token": req.openclaw_token[:8] + "***" if len(req.openclaw_token) > 8 else "***" if req.openclaw_token else "",
        "token_set": bool(req.openclaw_token),
        "agent_id": req.openclaw_agent_id,
        "connected": bool(req.openclaw_url and req.openclaw_token),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    if req.soul_content:
        agent.metadata["soul_md"] = req.soul_content
    agent.metadata["visibility"] = req.visibility
    ok = _tm().add_agent_to_team(team_id, agent)
    if not ok:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add agent"
        )
    return agent.to_dict()


@router.get(
    "/teams/{team_id}/agents/{agent_id}/openclaw-status",
    summary="Get OpenClaw connection status",
)
def get_openclaw_status(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    return agent.metadata.get("openclaw", {"connected": False})

@router.post(
    "/teams/{team_id}/agents/{agent_id}/sync-openclaw",
    summary="Sync OpenClaw Agent",
)
def sync_openclaw_agent(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if "openclaw" not in agent.metadata:
        agent.metadata["openclaw"] = {"connected": False}
    agent.metadata["openclaw"]["last_sync"] = datetime.now(timezone.utc).isoformat()
    return agent.metadata["openclaw"]


# ══════════════════════════════════════════════════════════════
# External Team Import (整队导入)
# ══════════════════════════════════════════════════════════════

MAX_IMPORT_AGENTS = 100
MAX_IMPORT_MODELS = 50


def _mask_token(token: str) -> str:
    """凭据脱敏：只回显前 4 位，其余固定掩码，避免密钥经响应体外泄。"""
    if not token:
        return ""
    return f"{token[:4]}***" if len(token) > 4 else "***"


class ImportTeamAgentItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    role: str = ""
    description: str = ""
    model_id: str = ""
    system_prompt: str = ""
    tools: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    openclaw_agent_id: str = ""


class ImportTeamModelItem(BaseModel):
    provider: str = "anthropic"
    name: str = Field(..., min_length=1, max_length=128)
    max_tokens: int = Field(default=8192, ge=1, le=200000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    api_base_url: str = ""


class ImportTeamRequest(BaseModel):
    """整支外部智能体团队导入请求。"""

    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    source: str = "json"  # json | openclaw
    openclaw_url: str = ""
    openclaw_token: str = ""
    agents: List[ImportTeamAgentItem] = Field(default_factory=list)
    models: List[ImportTeamModelItem] = Field(default_factory=list)
    workflow_mode: str = "single"


@router.post(
    "/teams/import",
    summary="Import an external agent team",
    status_code=status.HTTP_201_CREATED,
)
def import_team(req: ImportTeamRequest) -> Dict[str, Any]:
    """把外部团队包（JSON 或 OpenClaw 网关）落成本地团队。

    整支导入是原子的：任一成员构造失败即回滚已创建的团队，避免留下半成品。
    """
    if not req.agents:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="团队至少需要包含一个智能体"
        )
    if len(req.agents) > MAX_IMPORT_AGENTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"智能体数量超限（{len(req.agents)} > {MAX_IMPORT_AGENTS}）",
        )
    if len(req.models) > MAX_IMPORT_MODELS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"模型数量超限（{len(req.models)} > {MAX_IMPORT_MODELS}）",
        )
    source = req.source if req.source in ("json", "openclaw") else "json"
    if source == "openclaw" and not req.openclaw_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="OpenClaw 来源必须提供 Gateway URL"
        )

    # 同名团队自动改名，不覆盖既有团队
    existing_names = {t.name for t in _tm().list_teams()}
    final_name = req.name
    if final_name in existing_names:
        suffix = 2
        while f"{final_name} ({suffix})" in existing_names:
            suffix += 1
        final_name = f"{final_name} ({suffix})"

    team = _tm().create_team(name=final_name, description=req.description)
    warnings: List[str] = []
    try:
        team.workflow_mode = req.workflow_mode
        team.metadata["import"] = {
            "source": source,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "original_name": req.name,
            "openclaw_url": req.openclaw_url,
            "openclaw_token": _mask_token(req.openclaw_token),
            "openclaw_token_set": bool(req.openclaw_token),
        }

        model_name_to_id: Dict[str, str] = {}
        for m in req.models:
            cfg = ModelConfig(
                provider=m.provider,
                name=m.name,
                max_tokens=m.max_tokens,
                temperature=m.temperature,
                api_base_url=m.api_base_url,
            )
            team.add_model(cfg)
            model_name_to_id[m.name] = cfg.model_id

        for item in req.agents:
            resolved_model = model_name_to_id.get(item.model_id, item.model_id)
            if item.model_id and resolved_model == item.model_id and item.model_id not in team.models:
                warnings.append(f"成员「{item.name}」引用了未随包提供的模型 {item.model_id}")
            agent = AgentProfile(
                name=item.name,
                role=item.role,
                description=item.description,
                model_id=resolved_model,
                system_prompt=item.system_prompt,
                tools=list(item.tools),
                skills=list(item.skills),
            )
            agent.metadata["import_source"] = source
            if source == "openclaw":
                agent.metadata["openclaw"] = {
                    "url": req.openclaw_url,
                    "token": _mask_token(req.openclaw_token),
                    "token_set": bool(req.openclaw_token),
                    "agent_id": item.openclaw_agent_id,
                    "connected": bool(req.openclaw_url and req.openclaw_token),
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
            team.add_agent(agent)

        _tm()._persist()
    except HTTPException:
        _tm().delete_team(team.team_id)
        raise
    except Exception as e:
        _tm().delete_team(team.team_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"团队导入失败已回滚: {e}"
        ) from e

    return {
        "team": team.to_dict(),
        "report": {
            "team_id": team.team_id,
            "name": final_name,
            "renamed": final_name != req.name,
            "source": source,
            "agents_imported": len(req.agents),
            "models_imported": len(req.models),
            "warnings": warnings,
        },
    }


# ══════════════════════════════════════════════════════════════
# Hermes Agent API — Research Agent Management
# Inspired by NousResearch/hermes-agent architecture
# ══════════════════════════════════════════════════════════════


class CreateHermesResearcherRequest(BaseModel):
    """Create a Hermes-style research agent."""
    name: str = Field(default="Researcher", min_length=1, max_length=128)
    distribution: str = "general_research"
    soul_md: str = ""
    can_delegate: bool = True


class UpdateHermesConfigRequest(BaseModel):
    """Update Hermes agent configuration."""
    max_iterations: int = Field(default=90, ge=1, le=500)
    memory_enabled: bool = True
    session_search_enabled: bool = True
    skill_auto_create: bool = True
    soul_md: str = ""
    can_delegate: bool = True
    max_subagents: int = Field(default=3, ge=0, le=10)
    distribution: str = ""
    enabled_toolsets: List[str] = Field(default_factory=list)
    disabled_toolsets: List[str] = Field(default_factory=list)


@router.post(
    "/teams/{team_id}/agents/create-hermes-researcher",
    summary="Create a Hermes-style research agent",
    status_code=status.HTTP_201_CREATED,
)
def create_hermes_researcher_endpoint(
    team_id: str, req: CreateHermesResearcherRequest
) -> Dict[str, Any]:
    _get_team_or_404(team_id)
    agent = create_hermes_researcher(
        name=req.name,
        distribution=req.distribution,
        soul_md=req.soul_md,
        can_delegate=req.can_delegate,
    )
    ok = _tm().add_agent_to_team(team_id, agent)
    if not ok:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add agent"
        )
    return agent.to_dict()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/hermes-config",
    summary="Update Hermes agent configuration",
)
def update_hermes_config(
    team_id: str, agent_id: str, req: UpdateHermesConfigRequest
) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if agent.hermes_config is None:
        agent.hermes_config = HermesAgentConfig()

    hc = agent.hermes_config
    hc.max_iterations = req.max_iterations
    hc.iteration_budget = req.max_iterations
    hc.memory_enabled = req.memory_enabled
    hc.session_search_enabled = req.session_search_enabled
    hc.skill_auto_create = req.skill_auto_create
    hc.can_delegate = req.can_delegate
    hc.max_subagents = req.max_subagents

    if req.soul_md:
        hc.soul_md = req.soul_md

    if req.distribution:
        dist = RESEARCH_TOOLSET_DISTRIBUTIONS.get(req.distribution)
        if dist:
            hc.toolset_distribution = ToolsetDistribution(
                name=req.distribution,
                description=dist["description"],
                toolsets=dict(dist["toolsets"]),
            )
            hc.enabled_toolsets = list(dist["toolsets"].keys())

    if req.enabled_toolsets:
        hc.enabled_toolsets = list(req.enabled_toolsets)
    if req.disabled_toolsets:
        hc.disabled_toolsets = list(req.disabled_toolsets)

    # Rebuild system prompt with new config
    active_toolsets = sample_toolsets(hc.toolset_distribution.name)
    agent.system_prompt = build_research_system_prompt(agent, active_toolsets)
    agent.tools = resolve_tools(active_toolsets)

    return agent.to_dict()


@router.get(
    "/teams/{team_id}/agents/{agent_id}/hermes-config",
    summary="Get Hermes agent configuration",
)
def get_hermes_config(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if agent.hermes_config is None:
        return {"is_hermes_agent": False}
    return {
        "is_hermes_agent": True,
        **agent.hermes_config.to_dict(),
    }


@router.get(
    "/hermes/distributions",
    summary="List available Hermes toolset distributions",
)
def list_hermes_distributions() -> Dict[str, Any]:
    return get_research_distributions()


@router.get(
    "/hermes/toolsets",
    summary="List available Hermes toolsets",
)
def list_hermes_toolsets() -> Dict[str, Any]:
    return get_hermes_toolsets()


@router.post(
    "/teams/{team_id}/agents/{agent_id}/hermes-sample-toolsets",
    summary="Sample toolsets from distribution (probabilistic)",
)
def hermes_sample_toolsets(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if agent.hermes_config is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Agent is not a Hermes agent"
        )
    dist_name = agent.hermes_config.toolset_distribution.name
    sampled = sample_toolsets(dist_name)
    resolved = resolve_tools(sampled)
    return {
        "distribution": dist_name,
        "sampled_toolsets": sampled,
        "resolved_tools": resolved,
    }


@router.post(
    "/teams/{team_id}/agents/{agent_id}/hermes-rebuild-prompt",
    summary="Rebuild Hermes agent system prompt with fresh toolset sample",
)
def hermes_rebuild_prompt(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if agent.hermes_config is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Agent is not a Hermes agent"
        )
    active_toolsets = sample_toolsets(agent.hermes_config.toolset_distribution.name)
    agent.system_prompt = build_research_system_prompt(agent, active_toolsets)
    agent.tools = resolve_tools(active_toolsets)
    return {
        "active_toolsets": active_toolsets,
        "tools": agent.tools,
        "prompt_length": len(agent.system_prompt),
    }


@router.put(
    "/teams/{team_id}/agents/{agent_id}/soul",
    summary="Update agent SOUL.md (Hermes persona)",
)
def update_agent_soul(team_id: str, agent_id: str, req: "SoulUpdateRequest") -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if agent.hermes_config is None:
        agent.hermes_config = HermesAgentConfig()
    agent.hermes_config.soul_md = req.content
    # Rebuild prompt with new soul
    active_toolsets = sample_toolsets(agent.hermes_config.toolset_distribution.name)
    agent.system_prompt = build_research_system_prompt(agent, active_toolsets)
    return {"soul_md_length": len(req.content), "prompt_rebuilt": True}


@router.post(
    "/teams/{team_id}/agents/{agent_id}/convert-to-hermes",
    summary="Convert a standard agent to Hermes-style",
)
def convert_to_hermes(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    if agent.hermes_config is not None:
        return {"status": "already_hermes", "agent_id": agent_id}

    # Determine distribution based on template type
    dist_map = {
        AgentTemplateType.RESEARCHER: "general_research",
        AgentTemplateType.ANALYST: "compliance_audit",
        AgentTemplateType.NAVIGATOR: "colregs_analysis",
        AgentTemplateType.ENGINEER: "ship_design_review",
    }
    dist = dist_map.get(agent.template_type, "general_research")

    dist_data = RESEARCH_TOOLSET_DISTRIBUTIONS[dist]
    agent.hermes_config = HermesAgentConfig(
        toolset_distribution=ToolsetDistribution(
            name=dist,
            description=dist_data["description"],
            toolsets=dict(dist_data["toolsets"]),
        ),
        enabled_toolsets=list(dist_data["toolsets"].keys()),
        can_delegate=True,
    )
    agent.template_type = AgentTemplateType.HERMES_RESEARCHER

    # Rebuild prompt
    active_toolsets = sample_toolsets(dist)
    agent.system_prompt = build_research_system_prompt(agent, active_toolsets)
    agent.tools = resolve_tools(active_toolsets)

    return {"status": "converted", "agent_id": agent_id, "distribution": dist}


# ══════════════════════════════════════════════════════════════
# P3 — Agent Visibility, Activity Logging, Metrics
# ══════════════════════════════════════════════════════════════


class UpdateVisibilityRequest(BaseModel):
    visibility: str = "public"
    default_access: str = "use"


class AgentLogEntry(BaseModel):
    action: str = ""
    detail: str = ""


# In-memory activity logs (per agent_id)
_agent_logs: Dict[str, List[Dict[str, Any]]] = {}
# In-memory agent metrics (per agent_id)
_agent_metrics: Dict[str, Dict[str, Any]] = {}


def _log_agent_action(agent_id: str, action: str, detail: str = "") -> Dict[str, Any]:
    """Record an activity log entry for an agent."""
    if agent_id not in _agent_logs:
        _agent_logs[agent_id] = []
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
    }
    _agent_logs[agent_id].append(entry)
    # Keep last 200 entries per agent
    if len(_agent_logs[agent_id]) > 200:
        _agent_logs[agent_id] = _agent_logs[agent_id][-200:]
    return entry


def _get_agent_metrics(agent_id: str) -> Dict[str, Any]:
    """Get or create metrics for an agent."""
    if agent_id not in _agent_metrics:
        _agent_metrics[agent_id] = {
            "total_tokens": 0,
            "today_tokens": 0,
            "month_tokens": 0,
            "today_llm_calls": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "sessions_created": 0,
            "messages_sent": 0,
            "tools_invoked": 0,
            "last_active": None,
        }
    return _agent_metrics[agent_id]


def _bump_metric(agent_id: str, key: str, amount: int = 1) -> None:
    """Increment a specific metric counter."""
    m = _get_agent_metrics(agent_id)
    m[key] = m.get(key, 0) + amount
    m["last_active"] = datetime.now(timezone.utc).isoformat()


@router.put(
    "/teams/{team_id}/agents/{agent_id}/visibility",
    summary="Update agent visibility and default access level",
)
def update_agent_visibility(
    team_id: str, agent_id: str, req: UpdateVisibilityRequest
) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    agent.metadata["visibility"] = req.visibility
    agent.metadata["default_access"] = req.default_access
    _log_agent_action(agent_id, "visibility_changed",
                      f"visibility={req.visibility}, access={req.default_access}")
    return {
        "agent_id": agent_id,
        "visibility": req.visibility,
        "default_access": req.default_access,
    }


@router.get(
    "/teams/{team_id}/agents/{agent_id}/metrics",
    summary="Get agent usage metrics",
)
def get_agent_metrics(team_id: str, agent_id: str) -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    metrics = _get_agent_metrics(agent_id)
    # Enrich with task engine data
    engine_tasks = _te().get_agent_tasks(agent_id)
    from collections import Counter
    task_counts = Counter(t.status.value for t in engine_tasks)
    metrics["task_engine"] = {
        "total": len(engine_tasks),
        "by_status": dict(task_counts),
    }
    return {"agent_id": agent_id, **metrics}


@router.post(
    "/teams/{team_id}/agents/{agent_id}/logs",
    summary="Add agent activity log entry",
    status_code=status.HTTP_201_CREATED,
)
def add_agent_log(team_id: str, agent_id: str, req: AgentLogEntry) -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    entry = _log_agent_action(agent_id, req.action, req.detail)
    return entry


@router.get(
    "/teams/{team_id}/agents/{agent_id}/activity",
    summary="Get agent activity summary (24h)",
)
def get_agent_activity(team_id: str, agent_id: str) -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    logs = _agent_logs.get(agent_id, [])
    metrics = _get_agent_metrics(agent_id)
    # Filter to last 24h
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = [l for l in logs if l.get("timestamp", "") >= cutoff]
    from collections import Counter
    action_counts = Counter(l["action"] for l in recent)
    return {
        "agent_id": agent_id,
        "period": "24h",
        "total_actions": len(recent),
        "action_breakdown": dict(action_counts),
        "recent_logs": recent[-20:],
        "metrics": metrics,
    }


# ══════════════════════════════════════════════════════════════
# P4 — Enhanced Team Dashboard API
# ══════════════════════════════════════════════════════════════


def _summarize_team_tasks(team_id: str) -> Dict[str, Any]:
    from collections import Counter

    all_tasks = _te().get_team_tasks(team_id)
    task_status = Counter(t.status.value for t in all_tasks)
    return {
        "total": len(all_tasks),
        "by_status": dict(task_status),
    }


@router.get(
    "/teams/{team_id}/dashboard",
    summary="Get team dashboard data for overview panel",
)
def get_team_dashboard(team_id: str) -> Dict[str, Any]:
    team = _get_team_or_404(team_id)
    agents_data = []
    for a in team.agents.values():
        m = _get_agent_metrics(a.agent_id)
        agents_data.append({
            "agent_id": a.agent_id,
            "name": a.name,
            "role": a.role,
            "state": a.state.value,
            "template_type": a.template_type.value,
            "skills_count": len(a.skills),
            "tools_count": len(a.tools),
            "is_hermes": a.is_hermes_agent,
            "metrics": {
                "today_tokens": m.get("today_tokens", 0),
                "today_llm_calls": m.get("today_llm_calls", 0),
                "tasks_completed": m.get("tasks_completed", 0),
                "last_active": m.get("last_active"),
            },
        })

    return {
        "team_id": team_id,
        "name": team.name,
        "agent_count": len(team.agents),
        "model_count": len(team.models),
        "tool_count": len(team.tools),
        "skill_count": len(team.skills),
        "agents": agents_data,
        "tasks": _summarize_team_tasks(team_id),
        "recent_activity": [],
    }


# ══════════════════════════════════════════════════════════════
# P5 — LLM Provider Configuration & Chat Harness API
# ══════════════════════════════════════════════════════════════


class LLMProviderConfigRequest(BaseModel):
    """Request to configure LLM provider."""
    provider: str = Field(default="deepseek", description="Provider: openai, deepseek, anthropic, local, openrouter, github, qwen")
    api_key: str = Field(default="", description="API key")
    api_base_url: str = Field(default="", description="Custom base URL (optional)")
    model: str = Field(default="deepseek-chat", description="Model name")
    max_tokens: int = Field(default=4096, ge=100, le=128000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


@router.get("/llm/status", summary="Get current LLM provider status")
def get_llm_status() -> Dict[str, Any]:
    """Return current LLM provider configuration and health."""
    harness = get_chat_harness()
    return harness.get_status()


@router.get("/llm/provider", summary="Get LLM provider details")
def get_llm_provider() -> Dict[str, Any]:
    """Return the current provider configuration (api_key masked)."""
    harness = get_chat_harness()
    return harness.get_provider_info()


@router.put("/llm/provider", summary="Update LLM provider configuration")
def update_llm_provider(req: LLMProviderConfigRequest) -> Dict[str, Any]:
    """Update the default LLM provider at runtime."""
    harness = get_chat_harness()
    config = harness.update_default_provider(
        provider=req.provider,
        api_key=req.api_key,
        api_base_url=req.api_base_url,
        model=req.model,
    )
    if req.max_tokens:
        config.max_tokens = req.max_tokens
    if req.temperature >= 0:
        config.temperature = req.temperature
    # Sync back to the team's default model so config persists across restarts
    try:
        tm = _tm()
        for team in tm.list_teams():
            for m in team.models.values():
                if m.is_default:
                    if req.provider:
                        m.provider = req.provider
                    if req.api_key:
                        m.api_key = req.api_key
                    if req.api_base_url:
                        m.api_base_url = req.api_base_url
                    if req.model and any(c.isalpha() for c in req.model):
                        m.name = req.model
                    if req.max_tokens:
                        m.max_tokens = req.max_tokens
                    if req.temperature >= 0:
                        m.temperature = req.temperature
                    _save_model_pool()
                    break
    except Exception:
        pass
    # 默认密钥进加密 secret store（.api_keys.json），不落明文。
    if req.api_key:
        try:
            from .secret_store import save_default_llm_api_key
            save_default_llm_api_key(req.api_key)
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Failed to persist default LLM api key to secret store", exc_info=True
            )
    # P6: 同时持久化到 settings.json 的 llm 段（不含 api_key），确保重启后 from_settings_file 能读到
    if req.api_key:
        try:
            import json as _json
            import os as _os
            _settings_path = _os.path.join(_CONFIG_DIR, "settings.json")
            with open(_settings_path, "r", encoding="utf-8") as f:
                settings = _json.load(f)
            llm = settings.setdefault("llm", {})
            if req.provider:
                llm["provider"] = req.provider
            llm.pop("api_key", None)  # 明文密钥不再写入 settings.json，统一走 secret store
            if req.api_base_url:
                llm["api_base_url"] = req.api_base_url
            if req.model and any(c.isalpha() for c in req.model):
                llm["model"] = req.model
            if req.max_tokens:
                llm["max_tokens"] = req.max_tokens
            if req.temperature >= 0:
                llm["temperature"] = req.temperature
            with open(_settings_path, "w", encoding="utf-8") as f:
                _json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return {
        "status": "updated",
        "provider": harness.get_provider_info(),
    }


@router.put(
    "/llm/agent/{agent_id}/provider",
    summary="Set per-agent LLM provider override",
)
def set_agent_llm_provider(agent_id: str, req: LLMProviderConfigRequest) -> Dict[str, Any]:
    """Override the LLM provider for a specific agent."""
    harness = get_chat_harness()
    try:
        provider = LLMProvider(req.provider)
    except ValueError:
        provider = LLMProvider.DEEPSEEK
    config = ProviderConfig(
        provider=provider,
        api_key=req.api_key,
        api_base_url=req.api_base_url,
        model=req.model,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    harness.set_agent_provider(agent_id, config)
    return {"status": "set", "agent_id": agent_id, "provider": req.provider, "model": req.model}


@router.get("/llm/sessions", summary="List active chat sessions")
def list_llm_sessions() -> List[Dict[str, Any]]:
    """List all active chat sessions managed by the harness."""
    harness = get_chat_harness()
    return [s.to_dict() for s in harness.list_sessions()]


@router.get("/agents/{agent_id}/model-status", summary="Get agent model name and LLM availability")
def agent_model_status(agent_id: str) -> Dict[str, Any]:
    """Return resolved model name, provider, and whether LLM is reachable for the agent."""
    tm = _tm()
    agent = None
    team_models: Dict[str, Any] = {}
    for team in tm.list_teams():
        a = team.get_agent(agent_id)
        if a:
            agent = a
            team_models = team.models
            break
    if agent is None:
        return {"agent_id": agent_id, "model_name": "unknown", "provider": "unknown", "active": False}

    model_id = agent.model_id or ""
    model = team_models.get(model_id)
    if model:
        model_name = model.name
        provider = model.provider
        has_key = bool(model.get_resolved_api_key())
    else:
        model_name = model_id or "default"
        provider = "unknown"
        has_key = False

    # Check harness default as fallback
    if not has_key:
        harness = get_chat_harness()
        cfg = harness.get_provider_config()
        if cfg and cfg.api_key:
            has_key = True
            if not model:
                model_name = cfg.model or model_name
                provider = cfg.provider.value if hasattr(cfg.provider, 'value') else str(cfg.provider)

    return {
        "agent_id": agent_id,
        "model_id": model_id,
        "model_name": model_name,
        "provider": provider,
        "active": has_key,
    }


@router.post("/llm/test", summary="Test LLM connection")
async def test_llm_connection() -> Dict[str, Any]:
    """Send a test message to verify the **global default** LLM provider is working.

    注意：此接口测的是 ChatHarness 当前全局默认（/llm/provider 或 global_model），
    不是编辑弹窗里某一条团队模型。测某条模型请用 POST /llm/test-model。
    """
    harness = get_chat_harness()
    cfg = harness.get_provider_config()
    # model_override 钉死全局默认模型名，避免 TG model_route 改写成 deepseek-v4-flash
    result = await harness.chat(
        "用一句话介绍你自己。",
        agent_id="__test__",
        system_prompt="你是 AgentsGroup2026 系统的 AI 助手。",
        model_override=cfg.model or "",
    )
    base = ""
    try:
        base = cfg.resolve_base_url() if hasattr(cfg, "resolve_base_url") else (cfg.api_base_url or "")
    except Exception:
        base = cfg.api_base_url or ""
    err = result.error or ""
    sent = result.model or cfg.model
    # 网关 model_not_found 时常误以为「key 错了」——把实际请求的 model 写进 tip
    tip = ""
    if "model_not_found" in err or "not supported" in err.lower() or "is not supported" in err:
        tip = (
            f"实际上游收到的模型是「{sent}」。"
            f"若你刚配的是另一模型名，请到该模型编辑弹窗点「测试连接」(POST /llm/test-model)，"
            f"并确认「模型名称」与上游一致；本按钮只测全局默认。"
        )
    return {
        "success": not bool(result.error),
        "response": (result.response or "")[:200],
        "model": sent,
        "provider": result.provider or (cfg.provider.value if hasattr(cfg.provider, "value") else str(cfg.provider)),
        "base_url": base,
        "requested_model": cfg.model,
        "sent_model": sent,
        "latency_ms": result.latency_ms,
        "error": err,
        "tip": tip,
        "scope": "global_default",
    }


class CatSpeakRequest(BaseModel):
    """猫小虎的 LLM 即兴发言请求."""
    context: str = ""   # 场景描述，如 "发现老鼠吱吱"


@router.post("/llm/cat-speak", summary="猫小虎 LLM 即兴发言")
async def cat_speak(req: CatSpeakRequest) -> Dict[str, Any]:
    """让 LLM 以猫小虎的口吻即兴说一句话。Prompt 从猫的技能 'cat_speak_prompt' 的 instructions 读取，可编辑。

    XB-8.1: 凭据三级回退——pet_squad 团队默认模型 → 全局默认 provider → provider env。
    """
    harness = get_chat_harness()
    # 从 pet_squad 团队的技能目录里读取 cat_speak_prompt 的 instructions
    system = ""
    pet_squad_team = None
    try:
        tm = _tm()
        pet_squad_team = tm.get_team("pet_squad")
        if pet_squad_team and "cat_speak_prompt" in pet_squad_team.skills:
            skill = pet_squad_team.skills["cat_speak_prompt"]
            system = skill.instructions or skill.description or ""
    except Exception:
        pass
    # fallback
    if not system:
        system = (
            "Say a classic quote from Mei Ling in Metal Gear Solid series (English only). "
            "Output only the quote, nothing else."
        )
    # 每次用不同 session_id（避免对话历史导致重复）+ prompt 里加随机数强制变化
    import random as _rand
    _seed = _rand.randint(1, 999999)
    _ctx = (req.context or "").strip()
    if _ctx:
        _user_msg = f"Context: {_ctx}. Share ONE line in ENGLISH — a classic proverb, idiom, or fable (Mei Ling style) that fits this moment. #{_seed}"
    else:
        _user_msg = f"Generate quote #{_seed}. Share ONE line in ENGLISH — a classic proverb, idiom, or fable (Mei Ling style), different from any previous one. Seed={_seed}."

    # XB-8.1: 凭据三级回退——构造 config_override
    config_override = None
    # ① pet_squad 团队默认模型的 resolved key
    if pet_squad_team is not None:
        try:
            _default_model = next(
                (m for m in pet_squad_team.models.values() if m.is_default), None
            )
            if _default_model is not None:
                _resolved_key = _default_model.get_resolved_api_key()
                if _resolved_key:
                    from .chat_harness import ProviderConfig, LLMProvider
                    try:
                        _provider = LLMProvider(_default_model.provider)
                    except ValueError:
                        _provider = LLMProvider.DEEPSEEK
                    config_override = ProviderConfig(
                        provider=_provider,
                        api_key=_resolved_key,
                        api_base_url=_default_model.api_base_url or "",
                        model=_default_model.name,
                        max_tokens=_default_model.max_tokens,
                        temperature=_default_model.temperature,
                    )
        except Exception:
            pass
    # ② 全局默认 provider（harness 默认配置）——如果已有 key 则不覆盖
    if config_override is None:
        _default_cfg = harness.get_provider_config()
        if not _default_cfg.api_key:
            # ③ provider env 兜底
            try:
                # XB-8.1 fix(Fable 5 复查): ProviderConfig 必须在本分支显式 import——
                # 分支①未执行时（pet_squad 缺失/无默认模型）其局部 import 不存在，
                # 否则此处 NameError 被 except 吞掉，env 兜底静默失效（bug-049）。
                from .chat_harness import resolve_api_key, LLMProvider, ProviderConfig
                _env_key = resolve_api_key(_default_cfg.provider.value)
                if _env_key:
                    config_override = ProviderConfig(
                        provider=_default_cfg.provider,
                        api_key=_env_key,
                        api_base_url=_default_cfg.api_base_url,
                        model=_default_cfg.model,
                        max_tokens=_default_cfg.max_tokens,
                        temperature=_default_cfg.temperature,
                    )
            except Exception:
                pass

    # bug-051 硬化：harness.chat 任何异常不再冒泡成 500——500 会让前端拿不到
    # reply 字段而落到"硕鼠硕鼠"兜底，且错误信息完全丢失。转成可诊断 JSON。
    try:
        result = await harness.chat(
            _user_msg,
            agent_id="xiaohu_cat",
            session_id=f"cat_speak_{_seed}",   # 每次新 session，无历史
            system_prompt=system,
            config_override=config_override,
        )
    except Exception as _chat_exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("cat_speak harness.chat 异常", exc_info=True)
        return {"success": False,
                "reply": "Even the smallest light can pierce the darkness.",
                "error": f"chat_exception: {type(_chat_exc).__name__}: {str(_chat_exc)[:200]}"}

    # bug-053: 三级回退第①级（pet_squad 模型 key）鉴权失败时自动降级——
    # 团队模型里残留的失效旧 key 不应挡住有效的全局默认 key。
    _err_l = str(result.error or "").lower() + str(result.response or "")[:200].lower()
    if ("authentication" in _err_l or "invalid" in _err_l and "api key" in _err_l)             and config_override is not None:
        _default_cfg2 = harness.get_provider_config()
        if _default_cfg2.api_key and _default_cfg2.api_key != config_override.api_key:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "cat_speak: 团队模型 key 鉴权失败(%s)，降级重试全局默认 provider(%s)",
                config_override.provider, _default_cfg2.provider)
            try:
                result = await harness.chat(
                    _user_msg,
                    agent_id="xiaohu_cat",
                    session_id=f"cat_speak_{_seed}_retry",
                    system_prompt=system,
                    config_override=_default_cfg2,
                )
            except Exception:
                pass
    # 去掉引号和首尾空白
    reply = (result.response or "").strip().strip('"').strip("'").strip()[:100]
    # bug-045: LLM 未连接时 harness 返回大段中文降级文案（"我是 AgentsGroup2026 智能体…LLM 未连接"），
    # 会原样泄进猫气泡且完全不是 Mei Ling 台词。检测降级特征 → 换本地 Mei Ling 风格兜底一句。
    if result.error or "LLM 未连接" in (result.response or "") or "收到您的消息" in (result.response or ""):
        _fallbacks = [
            "A journey of a thousand miles begins with a single step.",
            "Even the smallest light can pierce the darkness.",
            "The wise adapt themselves to circumstances, as water molds itself to the pitcher.",
            "A bird does not sing because it has an answer. It sings because it has a song.",
            "Fall seven times, stand up eight.",
        ]
        reply = _rand.choice(_fallbacks)
        return {"success": False, "reply": reply,
                "error": result.error or "llm_unavailable_fallback"}
    return {
        "success": not bool(result.error),
        "reply": reply,
        "error": result.error or "",
    }


class TestModelRequest(BaseModel):
    """Test a specific model configuration without changing global settings."""
    provider: str = "deepseek"
    name: str = "deepseek-chat"
    api_key: str = ""
    api_base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    # 当 api_key 留空时，用 (team_id, model_id) 回退到已保存的密钥（“留空不修改”语义）
    team_id: str = ""
    model_id: str = ""


@router.post("/llm/test-model", summary="Test a specific model config")
async def test_model_config(req: TestModelRequest) -> Dict[str, Any]:
    """Test a specific provider/model/key combo without altering global config.

    若请求未带 api_key（编辑框“留空不修改”），回退到已保存的团队模型密钥，
    使重新登录后无需重新输入即可测试连接。base_url/name/provider 同样在留空时回退。
    """
    from .chat_harness import ChatHarness, ProviderConfig, LLMProvider

    # 留空回退：从已保存的团队模型取密钥与其余配置
    api_key = req.api_key
    provider_name = req.provider
    name = (req.name or "").strip()
    api_base_url = (req.api_base_url or "").strip()
    if req.team_id and req.model_id and _team_manager is not None:
        stored = _team_manager.get_team(req.team_id)
        stored_model = stored.get_model(req.model_id) if stored else None
        if stored_model is not None:
            if not api_key:
                api_key = stored_model.get_resolved_api_key() or api_key
            if not provider_name:
                provider_name = stored_model.provider
            if not name:
                name = stored_model.name or name
            if not api_base_url:
                api_base_url = stored_model.api_base_url or api_base_url

    if not name:
        return {
            "success": False,
            "response": "",
            "model": "",
            "provider": provider_name,
            "base_url": api_base_url,
            "requested_model": "",
            "latency_ms": 0,
            "error": "模型名称为空：请在编辑框填写上游实际模型 ID（例如 qwen27b-abliterated-Fable-MTP），不要留空。",
            "tip": "「模型名称」会原样作为 chat/completions 的 model 字段发给 Base URL。",
            "scope": "model_edit",
        }

    try:
        provider = LLMProvider(provider_name)
    except ValueError:
        provider = LLMProvider.OPENAI  # OpenAI-compatible 网关比 deepseek 默认更中性

    config = ProviderConfig(
        provider=provider,
        api_key=api_key,
        api_base_url=api_base_url,
        model=name,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    temp_harness = ChatHarness(default_config=config)
    # 必须 model_override=编辑框名称：否则 TG model_route/cost_tier 会把短测试句
    # 改写成 economy 默认 deepseek-v4-flash，UI 却显示 requested_model=用户填的名，
    # 上游报错就会出现「明明写了 qwen 却说 deepseek-v4-flash」的假象。
    result = await temp_harness.chat(
        "用一句话介绍你自己。",
        agent_id="__model_test__",
        system_prompt="你是 AgentsGroup2026 系统的 AI 助手。请用中文回答。",
        model_override=name,
    )
    err = result.error or ""
    sent = result.model or name
    tip = ""
    if "model_not_found" in err or "not supported" in err.lower() or "is not supported" in err:
        tip = (
            f"上游拒绝了模型「{sent}」（编辑框填写「{name}」）。"
            f"请核对：① 编辑框「模型名称」是否等于上游允许的 id；"
            f"② Base URL 是否对应正确分组（当前 {api_base_url or '(默认)'}）；"
            f"③ Key 是否属于该分组且已开通此模型。"
        )
        if sent != name:
            tip += f" 注意：实际发出的 model 与编辑框不一致（{name} → {sent}），请报告此为路由改写 bug。"
    return {
        "success": not bool(result.error),
        "response": (result.response or "")[:200],
        "model": sent,
        "provider": result.provider or provider.value,
        "base_url": api_base_url or (config.resolve_base_url() if hasattr(config, "resolve_base_url") else ""),
        "requested_model": name,
        "sent_model": sent,
        "latency_ms": result.latency_ms,
        "error": err,
        "tip": tip,
        "scope": "model_edit",
    }


# ═══════════════════════════════════════════════════════════════
# 全局模型 override — 一处设置，plaza/skill 演进/棘轮/数字孪生 等所有走 harness 的地方统一用它
# ═══════════════════════════════════════════════════════════════

def _build_provider_config_from_model(team_id: str, model_id: str):
    """从某团队的模型(含已存密钥)构造 ProviderConfig；找不到返回 None。"""
    from .chat_harness import ProviderConfig, LLMProvider
    if _team_manager is None:
        return None
    team = _team_manager.get_team(team_id)
    model = team.get_model(model_id) if team else None
    if model is None:
        return None
    try:
        provider = LLMProvider(model.provider)
    except ValueError:
        provider = LLMProvider.DEEPSEEK
    # 必须 get_resolved_api_key：env: 引用与内存中明文 key 都走这里
    resolved = model.get_resolved_api_key() if hasattr(model, "get_resolved_api_key") else (model.api_key or "")
    return ProviderConfig(
        provider=provider,
        api_key=resolved,
        api_base_url=model.api_base_url,
        model=model.name,
        max_tokens=model.max_tokens,
        temperature=model.temperature,
    )


def _read_global_model_sel() -> Optional[Dict[str, str]]:
    import json as _json, os as _os
    path = _os.path.join(_CONFIG_DIR, "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            sel = _json.load(f).get("global_model")
        if isinstance(sel, dict) and sel.get("team_id") and sel.get("model_id"):
            return {"team_id": sel["team_id"], "model_id": sel["model_id"]}
    except Exception:
        pass
    return None


def _refresh_global_override_for_model(team_id: str, model_id: str) -> bool:
    """若该模型正是 settings.global_model，用最新 key/name/base 刷新 harness 全局覆盖。

    修复：编辑/测试连接只更新了团队模型槽，广场仍读旧的 global_override（旧 Key → INVALID_API_KEY）。
    """
    sel = _read_global_model_sel()
    if not sel or sel.get("team_id") != team_id or sel.get("model_id") != model_id:
        return False
    cfg = _build_provider_config_from_model(team_id, model_id)
    if cfg is None or not cfg.api_key:
        return False
    try:
        from .chat_harness import get_chat_harness
        team = _team_manager.get_team(team_id) if _team_manager else None
        model = team.get_model(model_id) if team else None
        get_chat_harness().set_global_override(cfg, {
            "team_id": team_id,
            "model_id": model_id,
            "name": getattr(model, "name", model_id),
        })
        # 同步 settings.llm 默认（广场/萃取等读 harness 与 settings）
        try:
            import json as _json, os as _os
            path = _os.path.join(_CONFIG_DIR, "settings.json")
            with open(path, "r", encoding="utf-8") as f:
                settings = _json.load(f)
            llm = settings.setdefault("llm", {})
            llm["provider"] = cfg.provider.value if hasattr(cfg.provider, "value") else str(cfg.provider)
            llm["api_key"] = cfg.api_key
            llm["api_base_url"] = cfg.api_base_url or ""
            llm["model"] = cfg.model
            llm["max_tokens"] = cfg.max_tokens
            llm["temperature"] = cfg.temperature
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(settings, f, ensure_ascii=False, indent=2)
            try:
                from .secret_store import save_default_llm_api_key
                save_default_llm_api_key(cfg.api_key)
            except Exception:
                pass
        except Exception:
            pass
        _logging.getLogger(__name__).info(
            "🌐 全局模型覆盖已刷新: %s/%s model=%s", team_id, model_id, cfg.model,
        )
        return True
    except Exception:
        _logging.getLogger(__name__).warning("刷新 global_override 失败", exc_info=True)
        return False


def _persist_global_model(sel: Optional[Dict[str, str]]) -> None:
    """把全局模型选择(team_id/model_id)写入 settings.json；sel=None 清除。"""
    import json as _json, os as _os
    path = _os.path.join(_CONFIG_DIR, "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            settings = _json.load(f)
    except Exception:
        settings = {}
    if sel:
        settings["global_model"] = {"team_id": sel["team_id"], "model_id": sel["model_id"]}
    else:
        settings.pop("global_model", None)
    try:
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_global_model_on_startup() -> None:
    """启动时从 settings.json 读全局模型并应用到 harness。"""
    import json as _json, os as _os
    path = _os.path.join(_CONFIG_DIR, "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            sel = _json.load(f).get("global_model")
    except Exception:
        sel = None
    if not sel:
        return
    cfg = _build_provider_config_from_model(sel.get("team_id", ""), sel.get("model_id", ""))
    if cfg is not None:
        from .chat_harness import get_chat_harness
        team = _team_manager.get_team(sel["team_id"]) if _team_manager else None
        model = team.get_model(sel["model_id"]) if team else None
        get_chat_harness().set_global_override(cfg, {
            "team_id": sel["team_id"], "model_id": sel["model_id"],
            "name": getattr(model, "name", sel["model_id"]),
        })
        _logging.getLogger(__name__).info("🌐 全局模型已加载: %s/%s", sel["team_id"], sel["model_id"])


class GlobalModelRequest(BaseModel):
    team_id: str = ""
    model_id: str = ""


@router.get("/llm/global-model", summary="读取当前全局模型")
def get_global_model() -> Dict[str, Any]:
    from .chat_harness import get_chat_harness
    h = get_chat_harness()
    ov = h.get_global_override()
    return {"enabled": ov is not None, "current": h._global_override_meta if ov is not None else None}


@router.post("/llm/global-model", summary="设为全局模型（全系统统一使用）")
def set_global_model(req: GlobalModelRequest) -> Dict[str, Any]:
    if not req.team_id or not req.model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id 与 model_id 必填")
    cfg = _build_provider_config_from_model(req.team_id, req.model_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="未找到该团队模型")
    from .chat_harness import get_chat_harness
    team = _team_manager.get_team(req.team_id)
    model = team.get_model(req.model_id)
    harness = get_chat_harness()
    harness.set_global_override(cfg, {
        "team_id": req.team_id, "model_id": req.model_id, "name": model.name,
    })
    # 同步 default provider + settings.llm，确保全链路只认这一份
    harness.update_default_provider(
        provider=str(getattr(cfg.provider, "value", cfg.provider) or ""),
        api_key=cfg.api_key or "",
        api_base_url=cfg.api_base_url or "",
        model=cfg.model or "",
    )
    try:
        import json as _json, os as _os
        path = _os.path.join(_CONFIG_DIR, "settings.json")
        with open(path, "r", encoding="utf-8") as f:
            settings = _json.load(f)
        llm = settings.setdefault("llm", {})
        llm["provider"] = str(getattr(cfg.provider, "value", cfg.provider) or "")
        llm["api_key"] = cfg.api_key or ""
        llm["api_base_url"] = cfg.api_base_url or ""
        llm["model"] = cfg.model or ""
        llm["max_tokens"] = cfg.max_tokens
        llm["temperature"] = cfg.temperature
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(settings, f, ensure_ascii=False, indent=2)
        try:
            from .secret_store import save_default_llm_api_key
            if cfg.api_key:
                save_default_llm_api_key(cfg.api_key)
        except Exception:
            pass
    except Exception:
        pass
    _persist_global_model({"team_id": req.team_id, "model_id": req.model_id})
    return {
        "enabled": True,
        "current": {"team_id": req.team_id, "model_id": req.model_id, "name": model.name},
        "note": "已设为全局 LLM：演练/广场/萃取/任务/tool_loop 等全部只使用该连接；model_route 与团队槽均不再生效",
    }


@router.delete("/llm/global-model", summary="清除全局模型（回退各团队默认）")
def clear_global_model() -> Dict[str, Any]:
    from .chat_harness import get_chat_harness
    get_chat_harness().set_global_override(None)
    _persist_global_model(None)
    return {"enabled": False, "current": None}


# ═══════════════════════════════════════════════════════════════
# UltraPlan Agentic Loop Endpoints
# ═══════════════════════════════════════════════════════════════


class AgentLoopRequest(BaseModel):
    """Run a full agentic loop: plan → act → observe → respond."""
    prompt: str
    agent_id: str = ""
    session_id: str = ""
    system_prompt: str = ""
    max_iterations: int = Field(default=10, ge=1, le=50)


@router.post("/agent-loop", summary="Agentic loop with tool execution")
def _agent_loop_permission_context(agent_id: str):
    """Locate the agent across teams and build its tool permission context."""
    if not agent_id:
        return None
    try:
        for team in _tm().list_teams():
            agents = team.agents if isinstance(team.agents, dict) else {}
            candidate = agents.get(agent_id)
            if candidate is not None:
                return _build_agent_permission_context(candidate)
    except Exception:
        pass
    return None


async def run_agent_loop(req: AgentLoopRequest) -> Dict[str, Any]:
    """Execute a full plan→act→observe→reflect agentic loop."""
    harness = get_chat_harness()
    permission_context = _agent_loop_permission_context(req.agent_id)
    events: List[Dict[str, Any]] = []

    def _on_event(event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        event: Dict[str, Any] = {"type": event_type}
        if payload:
            event.update(payload)
        events.append(event)
        record_runtime_event(event)

    result = await harness.agent_loop(
        req.prompt,
        agent_id=req.agent_id,
        session_id=req.session_id,
        system_prompt=req.system_prompt,
        max_iterations=req.max_iterations,
        permission_context=permission_context,
        on_event=_on_event,
    )
    payload = result.to_dict()
    payload["events"] = events
    return payload


@router.post("/agent-loop/stream", summary="Run agentic loop with SSE streaming")
async def run_agent_loop_stream(req: AgentLoopRequest):
    """Stream the agentic loop as Server-Sent Events, with permission context."""
    from starlette.responses import StreamingResponse

    harness = get_chat_harness()
    permission_context = _agent_loop_permission_context(req.agent_id)

    async def event_gen():
        async for event in harness.agent_loop_stream(
            req.prompt,
            agent_id=req.agent_id,
            session_id=req.session_id,
            system_prompt=req.system_prompt,
            max_iterations=req.max_iterations,
            permission_context=permission_context,
        ):
            record_runtime_event(dict(event))
            yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class PlanPreviewRequest(BaseModel):
    """Preview an execution plan without executing it."""
    prompt: str


@router.post("/agent-loop/plan-preview", summary="Preview execution plan")
async def preview_plan(req: PlanPreviewRequest) -> Dict[str, Any]:
    """Generate a plan without executing it — for UI display."""
    from .chat_harness import build_plan_from_prompt
    plan = build_plan_from_prompt(req.prompt)
    return plan.to_dict()


# ═══════════════════════════════════════════════════════════════
# Skill Execution Endpoints (Clawith-style)
# ═══════════════════════════════════════════════════════════════


class SkillCreateRequest(BaseModel):
    """Create a new skill at runtime."""
    name: str
    description: str = ""
    category: str = "general"
    instructions: str = ""
    required_tools: List[str] = []


@router.post("/skills/create", summary="Create a skill at runtime")
async def create_runtime_skill(req: SkillCreateRequest) -> Dict[str, Any]:
    """Clawith-style runtime skill creation."""
    from .skill_registry import SkillRegistry
    from .models import SkillCategory
    registry = SkillRegistry()
    registry.load_defaults()
    try:
        cat = SkillCategory(req.category)
    except ValueError:
        cat = SkillCategory.GENERAL
    skill = registry.create_skill(
        name=req.name,
        description=req.description,
        category=cat,
        instructions=req.instructions,
        required_tools=req.required_tools,
    )
    return skill.to_dict()


@router.get("/skills/search", summary="Search skills")
async def search_skills_endpoint(q: str = "") -> List[Dict[str, Any]]:
    """Search skills by name or description."""
    from .skill_registry import SkillRegistry
    registry = SkillRegistry()
    registry.load_defaults()
    if q:
        results = registry.search(q)
    else:
        results = registry.list_all()
    return [s.to_dict() for s in results[:50]]


# ═══════════════════════════════════════════════════════════════
# Tool Binding & Discovery Endpoints
# ═══════════════════════════════════════════════════════════════


@router.get("/tools/openai-schema", summary="Get OpenAI-format tools schema")
async def get_openai_tools_schema(agent_id: str = "") -> List[Dict[str, Any]]:
    """Return tool definitions in OpenAI function-calling format."""
    from .tool_registry import ToolRegistry
    registry = ToolRegistry()
    registry.load_defaults()
    return registry.get_openai_tools_schema(agent_id)


@router.get("/tools/search", summary="Search tools")
async def search_tools_endpoint(q: str = "") -> List[Dict[str, Any]]:
    """Search tools by name or description."""
    from .tool_registry import ToolRegistry
    registry = ToolRegistry()
    registry.load_defaults()
    if q:
        results = registry.search(q)
    else:
        results = registry.list_all()
    return [t.to_dict() for t in results[:50]]


# ═══════════════════════════════════════════════════════════════
# System Health & Diagnostics
# ═══════════════════════════════════════════════════════════════


# ── bug-052: 进程代龄快照（启动时一次性求值，/health 用）──
_PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()
_GIT_REV_AT_BOOT = ""
_GIT_BRANCH_AT_BOOT = ""
try:
    import subprocess as _sp_boot
    _repo_root_boot = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    _GIT_REV_AT_BOOT = _sp_boot.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_repo_root_boot, stderr=_sp_boot.DEVNULL, timeout=3,
    ).decode().strip()
    _GIT_BRANCH_AT_BOOT = _sp_boot.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=_repo_root_boot, stderr=_sp_boot.DEVNULL, timeout=3,
    ).decode().strip()
except Exception:
    pass


@router.get("/health", summary="System health check")
async def agent_health_check() -> Dict[str, Any]:
    """Comprehensive health check for the agent subsystem."""
    harness = get_chat_harness()
    harness_status = harness.get_status()

    from .tool_registry import ToolRegistry
    from .skill_registry import SkillRegistry
    tool_reg = ToolRegistry()
    tool_reg.load_defaults()
    skill_reg = SkillRegistry()
    skill_reg.load_defaults()

    # XC-6.1 / bug-052: git rev 必须用「进程启动时缓存」的值——
    # 每次请求现场跑 git rev-parse 报告的是磁盘仓库 HEAD，不是进程加载的代码。
    # 用户 commit 后未重启时，旧实现会谎报新 rev，制造"已是新代码"假象
    # （2026-07-11 实锤：/health 显示 1935ea1，但演练结果无 populations/无世代号，
    # 证明进程仍是旧代码——代龄检测本身失真）。
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_rev": _GIT_REV_AT_BOOT,
        "git_branch": _GIT_BRANCH_AT_BOOT,
        "process_started_at": _PROCESS_STARTED_AT,
        "llm": {
            "provider": harness_status["provider"],
            "model": harness_status["model"],
            "has_api_key": harness_status["has_api_key"],
            "total_calls": harness_status["total_calls"],
        },
        "tools": {
            "registered": len(tool_reg.list_all()),
            "enabled": len(tool_reg.list_enabled()),
        },
        "skills": {
            "registered": len(skill_reg.list_all()),
            "required": len(skill_reg.list_required()),
        },
        "sessions": harness_status["active_sessions"],
    }


@router.get("/diagnostics", summary="Full diagnostics dump")
async def agent_diagnostics() -> Dict[str, Any]:
    """Full diagnostics dump for debugging."""
    harness = get_chat_harness()

    from .tool_registry import ToolRegistry
    from .skill_registry import SkillRegistry
    tool_reg = ToolRegistry()
    tool_reg.load_defaults()
    skill_reg = SkillRegistry()
    skill_reg.load_defaults()

    from .tool_executor import get_tool_executor
    executor = get_tool_executor()

    return {
        "harness": harness.get_status(),
        "provider_info": harness.get_provider_info(),
        "tool_categories": {
            cat.value: len(tool_reg.list_by_category(cat))
            for cat in set(t.category for t in tool_reg.list_all())
        },
        "skill_categories": {
            cat.value: len(skill_reg.list_by_category(cat))
            for cat in set(s.category for s in skill_reg.list_all())
        },
        "tool_execution_history": executor.get_history(limit=20),
        "sessions": [s.to_dict() for s in harness.list_sessions()],
    }


# ═══════════════════════════════════════════════════════════════
# Session Persistence & Cross-Session Search (claw-code-parity)
# ═══════════════════════════════════════════════════════════════


@router.post("/sessions/{session_id}/persist", summary="Persist session to disk")
async def persist_session(session_id: str) -> Dict[str, Any]:
    """Save a session to disk for later replay/search."""
    harness = get_chat_harness()
    path = harness.persist_session(session_id)
    if not path:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "path": path}


@router.get("/sessions/persisted", summary="List persisted sessions")
async def list_persisted_sessions() -> Dict[str, Any]:
    """List all session IDs saved to disk."""
    harness = get_chat_harness()
    session_ids = harness.list_persisted_sessions()
    return {"sessions": session_ids, "count": len(session_ids)}


@router.post("/sessions/persisted/{session_id}/load", summary="Load persisted session")
async def load_persisted_session(session_id: str) -> Dict[str, Any]:
    """Load a previously persisted session into memory."""
    harness = get_chat_harness()
    session = harness.load_persisted_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Persisted session not found")
    return session.to_dict()


class SessionSearchRequest(BaseModel):
    query: str
    max_results: int = 10


@router.post("/sessions/search", summary="Cross-session search")
async def search_sessions_endpoint(body: SessionSearchRequest) -> Dict[str, Any]:
    """Search across all persisted sessions — mirrors claw-code session_search."""
    harness = get_chat_harness()
    results = harness.search_persisted_sessions(body.query, body.max_results)
    return {"results": results, "count": len(results)}


# ═══════════════════════════════════════════════════════════════
# Prompt Routing & Runtime (claw-code-parity PortRuntime)
# ═══════════════════════════════════════════════════════════════


class RoutePromptRequest(BaseModel):
    prompt: str
    limit: int = 5
    deny_tools: List[str] = []
    deny_prefixes: List[str] = []


@router.post("/runtime/route", summary="Route prompt to tools/commands")
async def route_prompt(body: RoutePromptRequest) -> Dict[str, Any]:
    """Route a prompt to matching tools and commands by keyword scoring.

    Mirrors claw-code-parity PortRuntime.route_prompt.
    """
    perm = ToolPermissionContext.from_lists(body.deny_tools, body.deny_prefixes)
    runtime = PortRuntime(permission_context=perm)
    matches = runtime.route_prompt(body.prompt, limit=body.limit)
    return {
        "matches": [
            {"kind": m.kind, "name": m.name, "source_hint": m.source_hint, "score": m.score}
            for m in matches
        ],
        "count": len(matches),
    }


class BootstrapRequest(BaseModel):
    prompt: str
    limit: int = 5
    deny_tools: List[str] = []
    deny_prefixes: List[str] = []


@router.post("/runtime/bootstrap", summary="Bootstrap a runtime session")
async def bootstrap_session(body: BootstrapRequest) -> Dict[str, Any]:
    """Bootstrap a full session: route → assemble tools → execute.

    Mirrors claw-code-parity PortRuntime.bootstrap_session.
    """
    perm = ToolPermissionContext.from_lists(body.deny_tools, body.deny_prefixes)
    runtime = PortRuntime(permission_context=perm)
    session = await runtime.bootstrap_session(body.prompt, limit=body.limit)
    return {
        "prompt": session.prompt,
        "matches": [
            {"kind": m.kind, "name": m.name, "score": m.score}
            for m in session.routed_matches
        ],
        "tool_results": [
            {"name": r.name, "handled": r.handled, "output": r.output[:500]}
            for r in session.tool_results
        ],
        "command_results": [
            {"name": r.name, "output": r.output[:500]}
            for r in session.command_results
        ],
        "denials": [
            {"tool_name": d.tool_name, "reason": d.reason}
            for d in session.permission_denials
        ],
        "history": session.history.to_list(),
    }


@router.post("/runtime/route-and-chat", summary="Route prompt then chat with LLM")
async def route_and_chat(body: RoutePromptRequest) -> Dict[str, Any]:
    """Integrated routing + LLM chat — best of both worlds."""
    harness = get_chat_harness()
    perm = ToolPermissionContext.from_lists(body.deny_tools, body.deny_prefixes)
    result = await harness.route_and_chat(
        body.prompt,
        permission_context=perm,
        route_limit=body.limit,
    )
    return result.to_dict()


# ═══════════════════════════════════════════════════════════════
# Tool Pool & Permission (Clawith + claw-code-parity)
# ═══════════════════════════════════════════════════════════════


class ToolPoolRequest(BaseModel):
    simple_mode: bool = False
    include_mcp: bool = True
    deny_tools: List[str] = []
    deny_prefixes: List[str] = []


@router.post("/tool-pool", summary="Assemble filtered tool pool")
async def get_tool_pool(body: ToolPoolRequest) -> Dict[str, Any]:
    """Assemble a ToolPool with permission filtering — mirrors claw-code tool_pool."""
    perm = ToolPermissionContext.from_lists(body.deny_tools, body.deny_prefixes)
    pool = assemble_tool_pool(
        simple_mode=body.simple_mode,
        include_mcp=body.include_mcp,
        permission_context=perm,
    )
    return {
        "tools": pool.tool_names,
        "count": pool.tool_count,
        "simple_mode": pool.simple_mode,
        "include_mcp": pool.include_mcp,
    }


# ── Tool Bulk Operations (Clawith-style) ────────────────────


class BulkToolUpdate(BaseModel):
    tool_id: str
    enabled: bool


@router.put("/tools/bulk", summary="Bulk update tool enabled status")
async def bulk_update_tools(updates: List[BulkToolUpdate]) -> Dict[str, Any]:
    """Bulk update enabled status for multiple tools — mirrors Clawith bulk update."""
    reg = _get_tool_registry()
    count = reg.bulk_update_enabled([u.model_dump() for u in updates])
    return {"ok": True, "updated": count}


class MCPToolRegister(BaseModel):
    name: str
    description: str = ""
    mcp_server_url: str = ""
    mcp_server_name: str = ""
    parameters: Dict[str, Any] = {}


@router.post("/tools/mcp/register", summary="Register MCP tool at runtime")
async def register_mcp_tool(body: MCPToolRegister) -> Dict[str, Any]:
    """Register an MCP tool at runtime — mirrors Clawith MCP tool creation."""
    reg = _get_tool_registry()
    tool = reg.register_mcp_tool(
        name=body.name,
        description=body.description,
        parameters=body.parameters,
        mcp_server_url=body.mcp_server_url,
        mcp_server_name=body.mcp_server_name,
    )
    return {"ok": True, "tool_id": tool.tool_id, "name": tool.name}


class ToolConfigUpdate(BaseModel):
    config: Dict[str, Any]


@router.put("/tools/{tool_id}/config", summary="Update tool runtime config")
async def update_tool_config(tool_id: str, body: ToolConfigUpdate) -> Dict[str, Any]:
    """Update a tool's runtime configuration — mirrors Clawith per-tool config."""
    reg = _get_tool_registry()
    tool = reg.update_tool_config(tool_id, body.config)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"ok": True, "tool_id": tool.tool_id}


@router.get("/tools/{tool_id}/config", summary="Get tool config")
async def get_tool_config(tool_id: str) -> Dict[str, Any]:
    """Get merged runtime config for a tool."""
    reg = _get_tool_registry()
    config = reg.get_tool_config(tool_id)
    return {"tool_id": tool_id, "config": config}


# ── Skill Browse & Import (Clawith-style) ───────────────────


@router.get("/skills/{skill_id}/folder", summary="Get skill file structure")
async def get_skill_folder(skill_id: str) -> Dict[str, Any]:
    """Get a skill's file structure — mirrors Clawith skill browse."""
    reg = _get_skill_registry()
    return reg.get_skill_folder(skill_id)


class SkillImportRequest(BaseModel):
    name: str
    content: str
    category: str = "general"


@router.post("/skills/import", summary="Import skill from SKILL.md content")
async def import_skill(body: SkillImportRequest) -> Dict[str, Any]:
    """Import a skill from SKILL.md markdown content — mirrors Clawith URL import."""
    from .models import SkillCategory
    reg = _get_skill_registry()
    try:
        cat = SkillCategory(body.category)
    except ValueError:
        cat = SkillCategory.GENERAL
    skill = reg.import_from_instructions(body.name, body.content, category=cat)
    return {"ok": True, "skill_id": skill.skill_id, "name": skill.name}


@router.get("/skills/{skill_id}/portability", summary="Classify skill portability")
async def classify_skill_portability(skill_id: str) -> Dict[str, Any]:
    """Classify skill portability tier (1=prompt, 2=CLI, 3=platform)."""
    reg = _get_skill_registry()
    tier = reg.classify_portability(skill_id)
    tier_labels = {1: "pure-prompt", 2: "cli-api", 3: "platform-native"}
    return {"skill_id": skill_id, "tier": tier, "label": tier_labels.get(tier, "unknown")}


@router.get("/skills/export/markdown", summary="Export all skills as markdown")
async def export_skills_markdown() -> Dict[str, Any]:
    """Export all skills as a single markdown document."""
    reg = _get_skill_registry()
    md = reg.export_all_as_markdown()
    return {"markdown": md, "length": len(md)}


# ── Execution Registry Info ─────────────────────────────────


@router.get("/execution-registry", summary="Get execution registry info")
async def get_execution_registry_info() -> Dict[str, Any]:
    """List all registered tools and commands in the execution registry."""
    reg = build_execution_registry()
    return {
        "tools": reg._tool_names,
        "commands": reg._command_names,
        "tool_count": len(reg._tool_names),
        "command_count": len(reg._command_names),
    }


# ═══════════════════════════════════════════════════════════════
# Agent Workspace — File/Folder CRUD with filesystem persistence
# ═══════════════════════════════════════════════════════════════

import pathlib as _ws_pathlib

_WS_BASE: Optional[_ws_pathlib.Path] = None


def _get_ws_base() -> _ws_pathlib.Path:
    global _WS_BASE
    if _WS_BASE is None:
        _WS_BASE = _ws_pathlib.Path(
            _mp_os.path.dirname(_mp_os.path.dirname(_mp_os.path.dirname(
                _mp_os.path.dirname(_mp_os.path.abspath(__file__))))),
        ) / "storage" / "agent_workspaces"
        _WS_BASE.mkdir(parents=True, exist_ok=True)
    return _WS_BASE


def _agent_ws_root(team_id: str, agent_id: str) -> _ws_pathlib.Path:
    """Return agent workspace root, creating default folders if new."""
    root = _get_ws_base() / team_id / agent_id
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        (root / "archived").mkdir(exist_ok=True)
        (root / "knowledge_base").mkdir(exist_ok=True)
        (root / "team_structure").mkdir(exist_ok=True)
    return root


def _safe_subpath(root: _ws_pathlib.Path, rel: str) -> _ws_pathlib.Path:
    """Resolve a relative path safely within root (prevent traversal)."""
    resolved = (root / rel).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Path traversal denied")
    return resolved


def _dir_listing(dirp: _ws_pathlib.Path) -> List[Dict[str, Any]]:
    items = []
    if not dirp.is_dir():
        return items
    for child in sorted(dirp.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
            items.append({"name": child.name, "type": "folder",
                          "size": size, "size_display": _fmt_size(size)})
        else:
            sz = child.stat().st_size
            items.append({"name": child.name, "type": "file",
                          "size": sz, "size_display": _fmt_size(sz)})
    return items


@router.get(
    "/teams/{team_id}/agents/{agent_id}/workspace",
    summary="List workspace root",
)
def list_workspace(team_id: str, agent_id: str, path: str = "") -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    root = _agent_ws_root(team_id, agent_id)
    target = _safe_subpath(root, path) if path else root
    if not target.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Path not found")
    if target.is_file():
        return {"type": "file", "name": target.name, "path": path,
                "content": target.read_text(encoding="utf-8", errors="replace"),
                "size": target.stat().st_size}
    return {"type": "folder", "path": path or "/",
            "items": _dir_listing(target)}


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(default="file", pattern=r"^(file|folder)$")
    content: str = ""


@router.post(
    "/teams/{team_id}/agents/{agent_id}/workspace",
    summary="Create file or folder in workspace",
    status_code=status.HTTP_201_CREATED,
)
def create_workspace_item(
    team_id: str, agent_id: str, req: WorkspaceCreateRequest, path: str = ""
) -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    root = _agent_ws_root(team_id, agent_id)
    parent = _safe_subpath(root, path) if path else root
    parent.mkdir(parents=True, exist_ok=True)
    target = _safe_subpath(root, _mp_os.path.join(path, req.name) if path else req.name)
    if req.type == "folder":
        target.mkdir(parents=True, exist_ok=True)
        return {"type": "folder", "name": req.name, "path": str(target.relative_to(root))}
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(req.content, encoding="utf-8")
        return {"type": "file", "name": req.name,
                "path": str(target.relative_to(root)),
                "size": len(req.content.encode("utf-8"))}


class WorkspaceUpdateRequest(BaseModel):
    content: str = ""


@router.put(
    "/teams/{team_id}/agents/{agent_id}/workspace/{filepath:path}",
    summary="Update file content",
)
def update_workspace_file(
    team_id: str, agent_id: str, filepath: str, req: WorkspaceUpdateRequest
) -> Dict[str, Any]:
    _get_agent_or_404(team_id, agent_id)
    root = _agent_ws_root(team_id, agent_id)
    target = _safe_subpath(root, filepath)
    if not target.exists() or target.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    target.write_text(req.content, encoding="utf-8")
    return {"status": "updated", "path": filepath, "size": len(req.content.encode("utf-8"))}


@router.delete(
    "/teams/{team_id}/agents/{agent_id}/workspace/{filepath:path}",
    summary="Delete file or folder",
)
def delete_workspace_item(team_id: str, agent_id: str, filepath: str) -> Dict[str, str]:
    _get_agent_or_404(team_id, agent_id)
    root = _agent_ws_root(team_id, agent_id)
    target = _safe_subpath(root, filepath)
    if not target.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    if target.is_dir():
        import shutil
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"status": "deleted", "path": filepath}


# ═══════════════════════════════════════════════════════════════
# Knowledge Base RAG API — Store, search, retrieve agent deliverables
# ═══════════════════════════════════════════════════════════════

from .knowledge_base import KBDocument, get_knowledge_base


class KBAddRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1)
    source_agent: str = ""
    source_team: str = ""
    category: str = "deliverable"
    tags: List[str] = []
    path: str = ""
    metadata: Dict[str, Any] = {}


class KBSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=100)
    category: str = ""
    agent_id: str = ""


class KBUpdateRequest(BaseModel):
    title: str = ""
    content: str = ""
    category: str = ""
    tags: List[str] = []


@router.post("/knowledge-base/documents", summary="Add document to knowledge base",
             status_code=status.HTTP_201_CREATED)
def kb_add_document(req: KBAddRequest) -> Dict[str, Any]:
    kb = get_knowledge_base()
    doc = KBDocument(
        title=req.title,
        content=req.content,
        source_agent=req.source_agent,
        source_team=req.source_team,
        category=req.category,
        tags=req.tags,
        path=req.path,
        metadata=req.metadata,
    )
    kb.add(doc)
    return doc.to_dict()


@router.get("/knowledge-base/documents", summary="List documents")
def kb_list_documents(category: str = "", agent_id: str = "",
                      team_id: str = "") -> Dict[str, Any]:
    kb = get_knowledge_base()
    docs = kb.list_all(category=category, agent_id=agent_id, team_id=team_id)
    return {"documents": [d.to_summary() for d in docs], "total": len(docs)}


@router.get("/knowledge-base/documents/{doc_id}", summary="Get document by ID")
def kb_get_document(doc_id: str) -> Dict[str, Any]:
    kb = get_knowledge_base()
    doc = kb.get(doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc.to_dict()


@router.put("/knowledge-base/documents/{doc_id}", summary="Update document")
def kb_update_document(doc_id: str, req: KBUpdateRequest) -> Dict[str, Any]:
    kb = get_knowledge_base()
    kwargs = {}
    if req.title:
        kwargs["title"] = req.title
    if req.content:
        kwargs["content"] = req.content
    if req.category:
        kwargs["category"] = req.category
    if req.tags:
        kwargs["tags"] = req.tags
    doc = kb.update(doc_id, **kwargs)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc.to_dict()


@router.delete("/knowledge-base/documents/{doc_id}", summary="Delete document")
def kb_delete_document(doc_id: str) -> Dict[str, str]:
    kb = get_knowledge_base()
    if not kb.delete(doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"status": "deleted", "doc_id": doc_id}


@router.post("/knowledge-base/search", summary="RAG search in knowledge base")
def kb_search(req: KBSearchRequest) -> Dict[str, Any]:
    kb = get_knowledge_base()
    results = kb.search(
        query=req.query,
        max_results=req.max_results,
        category=req.category,
        agent_id=req.agent_id,
    )
    return {"query": req.query, "results": results, "total": len(results)}


@router.get("/knowledge-base/stats", summary="Knowledge base statistics")
def kb_stats() -> Dict[str, Any]:
    kb = get_knowledge_base()
    return kb.stats()


@router.post(
    "/teams/{team_id}/agents/{agent_id}/workspace/ingest-to-kb",
    summary="Ingest workspace files into knowledge base",
)
def ingest_workspace_to_kb(team_id: str, agent_id: str, path: str = "") -> Dict[str, Any]:
    """Ingest all files in a workspace folder into the knowledge base."""
    agent = _get_agent_or_404(team_id, agent_id)
    root = _agent_ws_root(team_id, agent_id)
    target = _safe_subpath(root, path) if path else root
    if not target.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Path not found")

    kb = get_knowledge_base()
    ingested = 0
    files = [target] if target.is_file() else list(target.rglob("*"))
    for f in files:
        if not f.is_file() or f.name.startswith("."):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel_path = str(f.relative_to(root))
        doc = KBDocument(
            title=f.name,
            content=content,
            source_agent=agent_id,
            source_team=team_id,
            category="workspace",
            tags=[agent.name, team_id, f.suffix.lstrip(".")],
            path=rel_path,
        )
        kb.add(doc)
        ingested += 1

    return {"status": "ingested", "files": ingested, "agent_id": agent_id}


# ── Phase 3.1: Batch ingest evolution audit rules into KB ──

@router.post(
    "/knowledge-base/ingest-evolution-rules",
    summary="Batch ingest 41 evolution audit rules into knowledge base",
    status_code=status.HTTP_201_CREATED,
)
def kb_ingest_evolution_rules() -> Dict[str, Any]:
    """Read BUILTIN_AUDIT_RULES from system_evolution and create KB documents."""
    try:
        from src.backend.channels.system_evolution import BUILTIN_AUDIT_RULES
    except ImportError:
        try:
            import importlib, sys
            mod = importlib.import_module("channels.system_evolution")
            BUILTIN_AUDIT_RULES = mod.BUILTIN_AUDIT_RULES
        except Exception as exc:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"Cannot import BUILTIN_AUDIT_RULES: {exc}")

    kb = get_knowledge_base()
    # Avoid duplicates: skip rules already in KB
    existing_titles = {d.title for d in kb._docs.values() if d.category == "evolution_rule"}
    ingested = 0
    skipped = 0
    for rule in BUILTIN_AUDIT_RULES:
        rd = rule.to_dict() if hasattr(rule, "to_dict") else {}
        title = rd.get("title", getattr(rule, "title", ""))
        if title in existing_titles:
            skipped += 1
            continue
        rule_id = rd.get("id", getattr(rule, "id", ""))
        domain = rd.get("domain", getattr(rule, "domain", ""))
        desc = rd.get("description", getattr(rule, "description", ""))
        ref = rd.get("reference", getattr(rule, "reference", ""))
        severity = rd.get("severity", getattr(rule, "severity", "medium"))
        target = rd.get("target_channel", getattr(rule, "target_channel", ""))
        op_domain = rd.get("operational_domain", "")
        content = (
            f"# {rule_id}: {title}\n\n"
            f"**Domain**: {domain}  \n"
            f"**Severity**: {severity}  \n"
            f"**Target Channel**: {target}  \n"
            f"**Operational Domain**: {op_domain}  \n"
            f"**Reference**: {ref}  \n\n"
            f"## Description\n\n{desc}\n"
        )
        doc = KBDocument(
            title=title,
            content=content,
            source_agent="system_evolution",
            source_team="poseidon",
            category="evolution_rule",
            tags=[rule_id, domain, severity, target, "audit", "compliance"],
            path=f"evolution_rules/{rule_id}.md",
            metadata=rd,
        )
        kb.add(doc)
        ingested += 1

    return {"status": "ok", "ingested": ingested, "skipped": skipped,
            "total_rules": len(BUILTIN_AUDIT_RULES)}


# ── Phase 3.2: Auto-ingest pipeline step output into KB ──

def _auto_ingest_step_to_kb(task_id: str, step_key: str,
                             content: str, deliverables: list = None):
    """Called after _save_step_to_pipeline to push step output into KB."""
    try:
        kb = get_knowledge_base()
        tags = [task_id, step_key, "pipeline", "auto_ingest"]
        doc = KBDocument(
            title=f"[{task_id[:8]}] {step_key} output",
            content=content[:50000],  # cap at 50k chars
            source_agent=step_key,
            source_team="build_system",
            category="deliverable",
            tags=tags,
            path=f"pipeline/{task_id}/{step_key}.md",
        )
        kb.add(doc)
        # Also ingest code deliverables
        if deliverables:
            for d in deliverables:
                code_doc = KBDocument(
                    title=f"[{task_id[:8]}] {step_key}/{d.get('path', 'code')}",
                    content=d.get("content", "")[:50000],
                    source_agent=step_key,
                    source_team="build_system",
                    category="deliverable",
                    tags=tags + [d.get("path", "")],
                    path=f"pipeline/{task_id}/{step_key}/{d.get('path', 'file')}",
                )
                kb.add(code_doc)
    except Exception:
        pass  # best-effort, don't break pipeline


# ── Phase 3.3: Enhanced search with source_context ──

@router.post("/knowledge-base/search/enhanced", summary="Enhanced RAG search with source context")
def kb_search_enhanced(req: KBSearchRequest) -> Dict[str, Any]:
    kb = get_knowledge_base()
    results = kb.search(
        query=req.query,
        max_results=req.max_results,
        category=req.category,
        agent_id=req.agent_id,
    )
    # Enrich results with source_context
    for r in results:
        doc = kb.get(r.get("doc_id", ""))
        if doc:
            r["source_context"] = {
                "full_content": doc.content,
                "metadata": doc.metadata,
                "path": doc.path,
            }
    return {"query": req.query, "results": results, "total": len(results)}


# ── Skill Library Routes (演化/验证/效果/版本/发布) ──────────────────────

def _get_skill_library():
    from .skill_library import get_skill_library
    return get_skill_library()

def _get_skill_evolver():
    from .skill_evolver import get_skill_evolver
    return get_skill_evolver()

def _get_skill_verifier():
    from .skill_verifier import get_skill_verifier
    return get_skill_verifier()

def _get_skill_tracker():
    from .skill_tracker import get_skill_tracker
    return get_skill_tracker()


@router.get("/skill-library/overview", summary="技能库全局总览")
def skill_library_overview() -> Dict[str, Any]:
    return _get_skill_library().get_overview()


@router.get("/skill-library", summary="浏览技能库")
def skill_library_browse(
    team_id: str = "",
    query: str = "",
    visibility: str = "",
    category: str = "",
    lifecycle: str = "",
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    return _paginate_optional(
        _get_skill_library().browse(
            team_id=team_id, query=query,
            visibility_filter=visibility,
            category_filter=category,
            lifecycle_filter=lifecycle,
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/skill-library/suggestions", summary="获取演化建议")
def skill_library_suggestions(
    team_id: str = "",
    limit: int = Query(default=0, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    return _paginate_optional(
        _get_skill_evolver().suggest_evolution(team_id), limit=limit, offset=offset
    )


@router.get("/skill-library/duplicates", summary="检测重复/冗余技能（供成本治理 skill_extraction 杠杆高亮）")
def skill_library_duplicates(threshold: float = 0.85, team_id: str = "") -> Dict[str, Any]:
    """跨团队文本相似度检测重复技能；team_id 给定时只保留与该团队相关的对。

    返回 {duplicates: [...], skill_ids: [...]}；前端用 skill_ids 高亮对应水晶。
    """
    dups = _get_skill_library().find_duplicates(threshold=threshold)
    if team_id:
        dups = [d for d in dups
                if d.get("skill_a", {}).get("team") == team_id
                or d.get("skill_b", {}).get("team") == team_id]
    skill_ids = sorted({sid for d in dups for sid in
                        (d.get("skill_a", {}).get("skill_id"), d.get("skill_b", {}).get("skill_id")) if sid})
    return {"duplicates": dups, "skill_ids": skill_ids, "count": len(dups)}


@router.post("/skill-library/merge", summary="合并重复技能（9.6 一键去重以省 token）")
def skill_library_merge(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    """合并 2+ 个重复技能为一个，保留最优 instructions。

    body: {team_id, skill_ids:[a,b,...], strategy?='keep_longest'}
    """
    team_id = body.get("team_id", "")
    skill_ids = body.get("skill_ids", []) or []
    strategy = body.get("strategy", "keep_longest")
    if len(skill_ids) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="need >=2 skill_ids")
    return _get_skill_evolver().merge_skills(team_id, skill_ids, strategy)


@router.post("/skill-library/evolve", summary="触发技能演化")
async def skill_library_evolve(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    team_id = body.get("team_id", "")
    skill_id = body.get("skill_id", "")
    user_feedback = body.get("user_feedback", "")
    if not team_id or not skill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id and skill_id required")
    return await _get_skill_evolver().evolve_skill(team_id, skill_id, user_feedback=user_feedback or None)


@router.post("/skill-library/apply-evolution", summary="应用演化结果")
def skill_library_apply_evolution(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    team_id = body.get("team_id", "")
    skill_id = body.get("skill_id", "")
    new_instructions = body.get("new_instructions", "")
    changelog = body.get("changelog") or []
    if not team_id or not skill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id and skill_id required")
    if not isinstance(changelog, list):
        changelog = [str(changelog)]
    return _get_skill_evolver().apply_evolution(
        team_id, skill_id, new_instructions, changelog=changelog
    )


@router.post("/skill-library/verify", summary="验证技能")
async def skill_library_verify(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    team_id = body.get("team_id", "")
    skill_id = body.get("skill_id", "")
    if not team_id or not skill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id and skill_id required")
    # optional: twin A/B seed count (1–30); default AG_SKILL_TWIN_AB_SEEDS / 5
    n_seeds = body.get("n_seeds") or body.get("twin_seeds")
    if n_seeds is not None:
        try:
            import os
            os.environ["AG_SKILL_TWIN_AB_SEEDS"] = str(max(1, min(30, int(n_seeds))))
        except (TypeError, ValueError):
            pass
    result = await _get_skill_verifier().verify_skill(team_id, skill_id)
    return result.to_dict()


@router.post("/skill-library/publish", summary="发布技能到公共库")
def skill_library_publish(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    team_id = body.get("team_id", "")
    skill_id = body.get("skill_id", "")
    if not team_id or not skill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id and skill_id required")
    return _get_skill_library().publish(team_id, skill_id)


@router.post("/skill-library/import", summary="引入公共技能到团队")
def skill_library_import(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    target_team_id = body.get("target_team_id", "")
    skill_id = body.get("skill_id", "")
    if not target_team_id or not skill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="target_team_id and skill_id required")
    return _get_skill_library().import_skill(target_team_id, skill_id)


@router.get("/skill-library/{skill_id}/lineage", summary="获取技能演化谱系")
def skill_library_lineage(skill_id: str, team_id: str = "") -> Dict[str, Any]:
    return _get_skill_library().get_lineage(skill_id)


@router.get("/skill-library/{skill_id}/evolution-history", summary="获取技能演化历史")
def skill_library_evolution_history(skill_id: str, team_id: str = "") -> Dict[str, Any]:
    return _get_skill_evolver().get_evolution_history(team_id, skill_id)


# ══════════════════════════════════════════════════════════════════
# P1/P2 运维面: 能力画像 / 派单理由 / 成本任务 / 审计 / 运行时事件
# （契约见 tests/test_core_api_smoke.py::test_authenticated_p1_p2_api_shapes）
# ══════════════════════════════════════════════════════════════════

_runtime_events: List[Dict[str, Any]] = []
_RUNTIME_EVENTS_MAX = 500
_cost_tasks: List[Dict[str, Any]] = []


def record_runtime_event(event: Dict[str, Any]) -> None:
    """Append a runtime event to the in-memory ring buffer served by /runtime/events."""
    _runtime_events.append(dict(event))
    if len(_runtime_events) > _RUNTIME_EVENTS_MAX:
        del _runtime_events[: len(_runtime_events) - _RUNTIME_EVENTS_MAX]


@router.get(
    "/teams/{team_id}/agents/{agent_id}/capability-profile",
    summary="Agent capability profile (metrics + skill/tool coverage)",
)
def agent_capability_profile(team_id: str, agent_id: str) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, agent_id)
    team = _tm().get_team(team_id)
    metrics = _get_agent_metrics(agent_id) or {}
    # 解析绑定技能：team-local 优先（含 trait 技能），全局注册表可用时兜底。
    refs = set(agent.skills or [])
    pools: List[Any] = []
    if team:
        pools.extend(team.skills.values())
    try:
        pools.extend(_sr().list_all())
    except Exception:
        pass  # 注册表未初始化时仍能解析 team-local 技能
    resolved: List[Any] = []
    seen: set = set()
    for skill in pools:
        if skill.skill_id in seen:
            continue
        if (
            skill.skill_id in refs
            or skill.name in refs
            or (getattr(skill, "slug", "") and skill.slug in refs)
        ):
            resolved.append(skill)
            seen.add(skill.skill_id)
    verifier_results: Dict[str, Any] = {}
    try:
        verifier_results = getattr(_get_skill_verifier(), "_results", {}) or {}
    except Exception:
        pass
    skills_payload = [
        {
            "id": s.skill_id,
            "name": s.name,
            "visibility": getattr(s, "visibility", ""),
            "version": getattr(s, "version", 1),
            "quality_score": getattr(s, "quality_score", 0.0),
            "verified": bool(verifier_results.get(s.skill_id)),
        }
        for s in resolved
    ]
    tasks_completed = int(metrics.get("tasks_completed", 0) or 0)
    tasks_failed = int(metrics.get("tasks_failed", 0) or 0)
    finished = tasks_completed + tasks_failed
    success_rate = (tasks_completed / finished) if finished else 0.0
    # capability_score = 成功率(60%) + 技能覆盖(25%) + 工具覆盖(15%)；无历史时成功率取中性先验 0.5
    skill_cov = min(len(resolved) / 5.0, 1.0)
    tool_cov = min(len(agent.tools or []) / 5.0, 1.0)
    base = success_rate if finished else 0.5
    capability_score = round(0.6 * base + 0.25 * skill_cov + 0.15 * tool_cov, 4)
    return {
        "agent_id": agent_id,
        "team_id": team_id,
        "role": agent.role,
        "success_rate": round(success_rate, 4),
        "tasks_total": finished,
        "tasks_completed": tasks_completed,
        "tasks_failed": tasks_failed,
        "skill_count": len(skills_payload),
        "skills": skills_payload,
        "tool_count": len(agent.tools or []),
        "capability_score": capability_score,
    }


class DispatchReasonRequest(BaseModel):
    agent_id: str = ""
    task_description: str = ""


@router.post(
    "/teams/{team_id}/tasks/dispatch-reason",
    summary="Explain why an agent fits a task (dispatch transparency)",
)
def dispatch_reason(team_id: str, req: DispatchReasonRequest) -> Dict[str, Any]:
    agent = _get_agent_or_404(team_id, req.agent_id)
    desc = (req.task_description or "").lower()
    reasons: List[str] = []
    skills = _agent_bound_skills(agent, team_id)
    matched = [s.name for s in skills if s.name and s.name.lower() in desc]
    if matched:
        reasons.append(f"技能匹配: {', '.join(matched[:3])}")
    if agent.role:
        reasons.append(f"角色 {agent.role} 与任务类型相符")
    profile = agent_capability_profile(team_id, req.agent_id)
    if profile["tasks_total"]:
        reasons.append(
            f"历史成功率 {profile['success_rate']:.0%}"
            f"（{profile['tasks_completed']}/{profile['tasks_total']} 任务）"
        )
    reasons.append(f"能力评分 {profile['capability_score']}")
    return {"agent_id": req.agent_id, "team_id": team_id, "reasons": reasons}


class CostTaskRequest(BaseModel):
    team_id: str = ""
    violation_type: str = ""
    resource: str = ""
    estimated_saving: float = 0.0
    agent_id: str = ""


@router.post("/cost/generate-task", summary="Generate remediation task from a cost violation")
def cost_generate_task(req: CostTaskRequest) -> Dict[str, Any]:
    import uuid as _uuid

    _get_team_or_404(req.team_id)
    task_id = f"cost-{_uuid.uuid4().hex[:8]}"
    payload = {
        "task_id": task_id,
        "team_id": req.team_id,
        "agent_id": req.agent_id,
        "title": f"成本治理: {req.violation_type} @ {req.resource}",
        "description": (
            f"处理成本违规 {req.violation_type}，资源 {req.resource}，"
            f"预计节省 {req.estimated_saving}"
        ),
        "status": "pending",
        "estimated_saving": float(req.estimated_saving or 0.0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source": "cost_gate",
            "violation_type": req.violation_type,
            "resource": req.resource,
        },
    }
    _cost_tasks.append(payload)
    return payload


@router.get("/cost/savings-report", summary="Aggregated savings from cost remediation tasks")
def cost_savings_report() -> Dict[str, Any]:
    total = sum(t.get("estimated_saving", 0.0) for t in _cost_tasks)
    return {
        "total_savings": round(total, 2),
        "task_count": len(_cost_tasks),
        "tasks": list(_cost_tasks[-100:]),
    }


@router.get("/audit/recent", summary="Recent audit/review entries")
async def audit_recent(limit: int = Query(default=20, ge=1, le=200)) -> Dict[str, Any]:
    from .audit_store import get_audit_store

    store = await get_audit_store()
    entries = await store.list_entries(limit=limit)
    return {"entries": [e.to_dict() for e in entries], "total": len(entries)}


@router.get("/runtime/events", summary="Recent runtime events (ring buffer)")
def runtime_events(limit: int = Query(default=100, ge=1, le=_RUNTIME_EVENTS_MAX)) -> Dict[str, Any]:
    return {"events": list(_runtime_events[-limit:]), "total": len(_runtime_events)}

