# -*- coding: utf-8 -*-
"""T103 / T105 / T107 — Data models & state machine for Model Admission Clearance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_of(text: str | bytes) -> str:
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


class AppStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    GATING = "gating"
    NEED_INFO = "need_info"
    ADJUDICATING = "adjudicating"
    APPROVED = "approved"
    APPROVED_COND = "approved_with_conditions"
    REJECTED = "rejected"
    REGISTERED = "registered"
    REASSESSING = "reassessing"
    REVOKED = "revoked"


class ImmutableViolation(Exception):
    """Raised when an immutable entity or append-only field is modified."""
    pass


class IllegalTransition(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    AppStatus.DRAFT.value: {AppStatus.SUBMITTED.value},
    AppStatus.SUBMITTED.value: {AppStatus.GATING.value},
    AppStatus.GATING.value: {
        AppStatus.REJECTED.value,
        AppStatus.NEED_INFO.value,
        AppStatus.ADJUDICATING.value,
    },
    AppStatus.NEED_INFO.value: {
        AppStatus.SUBMITTED.value,
        AppStatus.REJECTED.value,
    },
    AppStatus.ADJUDICATING.value: {
        AppStatus.APPROVED.value,
        AppStatus.APPROVED_COND.value,
        AppStatus.REJECTED.value,
    },
    AppStatus.APPROVED.value: {AppStatus.REGISTERED.value},
    AppStatus.APPROVED_COND.value: {AppStatus.REGISTERED.value},
    AppStatus.REGISTERED.value: {AppStatus.REASSESSING.value},
    AppStatus.REASSESSING.value: {
        AppStatus.REGISTERED.value,
        AppStatus.REVOKED.value,
    },
    AppStatus.REJECTED.value: set(),  # Terminal state
    AppStatus.REVOKED.value: set(),   # Terminal state
}


@dataclass
class ModelIdentity:
    model_id: str
    revision: str = "main"
    root_digest: str = ""
    weights_uri: str = ""
    local_path: str = ""
    expected_signer_identity: Optional[str] = None
    expected_oidc_issuer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelIdentity:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CustodyStep:
    step_type: str  # origin | finetune | quantize | merge
    input_digest: str
    output_digest: str
    performed_by: str
    performed_at: str
    signature_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustodyStep:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Evidence:  # Immutable, append-only
    evidence_id: str
    gate: str  # G1..G5
    check_id: str  # e.g. G1-PROV-03
    collector: str
    collector_version: str
    collected_at: str
    payload: Dict[str, Any]
    digest: str = ""

    def __post_init__(self) -> None:
        if not self.digest:
            self.digest = sha256_of(canonical_json(self.payload))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Evidence:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class GateVerdict:
    gate: str
    verdict: str  # pass | fail | needs_info
    severity: str  # blocker | major | minor | none
    failed_checks: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    decided_by: str = "policy"  # policy | agent | human
    decided_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GateVerdict:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ReviewOpinion:
    gate: str
    reviewer: str
    verdict_suggestion: str  # pass | needs_info | tighten
    risk_level: str  # low | medium | high
    findings: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    recommended_conditions: List[str] = field(default_factory=list)
    tightens_verdict: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReviewOpinion:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ModelApplication:
    application_id: str
    applicant: str
    identity: ModelIdentity
    custody_chain: List[CustodyStep] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    verdicts: List[GateVerdict] = field(default_factory=list)
    opinions: List[ReviewOpinion] = field(default_factory=list)
    status: AppStatus = AppStatus.DRAFT
    need_info_count: int = 0  # Max 3
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def transition_to(self, target: AppStatus | str) -> None:
        target_val = target.value if isinstance(target, AppStatus) else str(target)
        curr_val = self.status.value if isinstance(self.status, AppStatus) else str(self.status)

        if target_val not in ALLOWED_TRANSITIONS.get(curr_val, set()):
            raise IllegalTransition(f"Transition from {curr_val} -> {target_val} is not permitted.")

        # If resubmitting from need_info and need_info_count > 3, auto reject
        if target_val == AppStatus.SUBMITTED.value and self.need_info_count > 3:
            self.status = AppStatus.REJECTED
            self.updated_at = utc_now_iso()
            return

        self.status = AppStatus(target_val)
        self.updated_at = utc_now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_id": self.application_id,
            "applicant": self.applicant,
            "identity": self.identity.to_dict(),
            "custody_chain": [c.to_dict() for c in self.custody_chain],
            "evidence": [e.to_dict() for e in self.evidence],
            "verdicts": [v.to_dict() for v in self.verdicts],
            "opinions": [o.to_dict() for o in self.opinions],
            "status": self.status.value if isinstance(self.status, AppStatus) else self.status,
            "need_info_count": self.need_info_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelApplication:
        raw_status = data.get("status", "draft")
        try:
            status_enum = AppStatus(raw_status)
        except ValueError:
            status_enum = AppStatus.DRAFT

        identity_data = data.get("identity") or {}
        if isinstance(identity_data, dict):
            ident = ModelIdentity.from_dict(identity_data)
        else:
            ident = ModelIdentity(model_id=str(identity_data))

        return cls(
            application_id=data.get("application_id", ""),
            applicant=data.get("applicant", ""),
            identity=ident,
            custody_chain=[CustodyStep.from_dict(c) for c in data.get("custody_chain", [])],
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            verdicts=[GateVerdict.from_dict(v) for v in data.get("verdicts", [])],
            opinions=[ReviewOpinion.from_dict(o) for o in data.get("opinions", [])],
            status=status_enum,
            need_info_count=int(data.get("need_info_count", 0)),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
        )


@dataclass
class GpuPool:
    card_model: str
    memory_gb: float
    count_total: int
    count_free: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GpuPool:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ClusterCapability:
    generated_at: str
    ttl_seconds: int = 86400  # 24 hours
    gpu_pools: List[GpuPool] = field(default_factory=list)
    max_single_node_gpus: int = 8
    supports_multi_node_serving: bool = True

    def is_stale(self) -> bool:
        try:
            gen_dt = datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - gen_dt
            return delta.total_seconds() > self.ttl_seconds
        except Exception:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "ttl_seconds": self.ttl_seconds,
            "gpu_pools": [g.to_dict() for g in self.gpu_pools],
            "max_single_node_gpus": self.max_single_node_gpus,
            "supports_multi_node_serving": self.supports_multi_node_serving,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClusterCapability:
        return cls(
            generated_at=data.get("generated_at", utc_now_iso()),
            ttl_seconds=int(data.get("ttl_seconds", 86400)),
            gpu_pools=[GpuPool.from_dict(g) for g in data.get("gpu_pools", [])],
            max_single_node_gpus=int(data.get("max_single_node_gpus", 8)),
            supports_multi_node_serving=bool(data.get("supports_multi_node_serving", True)),
        )
