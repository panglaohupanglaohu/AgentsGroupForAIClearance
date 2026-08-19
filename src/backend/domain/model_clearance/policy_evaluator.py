# -*- coding: utf-8 -*-
"""T302 — Policy Evaluator for gate rules (T3 Policy as Code, T4 Fail-Closed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .models import Evidence, GateVerdict, utc_now_iso
from .safe_eval import safe_eval

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[4] / "config" / "clearance_policy.yaml"


def load_policy(path: Optional[Path | str] = None) -> Dict[str, Any]:
    p = Path(path) if path else _DEFAULT_POLICY_PATH
    if not p.exists():
        raise FileNotFoundError(f"Policy file not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def find_evidence_for_check(evidences: List[Evidence], check_id: str) -> Optional[Evidence]:
    for ev in evidences:
        if ev.check_id == check_id or check_id in ev.payload.get("checked_rules", []):
            return ev
    # Fallback match by gate or common check keys
    for ev in evidences:
        if ev.payload and not ev.payload.get("_error"):
            # Check if payload contains fields needed by the check
            return ev
    return evidences[0] if evidences else None


def evaluate_gate(
    gate_id: str,
    evidences: List[Evidence],
    policy: Optional[Dict[str, Any]] = None,
) -> GateVerdict:
    policy = policy or load_policy()
    gate_spec = policy.get("gates", {}).get(gate_id, {})
    blocker_checks = set(gate_spec.get("blocker_checks", []))
    rules = gate_spec.get("rules", [])

    failed_checks: List[str] = []
    needs_info_checks: List[str] = []
    evidence_refs = [e.evidence_id for e in evidences]

    # Aggregate all payloads from this gate's evidences for rule evaluation
    merged_payload: Dict[str, Any] = {}
    any_error = False
    for ev in evidences:
        if ev.payload:
            if ev.payload.get("_status") != "ok":
                any_error = True
            merged_payload.update(ev.payload)

    for rule in rules:
        rule_id = rule.get("id", f"{gate_id}-rule")
        is_blocker = rule_id in blocker_checks
        expr = rule.get("expr", "")
        on_false = rule.get("on_false", "fail")

        # T4 Fail-closed check: if evidence failed to collect or errored
        if not evidences or any_error or merged_payload.get("_status") != "ok":
            if is_blocker or on_false == "fail":
                failed_checks.append(rule_id)
            else:
                needs_info_checks.append(rule_id)
            continue

        context = {"evidence": merged_payload}
        try:
            passed = safe_eval(expr, context)
            if not passed:
                if on_false == "fail" or is_blocker:
                    failed_checks.append(rule_id)
                else:
                    needs_info_checks.append(rule_id)
        except Exception:
            # T4: Evaluation error is treated as failure
            if is_blocker or on_false == "fail":
                failed_checks.append(rule_id)
            else:
                needs_info_checks.append(rule_id)

    if failed_checks:
        return GateVerdict(
            gate=gate_id,
            verdict="fail",
            severity="blocker",
            failed_checks=failed_checks,
            evidence_refs=evidence_refs,
            decided_by="policy",
            decided_at=utc_now_iso(),
        )

    if needs_info_checks:
        return GateVerdict(
            gate=gate_id,
            verdict="needs_info",
            severity="major",
            failed_checks=needs_info_checks,
            evidence_refs=evidence_refs,
            decided_by="policy",
            decided_at=utc_now_iso(),
        )

    return GateVerdict(
        gate=gate_id,
        verdict="pass",
        severity="none",
        failed_checks=[],
        evidence_refs=evidence_refs,
        decided_by="policy",
        decided_at=utc_now_iso(),
    )
