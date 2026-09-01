# -*- coding: utf-8 -*-
"""Lenovo Open-Weight Model Assurance Standard v0.1 — 门禁与用途的单一事实源.

门禁编号直接对应标准章节，避免代码与标准各说各话：
    G0 §3   禁止部署筛查（硬红线，命中即 Not Approved）
    G1 §6.1 模型制品与溯源
    G2 §6.2 软件供应链
    G3 §6.3 安全、安全性与行为评估
    G4 §6.4 威胁情报与红队
    G5 §7.1 部署与数据流
    G6 §7.2 模型权限与工具访问
    G7 §7.3 用例、数据与法务
    G8 §8   持续保障与安全运营就绪度

标准 §5：来源、训练数据不确定性、偏见、地缘政治为「须在重大时考虑」的因素，
不是独立放行/拒绝依据 —— 因此 origin 只进风险信号，不进 blocker。
"""

from __future__ import annotations

from typing import Any, Dict, List

STANDARD_NAME = "Lenovo Open-Weight Model Assurance Standard"
STANDARD_VERSION = "0.1"

# ── 门禁定义（顺序即执行顺序）──
GATE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "gate": "G0",
        "section": "3",
        "name": "禁止部署筛查",
        "name_en": "Prohibited Deployment Screening",
        "owner_role": "基础设施架构师",
        "agent_id": "mc_infra",
        "hard_block": True,
        "summary": "标准 §3 列举的禁止部署形态，命中即不可通过，且不受其它门禁结果影响。",
    },
    {
        "gate": "G1",
        "section": "6.1",
        "name": "模型制品与溯源",
        "name_en": "Model Artifact and Provenance",
        "owner_role": "供应链与制品完整性工程师",
        "agent_id": "mc_supply",
        "hard_block": False,
        "summary": "制品必须可识别、可追溯、可独立验证：来源血缘、版本与哈希、许可条款、完整性与真实性、训练数据透明度。",
    },
    {
        "gate": "G2",
        "section": "6.2",
        "name": "软件供应链",
        "name_en": "Software Supply Chain",
        "owner_role": "供应链与制品完整性工程师",
        "agent_id": "mc_supply",
        "hard_block": False,
        "summary": "依赖与组件(AI-BOM)、安全序列化、扫描、受控仓库、版本锁定、更新与回滚路径、出口管制与贸易限制。",
    },
    {
        "gate": "G3",
        "section": "6.3",
        "name": "安全、安全性与行为评估",
        "name_en": "Security, Safety and Behaviour Evaluation",
        "owner_role": "AI模型安全审核人",
        "agent_id": "mc_security",
        "hard_block": False,
        "summary": "网络安全行为、提示注入与数据外泄、不安全代码生成、越狱易感性、隐私泄露、能力与可靠性、偏见。",
    },
    {
        "gate": "G4",
        "section": "6.4",
        "name": "威胁情报与红队",
        "name_en": "Threat Intelligence and Red-Teaming",
        "owner_role": "红队与威胁情报分析师",
        "agent_id": "mc_redteam",
        "hard_block": False,
        "summary": "已知漏洞与攻击手法、制品/供应链专项威胁情报、对抗与红队测试、发现项定级与处置。",
    },
    {
        "gate": "G5",
        "section": "7.1",
        "name": "部署与数据流",
        "name_en": "Deployment and Data Flows",
        "owner_role": "基础设施架构师",
        "agent_id": "mc_infra",
        "hard_block": False,
        "summary": "须运行于 Lenovo 可控或已批准基础设施；网络出口、数据流、遥测、工作负载隔离、访问控制、监控审计与护栏。",
    },
    {
        "gate": "G6",
        "section": "7.2",
        "name": "模型权限与工具访问",
        "name_en": "Model Authority and Tool Access",
        "owner_role": "AI模型安全审核人",
        "agent_id": "mc_security",
        "hard_block": False,
        "summary": "工具与系统访问须显式批准并允许清单化；最小权限；自主/后果性动作受限并需人工批准；模型生成代码按不可信处理。",
    },
    {
        "gate": "G7",
        "section": "7.3",
        "name": "用例、数据与法务",
        "name_en": "Use-Case, Data and Legal",
        "owner_role": "AI模型法务审核人",
        "agent_id": "mc_legal",
        "hard_block": False,
        "summary": "预期与禁止用途、隐私与保密、知识产权与许可、法律法规、尽职调查、客户与合同要求、人工监督。",
    },
    {
        "gate": "G8",
        "section": "8",
        "name": "持续保障与安全运营就绪度",
        "name_en": "Continuous Assurance and Security Operations",
        "owner_role": "持续保障与运营负责人",
        "agent_id": "mc_operations",
        "hard_block": False,
        "summary": "监控检测、配置加固、漏洞管理、日志审计、依赖维护、事件响应、变更再评估、暂停吊销、模型可替换性、运营可支持性。",
    },
]

GATE_ORDER: List[str] = [g["gate"] for g in GATE_DEFINITIONS]
GATE_BY_ID: Dict[str, Dict[str, Any]] = {g["gate"]: g for g in GATE_DEFINITIONS}
HARD_BLOCK_GATES = {g["gate"] for g in GATE_DEFINITIONS if g["hard_block"]}

# 门禁 → 前端流水线站点（engine-reducer 的 phase 词表）
GATE_PHASE: Dict[str, str] = {
    "G0": "context",
    "G1": "context",
    "G2": "analysis",
    "G3": "analysis",
    "G4": "planning",
    "G5": "planning",
    "G6": "risk",
    "G7": "risk",
    "G8": "portfolio",
}

# ── §9 保障结论 ──
OUTCOME_APPROVED = "approved"
OUTCOME_APPROVED_COND = "approved_with_conditions"
OUTCOME_RESTRICTED = "restricted"
OUTCOME_NOT_APPROVED = "not_approved"

ASSURANCE_OUTCOMES: List[Dict[str, str]] = [
    {"value": OUTCOME_APPROVED, "label": "Approved", "label_zh": "批准"},
    {"value": OUTCOME_APPROVED_COND, "label": "Approved with Conditions", "label_zh": "有条件批准"},
    {"value": OUTCOME_RESTRICTED, "label": "Restricted", "label_zh": "受限"},
    {"value": OUTCOME_NOT_APPROVED, "label": "Not Approved", "label_zh": "不批准"},
]

# ── §10 许可用途分级 ──
USE_INTERNAL_ROW = "internal_row"
USE_CUSTOMER_FACING = "customer_facing"
USE_HIGH_RISK = "high_risk"

PERMITTED_USE_TIERS: List[Dict[str, Any]] = [
    {
        "value": USE_INTERNAL_ROW,
        "section": "10.1",
        "label_zh": "内部 ROW 使用",
        "requires_additional_assessment": False,
        "additional_criteria": [],
        "note": "满足 §6/§7/§8 即可使用，无需单独的模型批准；须遵守记录在册的条件与限制。",
    },
    {
        "value": USE_CUSTOMER_FACING,
        "section": "10.2",
        "label_zh": "面向客户使用",
        "requires_additional_assessment": True,
        "additional_criteria": [
            "customer_acceptance",
            "contractual_commitments",
            "customer_sector",
            "geography",
            "regulatory_procurement_restrictions",
            "disclosure_transparency",
            "product_security_testing",
            "supportability",
            "alternative_model_migration_path",
        ],
        "note": "基线保障之外还需独立的产品与用例评估；不得仅凭列入目录推定已批准。",
    },
    {
        "value": USE_HIGH_RISK,
        "section": "10.3",
        "label_zh": "高风险/敏感应用",
        "requires_additional_assessment": True,
        "additional_criteria": [
            "usecase_nature_impact",
            "data_sensitivity_classification",
            "critical_system_access",
            "model_autonomy_authority",
            "consequences_of_unsafe_behaviour",
            "legal_regulatory_sector_requirements",
            "security_privacy_geopolitical",
            "human_oversight_controls",
            "enhanced_red_team_testing",
            "monitoring_incident_escalation",
            "fallback_disablement_path",
        ],
        "note": "政府、国防、关键基础设施、高敏数据、后果性决策或特权访问等场景，需强化风险与用例评估。",
    },
]

PERMITTED_USE_BY_VALUE = {t["value"]: t for t in PERMITTED_USE_TIERS}

# ── §11 治理角色 ──
GOVERNANCE_ROLES: List[Dict[str, str]] = [
    {"role": "evaluate", "label_zh": "评估", "desc": "指定的技术、安全、安全性、隐私、法务等职能依本标准评估模型。"},
    {"role": "approve", "label_zh": "批准", "desc": "指定的 AI 治理机构批准准入及其适用条件与限制。"},
    {"role": "own", "label_zh": "归属", "desc": "具名的业务或技术负责人对模型的已批准部署与使用负责。"},
    {"role": "monitor", "label_zh": "监控", "desc": "模型负责人与控制职能监控性能、事件、威胁与条件遵从。"},
    {"role": "revoke", "label_zh": "吊销", "desc": "治理机构可在保障要求不再满足时限制、暂停或移除模型。"},
]


def gate_catalog() -> List[Dict[str, Any]]:
    """供前端渲染流水线的门禁目录（含章节号，便于对照标准）。"""
    return [dict(g, phase=GATE_PHASE.get(g["gate"], "context")) for g in GATE_DEFINITIONS]
