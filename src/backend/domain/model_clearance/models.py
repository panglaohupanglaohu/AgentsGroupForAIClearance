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
    gate: str  # G0..G8
    check_id: str  # e.g. G1-PROV-03
    collector: str
    collector_version: str
    collected_at: str
    payload: Dict[str, Any]
    digest: str = ""
    # 参考情报（智能体团队采集/分析）只作风险信号，不得进入门禁规则求值。
    advisory: bool = False

    def __post_init__(self) -> None:
        if not self.digest:
            self.digest = sha256_of(canonical_json(self.payload))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Evidence:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EvidenceContribution:
    """控制台上组装到某道门禁的外部情报来源。

    只存引用，不存内容；真实载荷由后端在跑门禁时自行解析，避免前端伪造证据。
    """

    gate: str
    kind: str  # team | source | document
    ref_id: str
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceContribution:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BlockerAdvisory:
    """阻断项的 LLM 说明性分析。三个文本字段均不参与任何判定。"""

    gate: str
    check_id: str
    result: str  # pass | fail
    analysis: str = ""
    recommendation: str = ""
    risk_if_ignored: str = ""
    generated_by: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    advisor_version: str = ""
    error: str = ""
    advisory: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BlockerAdvisory:
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
class DeploymentContext:
    """标准 §7/§8/§10 的评估输入 —— 没有它 §7.1/§7.2/§7.3/§8 的门就无从判定。

    默认值刻意取「最保守但可通过」的内部 ROW 形态，使既有申请数据仍可加载。
    """

    # §7.1 部署与数据流
    hosting_environment: str = "lenovo_controlled"   # lenovo_controlled | approved_third_party | external
    hosting_region: str = "ROW"                      # ROW | PRC | other
    access_mode: str = "self_hosted_weights"         # self_hosted_weights | remote_api
    provider_hosted_in_prc: bool = False
    data_egress_to_prc: bool = False
    outbound_egress_controlled: bool = True
    workload_segregated: bool = True
    monitoring_and_audit_logging: bool = True
    technical_guardrails: bool = True

    # §7.2 模型权限与工具访问
    tool_access_allowlisted: bool = True
    least_privilege_enforced: bool = True
    autonomous_actions_restricted: bool = True
    human_approval_for_consequential: bool = True
    generated_code_treated_untrusted: bool = True

    # §7.3 用例、数据与法务
    intended_use: str = ""
    prohibited_uses_documented: bool = True
    privacy_assessed: bool = True
    ip_licensing_reviewed: bool = True
    human_oversight_defined: bool = True

    # §8 持续保障就绪度
    monitoring_in_place: bool = True
    vulnerability_management: bool = True
    incident_response_defined: bool = True
    rollback_capability: bool = True
    suspension_revocation_capable: bool = True
    alternative_model_path: bool = True
    named_owner: str = ""

    # §10 申请的许可用途
    permitted_use: str = "internal_row"              # internal_row | customer_facing | high_risk
    additional_assessment_complete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def unknown(cls) -> DeploymentContext:
        """No deployment was proposed; keep every workflow fact explicitly unknown."""
        return cls(
            hosting_environment="",
            hosting_region="",
            access_mode="",
            provider_hosted_in_prc=False,
            data_egress_to_prc=False,
            outbound_egress_controlled=False,
            workload_segregated=False,
            monitoring_and_audit_logging=False,
            technical_guardrails=False,
            tool_access_allowlisted=False,
            least_privilege_enforced=False,
            autonomous_actions_restricted=False,
            human_approval_for_consequential=False,
            generated_code_treated_untrusted=False,
            intended_use="",
            prohibited_uses_documented=False,
            privacy_assessed=False,
            ip_licensing_reviewed=False,
            human_oversight_defined=False,
            monitoring_in_place=False,
            vulnerability_management=False,
            incident_response_defined=False,
            rollback_capability=False,
            suspension_revocation_capable=False,
            alternative_model_path=False,
            named_owner="",
            permitted_use="",
            additional_assessment_complete=False,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeploymentContext:
        if not isinstance(data, dict):
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ModelApplication:
    application_id: str
    applicant: str
    identity: ModelIdentity
    review_scope: str = "full"
    custody_chain: List[CustodyStep] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    verdicts: List[GateVerdict] = field(default_factory=list)
    opinions: List[ReviewOpinion] = field(default_factory=list)
    deployment: DeploymentContext = field(default_factory=DeploymentContext)
    contributions: List[EvidenceContribution] = field(default_factory=list)
    blocker_advisories: List[BlockerAdvisory] = field(default_factory=list)
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
            "review_scope": self.review_scope,
            "identity": self.identity.to_dict(),
            "custody_chain": [c.to_dict() for c in self.custody_chain],
            "evidence": [e.to_dict() for e in self.evidence],
            "verdicts": [v.to_dict() for v in self.verdicts],
            "opinions": [o.to_dict() for o in self.opinions],
            "deployment": self.deployment.to_dict(),
            "contributions": [c.to_dict() for c in self.contributions],
            "blocker_advisories": [a.to_dict() for a in self.blocker_advisories],
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
            review_scope=data.get("review_scope", "full"),
            custody_chain=[CustodyStep.from_dict(c) for c in data.get("custody_chain", [])],
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            verdicts=[GateVerdict.from_dict(v) for v in data.get("verdicts", [])],
            opinions=[ReviewOpinion.from_dict(o) for o in data.get("opinions", [])],
            deployment=DeploymentContext.from_dict(data.get("deployment") or {}),
            contributions=[
                EvidenceContribution.from_dict(c) for c in data.get("contributions", [])
            ],
            blocker_advisories=[
                BlockerAdvisory.from_dict(a) for a in data.get("blocker_advisories", [])
            ],
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
