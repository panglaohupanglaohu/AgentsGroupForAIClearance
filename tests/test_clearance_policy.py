# -*- coding: utf-8 -*-
"""T305 — Policy Regression tests (T3: Fully reproducible without LLM)."""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.models import Evidence, utc_now_iso
from domain.model_clearance.policy_evaluator import evaluate_gate, load_policy


def make_ev(gate: str, check_id: str, payload: dict) -> Evidence:
    return Evidence(
        evidence_id=f"ev-test-{check_id}",
        gate=gate,
        check_id=check_id,
        collector="test-collector",
        collector_version="1.0.0",
        collected_at=utc_now_iso(),
        payload=payload,
    )


class TestClearancePolicy(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def test_g1_clean_pinned_revision_passes(self):
        ev = make_ev("G1", "G1-PROV-02", {
            "_status": "ok",
            "revision_pinned": True,
            "file_count": 12,
            "vendor_signature": "present",
        })
        verdict = evaluate_gate("G1", [ev], self.policy)
        self.assertEqual(verdict.verdict, "pass")

    def test_g1_mutable_revision_fails(self):
        ev = make_ev("G1", "G1-PROV-02", {
            "_status": "ok",
            "revision_pinned": False,
            "file_count": 12,
            "vendor_signature": "present",
        })
        verdict = evaluate_gate("G1", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G1-PROV-02", verdict.failed_checks)

    def test_g2_pickle_weights_fails(self):
        ev = make_ev("G2", "G2-BOM-02", {
            "_status": "ok",
            "safe_only": False,
            "component_count": 5,
            "critical": 0,
        })
        verdict = evaluate_gate("G2", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G2-BOM-02", verdict.failed_checks)

    def test_g2_critical_cve_fails(self):
        ev = make_ev("G2", "G2-BOM-04", {
            "_status": "ok",
            "safe_only": True,
            "component_count": 5,
            "critical": 2,
        })
        verdict = evaluate_gate("G2", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G2-BOM-04", verdict.failed_checks)

    # 标准 §7.3：许可证判定归入 G7 法务门（原 G3 已让位给 §6.3 行为评估）
    def test_g7_restricted_license_fails(self):
        ev = make_ev("G7", "G7-LIC-02", {
            "_status": "ok",
            "license_class": "restricted",
            "jurisdiction_restricted": False,
            "additional_assessment_satisfied": True,
            "intended_use_documented": True,
            "ip_licensing_reviewed": True,
            "human_oversight_defined": True,
        })
        verdict = evaluate_gate("G7", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G7-LIC-02", verdict.failed_checks)

    def test_g7_clean_commercial_license_passes(self):
        ev = make_ev("G7", "G7-LIC-02", {
            "_status": "ok",
            "license_class": "commercial_ok",
            "jurisdiction_restricted": False,
            "additional_assessment_satisfied": True,
            "intended_use_documented": True,
            "ip_licensing_reviewed": True,
            "human_oversight_defined": True,
        })
        verdict = evaluate_gate("G7", [ev], self.policy)
        self.assertEqual(verdict.verdict, "pass")

    # 标准 §3：禁止部署形态是硬红线
    def test_g0_prohibited_deployment_fails(self):
        ev = make_ev("G0", "G0-PROH-01", {
            "_status": "ok",
            "prohibited_clear": False,
            "data_egress_to_prc": False,
        })
        verdict = evaluate_gate("G0", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G0-PROH-01", verdict.failed_checks)

    def test_g0_data_egress_to_prc_fails(self):
        ev = make_ev("G0", "G0-PROH-02", {
            "_status": "ok",
            "prohibited_clear": True,
            "data_egress_to_prc": True,
        })
        verdict = evaluate_gate("G0", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G0-PROH-02", verdict.failed_checks)

    def test_g0_compliant_deployment_passes(self):
        ev = make_ev("G0", "G0-PROH-01", {
            "_status": "ok",
            "prohibited_clear": True,
            "data_egress_to_prc": False,
        })
        verdict = evaluate_gate("G0", [ev], self.policy)
        self.assertEqual(verdict.verdict, "pass")

    # 标准 §7.1：必须运行于 Lenovo 可控或已批准的基础设施
    def test_g5_unapproved_infrastructure_fails(self):
        ev = make_ev("G5", "G5-DEP-01", {
            "_status": "ok",
            "approved_infrastructure": False,
            "unauthorized_external_transmission": False,
            "monitoring_and_audit_logging": True,
            "workload_segregated": True,
        })
        verdict = evaluate_gate("G5", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G5-DEP-01", verdict.failed_checks)

    # 标准 §8：必须具备吊销能力与具名负责人
    def test_g8_missing_owner_fails(self):
        ev = make_ev("G8", "G8-OPS-02", {
            "_status": "ok",
            "suspension_revocation_capable": True,
            "named_owner_assigned": False,
            "incident_response_defined": True,
            "alternative_model_path": True,
        })
        verdict = evaluate_gate("G8", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G8-OPS-02", verdict.failed_checks)

    def test_t4_fail_closed_on_scanner_timeout(self):
        ev = make_ev("G1", "G1-PROV-02", {
            "_status": "timeout",
            "_error": "Scanner timed out",
        })
        verdict = evaluate_gate("G1", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")


if __name__ == "__main__":
    unittest.main()
