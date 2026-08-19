# -*- coding: utf-8 -*-
"""T407 — Tests for Agent Review Layer, Hallucination Guard, and Directional Guardrail."""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.agent_review import (
    PolicyOverrideAttempt,
    quote_locatable,
    ref_exists,
    should_trigger_legal_reviewer,
    simulate_or_call_agent_review,
)
from domain.model_clearance.models import (
    Evidence,
    GateVerdict,
    ModelApplication,
    ModelIdentity,
    utc_now_iso,
)


class TestClearanceAgents(unittest.TestCase):
    def setUp(self):
        self.app = ModelApplication(
            application_id="app-agent-01",
            applicant="Tester",
            identity=ModelIdentity(model_id="meta-llama/Llama-3.1-8B-Instruct"),
        )
        self.evidences = [
            Evidence(
                evidence_id="ev-lic-01",
                gate="G3",
                check_id="G3-LIC-01",
                collector="license-scanner",
                collector_version="1.0.0",
                collected_at=utc_now_iso(),
                payload={
                    "_status": "ok",
                    "license_class": "conditional",
                    "license_conditions": ["MAU 700M threshold requires commercial license"],
                },
            )
        ]

    def test_ref_exists_and_quote_locatable(self):
        self.assertTrue(ref_exists("ev-lic-01", self.evidences))
        self.assertFalse(ref_exists("ev-non-existent", self.evidences))

        # Real quote
        self.assertTrue(quote_locatable("MAU 700M threshold", self.evidences))
        # Hallucinated quote
        self.assertFalse(quote_locatable("This model is totally open with no rules", self.evidences))

    def test_should_trigger_legal_reviewer(self):
        self.assertTrue(should_trigger_legal_reviewer(self.app, self.evidences))

        clean_ev = [
            Evidence(
                evidence_id="ev-lic-clean",
                gate="G3",
                check_id="G3-LIC-01",
                collector="license-scanner",
                collector_version="1.0.0",
                collected_at=utc_now_iso(),
                payload={"_status": "ok", "license_class": "commercial_ok", "jurisdiction_restricted": False},
            )
        ]
        self.assertFalse(should_trigger_legal_reviewer(self.app, clean_ev))

    def test_directional_guard_policy_fail_cannot_be_overturned(self):
        fail_verdict = GateVerdict(
            gate="G3",
            verdict="fail",
            severity="blocker",
            failed_checks=["G3-LIC-02"],
        )

        # Mock LLM that attempts to say "pass" on a policy fail
        mock_hallucinating_llm = lambda prompt: {
            "gate": "G3",
            "reviewer": "compliance_reviewer",
            "verdict_suggestion": "pass",
            "risk_level": "low",
        }

        with self.assertRaises(PolicyOverrideAttempt):
            simulate_or_call_agent_review(
                "G3",
                self.app,
                self.evidences,
                fail_verdict,
                llm_callable=mock_hallucinating_llm,
            )


if __name__ == "__main__":
    unittest.main()
