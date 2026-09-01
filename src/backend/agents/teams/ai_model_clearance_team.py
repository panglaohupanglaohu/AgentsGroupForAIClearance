# -*- coding: utf-8 -*-
"""AI 模型准入团队 — Lenovo Open-Weight Model Assurance Standard v0.1 的执行载体.

角色划分严格对齐标准的评估域，而不是按职能部门拍脑袋切：
  §6.1/§6.2 制品与供应链  → 供应链与制品完整性工程师
  §6.3 安全/安全性/行为评估 → AI 模型安全审核人
  §6.4 威胁情报与红队      → 红队与威胁情报分析师
  §7.1 部署与数据流        → 基础设施架构师（承接 §3 禁止部署红线）
  §7.2 模型权限与工具访问   → 基础设施架构师 + 安全审核人共管
  §7.3 用例、数据与法务    → AI 模型法务审核人
  §8   持续保障与安全运营   → 持续保障与运营负责人
  §9   证据与裁决记录      → AI 模型准入标准撰写人
  §11  Evaluate/Approve/Own/Monitor/Revoke → 主理人(Approve) + 运营负责人(Own/Monitor/Revoke)

用户指定 5 个角色，另 3 个（供应链完整性、红队威胁情报、持续保障运营）是按标准补齐的：
标准把这三块单列为独立章节且要求独立证据，缺人认领就会出现「无人负责的门」。
"""

from typing import Dict, List

from ..models import (
    AccessLevel,
    AgentChannelConfig,
    AgentPermission,
    AgentPersonality,
    AgentProfile,
    AgentTeam,
    AgentTemplateType,
    ModelConfig,
    Visibility,
)

TEAM_ID = "ai-model-clearance"
CHANNEL = "model_clearance_bus"
OWNER_ID = "mc_owner"  # §11 唯一有权 approve 的角色，拓扑中心

# (role, agent_id, governance_role, sections, tools, skills, expertise)
CLEARANCE_ROLES = [
    (
        "AI模型准入主理人", "mc_owner", "approve",
        ["§9", "§10", "§11", "§12"],
        ["delegate_task", "read_file", "search_files"],
        ["clearance_intake_triage", "assurance_decision_adjudication", "permitted_use_scoping"],
        ["governance", "program_management", "risk_acceptance"],
    ),
    (
        "基础设施架构师", "mc_infra", "evaluate",
        ["§7.1", "§7.2", "§3"],
        ["run_shell", "read_file", "search_files"],
        ["deployment_dataflow_assurance", "prohibited_deployment_screening", "model_authority_least_privilege"],
        ["infrastructure", "network_egress", "deployment_architecture"],
    ),
    (
        "AI模型安全审核人", "mc_security", "evaluate",
        ["§6.3", "§7.2"],
        ["run_python", "run_shell", "read_file"],
        ["model_behaviour_security_eval", "prompt_injection_exfiltration_test", "insecure_code_generation_review"],
        ["ai_security", "adversarial_testing", "privacy_leakage"],
    ),
    (
        "AI模型法务审核人", "mc_legal", "evaluate",
        ["§7.3", "§6.2"],
        ["read_file", "search_files"],
        ["license_redistribution_review", "export_control_sanctions_check", "usecase_regulatory_assessment"],
        ["licensing", "export_control", "privacy_law"],
    ),
    (
        "AI模型准入标准撰写人", "mc_standard", "evaluate",
        ["§9", "§13"],
        ["read_file", "write_file", "search_files"],
        ["assurance_record_authoring", "residual_risk_documentation", "standard_maintenance_review"],
        ["technical_writing", "standards", "audit_evidence"],
    ),
    (
        "供应链与制品完整性工程师", "mc_supply", "evaluate",
        ["§6.1", "§6.2"],
        ["run_shell", "run_python", "read_file"],
        ["artifact_provenance_verification", "aibom_dependency_scanning", "secure_serialization_check"],
        ["supply_chain", "sbom", "cryptographic_verification"],
    ),
    (
        "红队与威胁情报分析师", "mc_redteam", "evaluate",
        ["§6.4"],
        ["run_python", "run_shell", "search_files"],
        ["threat_intelligence_review", "adversarial_red_team_campaign", "jailbreak_susceptibility_probe"],
        ["red_teaming", "threat_intelligence", "vulnerability_research"],
    ),
    (
        "持续保障与运营负责人", "mc_operations", "own_monitor_revoke",
        ["§8", "§11"],
        ["run_shell", "set_alarm", "watch_file"],
        ["continuous_assurance_monitoring", "incident_response_escalation", "suspension_revocation_control", "model_optionality_fallback"],
        ["security_operations", "incident_response", "lifecycle_management"],
    ),
]


def _model_default() -> ModelConfig:
    return ModelConfig(
        model_id="clearance-primary",
        provider="deepseek",
        name="deepseek-v4-pro",
        max_tokens=8192,
        temperature=0.2,
        is_default=True,
        api_base_url="https://api.deepseek.com",
    )


def _build_agent(
    agent_id: str,
    role: str,
    governance_role: str,
    sections: list,
    tools: list,
    skills: list,
    expertise: list,
) -> AgentProfile:
    sec = "、".join(sections)
    return AgentProfile(
        agent_id=agent_id,
        name=role,
        role=role,
        description=f"AI 模型准入团队 · {role}（负责标准 {sec}）",
        template_type=AgentTemplateType.CUSTOM,
        model_id="clearance-primary",
        system_prompt=(
            f"你是 Lenovo AI 模型准入团队的{role}，依据《Open-Weight Model Assurance Standard》"
            f"负责 {sec} 的评估。\n"
            "铁律：\n"
            "1. 结论必须基于可独立验证的证据，不得仅凭模型提供方的声明。\n"
            "2. 评估针对具体模型制品与版本，不等同于批准该提供方或其托管服务。\n"
            "3. 模型来源/产地只作为风险信号；判定必须落到可管可证的技术与运营控制项。\n"
            "4. 无法完全控制或独立验证的残余风险必须显式记录，不得隐去。\n"
            "5. 证据不足时输出 needs_info 并列出缺失项，禁止臆断放行。\n"
            "请用中文输出，结论需给出：判定、依据证据、残余风险、建议条件。\n"
        ),
        personality=AgentPersonality(
            tone="professional",
            language="zh-CN",
            expertise_areas=list(expertise),
            response_style="technical",
            creativity=0.2,
        ),
        permissions=[
            AgentPermission(
                resource="model_clearance",
                access_level=AccessLevel.WRITE if governance_role == "approve" else AccessLevel.READ,
                channels=[CHANNEL],
            ),
        ],
        channels=[AgentChannelConfig(channel_name=CHANNEL, subscribe=True, publish=True)],
        tools=list(tools),
        skills=list(skills),
        metadata={
            "team_type": "ai_model_clearance",
            "role": role,
            "governance_role": governance_role,
            "standard_sections": list(sections),
        },
    )


def _owner_led_full_mesh(agent_ids: List[str], owner_id: str) -> List[Dict[str, str]]:
    """主理人主导的全连接拓扑。

    主理人→每位评审人为有向派工与回收裁决（§9/§11 approve）；
    其余成员两两互连，保证任两道门禁的发现项能直接交叉会签，不必经主理人中转。
    """
    peers = [aid for aid in agent_ids if aid != owner_id]
    links = [{"source": owner_id, "target": p, "label": "派工/裁决"} for p in peers]
    links += [
        {"source": a, "target": b, "label": "交叉会签"}
        for i, a in enumerate(peers)
        for b in peers[i + 1:]
    ]
    return links


def create_ai_model_clearance_team() -> AgentTeam:
    """创建 AI 模型准入团队（8 角色，覆盖标准 §3/§6/§7/§8/§9/§10/§11）."""
    team = AgentTeam(
        team_id=TEAM_ID,
        name="AI 模型准入团队",
        description=(
            "依据 Lenovo Open-Weight Model Assurance Standard 组建的 8 角色准入评审团队："
            "主理人裁决、基础设施架构师把部署与数据流红线、安全审核人评估模型行为风险、"
            "法务审核人管许可与出口管制、标准撰写人产出保障记录、"
            "供应链工程师验制品完整性、红队分析师做对抗测试、运营负责人守全生命周期。"
        ),
        visibility=Visibility.INTERNAL,
        workflow_mode="custom",
        metadata={
            "team_type": "ai_model_clearance",
            "standard": "Lenovo Open-Weight Model Assurance Standard v0.1",
            "governance_roles": ["evaluate", "approve", "own", "monitor", "revoke"],
        },
    )
    team.add_model(_model_default())
    for role, aid, gov, sections, tools, skills, expertise in CLEARANCE_ROLES:
        team.add_agent(_build_agent(aid, role, gov, sections, tools, skills, expertise))
    team.metadata["custom_topology"] = _owner_led_full_mesh(list(team.agents), OWNER_ID)
    return team
