# -*- coding: utf-8 -*-
"""Skill Classifier — 技能三类分类器 (全局优化 G-2).

按演练/使用证据把技能归入: 特有(exclusive) / 通用(general) / 储备(reserve)。
分类是定期重算的函数，不是人工标签；分类变化产生毕业/降级事件。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
STORE_DIR = _ROOT / "storage" / "skill_classification"

# ── 判定阈值（集中放置便于调参） ──
EXCLUSIVE_TEAM_SHARE = 0.8        # 单团队使用占比
EXCLUSIVE_MIN_EFFECTIVENESS = 0.6
GENERAL_MIN_TEAMS = 2             # 跨团队采用数
GENERAL_MIN_CATEGORIES = 2        # 跨场景类目达标数
RESERVE_MAX_EFFECTIVENESS = 0.4   # 低于此 → 储备
STALE_DAYS = 90                   # 未使用天数 → 储备
GRADUATE_STREAK = 2               # 毕业需连续达标周期数
DEMOTE_GRACE = 1                  # 降级宽限周期数


class Classification(str, Enum):
    EXCLUSIVE = "exclusive"  # 特有技能
    GENERAL = "general"      # 通用技能
    RESERVE = "reserve"      # 储备技能


def classify(
    skill: Dict[str, Any],
    usage_evidence: Optional[Dict[str, Any]] = None,
    trial_evidence: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """单技能即时分类（无防抖）.

    Args:
        skill: SkillDefinition.to_dict() 格式（effectiveness/adopted_by/
               lifecycle_stage/last_used_at/origin_team_id 等）
        usage_evidence: {"team_usage": {team_id: count}}  各团队使用次数
        trial_evidence: {"category_pass": {scenario_category: bool},
                         "meets_rubric": bool, "gate_ok": bool}
    Returns:
        {"classification", "reasons": [...], "score_card": {...}}
    """
    now = now or datetime.now(timezone.utc)
    usage = usage_evidence or {}
    trial = trial_evidence or {}
    reasons: List[str] = []

    effectiveness = float(skill.get("effectiveness", 0) or 0)
    lifecycle = str(skill.get("lifecycle_stage", "draft"))
    adopted_by = skill.get("adopted_by", []) or []
    team_usage: Dict[str, int] = usage.get("team_usage", {}) or {}
    total_uses = sum(team_usage.values())
    meets_rubric = bool(trial.get("meets_rubric", False))
    gate_ok = bool(trial.get("gate_ok", False))
    category_pass = trial.get("category_pass", {}) or {}
    categories_passed = sum(1 for v in category_pass.values() if v)

    # ── 强制储备条件（优先级最高） ──
    if lifecycle == "degraded":
        return _result(Classification.RESERVE, [f"lifecycle=degraded，回收进储备池"], locals())
    if effectiveness < RESERVE_MAX_EFFECTIVENESS and total_uses > 0:
        return _result(Classification.RESERVE,
                       [f"effectiveness {effectiveness:.2f} < {RESERVE_MAX_EFFECTIVENESS}"], locals())
    last_used = _parse_ts(skill.get("last_used_at", ""))
    if last_used and (now - last_used) > timedelta(days=STALE_DAYS):
        return _result(Classification.RESERVE,
                       [f"超过 {STALE_DAYS} 天未使用 (last_used={last_used.date()})"], locals())
    if total_uses == 0:
        return _result(Classification.RESERVE, ["无使用记录（新技能默认储备）"], locals())

    # ── 通用判定 ──
    team_count = len(set(adopted_by) | ({skill.get("origin_team_id")} if skill.get("origin_team_id") else set()))
    if (team_count >= GENERAL_MIN_TEAMS or categories_passed >= GENERAL_MIN_CATEGORIES) and gate_ok:
        if team_count >= GENERAL_MIN_TEAMS:
            reasons.append(f"{team_count} 个团队采用 (≥{GENERAL_MIN_TEAMS})")
        if categories_passed >= GENERAL_MIN_CATEGORIES:
            reasons.append(f"{categories_passed} 个场景类目演练达标 (≥{GENERAL_MIN_CATEGORIES})")
        reasons.append("发布门禁通过")
        return _result(Classification.GENERAL, reasons, locals())

    # ── 特有判定 ──
    if team_usage:
        top_team, top_count = max(team_usage.items(), key=lambda kv: kv[1])
        share = top_count / total_uses if total_uses else 0
        if share >= EXCLUSIVE_TEAM_SHARE and effectiveness >= EXCLUSIVE_MIN_EFFECTIVENESS and meets_rubric:
            return _result(Classification.EXCLUSIVE, [
                f"团队 {top_team} 使用占比 {share:.0%} (≥{EXCLUSIVE_TEAM_SHARE:.0%})",
                f"effectiveness {effectiveness:.2f} ≥ {EXCLUSIVE_MIN_EFFECTIVENESS}",
                "演练成功率达 rubric 期望",
            ], locals())

    return _result(Classification.RESERVE, ["未满足特有/通用条件，保留在储备池"], locals())


def _result(cls: Classification, reasons: List[str], ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "classification": cls.value,
        "reasons": reasons,
        "score_card": {
            "effectiveness": ctx.get("effectiveness", 0),
            "total_uses": ctx.get("total_uses", 0),
            "team_count": ctx.get("team_count", len(ctx.get("team_usage", {}) or {})),
            "categories_passed": ctx.get("categories_passed", 0),
            "meets_rubric": ctx.get("meets_rubric", False),
            "gate_ok": ctx.get("gate_ok", False),
        },
    }


def _parse_ts(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


_RANK = {Classification.RESERVE.value: 0, Classification.EXCLUSIVE.value: 1, Classification.GENERAL.value: 2}


DEBOUNCE_WINDOW = 3
DEBOUNCE_MAJORITY = 2


def classify_with_history(
    prev_record: Optional[Dict[str, Any]],
    skill: Dict[str, Any],
    usage_evidence: Optional[Dict[str, Any]] = None,
    trial_evidence: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """带防抖的分类 (论文 Section 5.6 2-of-3 多数去抖 + 历史兼容):

    - 保留最近 3 次分类窗口，当某种分类在窗口中出现 >= 2 次时发生状态跃迁
    - 安全违规或严重故障立即旁路去抖（bypass debounce），直接降级至 reserve
    """
    raw = classify(skill, usage_evidence, trial_evidence, now)
    raw_cls = raw["classification"]
    prev = prev_record or {}
    current = prev.get("classification", Classification.RESERVE.value)
    streak = int(prev.get("streak", 0))
    grace = int(prev.get("grace", 0))

    # 维护最近 DEBOUNCE_WINDOW 次即时分类窗口
    prev_window = list(prev.get("window", []))
    window = prev_window[-(DEBOUNCE_WINDOW - 1):] + [raw_cls]

    effective = current
    event = None

    # 论文 5.6：安全违规/严重失败直接旁路去抖立即降级
    if skill.get("safety_violation") or skill.get("severe_failure"):
        effective = Classification.RESERVE.value
        event = {
            "type": "demote",
            "from": current,
            "to": effective,
            "rule": "safety_bypass_debounce",
            "suggest_evolution": True,
        }
        window = [effective]
        streak, grace = 0, 0
    elif raw_cls != current and window.count(raw_cls) >= DEBOUNCE_MAJORITY:
        effective = raw_cls
        kind = "graduate" if _RANK.get(raw_cls, 0) > _RANK.get(current, 0) else "demote"
        event = {
            "type": kind,
            "from": current,
            "to": raw_cls,
            "window": list(window),
            "rule": "2-of-3-majority",
            "suggest_evolution": raw_cls == Classification.RESERVE.value,
        }
        window = [effective]  # 跃迁后重置窗口，防止二次连续震荡
        streak, grace = 0, 0
    elif raw_cls == current:
        streak, grace = 0, 0
    elif _RANK.get(raw_cls, 0) > _RANK.get(current, 0):
        streak += 1
        grace = 0
    else:
        grace += 1
        streak = 0

    return {
        "classification": effective,
        "raw_classification": raw_cls,
        "reasons": raw["reasons"],
        "score_card": raw["score_card"],
        "streak": streak,
        "grace": grace,
        "window": window,
        "event": event,
        "evaluated_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


class ClassificationStore:
    """分类持久化 — storage/skill_classification/{team_id}.json (G2-2)."""

    def __init__(self, store_dir: Optional[Path] = None):
        self._dir = store_dir or STORE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, team_id: str) -> Path:
        safe = "".join(c for c in (team_id or "default") if c.isalnum() or c in "-_") or "default"
        return self._dir / f"{safe}.json"

    def load(self, team_id: str) -> Dict[str, Any]:
        p = self._path(team_id)
        if not p.exists():
            return {"skills": {}, "history": []}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"分类存储读取失败 ({team_id}): {e}")
            return {"skills": {}, "history": []}

    def save(self, team_id: str, data: Dict[str, Any]) -> None:
        p = self._path(team_id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    def reclassify_team(
        self,
        team_id: str,
        skills: List[Dict[str, Any]],
        evidence_fn=None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """批量重算 (G2-3). evidence_fn(skill) -> (usage_evidence, trial_evidence)."""
        data = self.load(team_id)
        changes: List[Dict[str, Any]] = []
        pools = {c.value: [] for c in Classification}

        for skill in skills:
            sid = skill.get("skill_id", "")
            if not sid:
                continue
            usage_ev, trial_ev = (evidence_fn(skill) if evidence_fn else ({}, {}))
            prev = data["skills"].get(sid)
            record = classify_with_history(prev, skill, usage_ev, trial_ev, now)
            record["skill_id"] = sid
            record["skill_name"] = skill.get("name", "")
            data["skills"][sid] = record
            pools[record["classification"]].append({
                "skill_id": sid, "name": skill.get("name", ""),
                "reasons": record["reasons"],
            })
            if record.get("event"):
                evt = dict(record["event"])
                evt.update({"skill_id": sid, "skill_name": skill.get("name", ""),
                            "at": record["evaluated_at"]})
                changes.append(evt)
                data.setdefault("history", []).append(evt)

        data["last_reclassified"] = (now or datetime.now(timezone.utc)).isoformat()
        self.save(team_id, data)
        return {
            "team_id": team_id,
            "total": len(skills),
            "pools": {k: len(v) for k, v in pools.items()},
            "pool_detail": pools,
            "changes": changes,
        }

    def get_view(self, team_id: str) -> Dict[str, Any]:
        """当前三池视图 (G2-4)."""
        data = self.load(team_id)
        pools: Dict[str, List[Dict[str, Any]]] = {c.value: [] for c in Classification}
        for sid, rec in data.get("skills", {}).items():
            pools[rec.get("classification", "reserve")].append({
                "skill_id": sid, "name": rec.get("skill_name", ""),
                "reasons": rec.get("reasons", []),
                "score_card": rec.get("score_card", {}),
                "evaluated_at": rec.get("evaluated_at", ""),
            })
        return {"team_id": team_id, "pools": pools,
                "last_reclassified": data.get("last_reclassified")}

    def get_history(self, team_id: str, skill_id: str = "") -> List[Dict[str, Any]]:
        history = self.load(team_id).get("history", [])
        if skill_id:
            history = [h for h in history if h.get("skill_id") == skill_id]
        return history

    def seed_reserve_from_extraction(
        self,
        team_id: str,
        skill: Dict[str, Any],
        source: str = "extraction",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """G1-2: 萃取完成后，默认写入储备池分类记录（幂等）.

        说明:
        - 仅在该技能尚无分类记录时写入，避免覆盖周期重算结果。
        - 写入一条 history 事件，便于追踪来源。
        """
        sid = str(skill.get("skill_id") or skill.get("slug") or "").strip()
        if not sid:
            return {"created": False, "reason": "missing_skill_id"}

        ts = (now or datetime.now(timezone.utc)).isoformat()
        data = self.load(team_id)
        if sid in data.get("skills", {}):
            return {"created": False, "reason": "already_exists", "skill_id": sid}

        record = {
            "skill_id": sid,
            "skill_name": str(skill.get("name") or sid),
            "classification": Classification.RESERVE.value,
            "raw_classification": Classification.RESERVE.value,
            "reasons": ["萃取产物默认进入储备池，待验证与周期重算决定毕业"],
            "score_card": {
                "effectiveness": float(skill.get("effectiveness", 0) or 0),
                "total_uses": 0,
                "team_count": 1 if team_id else 0,
                "categories_passed": 0,
                "meets_rubric": False,
                "gate_ok": False,
            },
            "streak": 0,
            "grace": 0,
            "evaluated_at": ts,
            "seed_source": source,
        }
        data.setdefault("skills", {})[sid] = record
        data.setdefault("history", []).append({
            "type": "seed_reserve",
            "from": "",
            "to": Classification.RESERVE.value,
            "skill_id": sid,
            "skill_name": record["skill_name"],
            "source": source,
            "at": ts,
        })
        data["last_reclassified"] = ts
        self.save(team_id, data)
        return {"created": True, "skill_id": sid, "classification": Classification.RESERVE.value}


# ── 单例 ──────────────────────────────────────────────────

_store: Optional[ClassificationStore] = None


def get_classification_store() -> ClassificationStore:
    global _store
    if _store is None:
        _store = ClassificationStore()
    return _store


def reset_classification_store(**kwargs) -> ClassificationStore:
    global _store
    _store = ClassificationStore(**kwargs)
    return _store
