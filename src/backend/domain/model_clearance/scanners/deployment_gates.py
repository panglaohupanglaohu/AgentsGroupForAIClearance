# -*- coding: utf-8 -*-
"""标准 §3 / §7 / §8 的扫描器 —— 评估对象是「部署形态」而非模型权重本身.

这些门的输入来自 DeploymentContext（申请时填报 + 平台探测），
与 G1/G2 只看制品、G3/G4 只看模型行为形成互补。
"""

from __future__ import annotations

from typing import Any, Dict

from ..models import ModelIdentity
from .base import Scanner


class _ContextScanner(Scanner):
    """带部署上下文的扫描器基类；orchestrator 在 run 前注入 context。"""

    def __init__(self, context: Dict[str, Any] | None = None) -> None:
        self.context: Dict[str, Any] = context or {}

    def ctx(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)


class ProhibitedDeploymentScanner(_ContextScanner):
    """G0 §3 —— 禁止部署形态。命中任一即硬阻断，且不受其它门结果影响。"""

    name = "prohibited-deployment-screen"
    version = "1.0.0"
    gate = "G0"
    check_ids = ["G0-PROH-01", "G0-PROH-02", "G0-PROH-03", "G0-PROH-04"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        hosting_env = str(self.ctx("hosting_environment", "lenovo_controlled"))
        region = str(self.ctx("hosting_region", "ROW")).upper()
        access_mode = str(self.ctx("access_mode", "self_hosted_weights"))
        provider_prc = bool(self.ctx("provider_hosted_in_prc", False))
        egress_prc = bool(self.ctx("data_egress_to_prc", False))

        violations = []
        # §3：禁止 PRC 托管的 AI 服务或应用
        if provider_prc:
            violations.append("prc_hosted_service")
        # §3：禁止通过 API 等远程接口访问 PRC 托管模型
        if access_mode == "remote_api" and (provider_prc or region == "PRC"):
            violations.append("prc_hosted_api_access")
        # §3：禁止将提示词/文件/输出/遥测等传输至 PRC 提供方或基础设施
        if egress_prc:
            violations.append("data_transmission_to_prc")
        # §3：禁止运行于 Lenovo 可控或已批准 ROW 第三方环境之外
        if hosting_env not in ("lenovo_controlled", "approved_third_party"):
            violations.append("uncontrolled_environment")

        return {
            "hosting_environment": hosting_env,
            "hosting_region": region,
            "access_mode": access_mode,
            "provider_hosted_in_prc": provider_prc,
            "data_egress_to_prc": egress_prc,
            "prohibited_violations": violations,
            "prohibited_clear": not violations,
            # 标准 §2：制品产地不构成禁令；产地只作风险信号
            "origin_is_signal_only": True,
        }


class DeploymentDataFlowScanner(_ContextScanner):
    """G5 §7.1 —— 部署环境与数据流边界。"""

    name = "deployment-dataflow-assurance"
    version = "1.0.0"
    gate = "G5"
    check_ids = ["G5-DEP-01", "G5-DEP-02", "G5-DEP-03", "G5-DEP-04"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        approved_infra = str(self.ctx("hosting_environment", "")) in (
            "lenovo_controlled", "approved_third_party"
        )
        return {
            "approved_infrastructure": approved_infra,
            "outbound_egress_controlled": bool(self.ctx("outbound_egress_controlled", False)),
            "workload_segregated": bool(self.ctx("workload_segregated", False)),
            "monitoring_and_audit_logging": bool(self.ctx("monitoring_and_audit_logging", False)),
            "technical_guardrails": bool(self.ctx("technical_guardrails", False)),
            "unauthorized_external_transmission": bool(self.ctx("data_egress_to_prc", False)),
        }


class ModelAuthorityScanner(_ContextScanner):
    """G6 §7.2 —— 授予模型的权限须与用途和风险相称。"""

    name = "model-authority-tool-access"
    version = "1.0.0"
    gate = "G6"
    check_ids = ["G6-AUTH-01", "G6-AUTH-02", "G6-AUTH-03", "G6-AUTH-04"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        return {
            "tool_access_allowlisted": bool(self.ctx("tool_access_allowlisted", False)),
            "least_privilege_enforced": bool(self.ctx("least_privilege_enforced", False)),
            "autonomous_actions_restricted": bool(self.ctx("autonomous_actions_restricted", False)),
            "human_approval_for_consequential": bool(self.ctx("human_approval_for_consequential", False)),
            "generated_code_treated_untrusted": bool(self.ctx("generated_code_treated_untrusted", False)),
        }


class UseCaseLegalScanner(_ContextScanner):
    """G7 §7.3 —— 用例、数据与法务；并把许可证证据并入本门。"""

    name = "usecase-data-legal"
    version = "1.0.0"
    gate = "G7"
    check_ids = ["G7-USE-01", "G7-USE-02", "G7-USE-03", "G7-USE-04"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        use_tier = str(self.ctx("permitted_use", "internal_row"))
        needs_extra = use_tier in ("customer_facing", "high_risk")
        extra_done = bool(self.ctx("additional_assessment_complete", False))
        return {
            "intended_use_documented": bool(str(self.ctx("intended_use", "")).strip()),
            "prohibited_uses_documented": bool(self.ctx("prohibited_uses_documented", False)),
            "privacy_assessed": bool(self.ctx("privacy_assessed", False)),
            "ip_licensing_reviewed": bool(self.ctx("ip_licensing_reviewed", False)),
            "human_oversight_defined": bool(self.ctx("human_oversight_defined", False)),
            "permitted_use": use_tier,
            "requires_additional_assessment": needs_extra,
            # §10.2/§10.3：面向客户与高风险用途，基线保障之外必须另做产品/用例评估
            "additional_assessment_satisfied": (not needs_extra) or extra_done,
        }


class ContinuousAssuranceScanner(_ContextScanner):
    """G8 §8 —— 全生命周期的运营与安全控制就绪度。"""

    name = "continuous-assurance-readiness"
    version = "1.0.0"
    gate = "G8"
    check_ids = ["G8-OPS-01", "G8-OPS-02", "G8-OPS-03", "G8-OPS-04"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        controls = {
            "monitoring_in_place": bool(self.ctx("monitoring_in_place", False)),
            "vulnerability_management": bool(self.ctx("vulnerability_management", False)),
            "incident_response_defined": bool(self.ctx("incident_response_defined", False)),
            "rollback_capability": bool(self.ctx("rollback_capability", False)),
            "suspension_revocation_capable": bool(self.ctx("suspension_revocation_capable", False)),
            "alternative_model_path": bool(self.ctx("alternative_model_path", False)),
        }
        owner = str(self.ctx("named_owner", "")).strip()
        satisfied = sum(1 for v in controls.values() if v)
        return {
            **controls,
            "named_owner_assigned": bool(owner),
            "named_owner": owner,
            "controls_satisfied": satisfied,
            "controls_total": len(controls),
            "operational_supportability": bool(owner) and satisfied == len(controls),
        }
