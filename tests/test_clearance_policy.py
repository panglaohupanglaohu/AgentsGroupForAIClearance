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

    def test_g3_restricted_license_fails(self):
        ev = make_ev("G3", "G3-LIC-02", {
            "_status": "ok",
            "license_class": "restricted",
            "jurisdiction_restricted": False,
        })
        verdict = evaluate_gate("G3", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("G3-LIC-02", verdict.failed_checks)

    def test_g3_clean_commercial_license_passes(self):
        ev = make_ev("G3", "G3-LIC-02", {
            "_status": "ok",
            "license_class": "commercial_ok",
            "jurisdiction_restricted": False,
        })
        verdict = evaluate_gate("G3", [ev], self.policy)
        self.assertEqual(verdict.verdict, "pass")

    def test_t4_fail_closed_on_scanner_timeout(self):
        ev = make_ev("G1", "G1-PROV-02", {
            "_status": "timeout",
            "_error": "Scanner timed out",
        })
        verdict = evaluate_gate("G1", [ev], self.policy)
        self.assertEqual(verdict.verdict, "fail")


if __name__ == "__main__":
    unittest.main()
