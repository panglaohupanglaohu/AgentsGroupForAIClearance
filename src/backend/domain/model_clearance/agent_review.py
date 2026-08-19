# -*- coding: utf-8 -*-
"""T401–T406 — Agent Review Board for Model Admission Clearance (T2 Principle: Opinion only)."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from .models import Evidence, GateVerdict, ModelApplication, ReviewOpinion

BOARD_AGENTS = {
    "security_reviewer": {
        "role": "Security & Supply Chain Reviewer",
        "gate": "G2",
        "instructions": "Audit ML-BOM, deserialization safety, and vulnerability scan evidence. Quote evidence verbatim.",
    },
    "compliance_reviewer": {
        "role": "License & Regulatory Compliance Reviewer",
        "gate": "G3",
        "instructions": "Audit commercial terms, MAU thresholds, AUP restrictions, and jurisdiction constraints.",
    },
    "infra_reviewer": {
        "role": "Infrastructure & GPU Capacity Reviewer",
        "gate": "G4",
        "instructions": "Audit parameter scale, KV-Cache memory, multi-node networking, and quantization headroom.",
    },
    "legal_reviewer": {
        "role": "Legal & Export Control Specialist",
        "gate": "G3",
        "instructions": "Triggered on conditional licenses or export restrictions for binding legal signoff.",
    },
    "adjudicator": {
        "role": "Clearance Adjudication Coordinator",
        "gate": "G6",
        "instructions": "Synthesize gate verdicts and reviewer opinions into final admission attestation.",
    },
}


class PolicyOverrideAttempt(Exception):
    """Raised when an Agent attempts to relax a failed policy gate to pass."""
    pass


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def quote_locatable(quote: str, evidences: List[Evidence]) -> bool:
    """T405: Verify that quoted_text is locatable in raw evidence payloads (hallucination guard)."""
    if not quote or not quote.strip():
        return False
    target = normalize_whitespace(quote)
    for ev in evidences:
        payload_str = normalize_whitespace(str(ev.payload))
        if target in payload_str:
            return True
    return False


def ref_exists(ref: str, evidences: List[Evidence]) -> bool:
    """Verify that evidence_ref exists in provided evidences."""
    return any(e.evidence_id == ref for e in evidences)


def should_trigger_legal_reviewer(app: ModelApplication, evidences: List[Evidence]) -> bool:
    """T406: Check if legal reviewer is required."""
    for ev in evidences:
        if ev.gate == "G3":
            lic_cls = ev.payload.get("license_class")
            if lic_cls == "conditional" or ev.payload.get("jurisdiction_restricted"):
                return True
    return False


def simulate_or_call_agent_review(
    gate: str,
    app: ModelApplication,
    evidences: List[Evidence],
    policy_verdict: GateVerdict,
    llm_callable: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> ReviewOpinion:
    """T404: Run agent review with validation, hallucination guards, and directional guardrail."""
    reviewer_name = "compliance_reviewer" if gate == "G3" else "security_reviewer" if gate == "G2" else "infra_reviewer"

    if llm_callable:
        raw = llm_callable(f"Review gate {gate} for model {app.identity.model_id}")
    else:
        # Deterministic default opinion generation from evidence
        matched_ev = next((e for e in evidences if e.gate == gate), evidences[0] if evidences else None)
        ev_ref = matched_ev.evidence_id if matched_ev else "ev-default"

        if gate == "G3":
            lic_cls = matched_ev.payload.get("license_class") if matched_ev else "conditional"
            conditions = matched_ev.payload.get("license_conditions", []) if matched_ev else []
            findings = []
            if conditions:
                findings.append({
                    "statement": f"许可证包含特定约束: {conditions[0]}",
                    "evidence_ref": ev_ref,
                    "quoted_text": conditions[0],
                })
            rec_conditions = ["仅限内部研发与推理服务使用"] if lic_cls == "conditional" else []
            raw = {
                "gate": "G3",
                "reviewer": "compliance_reviewer",
                "verdict_suggestion": "tighten" if lic_cls == "restricted" else "pass",
                "risk_level": "high" if lic_cls == "restricted" else "medium" if lic_cls == "conditional" else "low",
                "findings": findings,
                "missing_evidence": [],
                "recommended_conditions": rec_conditions,
                "tightens_verdict": lic_cls == "restricted",
            }
        elif gate == "G4":
            req_multi = matched_ev.payload.get("requires_multi_node", False) if matched_ev else False
            raw = {
                "gate": "G4",
                "reviewer": "infra_reviewer",
                "verdict_suggestion": "needs_info" if req_multi else "pass",
                "risk_level": "medium" if req_multi else "low",
                "findings": [],
                "missing_evidence": ["多节点网络拓扑基准未提供"] if req_multi else [],
                "recommended_conditions": ["绑定独立 GPU 资源池"] if req_multi else [],
                "tightens_verdict": False,
            }
        else:
            raw = {
                "gate": gate,
                "reviewer": reviewer_name,
                "verdict_suggestion": "pass",
                "risk_level": "low",
                "findings": [],
                "missing_evidence": [],
                "recommended_conditions": [],
                "tightens_verdict": False,
            }

    # Directional Guard: Policy fail CANNOT be overturned by Agent to pass
    if policy_verdict.verdict == "fail" and raw.get("verdict_suggestion") == "pass":
        raise PolicyOverrideAttempt(f"Agent {reviewer_name} attempted to relax failed gate {gate} to pass.")

    return ReviewOpinion.from_dict(raw)
