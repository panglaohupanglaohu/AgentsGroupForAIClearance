# -*- coding: utf-8 -*-
"""T307 — Adjudication Resolver for Clearance Board."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .models import ModelApplication, utc_now_iso
from .policy_evaluator import load_policy


@dataclass
class Decision:
    verdict: str  # approved | approved_with_conditions | rejected | need_info
    reason: str = ""
    conditions: List[str] = field(default_factory=list)
    runtime_profile: str = "standard"  # isolated | restricted | standard
    scope: List[str] = field(default_factory=lambda: ["internal"])
    expires_at: str = ""
    decided_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "conditions": self.conditions,
            "runtime_profile": self.runtime_profile,
            "scope": self.scope,
            "expires_at": self.expires_at,
            "decided_at": self.decided_at,
        }


def adjudicate(app: ModelApplication, policy: Optional[Dict[str, Any]] = None) -> Decision:
    policy = policy or load_policy()

    # Rule 1: Blocker fail cannot be overturned
    for v in app.verdicts:
        if v.verdict == "fail" and v.severity == "blocker":
            return Decision(
                verdict="rejected",
                reason=f"Blocker check failed at gate {v.gate}: {', '.join(v.failed_checks)}",
                runtime_profile="isolated",
                scope=[],
                expires_at="",
            )

    # Check for agent opinions that tightened to fail/reject
    for op in app.opinions:
        if op.verdict_suggestion == "tighten" and op.risk_level == "high":
            return Decision(
                verdict="rejected",
                reason=f"Agent review ({op.reviewer}) tightened gate {op.gate} to rejection",
                runtime_profile="isolated",
                scope=[],
                expires_at="",
            )

    # Majors & conditions
    conditions: List[str] = []
    has_majors = False
    for v in app.verdicts:
        if v.severity == "major" or v.verdict == "needs_info":
            has_majors = True
            for c in v.failed_checks:
                conditions.append(f"Gate {v.gate} condition: resolved via runtime guardrail ({c})")

    for op in app.opinions:
        conditions.extend(op.recommended_conditions)

    # Deduplicate conditions
    conditions = list(dict.fromkeys(conditions))

    # Profile determination
    profile = "standard"
    has_platform_endorsement = any(
        e.payload.get("endorsement") == "platform" for e in app.evidence
    )
    if has_platform_endorsement or has_majors:
        profile = "restricted"

    # Scope determination from G3 license evidence
    scope = ["internal"]
    for e in app.evidence:
        if e.gate == "G3":
            lic_cls = e.payload.get("license_class", "conditional")
            spec = policy.get("license_classes", {}).get(lic_cls, {})
            scope = spec.get("scope", ["internal"])
            break

    exp_date = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

    final_verdict = "approved_with_conditions" if conditions else "approved"

    return Decision(
        verdict=final_verdict,
        reason="All gates and reviews satisfied" if not conditions else "Approved under specified runtime conditions",
        conditions=conditions,
        runtime_profile=profile,
        scope=scope,
        expires_at=exp_date,
    )
