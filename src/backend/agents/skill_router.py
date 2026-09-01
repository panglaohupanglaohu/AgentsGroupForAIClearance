# -*- coding: utf-8 -*-
"""SkillRouter — 2-Stage Retrieve-and-Rerank skill selection for agents.

Architecture (per SkillRouter paper):
- Stage 1: Bi-Encoder Retrieval — BM25 + TF-IDF cosine + n-gram + instructions depth → top-20
- Stage 2: Cross-Encoder Reranker — field-level joint scoring + agent profile affinity → top-K
- Stage 3: Injection — selected skills injected into agent system prompt

Local deployment uses TF-IDF + BM25 approximation (no GPU required).
Semantic enhancement: Chinese n-gram sliding window, synonym expansion, instructions deep match.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# BM25 parameters
BM25_K1 = 1.5
BM25_B = 0.75

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROUTER_STATE_PATH = _REPO_ROOT / "storage" / "skill_router_state.json"

# lifecycle multipliers applied after retrieve+rerank (verified skills rank higher)
_LIFECYCLE_MULT = {
    "solidified": 1.14,
    "verified": 1.12,
    "published": 1.08,
    "team_local": 1.0,
    "draft": 0.90,
    "degraded": 0.72,
}

# Synonym/related term groups for Chinese tech/ops domain
_SYNONYM_GROUPS = [
    {"数据", "分析", "统计", "报表", "报告", "可视化", "图表"},
    {"沟通", "交流", "对话", "协商", "谈判", "表达", "客户"},
    {"代码", "编程", "开发", "编码", "实现", "写代码"},
    {"测试", "验证", "质量", "检测", "测试用例", "qa"},
    {"项目", "管理", "协调", "跟踪", "进度", "计划"},
    {"文档", "文件", "写作", "记录", "说明"},
    {"部署", "发布", "上线", "运维", "监控"},
    {"设计", "架构", "规划", "方案", "蓝图"},
    {"审查", "review", "检查", "审核", "评审"},
    {"安全", "防护", "加密", "认证", "权限"},
    {"优化", "性能", "调优", "提升", "加速"},
    {"学习", "培训", "研究", "探索", "调研"},
]


@dataclass
class RoutingFeedback:
    """Feedback record for a skill-agent injection."""
    feedback_id: str
    team_id: str
    agent_id: str
    skill_id: str
    action: str  # "rate" | "revoke"
    rating: int = 0  # 1-5 for rate, 0 for revoke
    reason: str = ""
    created_at: str = ""


@dataclass
class RouteResult:
    """Single skill routing result."""
    skill_id: str
    name: str
    description: str
    icon: str
    category: str
    score: float  # combined retrieval + rerank score
    retrieval_score: float
    rerank_score: float
    instructions_preview: str = ""
    match_reasons: List[str] = field(default_factory=list)
    lifecycle_stage: str = ""
    lifecycle_note: str = ""
    lifecycle_mult: float = 1.0


@dataclass
class RoutingSession:
    """A single routing session record."""
    session_id: str
    agent_id: str
    agent_name: str
    team_id: str
    query: str
    top_k: int
    results: List[RouteResult]
    assigned_skill_ids: List[str] = field(default_factory=list)
    created_at: str = ""
    duration_ms: float = 0
    mode: str = "assign"  # "assign" or "runtime"
    stage1_ms: float = 0
    stage2_ms: float = 0
    pool_size: int = 0
    state_filter: str = ""


# 论文 Section 5.6 状态硬过滤集合
PRODUCTION_STATES = frozenset({"published", "solidified"})
SANDBOX_STATES = frozenset({"published", "solidified", "verified", "team_local", "ready", "revision", "draft"})
EXCLUDED_ALWAYS = frozenset({"deprecated"})


class SkillRouter:
    """2-stage skill routing engine: Bi-Encoder Retrieval → Cross-Encoder Reranker."""

    def __init__(self, skill_library=None, team_manager=None):
        self._skill_library = skill_library
        self._team_manager = team_manager
        self._sessions: Dict[str, RoutingSession] = {}
        # IDF cache: token → log(N/df)
        self._idf_cache: Dict[str, float] = {}
        self._corpus_size: int = 0
        # Feedback storage: skill_id → list of feedback records
        self._feedback: Dict[str, List[RoutingFeedback]] = {}
        # Learned affinity boosts: (agent_id, skill_category) → boost value
        self._affinity_boosts: Dict[Tuple[str, str], float] = {}
        self._load_state()

    def route(
        self,
        query: str,
        team_id: str = "",
        agent_id: str = "",
        top_k: int = 10,
        mode: str = "assign",
        exclude_skill_ids: Optional[List[str]] = None,
        production_only: bool = False,
    ) -> RoutingSession:
        """Execute the 2-stage retrieve-and-rerank pipeline.

        Stage 1 (Bi-Encoder): Fast embedding similarity → top-20 candidates
        Stage 2 (Cross-Encoder): Field-level joint scoring → final top-K
        """
        start_time = time.time()
        exclude = set(exclude_skill_ids or [])

        # Get agent info
        agent_name = ""
        if agent_id and self._team_manager:
            team = self._team_manager.get_team(team_id)
            if team and agent_id in team.agents:
                agent_name = team.agents[agent_id].name

        # Get skill pool & state filtering
        all_skills = self._get_skill_pool(team_id)
        candidates = []
        is_prod = production_only or (mode == "production")
        allowed_states = PRODUCTION_STATES if is_prod else SANDBOX_STATES
        state_filter_label = "production_only" if is_prod else "sandbox_all"

        for s in all_skills:
            if s.get("skill_id", "") in exclude:
                continue
            st = str(self._lifecycle_stage_str(s) or "draft").lower()
            if st in EXCLUDED_ALWAYS:
                continue
            if is_prod and st not in allowed_states:
                continue
            candidates.append(s)

        pool_size = len(candidates)

        # Build IDF from corpus (cached)
        self._build_idf(candidates)

        # ── Stage 1: Bi-Encoder Retrieval ──────────────────────────
        t1 = time.time()
        retrieval_scores = self._stage1_retrieve(query, candidates)
        # Take top-20 for reranking (or top_k*3 if top_k > 7)
        n_rerank = max(top_k * 3, 20)
        retrieval_top = sorted(
            retrieval_scores, key=lambda x: x[1], reverse=True
        )[:n_rerank]
        stage1_ms = (time.time() - t1) * 1000

        # ── Stage 2: Cross-Encoder Reranker ────────────────────────
        t2 = time.time()
        reranked = self._stage2_rerank(query, retrieval_top)
        stage2_ms = (time.time() - t2) * 1000

        # ── Stage 2.5: lifecycle reweight (verified ↑ draft/degraded ↓) ──
        rescored: List[Tuple[Dict, float, float, float, float, str, str]] = []
        for skill_data, retrieval_score, rerank_score in reranked:
            combined = 0.45 * retrieval_score + 0.55 * rerank_score
            mult, lc_note = self._lifecycle_multiplier(skill_data)
            stage = self._lifecycle_stage_str(skill_data)
            combined = min(max(combined * mult, 0.0), 1.0)
            rescored.append(
                (skill_data, retrieval_score, rerank_score, combined, mult, lc_note, stage)
            )
        rescored.sort(key=lambda x: x[3], reverse=True)
        final = rescored[:top_k]

        # Build results
        results = []
        for skill_data, retrieval_score, rerank_score, combined, mult, lc_note, stage in final:
            instructions = skill_data.get("instructions", "")
            reasons = self._explain_match(query, skill_data)
            if lc_note:
                reasons = list(reasons) + [lc_note]
            results.append(RouteResult(
                skill_id=skill_data.get("skill_id", ""),
                name=skill_data.get("name", ""),
                description=skill_data.get("description", ""),
                icon=skill_data.get("icon", "⚡"),
                category=skill_data.get("category", "general"),
                score=round(combined, 4),
                retrieval_score=round(retrieval_score, 4),
                rerank_score=round(rerank_score, 4),
                instructions_preview=instructions[:200] if instructions else "",
                match_reasons=reasons,
                lifecycle_stage=stage,
                lifecycle_note=lc_note,
                lifecycle_mult=round(mult, 3),
            ))

        duration_ms = (time.time() - start_time) * 1000

        session = RoutingSession(
            session_id=uuid.uuid4().hex[:12],
            agent_id=agent_id,
            agent_name=agent_name,
            team_id=team_id,
            query=query,
            top_k=top_k,
            results=results,
            created_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=round(duration_ms, 1),
            mode=mode,
            stage1_ms=round(stage1_ms, 1),
            stage2_ms=round(stage2_ms, 1),
            pool_size=pool_size,
            state_filter=state_filter_label,
        )
        self._sessions[session.session_id] = session
        logger.info(
            "SkillRouter: query=%r → %d results in %.1fms (S1:%.1fms S2:%.1fms pool:%d mode=%s)",
            query[:50], len(results), duration_ms, stage1_ms, stage2_ms, pool_size, mode,
        )
        return session

    def assign(
        self,
        team_id: str,
        agent_id: str,
        skill_ids: List[str],
        session_id: str = "",
    ) -> Dict[str, Any]:
        """Assign selected skills to an agent (inject into agent config)."""
        if not self._team_manager:
            return {"error": "team_manager_not_available"}

        team = self._team_manager.get_team(team_id)
        if not team:
            return {"error": "team_not_found"}
        if agent_id not in team.agents:
            return {"error": "agent_not_found"}

        agent = team.agents[agent_id]
        assigned = []
        already_has = []

        for sid in skill_ids:
            if sid in (agent.skills or []):
                already_has.append(sid)
            else:
                if agent.skills is None:
                    agent.skills = []
                agent.skills.append(sid)
                assigned.append(sid)
            # 同步登记进 team.skills，使团队「知道」该技能 → 智能体页技能列表能按名称解析显示
            # （否则 agent.skills 里只有 skill_id 散值，团队不识别，页面只显示一串 id）
            if sid not in team.skills:
                try:
                    sdef = self._skill_library._find_skill(team_id, sid) if self._skill_library else None
                    if sdef is not None:
                        team.add_skill(sdef)
                except Exception as _e:  # noqa: BLE001
                    logger.debug("SkillRouter: register skill %s into team failed: %s", sid, _e)

        # Persist
        self._team_manager._persist()

        # Update session record
        if session_id and session_id in self._sessions:
            self._sessions[session_id].assigned_skill_ids.extend(assigned)

        # Generate injection prompt
        inject_prompt = self._generate_inject_prompt(team_id, assigned)

        # S-5.2: 赋予即抬升该 agent 目标技能的熟练度先验 → 打通到数字孪生 trial(闭环 UI 入口)。
        # 全程容错:proficiency 抬升失败绝不影响赋予本身。
        proficiency_boosted: Dict[str, float] = {}
        try:
            proficiency_boosted = self._boost_proficiency(team_id, agent_id, assigned)
        except Exception as e:  # noqa: BLE001
            logger.warning("SkillRouter: proficiency boost skipped: %s", e)

        logger.info(
            "SkillRouter: assigned %d skills to agent %s (team %s)",
            len(assigned), agent_id, team_id,
        )
        return {
            "status": "ok",
            "assigned": assigned,
            "assigned_count": len(assigned),
            "already_has": already_has,
            "agent_skills_count": len(agent.skills),
            "inject_prompt": inject_prompt,
            "proficiency_boosted": proficiency_boosted,
        }

    # ── S-5.2: 赋予 → 熟练度先验抬升(接通数字孪生闭环) ──
    _CATEGORY_TO_SKILL = {
        "code_delivery": "code_review",
        "research": "research",
        "automation": "automation",
        "domain_knowledge": "domain_knowledge",
    }
    _PROFICIENCY_FLOOR = 0.8  # 赋予后把目标技能先验抬到 ≥ 此值

    def _resolve_target_skill(self, team_id: str, skill_id: str) -> Optional[str]:
        """把被赋予的 skill 解析成数字孪生场景使用的「技能名」。

        优先 snapshot.metadata.target_skill;否则按 category 映射;再否则用 slug/name 归一化。
        """
        skills = self._skill_library.browse(team_id=team_id) if self._skill_library else []
        s = next((x for x in skills if x.get("skill_id") == skill_id), None)
        if not s:
            return None
        meta = s.get("metadata") or {}
        if meta.get("target_skill"):
            return str(meta["target_skill"])
        cat = (s.get("category") or "").lower()
        if cat in self._CATEGORY_TO_SKILL:
            return self._CATEGORY_TO_SKILL[cat]
        slug = (s.get("slug") or s.get("name") or "").strip().lower().replace(" ", "_")
        return slug or None

    def _boost_proficiency(self, team_id: str, agent_id: str, assigned: List[str]) -> Dict[str, float]:
        """为 agent 的目标技能写入/抬升熟练度先验(取 max(现值, FLOOR))。"""
        if not assigned:
            return {}
        from sandbox.proficiency_store import get_proficiency_store
        store = get_proficiency_store()
        data = store.load_proficiency(team_id) or {}
        boosted: Dict[str, float] = {}
        for sid in assigned:
            target = self._resolve_target_skill(team_id, sid)
            if not target:
                continue
            key = f"{agent_id}::{target}"
            cur = float((data.get(key) or {}).get("success_rate", 0.5))
            newv = max(cur, self._PROFICIENCY_FLOOR)
            data[key] = {
                "skill_name": target,
                "success_rate": newv,
                "agent_id": agent_id,
                "category": "assigned_skill",
            }
            boosted[target] = round(newv, 3)
        if boosted:
            store.save_proficiency(team_id, data)
        return boosted

    def get_session(self, session_id: str) -> Optional[RoutingSession]:
        return self._sessions.get(session_id)

    def list_sessions(self, team_id: str = "", limit: int = 20) -> List[Dict]:
        sessions = list(self._sessions.values())
        if team_id:
            sessions = [s for s in sessions if s.team_id == team_id]
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return [self._session_to_dict(s) for s in sessions[:limit]]

    def suggest_agents_for_skill(self, team_id: str, skill_id: str, top_k: int = 3) -> Dict[str, Any]:
        """Suggest best agents for a skill (reverse routing — skill→agents).

        Uses agent's existing skills + role description to calculate affinity.
        Called after skill approval for one-click injection suggestion.
        """
        if not self._team_manager:
            return {"error": "team_manager_not_available"}
        if not self._skill_library:
            return {"error": "skill_library_not_available"}

        team = self._team_manager.get_team(team_id)
        if not team:
            return {"error": "team_not_found"}

        # Get skill data
        all_skills = self._skill_library.browse(team_id=team_id)
        skill_data = next((s for s in all_skills if s.get("skill_id") == skill_id), None)
        if not skill_data:
            return {"error": "skill_not_found"}

        # Build skill's semantic profile
        skill_text = f"{skill_data.get('name', '')} {skill_data.get('description', '')} {skill_data.get('category', '')}"
        skill_tokens = self._tokenize(skill_text)
        skill_tf = Counter(skill_tokens)
        skill_set = set(skill_tokens)

        suggestions = []
        for agent_id, agent in team.agents.items():
            # Build agent's semantic profile from: name + role + existing skills
            agent_text = f"{agent.name} {getattr(agent, 'role', '')} {getattr(agent, 'description', '')}"

            # Add existing skill names/descriptions to agent profile
            existing_skills = getattr(agent, 'skills', []) or []
            for sid in existing_skills:
                existing = next((s for s in all_skills if s.get("skill_id") == sid), None)
                if existing:
                    agent_text += f" {existing.get('name', '')} {existing.get('category', '')}"

            agent_tokens = self._tokenize(agent_text)
            agent_tf = Counter(agent_tokens)
            agent_set = set(agent_tokens)

            # Affinity score: how well does this skill fit this agent?
            overlap = skill_set & agent_set
            overlap_ratio = len(overlap) / max(len(skill_set), 1)
            cosine = self._cosine_sim_idf(skill_tf, agent_tf) if self._idf_cache else 0
            # Category bonus
            cat_bonus = 0.15 if skill_data.get("category", "").lower() in agent_text.lower() else 0
            # Penalty for already having the skill
            already_has = skill_id in existing_skills
            penalty = -0.5 if already_has else 0

            affinity = min(0.4 * overlap_ratio + 0.4 * cosine + cat_bonus + penalty, 1.0)
            suggestions.append({
                "agent_id": agent_id,
                "agent_name": agent.name,
                "affinity": round(affinity, 4),
                "existing_skill_count": len(existing_skills),
                "already_has": already_has,
                "match_reasons": self._explain_agent_affinity(skill_data, agent_text, overlap),
            })

        suggestions.sort(key=lambda x: x["affinity"], reverse=True)
        return {
            "skill_id": skill_id,
            "skill_name": skill_data.get("name", ""),
            "suggestions": suggestions[:top_k],
        }

    def _explain_agent_affinity(self, skill: Dict, agent_text: str, overlap: set) -> List[str]:
        """Explain why an agent is a good fit for a skill."""
        reasons = []
        if overlap:
            top_terms = sorted(overlap, key=lambda t: self._idf_cache.get(t, 0), reverse=True)[:3]
            reasons.append(f"共同关键词: {', '.join(top_terms)}")
        cat = skill.get("category", "")
        if cat and cat.lower() in agent_text.lower():
            reasons.append(f"类别匹配: {cat}")
        if not reasons:
            reasons.append("通用匹配")
        return reasons

    # ══ Feedback & Revoke ════════════════════════════════════════

    def submit_feedback(self, team_id: str, agent_id: str, skill_id: str,
                        action: str, rating: int = 0, reason: str = "") -> Dict[str, Any]:
        """Submit feedback for a skill-agent injection.

        action: "rate" (1-5 rating) or "revoke" (remove skill from agent).
        Feedback data is used to adjust routing affinity over time.
        """
        if action not in ("rate", "revoke"):
            return {"error": "invalid_action"}
        if action == "rate" and not (1 <= rating <= 5):
            return {"error": "rating_must_be_1_to_5"}

        feedback = RoutingFeedback(
            feedback_id=uuid.uuid4().hex[:12],
            team_id=team_id,
            agent_id=agent_id,
            skill_id=skill_id,
            action=action,
            rating=rating,
            reason=reason,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Store feedback
        if skill_id not in self._feedback:
            self._feedback[skill_id] = []
        self._feedback[skill_id].append(feedback)

        # If revoke, remove skill from agent
        if action == "revoke" and self._team_manager:
            team = self._team_manager.get_team(team_id)
            if team and agent_id in team.agents:
                agent = team.agents[agent_id]
                if agent.skills and skill_id in agent.skills:
                    agent.skills.remove(skill_id)
                    self._team_manager._persist()
                    logger.info("SkillRouter: revoked skill %s from agent %s", skill_id, agent_id)

        # Update affinity boosts based on feedback pattern
        self._update_affinity_from_feedback(agent_id, skill_id, action, rating)
        # affinity helper saves when it mutates; always persist feedback rows
        self._save_state()

        return {
            "status": "ok",
            "feedback_id": feedback.feedback_id,
            "action": action,
            "rating": rating,
        }

    def _update_affinity_from_feedback(self, agent_id: str, skill_id: str, action: str, rating: int):
        """Adjust affinity boosts based on accumulated feedback."""
        # Get skill category for the boost key
        if not self._skill_library:
            return
        all_skills = self._skill_library.browse()
        skill = next((s for s in all_skills if s.get("skill_id") == skill_id), None)
        if not skill:
            return
        category = skill.get("category", "general")
        key = (agent_id, category)

        if action == "revoke":
            # Negative signal: agent doesn't benefit from this category
            self._affinity_boosts[key] = self._affinity_boosts.get(key, 0) - 0.1
        elif action == "rate":
            # Positive/negative based on rating
            boost = (rating - 3) * 0.05  # rating 5 → +0.1, rating 1 → -0.1
            self._affinity_boosts[key] = self._affinity_boosts.get(key, 0) + boost
        # clamp drift
        self._affinity_boosts[key] = max(-0.5, min(0.5, float(self._affinity_boosts.get(key, 0))))
        self._save_state()

    @staticmethod
    def _lifecycle_stage_str(skill_data: Dict[str, Any]) -> str:
        raw = skill_data.get("lifecycle_stage") or skill_data.get("lifecycle") or ""
        if hasattr(raw, "value"):
            return str(raw.value).lower().strip()
        return str(raw or "").lower().strip() or "unknown"

    @classmethod
    def _lifecycle_multiplier(cls, skill_data: Dict[str, Any]) -> Tuple[float, str]:
        """Boost verified/solidified skills; demote draft/degraded."""
        stage = cls._lifecycle_stage_str(skill_data)
        mult = _LIFECYCLE_MULT.get(stage, 1.0)
        if mult > 1.0:
            return mult, f"生命周期加成: {stage} ×{mult:.2f}"
        if mult < 1.0:
            label = "草稿/未验证" if stage in ("", "draft", "unknown") else stage
            return mult, f"生命周期降权: {label or 'unknown'} ×{mult:.2f}"
        return 1.0, ""

    def _load_state(self) -> None:
        """Load affinity + feedback from disk (survives restart)."""
        try:
            if not _ROUTER_STATE_PATH.is_file():
                return
            data = json.loads(_ROUTER_STATE_PATH.read_text(encoding="utf-8"))
            affinity = data.get("affinity_boosts") or {}
            if isinstance(affinity, dict):
                for k, v in affinity.items():
                    if not isinstance(k, str) or ":" not in k:
                        continue
                    agent_id, cat = k.split(":", 1)
                    try:
                        self._affinity_boosts[(agent_id, cat)] = float(v)
                    except (TypeError, ValueError):
                        continue
            fb_map = data.get("feedback") or {}
            if isinstance(fb_map, dict):
                for sid, rows in fb_map.items():
                    if not isinstance(rows, list):
                        continue
                    loaded: List[RoutingFeedback] = []
                    for row in rows[-50:]:  # cap per skill
                        if not isinstance(row, dict):
                            continue
                        loaded.append(RoutingFeedback(
                            feedback_id=str(row.get("feedback_id") or uuid.uuid4().hex[:12]),
                            team_id=str(row.get("team_id") or ""),
                            agent_id=str(row.get("agent_id") or ""),
                            skill_id=str(row.get("skill_id") or sid),
                            action=str(row.get("action") or "rate"),
                            rating=int(row.get("rating") or 0),
                            reason=str(row.get("reason") or ""),
                            created_at=str(row.get("created_at") or ""),
                        ))
                    if loaded:
                        self._feedback[str(sid)] = loaded
            if self._affinity_boosts or self._feedback:
                logger.info(
                    "SkillRouter: loaded state affinity=%d feedback_skills=%d",
                    len(self._affinity_boosts), len(self._feedback),
                )
        except Exception as e:
            logger.warning("SkillRouter: load state failed: %s", e)

    def _save_state(self) -> None:
        """Persist affinity + recent feedback to disk."""
        try:
            _ROUTER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            affinity = {
                f"{aid}:{cat}": round(float(v), 4)
                for (aid, cat), v in self._affinity_boosts.items()
            }
            feedback: Dict[str, List[Dict[str, Any]]] = {}
            for sid, rows in self._feedback.items():
                feedback[sid] = [
                    {
                        "feedback_id": f.feedback_id,
                        "team_id": f.team_id,
                        "agent_id": f.agent_id,
                        "skill_id": f.skill_id,
                        "action": f.action,
                        "rating": f.rating,
                        "reason": f.reason,
                        "created_at": f.created_at,
                    }
                    for f in rows[-50:]
                ]
            payload = {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "affinity_boosts": affinity,
                "feedback": feedback,
            }
            tmp = _ROUTER_STATE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_ROUTER_STATE_PATH)
        except Exception as e:
            logger.warning("SkillRouter: save state failed: %s", e)

    def get_feedback_stats(self, team_id: str = "") -> Dict[str, Any]:
        """Get aggregated feedback statistics."""
        all_feedback = []
        for fb_list in self._feedback.values():
            for fb in fb_list:
                if not team_id or fb.team_id == team_id:
                    all_feedback.append(fb)

        if not all_feedback:
            return {"total": 0, "rates": 0, "revokes": 0, "avg_rating": 0}

        rates = [f for f in all_feedback if f.action == "rate"]
        revokes = [f for f in all_feedback if f.action == "revoke"]
        avg_rating = sum(f.rating for f in rates) / max(len(rates), 1)

        return {
            "total": len(all_feedback),
            "rates": len(rates),
            "revokes": len(revokes),
            "avg_rating": round(avg_rating, 2),
            "affinity_boosts": dict(
                ((k[0] + ":" + k[1]), round(v, 3)) for k, v in self._affinity_boosts.items()
            ),
        }

    def get_skill_affinity_evidence(
        self,
        skill_id: str,
        team_id: str = "",
        category: str = "",
        limit: int = 8,
    ) -> Dict[str, Any]:
        """Compact routing affinity + feedback for a single skill (evolver evidence)."""
        sid = str(skill_id or "")
        if not sid:
            return {"feedback_count": 0, "avg_rating": 0, "revokes": 0, "affinity_boosts": [], "recent": []}

        # Feedback may be keyed by skill_id or slug — match both + loose contains
        rows: List[RoutingFeedback] = []
        for key, fb_list in self._feedback.items():
            k = str(key)
            if k == sid or (sid and (sid in k or k in sid)):
                rows.extend(fb_list or [])
        if team_id:
            rows = [f for f in rows if not f.team_id or f.team_id == team_id]

        rates = [f for f in rows if f.action == "rate"]
        revokes = [f for f in rows if f.action == "revoke"]
        avg_rating = sum(f.rating for f in rates) / max(len(rates), 1) if rates else 0.0

        cat = (category or "").strip().lower()
        boosts: List[Dict[str, Any]] = []
        for (agent_id, boost_cat), val in self._affinity_boosts.items():
            if cat and str(boost_cat).lower() != cat:
                # still include if feedback exists for this agent+skill
                if not any(f.agent_id == agent_id for f in rows):
                    continue
            boosts.append({
                "agent_id": agent_id,
                "category": boost_cat,
                "boost": round(float(val), 3),
            })
        boosts.sort(key=lambda x: abs(float(x.get("boost") or 0)), reverse=True)

        recent = []
        for f in sorted(rows, key=lambda x: x.created_at or "", reverse=True)[:limit]:
            recent.append({
                "agent_id": f.agent_id,
                "action": f.action,
                "rating": f.rating,
                "reason": (f.reason or "")[:120],
                "created_at": f.created_at,
            })

        return {
            "skill_id": sid,
            "feedback_count": len(rows),
            "rates": len(rates),
            "revokes": len(revokes),
            "avg_rating": round(avg_rating, 2),
            "affinity_boosts": boosts[:12],
            "recent": recent,
        }

    def get_agent_skill_profile(self, team_id: str, agent_id: str) -> Dict[str, Any]:
        """Get agent's skill profile for visualization (radar chart data)."""
        if not self._team_manager:
            return {"error": "team_manager_not_available"}

        team = self._team_manager.get_team(team_id)
        if not team:
            return {"error": "team_not_found"}
        if agent_id not in team.agents:
            return {"error": "agent_not_found"}

        agent = team.agents[agent_id]
        skill_ids = getattr(agent, 'skills', []) or []

        # Resolve skill details
        all_skills = self._skill_library.browse(team_id=team_id) if self._skill_library else []
        skills_detail = []
        category_counts: Dict[str, int] = {}
        for sid in skill_ids:
            s = next((sk for sk in all_skills if sk.get("skill_id") == sid), None)
            if s:
                cat = s.get("category", "general")
                category_counts[cat] = category_counts.get(cat, 0) + 1
                # Get feedback rating for this skill
                avg_r = 0
                fb_list = self._feedback.get(sid, [])
                rated = [f for f in fb_list if f.action == "rate" and f.agent_id == agent_id]
                if rated:
                    avg_r = sum(f.rating for f in rated) / len(rated)
                skills_detail.append({
                    "skill_id": sid,
                    "name": s.get("name", ""),
                    "icon": s.get("icon", "⚡"),
                    "category": cat,
                    "avg_rating": round(avg_r, 1),
                })
            else:
                skills_detail.append({"skill_id": sid, "name": sid, "icon": "?", "category": "unknown", "avg_rating": 0})

        # Radar chart axes: all known categories
        known_categories = list(set(
            s.get("category", "general") for s in all_skills
        ))[:8]  # max 8 axes for radar
        radar_data = [{"axis": cat, "value": category_counts.get(cat, 0)} for cat in known_categories]

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "total_skills": len(skill_ids),
            "skills": skills_detail,
            "category_distribution": category_counts,
            "radar": radar_data,
        }

    def get_dashboard_stats(self, team_id: str) -> Dict[str, Any]:
        """Skill pool growth dashboard: totals, categories, router precision metrics."""
        all_skills = self._skill_library.browse(team_id=team_id) if self._skill_library else []

        # Category distribution
        category_dist: Dict[str, int] = {}
        for s in all_skills:
            cat = s.get("category", "general")
            category_dist[cat] = category_dist.get(cat, 0) + 1

        # Router session metrics
        team_sessions = [s for s in self._sessions.values() if s.team_id == team_id]
        total_routes = len(team_sessions)
        total_assigns = sum(len(s.assigned_skill_ids) for s in team_sessions)
        avg_top1_score = 0
        if team_sessions:
            top1_scores = [s.results[0].score for s in team_sessions if s.results]
            avg_top1_score = sum(top1_scores) / max(len(top1_scores), 1)

        # Avg latency
        avg_latency = 0
        if team_sessions:
            avg_latency = sum(s.duration_ms for s in team_sessions) / len(team_sessions)

        # Feedback summary
        feedback_stats = self.get_feedback_stats(team_id=team_id)

        # Assignment success rate (sessions that resulted in assignment)
        sessions_with_assign = sum(1 for s in team_sessions if s.assigned_skill_ids)
        success_rate = sessions_with_assign / max(total_routes, 1)

        return {
            "pool_size": len(all_skills),
            "category_distribution": category_dist,
            "category_count": len(category_dist),
            "router_metrics": {
                "total_routes": total_routes,
                "total_assigns": total_assigns,
                "avg_top1_score": round(avg_top1_score, 4),
                "avg_latency_ms": round(avg_latency, 1),
                "success_rate": round(success_rate, 4),
            },
            "feedback": feedback_stats,
        }

    # ══ Stage 1: Bi-Encoder Retrieval (BM25 + Cosine) ════════════

    def _stage1_retrieve(self, query: str, candidates: List[Dict]) -> List[tuple]:
        """Bi-Encoder style retrieval using BM25 + TF-IDF cosine + deep text.

        Enhanced with:
        - Instructions/body field for deeper matching
        - Chinese n-gram sliding window
        - Synonym expansion for related term discovery
        """
        query_tokens = self._tokenize(query)
        query_expanded = self._expand_synonyms(query_tokens)
        query_bigrams = self._bigrams(query_tokens)
        query_trigrams = self._trigrams(query_tokens)
        query_tf = Counter(query_tokens)
        query_phrases = self._extract_chinese_phrases(query)

        # Synonym group saturation: which groups does the query activate?
        query_token_set = set(query_tokens)
        active_groups = []
        for group in _SYNONYM_GROUPS:
            overlap = query_token_set & group
            if overlap:
                active_groups.append(group)

        # Avg document length for BM25
        avg_dl = max(1, self._corpus_size / max(len(candidates), 1))

        scored = []
        for skill in candidates:
            # Primary field: name + description + category
            primary_text = f"{skill.get('name', '')} {skill.get('description', '')} {skill.get('category', '')}"
            primary_tokens = self._tokenize(primary_text)
            primary_tf = Counter(primary_tokens)
            dl = len(primary_tokens)

            # Deep field: instructions (body)
            instructions = skill.get("instructions", "")
            body_tokens = self._tokenize(instructions) if instructions else []
            body_tf = Counter(body_tokens)

            # BM25 score on primary field
            bm25 = 0.0
            for term in query_tokens:
                if term in primary_tf:
                    tf = primary_tf[term]
                    idf = self._idf_cache.get(term, 0.5)
                    numerator = tf * (BM25_K1 + 1)
                    denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(avg_dl, 1))
                    bm25 += idf * (numerator / denominator)

            # Cosine similarity (TF-IDF weighted) on primary
            cosine = self._cosine_sim_idf(query_tf, primary_tf)

            # Bigram + trigram overlap (better for Chinese phrases)
            doc_bigrams = self._bigrams(primary_tokens)
            doc_trigrams = self._trigrams(primary_tokens)
            bigram_overlap = len(query_bigrams & doc_bigrams) / max(len(query_bigrams), 1) if query_bigrams else 0
            trigram_overlap = len(query_trigrams & doc_trigrams) / max(len(query_trigrams), 1) if query_trigrams else 0

            # Description direct phrase match (strongest signal for Chinese queries)
            desc_text = skill.get("description", "")
            desc_phrase_score = 0.0
            if query_phrases:
                desc_hits = sum(1 for p in query_phrases if len(p) >= 2 and p in desc_text)
                desc_phrase_score = min(desc_hits / max(len([p for p in query_phrases if len(p) >= 2]), 1), 1.0)

            # Instructions depth score (body field — weaker signal, can be noisy)
            body_score = 0.0
            if body_tokens:
                body_overlap = len(set(query_tokens) & set(body_tokens)) / max(len(query_tokens), 1)
                body_cosine = self._cosine_sim_idf(query_tf, body_tf)
                body_score = 0.5 * body_overlap + 0.5 * body_cosine

            # Synonym expansion bonus (primary hits weighted 2x vs body-only)
            synonym_bonus = 0.0
            if query_expanded:
                primary_hits = sum(1 for t in query_expanded if t in primary_tf)
                body_only_hits = sum(1 for t in query_expanded if t not in primary_tf and t in body_tf)
                synonym_bonus = min((primary_hits * 2 + body_only_hits) / max(len(query_expanded) * 2, 1), 0.5)

            # Synonym group saturation: how many terms from activated groups appear in primary?
            saturation_score = 0.0
            if active_groups:
                primary_set = set(primary_tokens)
                for group in active_groups:
                    hits_in_primary = len(group & primary_set)
                    # Normalized by group size, reward skills hitting multiple terms
                    if hits_in_primary >= 2:
                        saturation_score += (hits_in_primary - 1) / max(len(group) - 1, 1)
                saturation_score = min(saturation_score / len(active_groups), 1.0)

            # Character n-gram overlap (robust against Chinese token segmentation boundaries)
            char_ngram_score = self._ngram_score(query, primary_text, n=3)

            # Combined retrieval score
            score = (
                0.22 * self._normalize_bm25(bm25) +
                0.16 * cosine +
                0.08 * bigram_overlap +
                0.03 * trigram_overlap +
                0.14 * desc_phrase_score +
                0.05 * body_score +
                0.08 * synonym_bonus +
                0.14 * saturation_score +
                0.10 * char_ngram_score
            )
            scored.append((skill, score))

        return scored

    # ══ Stage 2: Cross-Encoder Reranker ══════════════════════════

    def _stage2_rerank(self, query: str, retrieval_top: List[tuple]) -> List[tuple]:
        """Cross-Encoder style reranking: jointly scores query ⊕ skill.

        Enhanced with:
        - Field-level decomposition (name/desc/body/meta)
        - Instructions keyword coverage with IDF boost
        - Chinese phrase matching (2-3 character windows)
        """
        query_tokens = self._tokenize(query)
        query_tf = Counter(query_tokens)
        query_set = set(query_tokens)
        query_phrases = self._extract_chinese_phrases(query)

        reranked = []
        for skill_data, retrieval_score in retrieval_top:
            # ── Field-level scoring (Cross-Encoder decomposition) ──
            name = skill_data.get("name", "")
            desc = skill_data.get("description", "")
            body = skill_data.get("instructions", "")
            category = skill_data.get("category", "")
            tools = " ".join(skill_data.get("required_tools", []))

            # Name field score (high precision signal)
            name_tokens = self._tokenize(name)
            name_score = self._field_score(query_set, query_tf, name_tokens, weight_exact=2.0)

            # Description field score
            desc_tokens = self._tokenize(desc)
            desc_score = self._field_score(query_set, query_tf, desc_tokens, weight_exact=1.0)

            # Body/instructions field score (depth signal)
            body_tokens = self._tokenize(body)
            body_score = self._field_score(query_set, query_tf, body_tokens, weight_exact=0.5)

            # Category + tools signal
            meta_tokens = self._tokenize(f"{category} {tools}")
            meta_score = self._field_score(query_set, query_tf, meta_tokens, weight_exact=1.5)

            # Cross-encoder combined: weighted field scores
            rerank_score = (
                0.30 * name_score +
                0.35 * desc_score +
                0.18 * body_score +
                0.17 * meta_score
            )

            # Description-phrase priority: Chinese phrases in description (high-precision signal)
            if query_phrases:
                desc_hits = sum(1 for p in query_phrases if len(p) >= 2 and p in desc)
                desc_phrase_bonus = min(desc_hits / max(len([p for p in query_phrases if len(p) >= 2]), 1) * 0.20, 0.20)
                rerank_score = min(rerank_score + desc_phrase_bonus, 1.0)
            else:
                # Keyword-in-body boost (fallback for non-Chinese queries)
                if body:
                    body_lower = body.lower()
                    hit_count = sum(1 for t in query_tokens if t in body_lower and len(t) > 1)
                    coverage = hit_count / max(len(query_tokens), 1)
                    rerank_score = min(rerank_score + coverage * 0.10, 1.0)

            # Description synonym saturation: multiple group terms in desc → strong relevance signal
            desc_tokens_set = set(self._tokenize(desc))
            for group in _SYNONYM_GROUPS:
                if query_set & group:  # this group is activated by query
                    desc_group_hits = len(group & desc_tokens_set)
                    if desc_group_hits >= 2:
                        sat_bonus = (desc_group_hits - 1) * 0.06
                        rerank_score = min(rerank_score + sat_bonus, 1.0)
                        break  # apply once for strongest matching group

            # Affinity feedback boost (RLHF signal from user ratings)
            skill_id = skill_data.get("skill_id", "")
            skill_cat = skill_data.get("category", "general")
            if self._affinity_boosts:
                # Aggregate boost from all agents that rated skills in this category
                cat_boosts = [v for (aid, cat), v in self._affinity_boosts.items() if cat == skill_cat]
                if cat_boosts:
                    avg_boost = sum(cat_boosts) / len(cat_boosts)
                    rerank_score = min(max(rerank_score + avg_boost * 0.15, 0), 1.0)
                # Specific skill feedback: direct boost from skill's own rating history
                skill_fb = self._feedback.get(skill_id, [])
                if skill_fb:
                    ratings = [f.rating for f in skill_fb if f.action == "rate" and f.rating > 0]
                    if ratings:
                        avg_r = sum(ratings) / len(ratings)
                        # rating 5→+0.06, rating 3→0, rating 1→-0.06
                        rerank_score = min(max(rerank_score + (avg_r - 3) * 0.03, 0), 1.0)

            reranked.append((skill_data, retrieval_score, rerank_score))

        reranked.sort(key=lambda x: 0.45 * x[1] + 0.55 * x[2], reverse=True)
        return reranked

    def _field_score(self, query_set: set, query_tf: Counter, field_tokens: List[str], weight_exact: float = 1.0) -> float:
        """Score a single field against the query (cross-encoder field component)."""
        if not field_tokens:
            return 0.0
        field_tf = Counter(field_tokens)
        field_set = set(field_tokens)

        # Token overlap ratio — multi-char tokens weighted 2x (semantic vs noise)
        overlap = query_set & field_set
        if not overlap:
            return 0.0
        weighted_hits = sum(2.0 if len(t) >= 2 else 0.5 for t in overlap)
        weighted_total = sum(2.0 if len(t) >= 2 else 0.5 for t in query_set)
        overlap_ratio = weighted_hits / max(weighted_total, 1)

        # IDF-weighted cosine
        cosine = self._cosine_sim_idf(query_tf, field_tf)

        # Exact match bonus (higher weight for shorter fields like name)
        exact_bonus = 0.0
        if overlap:
            exact_bonus = sum(self._idf_cache.get(t, 0.5) * (2.0 if len(t) >= 2 else 0.5) for t in overlap) / max(weighted_total, 1)
            exact_bonus = min(exact_bonus * weight_exact * 0.3, 0.4)

        return min(0.4 * overlap_ratio + 0.4 * cosine + 0.2 * exact_bonus, 1.0)

    # ══ Injection Prompt Generation ══════════════════════════════

    def _generate_inject_prompt(self, team_id: str, skill_ids: List[str]) -> str:
        """Generate the skill injection text for agent system prompt."""
        if not skill_ids or not self._skill_library:
            return ""
        skills = self._skill_library.browse(team_id=team_id)
        selected = [s for s in skills if s.get("skill_id") in skill_ids]
        if not selected:
            return ""

        lines = ["## Injected Skills\n"]
        for s in selected:
            lines.append(f"### {s.get('icon', '⚡')} {s.get('name', '')}")
            if s.get("description"):
                lines.append(f"{s['description']}")
            if s.get("instructions"):
                lines.append(f"```\n{s['instructions'][:500]}\n```")
            lines.append("")
        return "\n".join(lines)

    # ══ Match Explanation ════════════════════════════════════════

    def _explain_match(self, query: str, skill: Dict) -> List[str]:
        """Generate human-readable match reasons."""
        reasons = []
        query_lower = query.lower()
        name = skill.get("name", "").lower()
        desc = skill.get("description", "").lower()

        query_words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-z]{3,}', query_lower))
        name_words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-z]{3,}', name))
        desc_words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-z]{3,}', desc))

        name_overlap = query_words & name_words
        if name_overlap:
            reasons.append(f"名称匹配: {', '.join(list(name_overlap)[:3])}")

        desc_overlap = query_words & desc_words
        if desc_overlap:
            reasons.append(f"描述匹配: {', '.join(list(desc_overlap)[:3])}")

        cat = skill.get("category", "")
        if cat and cat.lower() in query_lower:
            reasons.append(f"类别相关: {cat}")

        tools = skill.get("required_tools", [])
        for t in tools:
            if t.lower() in query_lower:
                reasons.append(f"工具匹配: {t}")
                break

        if not reasons:
            reasons.append("语义相似")

        return reasons

    # ══ Text Processing Utilities ════════════════════════════════

    def _build_idf(self, candidates: List[Dict]):
        """Build IDF cache from skill corpus (lazy, rebuilds if size changes)."""
        if len(candidates) == self._corpus_size and self._idf_cache:
            return  # cached
        self._corpus_size = len(candidates)
        df = Counter()
        for skill in candidates:
            text = f"{skill.get('name', '')} {skill.get('description', '')} {skill.get('instructions', '')}"
            tokens = set(self._tokenize(text))
            for t in tokens:
                df[t] += 1
        N = max(len(candidates), 1)
        self._idf_cache = {t: math.log((N - freq + 0.5) / (freq + 0.5) + 1) for t, freq in df.items()}

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize Chinese + English text with sliding window for Chinese."""
        text = text.lower()
        # Single Chinese chars + English words
        base_tokens = re.findall(r'[\u4e00-\u9fff]|[a-z0-9_]{2,}', text)
        # Add Chinese 2-char sliding window (captures phrases like "数据分析")
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_chars:
            if len(segment) >= 2:
                for i in range(len(segment) - 1):
                    base_tokens.append(segment[i:i+2])
        return base_tokens

    def _bigrams(self, tokens: List[str]) -> set:
        """Generate bigram set from token list."""
        if len(tokens) < 2:
            return set()
        return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}

    def _trigrams(self, tokens: List[str]) -> set:
        """Generate trigram set from token list."""
        if len(tokens) < 3:
            return set()
        return {(tokens[i], tokens[i + 1], tokens[i + 2]) for i in range(len(tokens) - 2)}

    @staticmethod
    def _char_ngrams(text: str, n: int = 3) -> Set[str]:
        """Generate character n-grams from raw text."""
        t = re.sub(r"\s+", "", text or "")
        if len(t) < n:
            return {t} if t else set()
        return {t[i:i+n] for i in range(len(t) - n + 1)}

    @classmethod
    def _ngram_score(cls, query: str, doc: str, n: int = 3) -> float:
        """Calculate Jaccard similarity over character n-grams."""
        a = cls._char_ngrams(query, n)
        b = cls._char_ngrams(doc, n)
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _expand_synonyms(self, tokens: List[str]) -> Set[str]:
        """Expand query tokens with related terms from synonym groups."""
        expanded = set()
        token_set = set(tokens)
        for group in _SYNONYM_GROUPS:
            overlap = token_set & group
            if overlap:
                # Add other terms from the group (excluding original tokens)
                expanded.update(group - token_set)
        return expanded

    def _extract_chinese_phrases(self, text: str) -> List[str]:
        """Extract 2-4 character Chinese phrases from text."""
        phrases = []
        segments = re.findall(r'[\u4e00-\u9fff]{2,}', text.lower())
        for seg in segments:
            if len(seg) >= 2:
                phrases.append(seg)
            # Also add sub-phrases for longer segments
            if len(seg) >= 4:
                for i in range(len(seg) - 1):
                    phrases.append(seg[i:i+2])
                for i in range(len(seg) - 2):
                    phrases.append(seg[i:i+3])
        return list(set(phrases))

    def _cosine_sim_idf(self, tf1: Counter, tf2: Counter) -> float:
        """IDF-weighted cosine similarity."""
        if not tf1 or not tf2:
            return 0.0
        common = set(tf1.keys()) & set(tf2.keys())
        if not common:
            return 0.0
        # Weight by IDF
        dot = sum(tf1[t] * tf2[t] * self._idf_cache.get(t, 0.5) ** 2 for t in common)
        mag1 = math.sqrt(sum((v * self._idf_cache.get(t, 0.5)) ** 2 for t, v in tf1.items()))
        mag2 = math.sqrt(sum((v * self._idf_cache.get(t, 0.5)) ** 2 for t, v in tf2.items()))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    def _normalize_bm25(self, score: float) -> float:
        """Normalize BM25 score to [0, 1] using sigmoid."""
        return 1.0 / (1.0 + math.exp(-score + 2))

    def _get_skill_pool(self, team_id: str) -> List[Dict]:
        """Get all available skills for routing."""
        if self._skill_library:
            return self._skill_library.browse(team_id=team_id)
        return []

    def _session_to_dict(self, s: RoutingSession) -> Dict:
        return {
            "session_id": s.session_id,
            "agent_id": s.agent_id,
            "agent_name": s.agent_name,
            "team_id": s.team_id,
            "query": s.query,
            "top_k": s.top_k,
            "results_count": len(s.results),
            "assigned_count": len(s.assigned_skill_ids),
            "created_at": s.created_at,
            "duration_ms": s.duration_ms,
            "stage1_ms": s.stage1_ms,
            "stage2_ms": s.stage2_ms,
            "pool_size": s.pool_size,
            "mode": s.mode,
        }


# ── Singleton ────────────────────────────────────────────────────
_router_instance: Optional[SkillRouter] = None


def get_skill_router() -> SkillRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = SkillRouter()
    return _router_instance


def init_skill_router(skill_library=None, team_manager=None) -> SkillRouter:
    global _router_instance
    _router_instance = SkillRouter(skill_library=skill_library, team_manager=team_manager)
    logger.info("✅ SkillRouter initialized")
    return _router_instance
