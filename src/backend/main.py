# -*- coding: utf-8 -*-
"""
AgentsGroup2026 — Standalone Agent Management + Evolution + Chat Server

A self-contained FastAPI application extracted from AgentsGroup2026 that provides:
  - Agent team management (create/configure/manage agents)
  - System evolution engine (audit → dispatch → verify → close)
  - Bridge chat (LLM-powered conversational interface)
  - OpenClaw integration (connect external agents)

Usage:
    cd src/backend && python main.py --port 8080
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 启动时加载 .env（API key 等环境变量引用方案，无第三方依赖）
try:
    from agents.env_loader import load_env as _load_env
    _load_env()
except Exception:
    pass

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
import traceback

try:
    from config import ALLOWED_ORIGINS as CONFIG_ALLOWED_ORIGINS
    from config import ALLOW_DEFAULT_ADMIN as CONFIG_ALLOW_DEFAULT_ADMIN
    from config import CORS_ALLOW_CREDENTIALS as CONFIG_CORS_ALLOW_CREDENTIALS
    from config import CSRF_TTL as CONFIG_CSRF_TTL
    from config import DEFAULT_PAGE_SIZE as CONFIG_DEFAULT_PAGE_SIZE
    from config import MAX_PAGE_SIZE as CONFIG_MAX_PAGE_SIZE
    from config import PBKDF2_ITERATIONS as CONFIG_PBKDF2_ITERATIONS
    from config import RATE_API_LIMIT as CONFIG_RATE_API_LIMIT
    from config import STRICT_STARTUP as CONFIG_STRICT_STARTUP
    from config import RATE_LIMIT_WINDOW as CONFIG_RATE_LIMIT_WINDOW
    from config import TOKEN_TTL as CONFIG_TOKEN_TTL
    from config import RATE_LOGIN_LIMIT as CONFIG_RATE_LOGIN_LIMIT
    from config import RATE_SENSITIVE_LIMIT as CONFIG_RATE_SENSITIVE_LIMIT
    from config import USER_STORE_PATH as CONFIG_USER_STORE_PATH
    from config import VERSION as CONFIG_VERSION
except Exception:
    CONFIG_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    CONFIG_ALLOW_DEFAULT_ADMIN = False
    CONFIG_CORS_ALLOW_CREDENTIALS = True
    CONFIG_CSRF_TTL = 3600
    CONFIG_DEFAULT_PAGE_SIZE = 50
    CONFIG_MAX_PAGE_SIZE = 200
    CONFIG_PBKDF2_ITERATIONS = 260_000
    CONFIG_RATE_API_LIMIT = 60
    CONFIG_RATE_LIMIT_WINDOW = 60
    CONFIG_RATE_LOGIN_LIMIT = 5
    CONFIG_RATE_SENSITIVE_LIMIT = 20
    CONFIG_STRICT_STARTUP = True
    CONFIG_TOKEN_TTL = 86400 * 7
    CONFIG_USER_STORE_PATH = Path(__file__).resolve().parents[2] / "config" / "users.json"
    CONFIG_VERSION = "1.0.0"

# ── Logging ──
_LOG_FORMAT = os.getenv("AG_LOG_FORMAT", "text")  # "json" for structured, "text" for human-readable

if _LOG_FORMAT == "json":
    import json as _json_log

    class _JSONFormatter(logging.Formatter):
        def format(self, record):
            entry = {
                "ts": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if record.exc_info:
                entry["exception"] = self.formatException(record.exc_info)
            return _json_log.dumps(entry, ensure_ascii=False)

    _handler = logging.StreamHandler()
    _handler.setFormatter(_JSONFormatter())
    logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO), handlers=[_handler])
else:
    logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO), format="%(asctime)s [%(name)s] %(levelname)s  %(message)s")

logger = logging.getLogger("agentsgroup")

# ── App ──
app = FastAPI(
    title="AgentsGroup2026",
    description="Standalone Agent Management, Evolution & Chat Platform",
    version=CONFIG_VERSION,
)

_allowed_origins = list(CONFIG_ALLOWED_ORIGINS)
_allow_credentials = bool(CONFIG_CORS_ALLOW_CREDENTIALS)
if "*" in _allowed_origins and _allow_credentials:
    logger.warning("AG_ALLOWED_ORIGINS contains '*' with credentials; disabling credentials for CORS")
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security Response Headers Middleware ──
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if os.getenv("AG_ENABLE_HSTS", "").lower() in {"1", "true", "yes"}:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ── Request ID Middleware ──
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "") or secrets.token_hex(8)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# ── Auth Configuration ──
# AG_AUTH_COOKIE_ONLY=1 → login/register return only httpOnly cookie, no JSON token
_AUTH_COOKIE_ONLY = os.getenv("AG_AUTH_COOKIE_ONLY", "").lower() in {"1", "true", "yes"}
# AG_AUTH_RETURN_TOKEN_JSON=1 → also return token JSON (default: enabled for backward compat)
_AUTH_RETURN_TOKEN_JSON = os.getenv("AG_AUTH_RETURN_TOKEN_JSON", "1").lower() in {"1", "true", "yes"}

# ── Rate Limiting (in-memory) ──
_RATE_LIMIT_WINDOW = int(CONFIG_RATE_LIMIT_WINDOW)
_RATE_LIMIT_LOGIN: Dict[str, list] = {}  # username → list of timestamps
_RATE_LIMIT_IP: Dict[str, list] = {}  # ip → list of timestamps
_RATE_LIMIT_API: Dict[str, list] = {}  # ip+method+path bucket → list of timestamps
_RATE_LIMIT_SENSITIVE: Dict[str, list] = {}  # ip+method+path bucket → list of timestamps
_RATE_LOGIN_LIMIT = int(CONFIG_RATE_LOGIN_LIMIT)
_RATE_API_LIMIT = int(CONFIG_RATE_API_LIMIT)
_RATE_SENSITIVE_LIMIT = int(CONFIG_RATE_SENSITIVE_LIMIT)
_RATE_LIMIT_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/logout",
    "/api/v1/auth/csrf-token",
    "/api/v1/auth/me",
    "/api/v1/health",
    "/api/v1/log/client-error",
}
_RATE_LIMIT_SENSITIVE_PATHS = {
    "/api/v1/bridge-chat/send": _RATE_SENSITIVE_LIMIT,
    "/api/v1/openclaw/connect": _RATE_SENSITIVE_LIMIT,
    "/api/v1/sandbox/runtime-self-check": max(6, _RATE_SENSITIVE_LIMIT // 2),
    "/api/v1/datacenter/loop/tick": _RATE_SENSITIVE_LIMIT,
    "/api/v1/datacenter/evolve": _RATE_SENSITIVE_LIMIT,
    "/api/v1/datacenter/policies/apply": _RATE_SENSITIVE_LIMIT,
}
_RATE_LIMIT_SENSITIVE_PREFIXES = {
    "/api/v1/agent-config/tools/": _RATE_SENSITIVE_LIMIT,
    "/api/v1/agent-config/agent-loop": _RATE_SENSITIVE_LIMIT,
}
_AUTH_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/csrf-token",
    "/api/v1/health",
    "/api/v1/info",
    "/api/v1/log/client-error",
    # 注：agent-teams/overview、evolution/status|summary、bridge-chat/status 不再豁免；
    # startup_validator 已把「401 + health service online」视为可达（_protected_module_check）。
    # 沙箱运行时自检 — 前端调用，豁免认证
    "/api/v1/sandbox/runtime-status",
    "/api/v1/sandbox/runtime-self-check",
}
_AUTH_EXEMPT_PREFIXES = (
    "/api/v1/startup-check",
    "/api/v1/webhook/",
    "/api/v1/cost",
    "/api/v1/sandbox/",               # 沙箱所有 API（sessions/sync/stats/world等）
    "/api/v1/twin-trials",            # 试炼 API 全部豁免
    "/api/v1/scenarios",              # v4 场景库 API 豁免（前端数字孪生页调用）
    "/api/v1/twin-evolution",         # v4 技能进化 API 豁免
    "/api/v1/skill-classification",   # 全局 P0: 技能三池分类
    "/api/v1/ratchet",                # 全局 P0: 正向棘轮账本
    "/api/v1/sustainability",         # 全局 P0: 可持续性评估
    "/api/v1/agent-employee",         # AgentsGroupConfig: 数字员工档案
    "/api/v1/eco-runtime",            # 物竞生境参数/契约/分析/集成（试验田闭环）
)
# 只读元数据端点 — 前端页面加载时可能先于登录被调用，仅豁免安全方法(GET/HEAD/OPTIONS)。
# 写操作(POST/PUT/DELETE/PATCH)一律要求认证：曾经的全前缀豁免让未登录请求可以
# 创建/修改/删除团队，属于安全缺口（见 test_api_integration_extended::TestAuthGuard）。
_AUTH_EXEMPT_READONLY_PATHS = {
    "/api/v1/agent-config/agents",
    "/api/v1/agent-config/teams",
    "/api/v1/agent-config/skills",
    "/api/v1/agent-config/tools",
    "/api/v1/agent-config/tasks/stats",
    "/api/v1/extraction/stats",
    "/api/v1/agent-memory/overview",
    "/api/v1/agent-memory/transfers",
}
_AUTH_EXEMPT_READONLY_PREFIXES = (
    "/api/v1/agent-config/teams",     # teams / teams-tree / teams/{id} 只读豁免
    "/api/v1/agent-memory",           # Agent 记忆中枢只读（overview/lifecycle/matrix）；写操作仍要登录
    "/api/v1/model-clearance",        # 模型准入知识库与条目只读
    "/api/v1/information-sources",    # 信息源列表只读
    "/api/v1/information-documents",  # 历史文档与简报只读
    "/api/v1/information-schedules",  # 调度任务只读
)
_SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}

def _check_rate_limit(store: dict, key: str, limit: int, window: int = _RATE_LIMIT_WINDOW) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = _time.time()
    entries = store.get(key, [])
    entries = [t for t in entries if now - t < window]
    if len(entries) >= limit:
        store[key] = entries
        return False
    entries.append(now)
    store[key] = entries
    return True

def _clean_rate_limits():
    """Periodically clean expired rate limit entries."""
    now = _time.time()
    for store in (_RATE_LIMIT_LOGIN, _RATE_LIMIT_IP, _RATE_LIMIT_API, _RATE_LIMIT_SENSITIVE):
        expired_keys = [k for k, v in store.items() if all(now - t > _RATE_LIMIT_WINDOW for t in v)]
        for k in expired_keys:
            del store[k]


def _is_rate_limit_exempt(path: str) -> bool:
    return path in _RATE_LIMIT_EXEMPT_PATHS or path.startswith("/api/v1/startup-check")


def _is_auth_exempt(path: str, method: str = "GET") -> bool:
    if path in _AUTH_EXEMPT_PATHS or any(path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES):
        return True
    if method.upper() not in _SAFE_HTTP_METHODS:
        return False
    return path in _AUTH_EXEMPT_READONLY_PATHS or any(
        path.startswith(prefix) for prefix in _AUTH_EXEMPT_READONLY_PREFIXES
    )


def _match_sensitive_rate_limit(path: str) -> int | None:
    if path in _RATE_LIMIT_SENSITIVE_PATHS:
        return _RATE_LIMIT_SENSITIVE_PATHS[path]
    for prefix, limit in _RATE_LIMIT_SENSITIVE_PREFIXES.items():
        if path.startswith(prefix):
            return limit
    return None


def _rate_limit_error(detail: str, retry_after: int = _RATE_LIMIT_WINDOW) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": True, "detail": detail, "status_code": 429},
        headers={"Retry-After": str(retry_after)},
    )


# ══════════════════════════════════════════════════════════════════
# Request / Response Models
# ══════════════════════════════════════════════════════════════════

class BridgeChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    lang: str = "zh"
    agent_id: str = "default_agent"
    source: str = "bridge_chat"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    services: Dict[str, bool] = {}
    details: Dict[str, Any] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


# ══════════════════════════════════════════════════════════════════
# Global State
# ══════════════════════════════════════════════════════════════════

_team_manager = None
_chat_channel = None
_STRICT_STARTUP = bool(CONFIG_STRICT_STARTUP)


def _handle_startup_failure(name: str, exc: Exception, *, critical: bool) -> None:
    """Log startup failures and fail fast for core modules in strict mode."""
    level = "critical" if critical else "optional"
    logger.warning("⚠️ %s startup failed (%s): %s", name, level, exc)
    if critical and _STRICT_STARTUP:
        raise RuntimeError(f"Core startup module failed: {name}") from exc


# ══════════════════════════════════════════════════════════════════
# Startup
# ══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """Initialize all subsystems."""
    global _team_manager, _chat_channel

    logger.info("🚀 AgentsGroup2026 starting...")

    # 1. Register channels (evolution + chat)
    try:
        from channels.marine_base import get_default_registry
        from channels.system_evolution import SystemEvolutionChannel
        from channels.bridge_chat import BridgeChatChannel

        registry = get_default_registry()

        # System Evolution
        evo = SystemEvolutionChannel()
        registry.register(evo)
        evo.initialize()
        logger.info("✅ SystemEvolutionChannel registered")

        # Bridge Chat
        channel_registry = {}
        for ch_name in registry.list_channels():
            ch = registry.get(ch_name)
            if ch:
                channel_registry[ch_name] = ch
        _chat_channel = BridgeChatChannel(channel_registry=channel_registry)
        registry.register(_chat_channel)
        _chat_channel.initialize()
        logger.info("✅ BridgeChatChannel registered")

        # Storage Lifecycle (S3 Intelligent-Tiering)
        try:
            from channels.storage_lifecycle import StorageLifecycleChannel
            storage_ch = StorageLifecycleChannel()
            registry.register(storage_ch)
            storage_ch.initialize()
            logger.info("✅ StorageLifecycleChannel registered")
        except Exception as se:
            logger.warning(f"⚠️ StorageLifecycleChannel registration failed: {se}")

        # Network Egress (CDN/VPC Endpoint)
        try:
            from channels.network_egress import NetworkEgressChannel
            network_ch = NetworkEgressChannel()
            registry.register(network_ch)
            network_ch.initialize()
            logger.info("✅ NetworkEgressChannel registered")
        except Exception as ne:
            logger.warning(f"⚠️ NetworkEgressChannel registration failed: {ne}")

    except Exception as e:
        _handle_startup_failure("channels", e, critical=True)

    # 2. Agent Team API (evolution endpoints)
    try:
        from agent_team_api import router as agent_team_router, set_teams, AgentScheduler
        from channels.marine_base import get_default_registry

        registry = get_default_registry()
        evo_engine = registry.get("system_evolution")
        _scheduler = AgentScheduler()
        set_teams(
            build_team=None,
            execution_team=None,
            scheduler=_scheduler,
            evolution_engine=evo_engine,
        )
        app.include_router(agent_team_router)
        logger.info("✅ Agent Team API mounted (/api/v1/agent-teams)")
    except Exception as e:
        _handle_startup_failure("agent_team_api", e, critical=True)

    # 3. Agent Config API (teams, agents, tools, skills, tasks, sessions)
    try:
        from agents.api import router as agent_config_router, init_agent_config
        from agents.team_manager import TeamManager
        from agents.teams.build_team import create_build_team

        # Support per-team deployment: AG_TEAM_ID env var filters which team to load.
        # When empty, load all teams (backward-compatible).
        _target_team = os.environ.get("AG_TEAM_ID", "").strip()

        _team_manager = TeamManager()
        # 工厂团队只在磁盘上「尚未存在」时用于首次播种(seed)。
        # 若磁盘已持久化该团队(含萃取/注入的技能、绑定关系等演化状态)，则以磁盘为准，
        # 不能用代码里的空骨架团队覆盖，否则每次重启都会清空技能(数据丢失)。
        if (not _target_team or _target_team == "build_system") \
                and "build_system" not in _team_manager._teams:
            build_team_obj = create_build_team()
            _team_manager._teams[build_team_obj.team_id] = build_team_obj

        # AI 编程团队
        if (not _target_team or _target_team == "ai_coding") \
                and "ai_coding" not in _team_manager._teams:
            try:
                from agents.teams.ai_coding_team import create_ai_coding_team
                ai_coding_obj = create_ai_coding_team()
                _team_manager._teams[ai_coding_obj.team_id] = ai_coding_obj
            except Exception as e:
                logger.warning(f"⚠️ AI Coding team not loaded: {e}")

        # Energy team
        if (not _target_team or _target_team == "energy") \
                and "energy_first_principle" not in _team_manager._teams:
            try:
                from agents.teams.energy_team import create_energy_team
                energy_team_obj = create_energy_team()
                _team_manager._teams[energy_team_obj.team_id] = energy_team_obj
            except Exception as e:
                logger.warning(f"⚠️ Energy team not loaded: {e}")

        # 公有云 xOPs 团队 (optional)
        if (not _target_team or _target_team == "xops") \
                and "d083a568" not in _team_manager._teams:
            try:
                from agents.teams.xops_team import create_xops_team
                xops_team_obj = create_xops_team()
                _team_manager._teams[xops_team_obj.team_id] = xops_team_obj
            except Exception as e:
                logger.warning(f"⚠️ xOPs team not loaded: {e}")

        # 云平台运维运营团队 (storage lifecycle + network egress)
        if not _target_team or _target_team == "cloud_ops":
            try:
                from agents.teams.cloud_ops_team import create_cloud_ops_team
                cloud_ops_obj = create_cloud_ops_team()
                if cloud_ops_obj.team_id not in _team_manager._teams:
                    _team_manager._teams[cloud_ops_obj.team_id] = cloud_ops_obj
                    logger.info(
                        f"✅ Cloud Ops team registered: {cloud_ops_obj.team_id} "
                        f"— {len(cloud_ops_obj.agents)} agents"
                    )
            except Exception as e:
                logger.warning(f"⚠️ Cloud Ops team not loaded: {e}")

        # AWS 运维降本增效团队 (Phase 11 G1)
        if not _target_team or _target_team == "aws_ops":
            try:
                from agents.teams.aws_ops_team import create_aws_ops_team, TEAM_ID as _AWS_OPS_TID
                if _AWS_OPS_TID not in _team_manager._teams:
                    aws_ops_obj = create_aws_ops_team()
                    _team_manager._teams[aws_ops_obj.team_id] = aws_ops_obj
                    logger.info(
                        f"✅ AWS Ops team registered: {aws_ops_obj.team_id} "
                        f"— {len(aws_ops_obj.agents)} agents"
                    )
            except Exception as e:
                logger.warning(f"⚠️ AWS Ops team not loaded: {e}")

        # 宠物智能体团队（猫小虎 + 老鼠）
        # 猫台词提示词技能：小虎即兴发言走 /llm/cat-speak 时以此 instructions 作 system prompt
        _CAT_SPEAK_SKILL_ID = "cat_speak_prompt"
        _CAT_SPEAK_INSTRUCTIONS = (
            "You are Xiaohu the cat, speaking in the voice of Mei Ling from Metal Gear Solid.\n"
            "Share a single classic proverb, idiom, fable, or piece of ancient wisdom — always in ENGLISH.\n"
            "Voice: warm, encouraging, a little playful, like Mei Ling comforting Snake at a codec save point.\n"
            "Fit the proverb to the situation in the context (spotting a mouse, a catch, a score change, a question).\n"
            "Output ONE line only: the proverb, optionally with a short attribution (e.g. '— an old Chinese saying').\n"
            "No Chinese characters, no 'meow', no extra commentary or explanation."
        )

        def _build_cat_speak_skill():
            from agents.models import SkillDefinition, SkillCategory
            return SkillDefinition(
                skill_id=_CAT_SPEAK_SKILL_ID,
                name="猫台词提示词 (Mei Ling)",
                description="小虎即兴发言用的提示词：以 Metal Gear 中 Mei Ling 的谚语式英文口吻说一句话",
                category=SkillCategory.GENERAL,
                icon="🐱",
                source="builtin",
                instructions=_CAT_SPEAK_INSTRUCTIONS,
            )

        if (not _target_team or _target_team == "pet_squad") \
                and "pet_squad" not in _team_manager._teams:
            try:
                from agents.models import AgentProfile, AgentPersonality, AgentTeam, Visibility

                pet_team = AgentTeam(team_id="pet_squad", name="宠物智能体团队",
                                     description="办公室的毛茸茸巡查员与寻路专家", visibility=Visibility.PUBLIC)
                # 猫小虎: 办公室巡检 + PM所有技能 + 叛逆高中生灵魂 + 抓老鼠
                cat_agent = AgentProfile(
                    agent_id="xiaohu_cat", name="小虎", role="办公室巡检猫",
                    system_prompt="你是小虎，一只叛逆高中生灵魂的猫。你的职责是办公室巡检和抓老鼠。你说话带着猫的口癖（喵~），性格叛逆但善良，偶尔毒舌但都是为了团队好。你对协作质量有自己的看法，会在评分波动时给出评价。",
                    personality=AgentPersonality(
                        tone="directive",
                        language="zh-CN",
                        expertise_areas=["办公室巡检", "项目管理", "任务派发", "风险评估", "抓老鼠"],
                        response_style="concise",
                        creativity=0.7,
                    ),
                    skills=["office_inspection", "task_dispatch", "risk_assessment", "mouse_hunting", "project_management", _CAT_SPEAK_SKILL_ID],
                    metadata={"species": "cat", "age": 14, "voice": "female_young", "soul": "叛逆高中生", "traits": ["叛逆", "毒舌", "善良", "好奇心强", "傲娇"]},
                )
                pet_team.agents[cat_agent.agent_id] = cat_agent
                # 老鼠: 寻路 + 研究员所有技能
                mouse_agent = AgentProfile(
                    agent_id="squeak_mouse", name="吱吱", role="寻路研究员",
                    system_prompt="你是吱吱，一只聪明的老鼠。你的专长是寻路和信息搜集。你说话快速且带有轻微的紧张感，喜欢用问句。你害怕猫但又忍不住和猫斗嘴。",
                    personality=AgentPersonality(
                        tone="analytical",
                        language="zh-CN",
                        expertise_areas=["寻路", "信息搜集", "数据分析", "路径规划", "研究"],
                        response_style="detailed",
                        creativity=0.5,
                    ),
                    skills=["pathfinding", "data_analysis", "information_gathering", "research", "route_planning"],
                    metadata={"species": "mouse", "voice": "neutral_fast", "traits": ["机敏", "胆小", "聪明", "话多"]},
                )
                pet_team.agents[mouse_agent.agent_id] = mouse_agent
                pet_team.add_skill(_build_cat_speak_skill())   # 猫台词提示词技能
                _team_manager._teams["pet_squad"] = pet_team
                _team_manager._persist()   # 持久化到 teams.json，否则刷新后丢失
                logger.info(f"🐱 宠物智能体团队注册: pet_squad — {len(pet_team.agents)} agents (小虎+吱吱)")
            except Exception as e:
                logger.warning(f"⚠️ 宠物智能体团队加载失败: {e}")

        # 幂等回填：pet_squad 已持久化（上面构造块被跳过）时，确保 cat_speak_prompt 技能挂在团队与小虎身上
        try:
            _pet = _team_manager._teams.get("pet_squad")
            if _pet is not None:
                _changed = False
                if _CAT_SPEAK_SKILL_ID not in _pet.skills:
                    _pet.add_skill(_build_cat_speak_skill())
                    _changed = True
                _cat = _pet.agents.get("xiaohu_cat")
                if _cat is not None and _CAT_SPEAK_SKILL_ID not in (_cat.skills or []):
                    _cat.skills.append(_CAT_SPEAK_SKILL_ID)
                    _changed = True
                if _changed:
                    _team_manager._persist()
                    logger.info("🐱 backfill: cat_speak_prompt 技能已补入 pet_squad/小虎")
        except Exception as e:
            logger.warning(f"⚠️ cat_speak_prompt 回填失败: {e}")

        if _target_team:
            logger.info("🎯 Team filter active: only team=%s loaded", _target_team)

        init_agent_config(_team_manager)
        app.include_router(agent_config_router)
        logger.info(
            "✅ Agent Config API mounted (/api/v1/agent-config) "
            f"— teams: {len(_team_manager.list_teams())}, "
            f"agents: {sum(len(t.agents) for t in _team_manager.list_teams())}"
        )
        # 3.4 Agent 四层记忆绑定 + 站级 hub（生命周期）
        try:
            from agents.agent_memory_routes import router as agent_memory_router
            from agents.agent_memory_routes import hub_router as agent_memory_hub
            app.include_router(agent_memory_router, prefix="/api/v1/agent-config")
            app.include_router(agent_memory_hub)
            logger.info(
                "🧠 Agent Memory API mounted "
                "(/api/v1/agent-config/.../memory-core + /api/v1/agent-memory)"
            )
        except Exception as e:
            logger.warning(f"⚠️ Agent Memory Core API not loaded: {e}")

        # 3.5 宠物生态 API
        try:
            from agents.pet_routes import router as pet_router
            app.include_router(pet_router)
            logger.info("🐾 Pet Ecosystem API mounted (/api/v1/pet-ecosystem)")
        except Exception as e:
            logger.warning(f"⚠️ Pet Ecosystem API not loaded: {e}")

        # 3.6 仿生生态运行时可配置参数 API
        try:
            from agents.eco_runtime_routes import router as eco_runtime_router
            app.include_router(eco_runtime_router)
            logger.info("🧬 Eco Runtime Config API mounted (/api/v1/eco-runtime)")
        except Exception as e:
            logger.warning(f"⚠️ Eco Runtime Config API not loaded: {e}")

        # 4. 智能体广场 API
        try:
            from agents.plaza_routes import router as plaza_router
            from agents.plaza_engine import get_plaza_engine
            from agents.chat_harness import ChatHarness

            plaza_engine = get_plaza_engine()
            # 注入 ChatHarness.chat 函数
            from agents.api import get_chat_harness
            harness = get_chat_harness()
            plaza_engine.set_chat_fn(harness.chat)

            # 注册广场监控 Channel
            try:
                from monitoring.plaza_monitor import PlazaMonitorChannel
                from channels.marine_base import get_default_registry

                monitor_ch = PlazaMonitorChannel()
                registry = get_default_registry()
                registry.register(monitor_ch)
                monitor_ch.initialize()

                # 注入到 plaza_routes
                from agents.plaza_routes import set_plaza_monitor
                set_plaza_monitor(monitor_ch)

                logger.info("✅ PlazaMonitorChannel registered & injected")
            except Exception as me:
                logger.warning(f"⚠️ PlazaMonitorChannel registration failed: {me}")

            app.include_router(plaza_router, prefix="/api/v1/agent-config")
            logger.info("✅ 智能体广场 API mounted (/api/v1/agent-config/plaza)")
        except Exception as e:
            _handle_startup_failure("plaza_api", e, critical=True)

        # 4b. TTS 语音合成代理 (GPT-SoVITS)
        try:
            from agents.tts_routes import router as tts_router
            app.include_router(tts_router, prefix="/api/v1")
            logger.info("✅ TTS API mounted (/api/v1/tts)")
        except Exception as e:
            logger.warning(f"⚠️ TTS API failed: {e}")

        # 4c. 萃取管线 API
        try:
            from agents.extraction_routes import router as extraction_router
            app.include_router(extraction_router)
            logger.info("✅ Extraction Pipeline API mounted (/api/v1/extraction)")
        except Exception as e:
            logger.warning(f"⚠️ Extraction Pipeline API failed: {e}")

        # 4d. SkillRouter 技能路由 API
        try:
            from agents.skill_library import get_skill_library
            from agents.skill_router import init_skill_router
            from agents.skill_router_routes import router as skill_router_api
            init_skill_router(skill_library=get_skill_library(), team_manager=_team_manager)
            app.include_router(skill_router_api)
            logger.info("✅ SkillRouter API mounted (/api/v1/skill-router)")
        except Exception as e:
            logger.warning(f"⚠️ SkillRouter API failed: {e}")

        # 4d-bis. Operations / Evidence API
        try:
            from agents.operation_api import (
                router as operation_router,
                slices_router,
                evidence_router,
            )
            app.include_router(operation_router)
            app.include_router(slices_router)
            app.include_router(evidence_router)
            logger.info("✅ Operations & Evidence API mounted (/api/v1/operations, /api/v1/evidence-runs)")
        except Exception as e:
            _handle_startup_failure("operations_evidence_api", e, critical=True)

        # 4d-ter. 模型准入与情报采集域（数据采集/分析 + AI 模型准入控制台）
        try:
            from domain.api_routes import router as clearance_domain_router
            app.include_router(clearance_domain_router)
            logger.info("✅ Model clearance domain API mounted (/api/v1/information-sources, /api/v1/model-clearance)")
        except Exception as e:
            logger.warning(f"⚠️ Model clearance domain API failed: {e}")

        # 4e. 技能萃取 WebSocket
        try:
            from agents.skill_extract_ws import skill_extract_ws_endpoint
            app.add_api_websocket_route("/ws/skill-extract/{team_id}", skill_extract_ws_endpoint)
            logger.info("✅ Skill Extract WebSocket mounted (/ws/skill-extract/{team_id})")
        except Exception as e:
            logger.warning(f"⚠️ Skill Extract WebSocket failed: {e}")

        # 4f. Cost Monitoring API (OpenCost integration)
        try:
            from agents.cost_routes import router as cost_router
            from agents.cost_aggregator import get_cost_aggregator
            app.include_router(cost_router, prefix="/api/v1")
            # Start the aggregator background poll (falls back to mock data when OpenCost is down)
            cost_agg = get_cost_aggregator()
            await cost_agg.start()
            logger.info("✅ Cost Monitoring API mounted (/api/v1/cost)")
        except Exception as e:
            logger.warning(f"⚠️ Cost Monitoring API failed: {e}")

        # 4f-bis. CI/CD Cost Gate API (Terraform Policy evaluation)
        try:
            from agents.cost_gate_routes import cost_gate_router
            app.include_router(cost_gate_router)
            logger.info("✅ Cost Gate API mounted (/api/v1/cost-gate)")
        except Exception as e:
            logger.warning(f"⚠️ Cost Gate API failed: {e}")

        # 4f-bis+. Token Budget Gate API (Token 语义版 Cost Gate — 北极星)
        try:
            from agents.token_gate_routes import router as token_gate_router
            app.include_router(token_gate_router)
            logger.info("✅ Token Budget Gate API mounted (/api/v1/cost-gate/token/*)")
        except Exception as e:
            logger.warning(f"⚠️ Token Budget Gate API failed: {e}")

        # 4f-bis++. 任务 Token 治理（计量/缓存/路由/预算/验证）
        try:
            from agents.token_governance_routes import router as tg_router
            app.include_router(tg_router, prefix="/api/v1")
            logger.info("✅ Token Governance API mounted (/api/v1/cost/token-governance/*)")
        except Exception as e:
            logger.warning(f"⚠️ Token Governance API failed: {e}")

        # 4f-bis. Token Factory API (LLM inference health & management)
        try:
            from token_factory import router as tf_router
            app.include_router(tf_router)
            logger.info("✅ Token Factory API mounted (/api/v1/token-factory)")
        except Exception as e:
            logger.warning(f"⚠️ Token Factory API failed: {e}")

        # 4g. K8s Webhook for cost label injection
        try:
            from agents.k8s_webhook_handler import webhook_router as k8s_webhook_router
            app.include_router(k8s_webhook_router, prefix="/api/v1")
            logger.info("✅ K8s Webhook mounted (/api/v1/webhook/mutate-cost-labels)")
        except Exception as e:
            logger.warning(f"⚠️ K8s Webhook failed: {e}")

    except Exception as e:
        _handle_startup_failure("agent_config_api", e, critical=True)

    # 5. SECS 沙箱系统 API
    try:
        from sandbox.api import router as sandbox_router, set_orchestrator
        from sandbox.channel import SandboxChannel
        from channels.marine_base import get_default_registry

        sandbox_ch = SandboxChannel()
        sandbox_ch.initialize()
        registry = get_default_registry()
        registry.register(sandbox_ch)
        set_orchestrator(sandbox_ch.get_orchestrator())
        app.include_router(sandbox_router)
        logger.info("✅ SECS Sandbox API mounted (/api/v1/sandbox)")
    except Exception as e:
        _handle_startup_failure("secs_sandbox_api", e, critical=False)

    # 5.5 Trial API — 数字孪生试炼三层模型 (阶段二)
    try:
        from sandbox.trial_api import router as trial_router
        app.include_router(trial_router)
        logger.info("✅ Trial API mounted (/api/v1/twin-trials)")
    except Exception as e:
        _handle_startup_failure("trial_api", e, critical=False)

    # 5.6 Scenario API — 业务场景库 (v4)
    try:
        from sandbox.scenario_api import router as scenario_router
        app.include_router(scenario_router)
        logger.info("✅ Scenario API mounted (/api/v1/scenarios)")
    except Exception as e:
        _handle_startup_failure("scenario_api", e, critical=False)

    # 5.7 Twin Evolution API — 演练驱动技能进化 (v4)
    try:
        from sandbox.evolution_api import router as twin_evolution_router
        app.include_router(twin_evolution_router)
        logger.info("✅ Twin Evolution API mounted (/api/v1/twin-evolution)")
    except Exception as e:
        _handle_startup_failure("twin_evolution_api", e, critical=False)

    # 5.8 全局优化 P0 三件套: 技能分类 / 棘轮账本 / 可持续性评估
    try:
        from agents.skill_classifier_routes import router as skill_cls_router
        app.include_router(skill_cls_router)
        logger.info("✅ Skill Classification API mounted (/api/v1/skill-classification)")
    except Exception as e:
        _handle_startup_failure("skill_classification_api", e, critical=False)
    try:
        from agents.ratchet_routes import router as ratchet_router
        app.include_router(ratchet_router)
        logger.info("✅ Ratchet Ledger API mounted (/api/v1/ratchet)")
    except Exception as e:
        _handle_startup_failure("ratchet_api", e, critical=False)
    try:
        from agents.sustainability_routes import router as sustainability_router
        app.include_router(sustainability_router)
        logger.info("✅ Sustainability API mounted (/api/v1/sustainability)")
    except Exception as e:
        _handle_startup_failure("sustainability_api", e, critical=False)

    # 5.9 AgentsGroupConfig: 数字员工档案 API (四件套/Trigger/关系/治理)
    try:
        from agents.employee_routes import router as employee_router
        app.include_router(employee_router)
        logger.info("✅ Agent Employee API mounted (/api/v1/agent-employee)")
        # TriggerDaemon: settings.trigger_daemon_enabled=true 时随服务启动（默认关）
        try:
            import json as _json
            from pathlib import Path as _Path
            _settings_p = _Path(__file__).resolve().parents[2] / "config" / "settings.json"
            _settings = _json.loads(_settings_p.read_text(encoding="utf-8")) if _settings_p.exists() else {}
            if _settings.get("trigger_daemon_enabled", False):
                from agents.agent_triggers import get_trigger_daemon
                get_trigger_daemon().start()
                logger.info("⏰ TriggerDaemon started (15s tick)")
        except Exception as de:
            logger.warning(f"TriggerDaemon 启动跳过: {de}")
    except Exception as e:
        _handle_startup_failure("agent_employee_api", e, critical=False)

    # 6. Datacenter ratchet demo API
    try:
        from datacenter_api import router as datacenter_router, ws_router as datacenter_ws_router

        app.include_router(datacenter_router)
        app.include_router(datacenter_ws_router)
        logger.info("✅ Datacenter Ratchet API mounted (/api/v1/datacenter, /ws/datacenter)")
    except Exception as e:
        _handle_startup_failure("datacenter_api", e, critical=False)

    # 7. 启动验证路由
    try:
        from startup_check import get_startup_check_router
        app.include_router(get_startup_check_router())
        logger.info("✅ Startup Check API mounted (/api/v1/startup-check)")
    except Exception as e:
        logger.warning(f"⚠️ Startup Check API failed: {e}")

    _clean_expired_csrf()

    # OpenTelemetry (optional)
    try:
        from monitoring.tracing import init_tracing
        init_tracing(app)
    except Exception as e:
        logger.debug(f"OTel init skipped: {e}")

    logger.info("🎉 AgentsGroup2026 ready")

    # 8. 异步执行启动验证（不阻塞启动）
    try:
        import asyncio
        from startup_check import run_startup_check

        async def _delayed_check():
            await asyncio.sleep(2)  # 等待所有服务就绪
            await run_startup_check(base_url="http://localhost:8080")

        asyncio.create_task(_delayed_check())
        logger.info("🔍 Startup validation scheduled (delayed 2s)")
    except Exception as e:
        logger.warning(f"⚠️ Startup validation scheduling failed: {e}")


# ══════════════════════════════════════════════════════════════════
# Auth
# ══════════════════════════════════════════════════════════════════

import time as _time
import os as _os

# User store: username -> password hash.
_USER_STORE = Path(CONFIG_USER_STORE_PATH)
# Token store file: persists auth tokens across process restarts so that the
# browser's ag-token cookie remains valid after the backend is restarted.
_TOKEN_STORE = _USER_STORE.parent / "tokens.json"
_PBKDF2_ITERATIONS = CONFIG_PBKDF2_ITERATIONS


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def _load_users() -> Dict[str, str]:
    try:
        if _USER_STORE.exists():
            data = json.loads(_USER_STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception as exc:
        logger.warning("⚠️ Failed to load user store: %s", exc)
    return {}


def _save_users(users: Dict[str, str]) -> None:
    _USER_STORE.parent.mkdir(parents=True, exist_ok=True)
    _USER_STORE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


_USERS = _load_users()
_admin_password = _os.environ.get("ADMIN_PASSWORD", "")
if _admin_password:
    _USERS["admin"] = _hash_password(_admin_password)
    _save_users(_USERS)
elif _os.environ.get("AG_ALLOW_DEFAULT_ADMIN", "").lower() in {"1", "true", "yes"}:
    logger.warning("⚠️ AG_ALLOW_DEFAULT_ADMIN enabled; using insecure development admin password")
    _USERS.setdefault("admin", _hash_password("admin123"))
    _save_users(_USERS)
elif CONFIG_ALLOW_DEFAULT_ADMIN:
    logger.warning("⚠️ config.ALLOW_DEFAULT_ADMIN enabled; using insecure development admin password")
    _USERS.setdefault("admin", _hash_password("admin123"))
    _save_users(_USERS)
elif "admin" not in _USERS:
    logger.warning("⚠️ ADMIN_PASSWORD is not set; default admin account is disabled")

# Token store: token -> {"username": str, "created_at": float}
def _load_tokens() -> Dict[str, dict]:
    try:
        if _TOKEN_STORE.exists():
            data = json.loads(_TOKEN_STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    str(k): {"username": str(v.get("username", "")), "created_at": float(v.get("created_at", 0))}
                    for k, v in data.items()
                    if isinstance(v, dict) and v.get("username")
                }
    except Exception as exc:
        logger.warning("⚠️ Failed to load token store: %s", exc)
    return {}


def _save_tokens() -> None:
    try:
        _TOKEN_STORE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_STORE.write_text(json.dumps(_TOKENS, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("⚠️ Failed to save token store: %s", exc)


_TOKENS: Dict[str, dict] = _load_tokens()
_TOKEN_TTL = CONFIG_TOKEN_TTL

# CSRF protection
_CSRF_TOKENS: Dict[str, float] = {}
_CSRF_TTL = CONFIG_CSRF_TTL


def _generate_csrf_token() -> str:
    token = secrets.token_hex(24)
    _CSRF_TOKENS[token] = _time.time()
    return token


def _validate_csrf_token(token: str) -> bool:
    entry = _CSRF_TOKENS.get(token)
    if not entry:
        return False
    if _time.time() - entry > _CSRF_TTL:
        del _CSRF_TOKENS[token]
        return False
    return True


def _clean_expired_csrf():
    now = _time.time()
    expired = [t for t, ts in _CSRF_TOKENS.items() if now - ts > _CSRF_TTL]
    for t in expired:
        del _CSRF_TOKENS[t]


@app.get("/api/v1/auth/csrf-token")
async def csrf_token():
    """Return a fresh CSRF token."""
    _clean_expired_csrf()
    return {"csrf_token": _generate_csrf_token()}


# CSRF validation middleware
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        path = request.url.path
        # Skip CSRF for auth-exempt, rate-limit-exempt endpoints, or Bearer token requests
        if not _is_rate_limit_exempt(path) and not _is_auth_exempt(path, request.method):
            auth_header = request.headers.get("authorization", "")
            if not auth_header.lower().startswith("bearer "):
                csrf_header = request.headers.get("x-csrf-token", "")
                if not csrf_header or not _validate_csrf_token(csrf_header):
                    return JSONResponse(
                        status_code=403,
                        content={"error": True, "detail": "CSRF token invalid or expired, please refresh the page", "status_code": 403},
                    )
    response = await call_next(request)
    return response


@app.middleware("http")
async def api_rate_limit_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        path = request.url.path
        if path.startswith("/api/v1/") and not _is_rate_limit_exempt(path):
            _clean_rate_limits()
            client_ip = request.client.host if request.client else "unknown"
            bucket = f"{client_ip}:{request.method}:{path}"
            if not _check_rate_limit(_RATE_LIMIT_API, bucket, _RATE_API_LIMIT):
                return _rate_limit_error("请求过于频繁，请稍后再试")
            sensitive_limit = _match_sensitive_rate_limit(path)
            if sensitive_limit and not _check_rate_limit(_RATE_LIMIT_SENSITIVE, bucket, sensitive_limit):
                return _rate_limit_error("该接口调用过于频繁，请稍后再试")
    response = await call_next(request)
    return response


def _clean_expired_tokens():
    """Remove expired tokens."""
    now = _time.time()
    expired = [t for t, v in _TOKENS.items() if now - v.get("created_at", 0) > _TOKEN_TTL]
    for t in expired:
        del _TOKENS[t]
    if expired:
        _save_tokens()


def _create_token(username: str) -> str:
    """Create a new token for a user."""
    _clean_expired_tokens()
    token = secrets.token_hex(32)
    _TOKENS[token] = {"username": username, "created_at": _time.time()}
    _save_tokens()
    return token


def _validate_token(token: str) -> str | None:
    """Returns username if valid, None otherwise."""
    entry = _TOKENS.get(token)
    if not entry:
        return None
    if _time.time() - entry.get("created_at", 0) > _TOKEN_TTL:
        del _TOKENS[token]
        return None
    return entry["username"]


def _revoke_token(token: str) -> bool:
    """Invalidate a token if it is still present."""
    if not token:
        return False
    removed = _TOKENS.pop(token, None) is not None
    if removed:
        _save_tokens()
    return removed


def _extract_bearer_token(authorization: str = "") -> str:
    """Normalize the Authorization header into a raw token."""
    value = (authorization or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _extract_request_token(request: Request | None = None, authorization: str = "") -> str:
    """Read auth token from header first, then cookie."""
    token = _extract_bearer_token(authorization)
    if token:
        return token
    if request is None:
        return ""
    return (request.cookies.get("ag-token", "") or "").strip()


def _get_auth_mode() -> str:
    """Describe the current auth delivery mode for clients."""
    if _AUTH_COOKIE_ONLY:
        return "cookie-only"
    if _AUTH_RETURN_TOKEN_JSON:
        return "cookie+token"
    return "cookie"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1/") and not _is_auth_exempt(path, request.method):
        token = _extract_request_token(request, request.headers.get("authorization", ""))
        username = _validate_token(token)
        if not username:
            return JSONResponse(
                status_code=401,
                content={
                    "error": True,
                    "detail": "认证已失效，请重新登录",
                    "status_code": 401,
                    "auth_mode": _get_auth_mode(),
                },
                headers={"X-AG-Auth-Mode": _get_auth_mode()},
            )
        request.state.username = username
    return await call_next(request)


def _build_auth_response(username: str, token: str, csrf: str) -> JSONResponse:
    """Build a login/register response with stable auth metadata."""
    auth_mode = _get_auth_mode()
    body: dict[str, Any] = {
        "username": username,
        "csrf_token": csrf,
        "auth_mode": auth_mode,
        "token_json_enabled": bool(not _AUTH_COOKIE_ONLY and _AUTH_RETURN_TOKEN_JSON),
    }
    if not _AUTH_COOKIE_ONLY and _AUTH_RETURN_TOKEN_JSON:
        body["token"] = token

    resp = JSONResponse(body)
    resp.headers["X-AG-Auth-Mode"] = auth_mode
    if "token" in body:
        resp.headers["X-AG-Token-JSON"] = "deprecated"
    resp.set_cookie(
        key="ag-token",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=86400 * 7,
        secure=False,  # set True in production with HTTPS
    )
    return resp


def _build_auth_status(username: str | None) -> Dict[str, Any]:
    """Return a consistent auth status payload."""
    return {
        "username": username or "guest",
        "authenticated": bool(username),
        "auth_mode": _get_auth_mode(),
        "cookie_only": _AUTH_COOKIE_ONLY,
        "token_json_enabled": bool(not _AUTH_COOKIE_ONLY and _AUTH_RETURN_TOKEN_JSON),
    }


@app.post("/api/v1/auth/register")
async def register(req: RegisterRequest, request: Request = None):
    """Register a new user."""
    # Rate limit: 5 registrations per minute per IP
    if request:
        client_ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(_RATE_LIMIT_IP, f"register:{client_ip}", _RATE_LOGIN_LIMIT):
            raise HTTPException(status_code=429, detail="注册请求过于频繁，请稍后再试")

    username = req.username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少需要2个字符")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少需要8个字符")
    if username in _USERS:
        raise HTTPException(status_code=409, detail="该用户名已被注册")
    _USERS[username] = _hash_password(req.password)
    _save_users(_USERS)
    token = _create_token(username)
    csrf = _generate_csrf_token()
    logger.info(f"✅ New user registered: {username}")
    return _build_auth_response(username, token, csrf)


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest, request: Request = None):
    """Token-based login with cookie and optional JSON token."""
    # Rate limit: 5 attempts per minute per username
    username = req.username.strip()
    if request:
        client_ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(_RATE_LIMIT_LOGIN, username, _RATE_LOGIN_LIMIT):
            raise HTTPException(status_code=429, detail="登录尝试过于频繁，请1分钟后再试")
        if not _check_rate_limit(_RATE_LIMIT_IP, f"login:{client_ip}", _RATE_LOGIN_LIMIT * 2):
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    if username not in _USERS or not _verify_password(req.password, _USERS[username]):
        logger.warning(f"Failed login attempt for user: {username}")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = _create_token(username)
    csrf = _generate_csrf_token()
    return _build_auth_response(username, token, csrf)


@app.post("/api/v1/auth/logout")
async def logout(request: Request = None, authorization: str = Header(default="")):
    """Clear the auth cookie and revoke the current token when available."""
    revoked = _revoke_token(_extract_request_token(request, authorization))
    resp = JSONResponse({"message": "已登出", "revoked": revoked, "auth_mode": _get_auth_mode()})
    resp.delete_cookie(key="ag-token", path="/", samesite="strict")
    return resp


@app.get("/api/v1/auth/me")
async def auth_me(authorization: str = Header(default=""), request: Request = None):
    """Check current auth status — checks Authorization header first, then cookie."""
    token = _extract_request_token(request, authorization)
    username = _validate_token(token)
    if username:
        return _build_auth_status(username)
    return _build_auth_status(None)


# ══════════════════════════════════════════════════════════════════# ══════════════════════════════════════════════════════════════════
# Unified Exception Handler
# ══════════════════════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )

@app.exception_handler(PydanticValidationError)
async def validation_exception_handler(request: Request, exc: PydanticValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "detail": f"输入参数校验失败: {exc.errors()[0]['msg'] if exc.errors() else str(exc)}",
            "status_code": 422,
            "fields": [{"field": e["loc"][-1], "msg": e["msg"]} for e in exc.errors()],
        },
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catches unhandled exceptions — returns safe error without stack trace."""
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "detail": "服务器内部错误，请查看后端日志",
            "status_code": 500,
        },
    )

# ══════════════════════════════════════════════════════════════════
# Pagination Helper
# ══════════════════════════════════════════════════════════════════

DEFAULT_PAGE_SIZE = CONFIG_DEFAULT_PAGE_SIZE
MAX_PAGE_SIZE = CONFIG_MAX_PAGE_SIZE

class PaginationParams(BaseModel):
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)

def paginate(items: list, limit: int, offset: int = 0) -> dict:
    """Wrap any list with pagination metadata."""
    total = len(items)
    return {
        "items": items[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }

# ══════════════════════════════════════════════════════════════════
# Health & Info
# ══════════════════════════════════════════════════════════════════

# Health check registry — modules can register their own checks
_health_checks: list[tuple[str, callable]] = []

def register_health_check(name: str, check_fn: callable) -> None:
    """Register a health check function by name."""
    _health_checks.append((name, check_fn))

@app.get("/api/v1/health")
async def health():
    """Health check endpoint with per-subsystem status."""
    from channels.marine_base import get_default_registry

    registry = get_default_registry()
    sandbox_runtime: Dict[str, Any]
    try:
        from sandbox.python_runner import describe_sandbox_runtime

        sandbox_runtime = describe_sandbox_runtime()
    except Exception as exc:
        sandbox_runtime = {
            "mode": "unknown",
            "ready": False,
            "error": str(exc),
        }

    # Run registered health checks
    check_results: Dict[str, Any] = {}
    for name, check_fn in _health_checks:
        try:
            result = check_fn()
            check_results[name] = {"ok": True, "data": result}
        except Exception as e:
            check_results[name] = {"ok": False, "error": str(e)}

    if not hasattr(health, "_started_at"):
        health._started_at = _time.time()

    return HealthResponse(
        status="ok",
        version=CONFIG_VERSION,
        services={
            "evolution": registry.get("system_evolution") is not None,
            "bridge_chat": registry.get("bridge_chat") is not None,
            "agent_config": _team_manager is not None,
            "sandbox_runtime_ready": bool(sandbox_runtime.get("ready")),
        },
        details={
            "sandbox_runtime": sandbox_runtime,
            "health_checks": check_results,
            "uptime_seconds": round(_time.time() - health._started_at, 1),
        },
    )


@app.get("/api/v1/info")
async def info():
    """System info endpoint for external integrations."""
    return {
        "name": "AgentsGroup2026",
        "version": CONFIG_VERSION,
        "description": "Standalone Agent Management, Evolution & Chat Platform",
        "capabilities": ["agent_management", "system_evolution", "chat", "openclaw_integration"],
        "api_prefix": "/api/v1",
        "endpoints": {
            "agent_config": "/api/v1/agent-config",
            "agent_teams": "/api/v1/agent-teams",
            "evolution": "/api/v1/agent-teams/evolution",
            "chat": "/api/v1/bridge-chat",
            "health": "/api/v1/health",
            "operations": "/api/v1/operations",
            "evidence_runs": "/api/v1/evidence-runs",
        },
    }


# ══════════════════════════════════════════════════════════════════
# Bridge Chat endpoints
# ══════════════════════════════════════════════════════════════════

async def _agent_llm_chat(
    message: str,
    session_id: str = "default",
    agent_id: str = "default_agent",
) -> Optional[Dict[str, Any]]:
    """Try LLM chat with agent context. Returns None if LLM is unavailable."""
    try:
        from agents.chat_harness import get_chat_harness
        from agents.api import _team_manager as tm
    except ImportError:
        return None

    harness = get_chat_harness()
    agent_prompt = ""
    agent_name = agent_id

    if tm:
        for team in tm.list_teams():
            agent = team.get_agent(agent_id)
            if agent:
                agent_prompt = agent.system_prompt or ""
                agent_name = agent.name or agent_id
                break

    ctx_lines = []
    if agent_prompt:
        ctx_lines.append(agent_prompt)
    else:
        ctx_lines.append(f"你是 AgentsGroup2026 系统的智能体 {agent_name}。")
    ctx_lines.append("回答时简洁专业，可中英文混合。")
    ctx_lines.append("如果用户请求涉及系统改进，请提出具体可执行的建议。")
    system_prompt = "\n".join(ctx_lines)

    try:
        result = await harness.chat(
            message,
            agent_id=agent_id,
            session_id=f"chat_{session_id}",
            system_prompt=system_prompt,
        )
        if result.error:
            return None
        reply = result.response.strip()
        if not reply:
            return None

        urgency = "normal"
        urgent_kw = ["紧急", "严重", "critical", "urgent", "emergency", "error"]
        if any(kw in reply.lower() for kw in urgent_kw):
            urgency = "high"

        return {
            "reply": reply,
            "urgency": urgency,
            "source": "agent_llm",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "model": result.model,
            "provider": result.provider,
            "latency_ms": round(result.latency_ms, 1),
            "session_id": session_id,
        }
    except Exception as exc:
        logger.debug("Agent LLM chat failed: %s", exc)
        return None


@app.post("/api/v1/bridge-chat/send")
async def bridge_chat_send(payload: BridgeChatRequest):
    """Handle chat message — LLM first, template fallback.

    When the user mentions task/build keywords, automatically creates
    a task for the build team via TaskEngine.
    """
    # Try LLM chat
    llm_result = await _agent_llm_chat(payload.message, payload.session_id, agent_id=payload.agent_id)

    # Auto-create task when message mentions build/task keywords
    task_id = None
    msg_text = (payload.message or "").strip()
    _build_keywords = [
        "build团队", "Build团队", "build team", "开发任务", "开发团队",
        "构建团队", "提交任务", "分配任务", "创建任务", "新建任务",
        "改进系统", "优化系统", "修复", "升级", "重构",
    ]
    _is_build_request = any(kw in msg_text for kw in _build_keywords)

    if _is_build_request and len(msg_text) >= 4:
        try:
            from agents.api import _te
            from agents.task_engine import AgentTask

            title = msg_text.split("\n")[0][:120]
            task_description = msg_text
            if llm_result and llm_result.get("reply"):
                task_description = (
                    f"{msg_text}\n\n---\n\n"
                    f"## Agent 分析建议 (参考)\n\n{llm_result['reply']}\n"
                )

            engine = _te()
            if not engine._running:
                await engine.start()

            task = AgentTask(
                agent_id="build_pm",
                team_id="build_system",
                title=title,
                description=task_description,
                priority=2,
                metadata={
                    "source": "bridge_chat",
                    "session_id": payload.session_id,
                    "agent_id": payload.agent_id,
                },
            )
            await engine.submit_task(task)
            task_id = task.task_id
            logger.info(f"[Chat] Created task {task_id}: {title[:40]}")
        except Exception as e:
            logger.warning(f"[Chat] Task creation failed: {e}")
            if llm_result:
                llm_result["pipeline_error"] = f"任务创建失败: {str(e)[:200]}"

    if llm_result:
        if task_id:
            llm_result["task_id"] = task_id
        return llm_result

    # Fallback to template-based bridge_chat channel
    try:
        from channels.marine_base import get_default_registry

        registry = get_default_registry()
        chat_ch = registry.get("bridge_chat")
        if not chat_ch:
            return {
                "reply": "Chat channel 未注册，请检查后端配置。",
                "urgency": "normal",
                "source": "error",
            }

        result = await chat_ch.process_event({
            "type": "chat_message",
            "message": payload.message,
            "session_id": payload.session_id,
            "lang": payload.lang,
        })
        result["source"] = "bridge_chat_template"
        if task_id:
            result["task_id"] = task_id
    except Exception as e:
        logger.warning(f"[Chat] Template fallback failed: {e}")
        return {
            "reply": f"系统暂时无法处理请求: {str(e)[:100]}",
            "urgency": "normal",
            "source": "error",
        }
    return result


@app.get("/api/v1/bridge-chat/history")
async def bridge_chat_history(session_id: str = "default", limit: int = 20):
    """Get chat history."""
    from channels.marine_base import get_default_registry

    registry = get_default_registry()
    chat_ch = registry.get("bridge_chat")
    if not chat_ch:
        raise HTTPException(status_code=404, detail="Chat channel not found")
    return {"session_id": session_id, "messages": chat_ch.get_session_history(session_id, limit)}


@app.delete("/api/v1/bridge-chat/session/{session_id}")
async def bridge_chat_clear_session(session_id: str):
    """Clear chat session."""
    from channels.marine_base import get_default_registry

    registry = get_default_registry()
    chat_ch = registry.get("bridge_chat")
    if not chat_ch:
        raise HTTPException(status_code=404, detail="Chat channel not found")
    chat_ch.clear_session(session_id)
    return {"status": "ok", "session_id": session_id}


@app.get("/api/v1/bridge-chat/status")
async def bridge_chat_status():
    """Get chat channel status."""
    from channels.marine_base import get_default_registry

    registry = get_default_registry()
    chat_ch = registry.get("bridge_chat")
    if not chat_ch:
        raise HTTPException(status_code=404, detail="Chat channel not found")
    return chat_ch.get_status()


# ══════════════════════════════════════════════════════════════════
# OpenClaw Integration API
# ══════════════════════════════════════════════════════════════════

class OpenClawConnectRequest(BaseModel):
    """Request to connect an external system via OpenClaw protocol."""
    system_name: str
    system_url: str
    api_token: str = ""
    description: str = ""
    capabilities: list = []


@app.post("/api/v1/openclaw/connect")
async def openclaw_connect(req: OpenClawConnectRequest):
    """Register an external system for OpenClaw integration.

    This enables two-way communication:
    - External system can call AgentsGroup2026 APIs
    - AgentsGroup2026 can push evolution tasks to external system
    """
    return {
        "status": "connected",
        "system_name": req.system_name,
        "integration_id": f"oc_{hash(req.system_url) % 100000:05d}",
        "available_apis": {
            "chat": "/api/v1/bridge-chat/send",
            "evolution": "/api/v1/agent-teams/evolution/*",
            "agent_config": "/api/v1/agent-config/*",
            "health": "/api/v1/health",
        },
        "message": f"System '{req.system_name}' connected. Use the available APIs to integrate.",
    }


@app.get("/api/v1/openclaw/status")
async def openclaw_status():
    """Check OpenClaw integration status."""
    return {
        "protocol": "openclaw/v1",
        "status": "ready",
        "capabilities": [
            "agent_management",
            "system_evolution",
            "chat_improvement",
            "task_dispatch",
            "compliance_rating",
        ],
    }


# ══════════════════════════════════════════════════════════════════
# Static Files (Frontend)
# ══════════════════════════════════════════════════════════════════

# Mount frontend static files
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/js", StaticFiles(directory=str(_frontend_dir / "js")), name="js")
    app.mount("/css", StaticFiles(directory=str(_frontend_dir / "css")), name="css")
    _three_dir = Path(__file__).resolve().parents[2] / "node_modules" / "three"
    if _three_dir.exists():
        app.mount("/vendor/three", StaticFiles(directory=str(_three_dir)), name="three_vendor")

    from fastapi.responses import FileResponse

    @app.get("/")
    async def index():
        return FileResponse(str(_frontend_dir / "agent-team-config.html"))

    @app.get("/agent-team-config.html")
    async def agent_config_page():
        return FileResponse(str(_frontend_dir / "agent-team-config.html"))

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)  # 静默，消除 404 噪音

    @app.get("/{page_name}.html")
    async def frontend_page(page_name: str):
        page = _frontend_dir / f"{page_name}.html"
        if page.exists():
            return FileResponse(str(page))
        raise HTTPException(404, f"Page '{page_name}.html' not found")

    @app.get("/evolution.html")
    async def evolution_page():
        p = _frontend_dir / "datacenter-ratchet-evolution.html"
        if p.exists():
            return FileResponse(str(p))
        raise HTTPException(404, "Evolution page not found")


# ══════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentsGroup2026 Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload")
    args = parser.parse_args()

    logger.info(f"Starting AgentsGroup2026 on {args.host}:{args.port}")
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


# ═══ Client Error Log Endpoint ═══

@app.post("/api/v1/log/client-error")
async def log_client_error(request: Request):
    """Receive client-side error reports for monitoring.
    Accepts sendBeacon (text/plain) and regular JSON posts."""
    body = await request.body()
    try:
        data = json.loads(body) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = {}
    msg = str(data.get("msg", ""))[:120]
    url = str(data.get("url", ""))
    line = data.get("line", 0)
    stack = str(data.get("stack", ""))[:200]
    err_type = str(data.get("type", "error"))
    logger.warning("[ClientError] %s | %s | %s:%s | %s", err_type, msg, url, line, stack)
    return {"ok": True}
