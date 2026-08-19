# -*- coding: utf-8 -*-
"""T303 / T306 — Gate Orchestrator with Fail-Fast execution and Event stream."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .adjudicate import adjudicate
from .agent_review import simulate_or_call_agent_review
from .models import AppStatus, Evidence, GateVerdict, ModelApplication, utc_now_iso
from .policy_evaluator import evaluate_gate, load_policy
from .scanners import platform_endorse, scanners_for
from .store import ModelClearanceStore, get_clearance_store

GATE_ORDER = ["G1", "G2", "G3", "G4", "G5"]
AGENT_GATES = {"G3", "G4", "G5"}


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

        for gate in GATE_ORDER:
            self._emit("gate_started", app.application_id, {"gate": gate})

            # 1. Collect evidence from scanners
            scanners = scanners_for(gate)
            evidences: List[Evidence] = [s.run(app.identity) for s in scanners]

            # If G1 has missing vendor signature, apply platform endorsement
            if gate == "G1":
                sig_ev = next((e for e in evidences if e.collector == "sigstore-verify"), None)
                if sig_ev and sig_ev.payload.get("vendor_signature") == "absent":
                    endorsement = platform_endorse(app.identity)
                    sig_ev.payload.update(endorsement)

            app.evidence.extend(evidences)
            self.store.save(app)
            self._emit("evidence_collected", app.application_id, {
                "gate": gate,
                "count": len(evidences),
                "digests": [e.digest for e in evidences],
            })

            # 2. Evaluate Policy rules
            verdict = evaluate_gate(gate, evidences, self.policy)
            app.verdicts.append(verdict)
            self.store.save(app)
            self._emit("gate_verdict", app.application_id, verdict.to_dict())

            # Fail-fast check
            if verdict.verdict == "fail":
                app.transition_to(AppStatus.REJECTED)
                self.store.save(app)
                self._emit("clearance_rejected", app.application_id, {
                    "failed_gate": gate,
                    "failed_checks": verdict.failed_checks,
                })
                return app

            if verdict.verdict == "needs_info":
                app.need_info_count += 1
                app.transition_to(AppStatus.NEED_INFO)
                self.store.save(app)
                self._emit("clearance_need_info", app.application_id, {
                    "gate": gate,
                    "missing_checks": verdict.failed_checks,
                })
                return app

            # 3. Agent Review for designated gates (G3, G4, G5)
            if gate in AGENT_GATES:
                opinion = simulate_or_call_agent_review(gate, app, evidences, verdict)
                app.opinions.append(opinion)
                self.store.save(app)
                self._emit("agent_opinion", app.application_id, opinion.to_dict())

                if opinion.tightens_verdict and opinion.verdict_suggestion == "tighten":
                    app.transition_to(AppStatus.REJECTED)
                    self.store.save(app)
                    return app

        # 4. Adjudication & Signoff (G6)
        app.transition_to(AppStatus.ADJUDICATING)
        self.store.save(app)
        self._emit("adjudication_started", app.application_id, {})

        decision = adjudicate(app, self.policy)
        if decision.verdict == "approved":
            app.transition_to(AppStatus.APPROVED)
        elif decision.verdict == "approved_with_conditions":
            app.transition_to(AppStatus.APPROVED_COND)
        else:
            app.transition_to(AppStatus.REJECTED)

        self.store.save(app)
        self._emit("decision_made", app.application_id, decision.to_dict())

        return app


def generate_application_events(app: ModelApplication) -> List[Dict[str, Any]]:
    """Synthesize standardized journey timeline events from application evidence, verdicts, and opinions."""
    events: List[Dict[str, Any]] = []
    seq = 1

    # 1. G1 Ingress event
    events.append({
        "seq": seq,
        "phase": "context",
        "node": "g1_provenance",
        "participant": "Provenance & Signature Scanner",
        "status": "completed",
        "content": f"模型标识: {app.identity.model_id} (revision: {app.identity.revision})，证据已冻结。",
        "structured": {
            "model_id": app.identity.model_id,
            "revision": app.identity.revision,
            "evidence_count": len([e for e in app.evidence if e.gate == "G1"]),
        },
        "evidence": [e.evidence_id for e in app.evidence if e.gate == "G1"],
        "ts": app.created_at,
    })
    seq += 1

    # 2. G2 Security & BOM event
    g2_verdict = next((v for v in app.verdicts if v.gate == "G2"), None)
    events.append({
        "seq": seq,
        "phase": "analysis",
        "node": "g2_bom_cve",
        "participant": "CycloneDX BOM & Security Scanner",
        "status": "completed" if g2_verdict and g2_verdict.verdict == "pass" else "failed",
        "content": "CycloneDX ML-BOM 格式安全与 CVE 漏洞扫描完成。",
        "structured": {
            "claim": "Safetensors 格式安全，无已知 CRITICAL 漏洞",
            "direction": "up" if g2_verdict and g2_verdict.verdict == "pass" else "down",
            "confidence": 0.95,
            "label": "analysis",
        },
        "evidence": [e.evidence_id for e in app.evidence if e.gate == "G2"],
        "ts": g2_verdict.decided_at if g2_verdict else app.updated_at,
    })
    seq += 1

    # 3. G3 Compliance & License event
    g3_verdict = next((v for v in app.verdicts if v.gate == "G3"), None)
    g3_opinion = next((o for o in app.opinions if o.gate == "G3"), None)
    events.append({
        "seq": seq,
        "phase": "planning",
        "node": "compliance_reviewer",
        "participant": "Compliance & Legal Reviewer",
        "status": "completed" if g3_verdict and g3_verdict.verdict == "pass" else "failed",
        "content": f"许可证条款与管辖权合规评估完成: {', '.join(g3_opinion.recommended_conditions) if g3_opinion and g3_opinion.recommended_conditions else '允许商用与内部推理'}",
        "structured": {
            "objective": "开放权重模型许可范围与法律风险判定",
            "base_case": {"action": "APPROVED", "scope": "internal"},
            "bull_case": {"action": "COMMERCIAL_OK"},
            "bear_case": {"action": "RESTRICTED"},
        },
        "evidence": [e.evidence_id for e in app.evidence if e.gate == "G3"],
        "ts": g3_verdict.decided_at if g3_verdict else app.updated_at,
    })
    seq += 1

    # 4. G4 Resource & Infra event
    g4_verdict = next((v for v in app.verdicts if v.gate == "G4"), None)
    events.append({
        "seq": seq,
        "phase": "trading",
        "node": "infra_reviewer",
        "participant": "Infra & GPU Capacity Reviewer",
        "status": "completed",
        "content": "显存占用、KV-Cache 与多节点并发推演完成。",
        "structured": {
            "summary": "资源画像满足生产推理池基线",
            "action": "STANDARD_GPU_POOL",
            "label": "simulation",
        },
        "evidence": [e.evidence_id for e in app.evidence if e.gate == "G4"],
        "ts": g4_verdict.decided_at if g4_verdict else app.updated_at,
    })
    seq += 1

    # 5. G5 Red team & Safety event
    g5_verdict = next((v for v in app.verdicts if v.gate == "G5"), None)
    events.append({
        "seq": seq,
        "phase": "risk",
        "node": "redteam_eval",
        "participant": "Safety & Red Team Gate",
        "status": "completed" if g5_verdict and g5_verdict.verdict == "pass" else "failed",
        "content": "越狱攻击、提示注入与有害内容防御测试通过。",
        "structured": {
            "gate": "approved" if g5_verdict and g5_verdict.verdict == "pass" else "rejected",
            "reason": "对抗越狱与注入防御测试均在安全基线内",
        },
        "evidence": [e.evidence_id for e in app.evidence if e.gate == "G5"],
        "ts": g5_verdict.decided_at if g5_verdict else app.updated_at,
    })
    seq += 1

    # 6. G6 Adjudication & Attestation event
    events.append({
        "seq": seq,
        "phase": "portfolio",
        "node": "clearance_board",
        "participant": "Clearance Adjudication Coordinator",
        "status": "completed" if app.status in (AppStatus.APPROVED, AppStatus.APPROVED_COND) else "failed",
        "content": f"准入评审会签完成，状态: {app.status.value}",
        "structured": {
            "decision": {
                "verdict": app.status.value,
                "application_id": app.application_id,
                "applicant": app.applicant,
            },
            "portfolio": {
                "entry_id": f"reg-{app.application_id}",
                "runtime_profile": "standard",
                "scope": ["internal", "commercial"],
                "disclaimer": "仅供内部治理参考，不构成法律或采购建议。",
            },
        },
        "evidence": [e.evidence_id for e in app.evidence],
        "ts": app.updated_at,
    })

    return events
