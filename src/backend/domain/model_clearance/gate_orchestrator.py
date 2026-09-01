# -*- coding: utf-8 -*-
"""门禁编排器 — 按 Lenovo Open-Weight Model Assurance Standard 执行 G0–G8 并产出裁决.

与旧版的差异：
  1. 门禁顺序与内容由 standard.py 定义，不再散落在代码里；
  2. G0(§3) 是硬阻断，命中即不批准，其它门的结果不能覆盖；
  3. §7/§8 的门需要部署上下文，由本编排器注入扫描器；
  4. 时间线事件由门禁目录数据驱动生成，新增门禁无需再改事件代码。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .adjudicate import adjudicate
from .agent_review import simulate_or_call_agent_review
from .contributions import resolve_contributions
from .models import AppStatus, Evidence, GateVerdict, ModelApplication, utc_now_iso
from .policy_evaluator import evaluate_gate, load_policy
from .scanners import platform_endorse, scanners_for
from .standard import GATE_BY_ID, GATE_ORDER, GATE_PHASE, HARD_BLOCK_GATES
from .store import ModelClearanceStore, get_clearance_store

# 需要专家智能体复核的门：行为评估、红队、法务、持续保障
AGENT_GATES = {"G3", "G4", "G7", "G8"}


class GateOrchestrator:
    def __init__(
        self,
        store: Optional[ModelClearanceStore] = None,
        policy: Optional[Dict[str, Any]] = None,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.store = store or get_clearance_store()
        self.policy = policy or load_policy()
        self.event_sink = event_sink

    def _emit(self, event_type: str, app_id: str, data: Dict[str, Any]) -> None:
        if self.event_sink:
            self.event_sink({
                "type": event_type,
                "application_id": app_id,
                "data": data,
                "ts": utc_now_iso(),
            })

    def run_clearance(self, app: ModelApplication) -> ModelApplication:
        if app.status == AppStatus.DRAFT:
            app.transition_to(AppStatus.SUBMITTED)
        if app.status == AppStatus.SUBMITTED:
            app.transition_to(AppStatus.GATING)

        self.store.save(app)
        self._emit("clearance_started", app.application_id, {"status": app.status.value})

        context = app.deployment.to_dict()

        for gate in GATE_ORDER:
            meta = GATE_BY_ID.get(gate, {})
            self._emit("gate_started", app.application_id, {
                "gate": gate,
                "section": meta.get("section", ""),
                "name": meta.get("name", ""),
            })

            evidences: List[Evidence] = [s.run(app.identity) for s in scanners_for(gate, context)]

            # G1 §6.1：厂商签名缺失时用平台背书锁定 digest，仍满足「完整性与真实性」要求
            if gate == "G1":
                sig_ev = next((e for e in evidences if e.collector == "sigstore-verify"), None)
                if sig_ev and sig_ev.payload.get("vendor_signature") == "absent":
                    sig_ev.payload.update(platform_endorse(app.identity))

            # 控制台组装到本门禁的情报来源：advisory 证据，只留痕不参与规则求值
            # 截止日取申请创建日，避免采信申请之后才产生的情报
            advisory = resolve_contributions(
                app.contributions, gate, before=(app.created_at or "")[:10] or None
            )
            if advisory:
                evidences.extend(advisory)
                self._emit("advisory_attached", app.application_id, {
                    "gate": gate,
                    "count": len(advisory),
                    "labels": [e.payload.get("label", "") for e in advisory],
                })

            app.evidence.extend(evidences)
            self.store.save(app)
            self._emit("evidence_collected", app.application_id, {
                "gate": gate,
                "count": len(evidences),
                "advisory_count": len(advisory),
                "digests": [e.digest for e in evidences],
            })

            verdict = evaluate_gate(gate, evidences, self.policy)
            app.verdicts.append(verdict)
            self.store.save(app)
            self._emit("gate_verdict", app.application_id, verdict.to_dict())

            if verdict.verdict == "fail":
                app.transition_to(AppStatus.REJECTED)
                self.store.save(app)
                self._emit("clearance_rejected", app.application_id, {
                    "failed_gate": gate,
                    "section": meta.get("section", ""),
                    "failed_checks": verdict.failed_checks,
                    "hard_block": gate in HARD_BLOCK_GATES,
                })
                return app

            if verdict.verdict == "needs_info":
                app.need_info_count += 1
                app.transition_to(AppStatus.NEED_INFO)
                self.store.save(app)
                self._emit("clearance_need_info", app.application_id, {
                    "gate": gate,
                    "section": meta.get("section", ""),
                    "missing_checks": verdict.failed_checks,
                })
                return app

            if gate in AGENT_GATES:
                opinion = simulate_or_call_agent_review(gate, app, evidences, verdict)
                app.opinions.append(opinion)
                self.store.save(app)
                self._emit("agent_opinion", app.application_id, opinion.to_dict())

                if opinion.tightens_verdict and opinion.verdict_suggestion == "tighten":
                    app.transition_to(AppStatus.REJECTED)
                    self.store.save(app)
                    return app

        # §9 证据与保障裁决
        app.transition_to(AppStatus.ADJUDICATING)
        self.store.save(app)
        self._emit("adjudication_started", app.application_id, {})

        decision = adjudicate(app, self.policy)
        if decision.verdict == "approved":
            app.transition_to(AppStatus.APPROVED)
        elif decision.verdict in ("approved_with_conditions", "restricted"):
            app.transition_to(AppStatus.APPROVED_COND)
        else:
            app.transition_to(AppStatus.REJECTED)

        self.store.save(app)
        self._emit("decision_made", app.application_id, decision.to_dict())

        return app


def _gate_content(gate: str, verdict: Optional[GateVerdict], evidences: List[Evidence]) -> str:
    meta = GATE_BY_ID.get(gate, {})
    section = meta.get("section", "")
    name = meta.get("name", gate)
    if verdict is None:
        return f"§{section} {name}：未执行。"
    if verdict.verdict == "pass":
        return f"§{section} {name}：通过（{len(evidences)} 项证据）。"
    if verdict.verdict == "needs_info":
        return f"§{section} {name}：证据不足，待补 {', '.join(verdict.failed_checks) or '—'}。"
    return f"§{section} {name}：未通过，阻断项 {', '.join(verdict.failed_checks) or '—'}。"


def generate_application_events(app: ModelApplication) -> List[Dict[str, Any]]:
    """由门禁目录数据驱动生成流水线时间线事件。

    新增门禁只需改 standard.py，本函数无需同步修改。
    """
    events: List[Dict[str, Any]] = []
    seq = 1

    for gate in GATE_ORDER:
        meta = GATE_BY_ID.get(gate, {})
        verdict = next((v for v in app.verdicts if v.gate == gate), None)
        gate_ev = [e for e in app.evidence if e.gate == gate]
        opinion = next((o for o in app.opinions if o.gate == gate), None)

        if verdict is None:
            status = "pending"
        elif verdict.verdict == "pass":
            status = "completed"
        elif verdict.verdict == "needs_info":
            status = "needs_info"
        else:
            status = "failed"

        structured: Dict[str, Any] = {
            "gate": gate,
            "section": f"§{meta.get('section', '')}",
            "standard_name": meta.get("name_en", ""),
            "owner_role": meta.get("owner_role", ""),
            "hard_block": bool(meta.get("hard_block")),
            "verdict": verdict.verdict if verdict else "pending",
            "failed_checks": list(verdict.failed_checks) if verdict else [],
            "evidence_count": len(gate_ev),
            "label": "fact" if gate in ("G0", "G1", "G2") else "analysis",
        }
        if opinion:
            structured["reviewer"] = opinion.reviewer
            structured["risk_level"] = opinion.risk_level
            structured["recommended_conditions"] = list(opinion.recommended_conditions)

        events.append({
            "seq": seq,
            "phase": GATE_PHASE.get(gate, "context"),
            "node": f"{gate.lower()}_sec{meta.get('section', '').replace('.', '_')}",
            "participant": meta.get("owner_role", "Clearance Scanner"),
            "status": status,
            "content": _gate_content(gate, verdict, gate_ev),
            "structured": structured,
            "evidence": [e.evidence_id for e in gate_ev],
            "ts": verdict.decided_at if verdict else app.updated_at,
        })
        seq += 1

    # §9 裁决与 §10 许可用途
    approved = app.status in (AppStatus.APPROVED, AppStatus.APPROVED_COND)
    events.append({
        "seq": seq,
        "phase": "portfolio",
        "node": "assurance_decision",
        "participant": "AI模型准入主理人",
        "status": "completed" if approved else "failed",
        "content": f"§9 证据与保障裁决完成，状态: {app.status.value}",
        "structured": {
            "decision": {
                "verdict": app.status.value,
                "application_id": app.application_id,
                "applicant": app.applicant,
            },
            "permitted_use": app.deployment.permitted_use,
            "portfolio": {
                "entry_id": f"reg-{app.application_id}",
                "disclaimer": "保障适用于具体模型制品与已批准的部署条件，不构成对模型提供方或其托管服务的一般性批准。",
            },
        },
        "evidence": [e.evidence_id for e in app.evidence],
        "ts": app.updated_at,
    })

    return events
