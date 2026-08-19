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
