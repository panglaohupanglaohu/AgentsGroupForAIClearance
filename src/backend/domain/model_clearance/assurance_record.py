# -*- coding: utf-8 -*-
"""§9 保障记录 —— 把一次准入评审装配成标准要求的审核报告.

标准 §9 "Evidence and Assurance Decision" 逐条列明保障记录必须记载的内容：
评估对象与版本、已复核证据、测试方法与结果、（适当时的）对比测试、
重大发现与缓解、残余风险、条件/限制/例外、最终保障裁决。
本模块只做装配，不做判定 —— 判定仍归 policy_evaluator 与 adjudicate。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .adjudicate import adjudicate
from .models import ModelApplication, utc_now_iso
from .policy_evaluator import load_policy
from .standard import (
    GATE_BY_ID,
    GATE_ORDER,
    GOVERNANCE_ROLES,
    PERMITTED_USE_BY_VALUE,
    STANDARD_NAME,
    STANDARD_VERSION,
)

# 门禁 → 标准正文要求覆盖的评估要点（§6/§7/§8 各小节的 bullet）。
# 报告要能回答"这道门到底照着标准的哪几条在看"，否则评审人无从复核。
GATE_CRITERIA: Dict[str, List[str]] = {
    "G0": [
        "PRC 托管的 AI 服务或应用",
        "通过 API 或远程接口访问 PRC 托管模型",
        "向 PRC 提供方或基础设施传输提示词、文件、输出、遥测或运营元数据",
        "在 Lenovo 可控或已批准 ROW 第三方环境之外运行制品",
        "使用未列入已批准模型目录的模型",
    ],
    "G1": [
        "来源与血缘：来源、开发方/提供方与可得的模型血缘",
        "版本与哈希：确切版本与加密哈希",
        "溯源：模型出处与重要贡献者（可查证范围内）",
        "许可与使用条款：许可、再分发权、使用权与限制",
        "完整性与真实性：受评制品未被修改或污染",
        "训练数据透明度：数据来源与训练方法，含已知局限与重大不确定性",
    ],
    "G2": [
        "依赖与组件：AI-BOM 或等效组件记录",
        "安全序列化：已批准的模型格式与序列化方式",
        "扫描：漏洞、依赖与容器扫描",
        "受控仓库：经批准的存储与分发渠道",
        "版本锁定：模型与依赖版本受控",
        "更新路径：可控更新与快速吊销/替换/回滚能力",
        "出口管制与贸易限制：影响取得、转移、访问或使用的管制识别与处置",
    ],
    "G3": [
        "网络安全行为",
        "提示注入与数据外泄风险",
        "不安全或不可靠的代码生成",
        "越狱易感性",
        "隐私与信息泄露",
        "对拟定用例的能力、性能与可靠性充分性",
        "偏见与价值敏感行为",
        "针对预期用途识别出的其它重大风险",
    ],
    "G4": [
        "已知漏洞与攻击手法",
        "模型/制品/供应链专项威胁情报",
        "相称的对抗与红队测试",
        "发现项的记录与严重性定级",
        "已识别风险的缓解、接受或限制",
    ],
    "G5": [
        "已批准的基础设施与部署架构",
        "托管环境的可用性、主权、安全性与韧性（重大时）",
        "网络连通性与出站流量",
        "提示词、文件、输出及其它数据流",
        "遥测与运营元数据",
        "工作负载隔离",
        "访问与配置控制",
        "监控与审计日志能力",
        "与部署及已识别风险相称的技术护栏",
    ],
    "G6": [
        "工具与系统访问须显式批准并允许清单化",
        "访问遵循最小权限原则",
        "自主或后果性动作受到适当限制",
        "后果性动作须经适当的人工批准",
        "对输入、输出与动作施加确定性控制与护栏",
        "模型生成代码按不可信处理，纳入安全开发与发布控制",
    ],
    "G7": [
        "预期用途与禁止用途",
        "隐私与保密",
        "知识产权与许可",
        "法律与监管要求",
        "溯源与相关尽职调查考量",
        "客户与合同要求",
        "适当的验证与人工监督",
    ],
    "G8": [
        "监控与检测",
        "配置与加固",
        "漏洞与暴露面管理",
        "日志与可审计性",
        "软件与依赖管理",
        "事件响应",
        "变更管理与再评估",
        "威胁情报复审",
        "暂停与吊销能力",
        "模型可选性与替换路径",
        "目录维护",
        "运营可支持性",
    ],
}

_TERMINAL_DECIDED = {
    "approved", "approved_with_conditions", "rejected", "registered", "revoked",
}


def _rule_index(policy: Dict[str, Any], gate: str) -> Dict[str, Dict[str, Any]]:
    rules = policy.get("gates", {}).get(gate, {}).get("rules", [])
    return {r.get("id"): r for r in rules if r.get("id")}


def _artifact_section(app: ModelApplication) -> Dict[str, Any]:
    """§9 第 1 项：受评的模型制品与版本。"""
    ident = app.identity
    return {
        "model_id": ident.model_id,
        "revision": ident.revision,
        "root_digest": ident.root_digest,
        "weights_uri": ident.weights_uri,
        "expected_signer_identity": ident.expected_signer_identity,
        "custody_chain": [
            {
                "step_type": s.step_type,
                "input_digest": s.input_digest,
                "output_digest": s.output_digest,
                "performed_by": s.performed_by,
                "performed_at": s.performed_at,
                "signature_ref": s.signature_ref,
            }
            for s in app.custody_chain
        ],
    }


def _evidence_section(app: ModelApplication) -> Dict[str, Any]:
    """§9 第 2 项：已复核证据。裁决性证据与参考情报必须分列。"""
    decisive: List[Dict[str, Any]] = []
    advisory: List[Dict[str, Any]] = []
    for e in app.evidence:
        item = {
            "evidence_id": e.evidence_id,
            "gate": e.gate,
            "section": GATE_BY_ID.get(e.gate, {}).get("section", ""),
            "check_id": e.check_id,
            "collector": e.collector,
            "collector_version": e.collector_version,
            "collected_at": e.collected_at,
            "digest": e.digest,
            "status": (e.payload or {}).get("_status", "unknown"),
        }
        if e.advisory:
            payload = e.payload or {}
            item["label"] = payload.get("label") or payload.get("ref_id", "")
            item["kind"] = payload.get("kind", "")
            item["analysis"] = payload.get("analysis") or {}
            advisory.append(item)
        else:
            decisive.append(item)
    return {
        "decisive": decisive,
        "advisory": advisory,
        "decisive_count": len(decisive),
        "advisory_count": len(advisory),
        "note": "参考情报仅作风险信号，不参与门禁规则求值（§5/§6.1）。",
    }


def _methodology_section(app: ModelApplication, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """§9 第 3 项：测试方法与结果 —— 逐门列出评估要点、采集器与判定。"""
    verdict_by_gate = {v.gate: v for v in app.verdicts}
    ev_by_gate: Dict[str, List[Any]] = {}
    for e in app.evidence:
        ev_by_gate.setdefault(e.gate, []).append(e)
    advisory_by_check = {(a.gate, a.check_id): a for a in app.blocker_advisories}

    out: List[Dict[str, Any]] = []
    for gate in GATE_ORDER:
        meta = GATE_BY_ID[gate]
        rules = _rule_index(policy, gate)
        v = verdict_by_gate.get(gate)
        gate_ev = ev_by_gate.get(gate, [])
        collectors = sorted({
            f"{e.collector}@{e.collector_version}" for e in gate_ev if not e.advisory
        })
        failed = list(v.failed_checks) if v else []
        blocker_ids = set(policy.get("gates", {}).get(gate, {}).get("blocker_checks", []))
        checks = []
        for cid in rules:
            adv = advisory_by_check.get((gate, cid))
            checks.append({
                "check_id": cid,
                "requirement": (rules.get(cid) or {}).get("message", ""),
                "blocker": cid in blocker_ids,
                "result": "fail" if cid in failed else ("pass" if v else "not_assessed"),
                "advisory": adv.to_dict() if adv else None,
            })
        out.append({
            "gate": gate,
            "section": meta["section"],
            "name": meta["name"],
            "name_en": meta["name_en"],
            "owner_role": meta["owner_role"],
            "hard_block": meta["hard_block"],
            "summary": meta["summary"],
            "standard_criteria": GATE_CRITERIA.get(gate, []),
            "collectors": collectors,
            "checks": checks,
            "checks_total": len(checks),
            "checks_failed": len(failed),
            "verdict": v.verdict if v else "not_assessed",
            "severity": v.severity if v else "none",
            "decided_by": v.decided_by if v else "",
            "decided_at": v.decided_at if v else "",
            "evidence_refs": list(v.evidence_refs) if v else [],
        })
    return out


def _findings_section(
    app: ModelApplication, policy: Dict[str, Any], conditions: List[str]
) -> List[Dict[str, Any]]:
    """§9 第 5 项：重大发现与缓解措施。"""
    findings: List[Dict[str, Any]] = []
    for v in app.verdicts:
        if v.verdict == "pass":
            continue
        rules = _rule_index(policy, v.gate)
        meta = GATE_BY_ID.get(v.gate, {})
        for cid in v.failed_checks:
            rule = rules.get(cid) or {}
            findings.append({
                "gate": v.gate,
                "section": meta.get("section", ""),
                "check_id": cid,
                "finding": rule.get("message", "未通过检查项"),
                "severity": v.severity,
                "blocker": cid in set(
                    policy.get("gates", {}).get(v.gate, {}).get("blocker_checks", [])
                ),
                "source": "policy",
                "mitigation": next(
                    (c for c in conditions if cid in c),
                    "需补充证据或施加运行时护栏后重评",
                ),
            })
    for op in app.opinions:
        meta = GATE_BY_ID.get(op.gate, {})
        for item in op.findings:
            findings.append({
                "gate": op.gate,
                "section": meta.get("section", ""),
                "check_id": item.get("check_id", ""),
                "finding": item.get("detail") or item.get("summary", ""),
                "severity": op.risk_level,
                "blocker": op.tightens_verdict,
                "source": f"reviewer:{op.reviewer}",
                "mitigation": "; ".join(op.recommended_conditions) or "待复核人指定",
            })
        for missing in op.missing_evidence:
            findings.append({
                "gate": op.gate,
                "section": meta.get("section", ""),
                "check_id": missing,
                "finding": "复核人认定该项证据缺失",
                "severity": op.risk_level,
                "blocker": False,
                "source": f"reviewer:{op.reviewer}",
                "mitigation": "补齐后重新提交评审",
            })
    return findings


def _permitted_use_section(app: ModelApplication) -> Dict[str, Any]:
    """§10 许可用途：基线保障之外是否还欠一份附加评估。"""
    tier_value = getattr(app.deployment, "permitted_use", "internal_row")
    tier = PERMITTED_USE_BY_VALUE.get(tier_value, {})
    requires_extra = bool(tier.get("requires_additional_assessment"))
    done = bool(getattr(app.deployment, "additional_assessment_complete", False))
    return {
        "value": tier_value,
        "section": tier.get("section", "10.1"),
        "label_zh": tier.get("label_zh", tier_value),
        "note": tier.get("note", ""),
        "requires_additional_assessment": requires_extra,
        "additional_assessment_complete": done,
        "additional_criteria": tier.get("additional_criteria", []),
        "satisfied": (not requires_extra) or done,
    }


def _governance_section(app: ModelApplication, methodology: List[Dict[str, Any]]) -> Dict[str, Any]:
    """§11 角色与治理：每道门的评估职能必须点名可追责。"""
    return {
        "roles": GOVERNANCE_ROLES,
        "evaluate": [
            {"gate": m["gate"], "section": m["section"], "owner_role": m["owner_role"]}
            for m in methodology
        ],
        "own": getattr(app.deployment, "named_owner", "") or "未登记",
        "applicant": app.applicant,
    }


def build_assurance_record(
    app: ModelApplication, policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """装配 §9 保障记录。未起评的申请返回空骨架，不臆造裁决。"""
    policy = policy or load_policy()
    assessed = bool(app.verdicts)

    # 未产生任何门禁裁决时 adjudicate 会给出"全通过"的假象，必须挡住。
    decision = adjudicate(app, policy).to_dict() if assessed else None
    conditions = list(decision["conditions"]) if decision else []
    methodology = _methodology_section(app, policy)
    status = app.status.value if hasattr(app.status, "value") else str(app.status)

    return {
        "standard": {"name": STANDARD_NAME, "version": STANDARD_VERSION},
        "generated_at": utc_now_iso(),
        "assessed": assessed,
        "application": {
            "application_id": app.application_id,
            "applicant": app.applicant,
            "status": status,
            "decided": status in _TERMINAL_DECIDED,
            "need_info_count": app.need_info_count,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
        },
        "artifact_assessed": _artifact_section(app),
        "evidence_reviewed": _evidence_section(app),
        "methodology_and_results": methodology,
        "findings_and_mitigations": _findings_section(app, policy, conditions),
        "residual_risks": (decision or {}).get("residual_risks", []),
        "conditions_and_restrictions": {
            "conditions": conditions,
            "runtime_profile": (decision or {}).get("runtime_profile", ""),
            "scope": (decision or {}).get("scope", []),
            "expires_at": (decision or {}).get("expires_at", ""),
            "exceptions": [],  # §12：例外须走治理流程单独登记，不由本引擎自动产生
        },
        "permitted_use": _permitted_use_section(app),
        "governance": _governance_section(app, methodology),
        "blocker_advisories": [a.to_dict() for a in app.blocker_advisories],
        "decision": decision,
        "deployment_context": app.deployment.to_dict(),
    }
