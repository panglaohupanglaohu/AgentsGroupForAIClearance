"""生态证据回流 — 论文 Section 5.7 的差异化留存证据回路.

论文原文：published skills 与组合在资源/捕食/生态位压力下产生 differential
persistence，**证据必须返回下一轮变异与版本竞争**（"returning differential-
persistence evidence to the next round of variation"）。

此前 eco drill 的结果止步于试炼报告，不进入下一轮 Plaza 议题，链路是断的。
本模块把 drill 结果压成结构化证据并落盘，Plaza 开场时读取并注入 O 阶段上下文。

字段名对齐 `eco_drill.run_drill_via_trial` 的真实输出：
`final_ranking[].survival_ticks / skill_genome`、`gene_pool.dominant|deprecated`、
`integration.missing_plan_skills`、`env.demanded_skills`。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage" / "eco_feedback"

TOP_COMBINATIONS = 3
MAX_UNCOVERED = 8
MAX_RECURRENT = 5


def _storage_dir() -> Path:
    override = os.environ.get("AG_ECO_FEEDBACK_DIR")
    return Path(override) if override else _STORAGE_DIR


def evidence_path(team_id: str) -> Path:
    safe = "".join(ch for ch in str(team_id or "unknown") if ch.isalnum() or ch in "-_") or "unknown"
    return _storage_dir() / f"{safe}.json"


def extract_persistence_evidence(drill_result: Dict[str, Any]) -> Dict[str, Any]:
    """把 eco drill 结果压成可喂给下一轮 Plaza 的结构化证据。"""
    ranking = drill_result.get("final_ranking") or []

    persistent: List[Dict[str, Any]] = []
    seen: set = set()
    for row in ranking[:TOP_COMBINATIONS]:
        combo = sorted(str(s) for s in (row.get("skill_genome") or []))
        key = tuple(combo)
        if not combo or key in seen:
            continue
        seen.add(key)
        persistent.append({
            "skills": combo,
            "survival_ticks": int(row.get("survival_ticks") or 0),
            "population": row.get("population") or "",
            "alive": bool(row.get("alive")),
        })

    gene_pool = drill_result.get("gene_pool") or {}
    integration = drill_result.get("integration") or {}
    env = drill_result.get("env") or {}

    # 未覆盖需求：计划要求但基因池里没人携带 + 环境需求里无人存活携带
    carried = {str(d.get("skill")) for d in (gene_pool.get("dominant") or [])}
    carried |= {str(d.get("skill")) for d in (gene_pool.get("neutral") or [])}
    uncovered: List[str] = list(integration.get("missing_plan_skills") or [])
    for skill in env.get("demanded_skills") or []:
        if str(skill) not in carried and str(skill) not in uncovered:
            uncovered.append(str(skill))

    # 反复失败：被淘汰（携带者全灭）的 skill，按携带者数量降序
    recurrent = [
        {"skill": str(d.get("skill")), "dead_carriers": int(d.get("carriers") or 0)}
        for d in (gene_pool.get("deprecated") or [])
    ]
    recurrent.sort(key=lambda d: -d["dead_carriers"])

    return {
        "trial_id": drill_result.get("trial_id", ""),
        "persistent_combinations": persistent,
        "uncovered_demands": uncovered[:MAX_UNCOVERED],
        "recurrent_failures": recurrent[:MAX_RECURRENT],
        "best_survival_ticks": int(drill_result.get("best_survival_ticks") or 0),
        "total_generations": int(drill_result.get("total_generations") or 0),
        "env": {
            "abundance": env.get("abundance"),
            "predator_pressure": env.get("predator_pressure"),
            "niche_capacity": env.get("niche_capacity"),
            "demanded_skills": list(env.get("demanded_skills") or []),
        },
        "note": "T_i=survival_ticks 为唯一适应度；本证据仅供下一轮变异与版本竞争参考，不直接决定发布。",
    }


def build_next_agenda(evidence: Dict[str, Any]) -> str:
    """生成注入 Plaza objective 阶段的开场上下文。"""
    if not evidence:
        return ""
    lines = ["【上一轮生态演练的差异化留存证据】"]

    env = evidence.get("env") or {}
    if env.get("abundance") is not None:
        lines.append(
            f"- 环境：资源丰度 {env.get('abundance')}、捕食压力 "
            f"{env.get('predator_pressure')}、生态位容量 {env.get('niche_capacity')}"
        )

    for combo in evidence.get("persistent_combinations") or []:
        status = "存活" if combo.get("alive") else "已淘汰"
        lines.append(
            f"- 持续留存组合（{status}，{combo['survival_ticks']} ticks）: {combo['skills']}"
        )

    uncovered = evidence.get("uncovered_demands") or []
    if uncovered:
        lines.append(f"- 未覆盖需求（建议作为新技能议题）: {uncovered}")

    recurrent = evidence.get("recurrent_failures") or []
    if recurrent:
        pairs = [f"{d['skill']}×{d['dead_carriers']}" for d in recurrent]
        lines.append(f"- 携带者全灭的技能（反复失败）: {pairs}")

    lines.append("请据此补充可验证事实、挑战风险边界，并提出候选改进方案。")
    return "\n".join(lines)


def save_evidence(team_id: str, evidence: Dict[str, Any]) -> Optional[Path]:
    """落盘证据。失败只告警，绝不阻断演练主流程。"""
    try:
        path = evidence_path(team_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path
    except Exception as e:  # pragma: no cover
        logger.warning("eco feedback 落盘失败（不阻断）: %s", e)
        return None


def load_evidence(team_id: str) -> Dict[str, Any]:
    """读取证据；不存在或损坏时返回空 dict。"""
    try:
        path = evidence_path(team_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # pragma: no cover
        logger.debug("eco feedback 读取失败: %s", e)
        return {}


def capture_from_drill(drill_result: Dict[str, Any], team_id: str = "") -> Dict[str, Any]:
    """drill 结束后的一站式入口：抽取 + 落盘。"""
    evidence = extract_persistence_evidence(drill_result)
    tid = team_id or _first_population(drill_result)
    if tid:
        save_evidence(tid, evidence)
    return evidence


def _first_population(drill_result: Dict[str, Any]) -> str:
    for row in drill_result.get("final_ranking") or []:
        if row.get("population"):
            return str(row["population"])
    pops = drill_result.get("populations") or []
    return str(pops[0]) if pops else ""
