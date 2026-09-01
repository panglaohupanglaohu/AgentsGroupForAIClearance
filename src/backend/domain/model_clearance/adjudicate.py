# -*- coding: utf-8 -*-
"""T307 — Adjudication Resolver for Clearance Board."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .models import ModelApplication, utc_now_iso
from .policy_evaluator import load_policy
from .standard import (
    OUTCOME_APPROVED,
    OUTCOME_APPROVED_COND,
    OUTCOME_NOT_APPROVED,
    OUTCOME_RESTRICTED,
    PERMITTED_USE_BY_VALUE,
)


@dataclass
class Decision:
    """§9 保障裁决记录。"""

    verdict: str  # approved | approved_with_conditions | restricted | not_approved
    reason: str = ""
    conditions: List[str] = field(default_factory=list)
    runtime_profile: str = "standard"  # isolated | restricted | standard
    scope: List[str] = field(default_factory=lambda: ["internal"])
    permitted_use: str = "internal_row"
    residual_risks: List[str] = field(default_factory=list)
    hard_block: bool = False
    expires_at: str = ""
    decided_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "conditions": self.conditions,
            "runtime_profile": self.runtime_profile,
            "scope": self.scope,
            "permitted_use": self.permitted_use,
            "residual_risks": self.residual_risks,
            "hard_block": self.hard_block,
            "expires_at": self.expires_at,
            "decided_at": self.decided_at,
        }


def adjudicate(app: ModelApplication, policy: Optional[Dict[str, Any]] = None) -> Decision:
    policy = policy or load_policy()
    use_tier = getattr(app.deployment, "permitted_use", "internal_row")

    # §3 硬红线：G0 失败不可被任何其它证据或意见推翻
    for v in app.verdicts:
        if v.gate == "G0" and v.verdict == "fail":
            return Decision(
                verdict=OUTCOME_NOT_APPROVED,
                reason=f"命中标准 §3 禁止部署形态: {', '.join(v.failed_checks)}",
                runtime_profile="isolated",
                scope=[],
                permitted_use=use_tier,
                hard_block=True,
                expires_at="",
            )

    # Blocker 失败不可推翻
    for v in app.verdicts:
        if v.verdict == "fail" and v.severity == "blocker":
            return Decision(
                verdict=OUTCOME_NOT_APPROVED,
                reason=f"门禁 {v.gate} 阻断项未通过: {', '.join(v.failed_checks)}",
                runtime_profile="isolated",
                scope=[],
                permitted_use=use_tier,
                expires_at="",
            )

    for op in app.opinions:
        if op.verdict_suggestion == "tighten" and op.risk_level == "high":
            return Decision(
                verdict=OUTCOME_NOT_APPROVED,
                reason=f"专家复核（{op.reviewer}）将门禁 {op.gate} 收紧为不批准",
                runtime_profile="isolated",
                scope=[],
                permitted_use=use_tier,
                expires_at="",
            )

    conditions: List[str] = []
    residual_risks: List[str] = []
    has_majors = False
    for v in app.verdicts:
        if v.severity == "major" or v.verdict == "needs_info":
            has_majors = True
            for c in v.failed_checks:
                conditions.append(f"门禁 {v.gate} 条件：需以运行时护栏或补充证据消解（{c}）")

    for op in app.opinions:
        conditions.extend(op.recommended_conditions)

    conditions = list(dict.fromkeys(conditions))

    # §5：无法完全控制或独立验证的残余风险必须显式记录
    has_platform_endorsement = any(
        e.payload.get("endorsement") == "platform" for e in app.evidence
    )
    if has_platform_endorsement:
        residual_risks.append("厂商签名缺失，完整性依赖平台背书，供应方真实性无法独立验证")
    for e in app.evidence:
        if e.gate == "G1" and e.payload.get("training_data_transparency") is False:
            residual_risks.append("训练数据来源与方法披露不足（§6.1），偏见与污染风险无法完全排除")

    profile = "restricted" if (has_platform_endorsement or has_majors) else "standard"

    scope = ["internal"]
    for e in app.evidence:
        if e.gate == "G7" and "license_class" in e.payload:
            lic_cls = e.payload.get("license_class", "conditional")
            spec = policy.get("license_classes", {}).get(lic_cls, {})
            scope = spec.get("scope", ["internal"])
            break

    # §10.2/§10.3：面向客户与高风险用途未完成附加评估时，只能给 Restricted
    tier_spec = PERMITTED_USE_BY_VALUE.get(use_tier, {})
    extra_needed = bool(tier_spec.get("requires_additional_assessment"))
    extra_done = bool(getattr(app.deployment, "additional_assessment_complete", False))
    if extra_needed and not extra_done:
        return Decision(
            verdict=OUTCOME_RESTRICTED,
            reason=f"{tier_spec.get('label_zh', use_tier)}需 §{tier_spec.get('section', '10')} 附加评估，当前仅限内部受控试用",
            conditions=conditions + ["完成附加产品/用例评估后方可扩大至申请用途"],
            runtime_profile="restricted",
            scope=["internal"],
            permitted_use=use_tier,
            residual_risks=residual_risks,
            expires_at=(datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
        )

    exp_date = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    final_verdict = OUTCOME_APPROVED_COND if conditions else OUTCOME_APPROVED

    return Decision(
        verdict=final_verdict,
        reason="所有门禁与复核均已满足" if not conditions else "在指定运行条件下批准",
        conditions=conditions,
        runtime_profile=profile,
        scope=scope,
        permitted_use=use_tier,
        residual_risks=residual_risks,
        expires_at=exp_date,
    )
