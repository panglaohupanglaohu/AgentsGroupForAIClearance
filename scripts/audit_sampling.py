#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T908 — Weekly Model Clearance Audit Sampling and Verification Script."""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add backend to python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.registry import ApprovedRegistryEntry, ModelRegistryStore, get_registry_store


def run_audit_sampling(
    store: ModelRegistryStore,
    sample_ratio: float = 0.5,
    seed: int = 42,
) -> Dict[str, Any]:
    random.seed(seed)
    active_entries = store.list_active()
    if not active_entries:
        return {
            "audit_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_active": 0,
            "sampled_count": 0,
            "results": [],
            "all_healthy": True,
            "summary": "No active registry entries to audit.",
        }

    # Sample at least 1, or by ratio
    k = max(1, math.ceil(len(active_entries) * sample_ratio))
    sampled: List[ApprovedRegistryEntry] = random.sample(active_entries, min(k, len(active_entries)))

    results: List[Dict[str, Any]] = []
    issues_found: List[str] = []

    for entry in sampled:
        ver = store.verify_entry(entry.entry_id)
        has_owner = bool(entry.service_owner and entry.security_owner)
        has_kill_switch = bool(entry.kill_switch_ref)
        has_rollback = bool(entry.rollback_runbook_ref)
        attestation_valid = ver.get("all_valid", False)

        entry_issues: List[str] = []
        if not attestation_valid:
            entry_issues.append("Attestation signature validation failed")
        if not has_owner:
            entry_issues.append("Missing service or security owner in responsibility matrix")
        if not has_kill_switch:
            entry_issues.append("Missing kill_switch_ref")
        if not has_rollback:
            entry_issues.append("Missing rollback_runbook_ref")

        if entry_issues:
            issues_found.extend([f"[{entry.entry_id}] {iss}" for iss in entry_issues])

        results.append({
            "entry_id": entry.entry_id,
            "model_id": entry.model_id,
            "runtime_profile": entry.runtime_profile,
            "service_owner": entry.service_owner,
            "security_owner": entry.security_owner,
            "attestation_valid": attestation_valid,
            "has_kill_switch": has_kill_switch,
            "has_rollback": has_rollback,
            "healthy": len(entry_issues) == 0,
            "issues": entry_issues,
        })

    all_healthy = len(issues_found) == 0
    return {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_active": len(active_entries),
        "sampled_count": len(sampled),
        "results": results,
        "issues_found": issues_found,
        "all_healthy": all_healthy,
        "summary": "All sampled entries passed integrity and governance checks." if all_healthy else f"{len(issues_found)} issues detected during sampling audit.",
    }


def main():
    store = get_registry_store()
    res = run_audit_sampling(store)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["all_healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
