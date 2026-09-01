# -*- coding: utf-8 -*-
"""§9 保障记录装配的最小可运行校验。"""

import unittest

from domain.model_clearance.assurance_record import build_assurance_record
from domain.model_clearance.models import (
    DeploymentContext,
    Evidence,
    GateVerdict,
    ModelApplication,
    ModelIdentity,
    utc_now_iso,
)


def _app(verdicts=None, evidence=None, **deploy):
    return ModelApplication(
        application_id="app-report-1",
        applicant="tester",
        identity=ModelIdentity(model_id="acme/open-7b", revision="v1.2", root_digest="a" * 64),
        evidence=evidence or [],
        verdicts=verdicts or [],
        deployment=DeploymentContext(**deploy),
    )


def _ev(gate, check_id, payload=None, advisory=False):
    return Evidence(
        evidence_id=f"ev-{gate}-{check_id}",
        gate=gate,
        check_id=check_id,
        collector="test-scanner",
        collector_version="1.0.0",
        collected_at=utc_now_iso(),
        payload=payload or {"_status": "ok"},
        advisory=advisory,
    )


class TestAssuranceRecord(unittest.TestCase):
    def test_draft_without_verdicts_yields_no_decision(self):
        """没跑过门禁却给出裁决，是本模块最危险的失效模式。"""
        rec = build_assurance_record(_app())
        self.assertFalse(rec["assessed"])
        self.assertIsNone(rec["decision"])
        self.assertEqual(rec["conditions_and_restrictions"]["conditions"], [])

    def test_record_carries_all_section_9_items(self):
        rec = build_assurance_record(
            _app(
                verdicts=[GateVerdict(gate="G7", verdict="needs_info", severity="major",
                                      failed_checks=["G7-USE-02"])],
                evidence=[_ev("G7", "G7-USE-02")],
            )
        )
        for key in (
            "artifact_assessed",
            "evidence_reviewed",
            "methodology_and_results",
            "findings_and_mitigations",
            "residual_risks",
            "conditions_and_restrictions",
            "decision",
            "permitted_use",
            "governance",
        ):
            self.assertIn(key, rec, key)
        self.assertEqual(rec["artifact_assessed"]["model_id"], "acme/open-7b")
        self.assertEqual(len(rec["methodology_and_results"]), 9)

    def test_每道门都带标准要求覆盖点与检查项(self):
        rec = build_assurance_record(_app(verdicts=[GateVerdict(gate="G0", verdict="pass", severity="none")]))
        for m in rec["methodology_and_results"]:
            self.assertTrue(m["standard_criteria"], f"{m['gate']} 缺少标准要求覆盖点")
            self.assertTrue(m["checks"], f"{m['gate']} 缺少检查项")

    def test_advisory_evidence_listed_separately(self):
        rec = build_assurance_record(
            _app(
                verdicts=[GateVerdict(gate="G7", verdict="pass", severity="none")],
                evidence=[
                    _ev("G7", "G7-USE-02"),
                    _ev("G7", "G7-ADVISORY", {"_status": "ok", "label": "外部情报", "kind": "run"}, advisory=True),
                ],
            )
        )
        ev = rec["evidence_reviewed"]
        self.assertEqual(ev["decisive_count"], 1)
        self.assertEqual(ev["advisory_count"], 1)
        self.assertEqual(ev["advisory"][0]["label"], "外部情报")

    def test_findings_carry_policy_message_and_mitigation(self):
        rec = build_assurance_record(
            _app(
                verdicts=[GateVerdict(gate="G7", verdict="needs_info", severity="major",
                                      failed_checks=["G7-USE-02"])],
            )
        )
        finding = rec["findings_and_mitigations"][0]
        self.assertEqual(finding["check_id"], "G7-USE-02")
        self.assertIn("预期用途", finding["finding"])
        self.assertTrue(finding["mitigation"])

    def test_customer_facing_without_extra_assessment_is_restricted(self):
        rec = build_assurance_record(
            _app(
                verdicts=[GateVerdict(gate="G0", verdict="pass", severity="none")],
                permitted_use="customer_facing",
            )
        )
        self.assertEqual(rec["decision"]["verdict"], "restricted")
        self.assertFalse(rec["permitted_use"]["satisfied"])


if __name__ == "__main__":
    unittest.main()
