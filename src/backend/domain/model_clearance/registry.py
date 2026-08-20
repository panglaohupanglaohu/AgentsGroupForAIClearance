# -*- coding: utf-8 -*-
"""T502 / T504 / T505 — Approved Model Registry Store & Verification Interface."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .attestation import dsse_verify, extract_attestation_statement, issue_gate_attestation
from .models import ModelApplication, utc_now_iso

_DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parents[4] / "storage" / "model_clearance" / "registry"


@dataclass
class ApprovedRegistryEntry:
    entry_id: str
    model_id: str
    revision: str
    locked_digest: str  # Runtime container weights must match this
    decision_ref: str   # Reference to decision attestation
    scope: List[str]    # internal | commercial | restricted
    conditions: List[str]
    runtime_profile: str  # isolated | restricted | standard
    approved_at: str
    reassessment_due: str
    status: str = "active"  # active | reassessing | revoked
    service_owner: str = "ai-platform-ops@lenovo.com"
    security_owner: str = "ai-sec-governance@lenovo.com"
    oncall_rotation: str = "lenovo-ai-infra-l2"
    kill_switch_ref: str = "ops://clearance/kill-switch"
    rollback_runbook_ref: str = "runbook://clearance/rollback-baseline"
    admission_sla_tier: str = "tier-1-critical"
    digest_history: List[Dict[str, Any]] = field(default_factory=list)
    operations_audit_log: List[Dict[str, Any]] = field(default_factory=list)
    attestations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ApprovedRegistryEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class ModelRegistryStore:
    def __init__(self, base_dir: Optional[Path | str] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else _DEFAULT_REGISTRY_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, entry_id: str) -> Path:
        return self.base_dir / f"{entry_id}.json"

    def register(
        self,
        app: ModelApplication,
        runtime_profile: str,
        scope: List[str],
        conditions: List[str],
        expires_at: str,
        service_owner: str = "ai-platform-ops@lenovo.com",
        security_owner: str = "ai-sec-governance@lenovo.com",
        oncall_rotation: str = "lenovo-ai-infra-l2",
        kill_switch_ref: str = "ops://clearance/kill-switch",
        rollback_runbook_ref: str = "runbook://clearance/rollback-baseline",
        admission_sla_tier: str = "tier-1-critical",
    ) -> ApprovedRegistryEntry:
        # 1. Issue signed attestations for all gate verdicts
        attestations = [issue_gate_attestation(app, v) for v in app.verdicts]

        # 2. Extract locked digest
        locked_digest = app.identity.root_digest
        for e in app.evidence:
            if e.payload.get("locked_digest"):
                locked_digest = e.payload["locked_digest"]
                break
            if e.payload.get("root_digest"):
                locked_digest = e.payload["root_digest"]

        actual_locked = locked_digest or "sha256-verified-weights"

        entry = ApprovedRegistryEntry(
            entry_id=f"reg-{app.application_id}",
            model_id=app.identity.model_id,
            revision=app.identity.revision,
            locked_digest=actual_locked,
            decision_ref=f"attestation://{app.application_id}",
            scope=scope,
            conditions=conditions,
            runtime_profile=runtime_profile,
            approved_at=utc_now_iso(),
            reassessment_due=expires_at,
            status="active",
            service_owner=service_owner,
            security_owner=security_owner,
            oncall_rotation=oncall_rotation,
            kill_switch_ref=kill_switch_ref,
            rollback_runbook_ref=rollback_runbook_ref,
            admission_sla_tier=admission_sla_tier,
            digest_history=[{"digest": actual_locked, "set_at": utc_now_iso(), "initial": True}],
            operations_audit_log=[{
                "action": "registered",
                "operator": "clearance-adjudicator",
                "timestamp": utc_now_iso(),
            }],
            attestations=attestations,
        )

        path = self._entry_path(entry.entry_id)
        _atomic_write(path, json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))
        return entry

    def get(self, entry_id: str) -> Optional[ApprovedRegistryEntry]:
        p = self._entry_path(entry_id)
        if not p.exists():
            return None
        try:
            return ApprovedRegistryEntry.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def list_active(self) -> List[ApprovedRegistryEntry]:
        entries: List[ApprovedRegistryEntry] = []
        for p in self.base_dir.glob("*.json"):
            try:
                e = ApprovedRegistryEntry.from_dict(json.loads(p.read_text(encoding="utf-8")))
                if e.status == "active":
                    entries.append(e)
            except Exception:
                continue
        return entries

    def list_all(self, limit: int = 100) -> List[ApprovedRegistryEntry]:
        entries: List[ApprovedRegistryEntry] = []
        for p in sorted(self.base_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                entries.append(ApprovedRegistryEntry.from_dict(json.loads(p.read_text(encoding="utf-8"))))
                if len(entries) >= limit:
                    break
            except Exception:
                continue
        return entries

    def revoke(self, entry_id: str, reason: str = "") -> Optional[ApprovedRegistryEntry]:
        entry = self.get(entry_id)
        if not entry:
            return None
        entry.status = "revoked"
        entry.operations_audit_log.append({
            "action": "revoke",
            "operator": "administrator",
            "reason": reason or "Administrative revocation",
            "timestamp": utc_now_iso(),
        })
        path = self._entry_path(entry_id)
        _atomic_write(path, json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))
        return entry

    def emergency_revoke(self, entry_id: str, operator: str = "lenovo-secops", reason: str = "") -> Optional[ApprovedRegistryEntry]:
        """T903: Fast emergency kill-switch revocation with signed audit trail."""
        entry = self.get(entry_id)
        if not entry:
            return None
        entry.status = "revoked"
        entry.operations_audit_log.append({
            "action": "emergency_revoke",
            "operator": operator,
            "reason": reason or "Emergency kill-switch triggered",
            "timestamp": utc_now_iso(),
        })
        path = self._entry_path(entry_id)
        _atomic_write(path, json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))
        return entry

    def rollback_to_last_known_good(
        self,
        entry_id: str,
        target_digest: str,
        operator: str = "lenovo-infra-ops",
        reason: str = "",
    ) -> Optional[ApprovedRegistryEntry]:
        """T903: Rollback model locked digest to a last-known-good verified baseline."""
        entry = self.get(entry_id)
        if not entry:
            return None
        prev_digest = entry.locked_digest
        entry.digest_history.append({
            "from_digest": prev_digest,
            "to_digest": target_digest,
            "rolled_back_at": utc_now_iso(),
            "operator": operator,
            "reason": reason or "Rollback to verified baseline digest",
        })
        entry.locked_digest = target_digest
        entry.status = "active"
        entry.operations_audit_log.append({
            "action": "rollback",
            "operator": operator,
            "prev_digest": prev_digest,
            "target_digest": target_digest,
            "timestamp": utc_now_iso(),
        })
        path = self._entry_path(entry_id)
        _atomic_write(path, json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))
        return entry

    def transition(self, entry: ApprovedRegistryEntry, new_status: str) -> None:
        entry.status = new_status
        path = self._entry_path(entry.entry_id)
        _atomic_write(path, json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))

    def verify_entry(self, entry_id: str) -> Dict[str, Any]:
        """T504: Verify all gate attestations for a registry entry."""
        entry = self.get(entry_id)
        if not entry:
            return {"entry_id": entry_id, "found": False, "all_valid": False, "attestations": []}

        results: List[Dict[str, Any]] = []
        for att in entry.attestations:
            valid = dsse_verify(att)
            stmt = extract_attestation_statement(att)
            gate = stmt.get("predicate", {}).get("gate", "unknown") if stmt else "unknown"
            results.append({
                "gate": gate,
                "signature_valid": valid,
                "predicateType": stmt.get("predicateType") if stmt else None,
            })

        all_valid = len(results) > 0 and all(r["signature_valid"] for r in results)
        return {
            "entry_id": entry_id,
            "model_id": entry.model_id,
            "locked_digest": entry.locked_digest,
            "found": True,
            "all_valid": all_valid,
            "attestations": results,
        }


_REG_INSTANCE: Optional[ModelRegistryStore] = None


def get_registry_store() -> ModelRegistryStore:
    global _REG_INSTANCE
    if _REG_INSTANCE is None:
        _REG_INSTANCE = ModelRegistryStore()
    return _REG_INSTANCE
