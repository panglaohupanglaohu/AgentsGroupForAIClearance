# -*- coding: utf-8 -*-
"""Unit tests for Continuous Verification L5."""

import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.continuous_verification import (
    daily_cve_reassessment,
    due_reassessment_scheduler,
    generate_monthly_compliance_report,
    periodic_baseline_audit,
)
from domain.model_clearance.registry import ApprovedRegistryEntry, ModelRegistryStore


class TestContinuousVerification(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = ModelRegistryStore(base_dir=self.temp_dir)

        # Active entry
        self.entry_active = ApprovedRegistryEntry(
            entry_id="reg-active-01",
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            revision="v3.1",
            locked_digest="sha256-abc123",
            decision_ref="att://01",
            scope=["internal"],
            conditions=[],
            runtime_profile="standard",
            approved_at="2026-08-01T00:00:00Z",
            reassessment_due="2026-11-01T00:00:00Z",
            status="active",
        )
        self.store.base_dir.mkdir(parents=True, exist_ok=True)
        import json
        (self.store.base_dir / "reg-active-01.json").write_text(
            json.dumps(self.entry_active.to_dict()), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_periodic_baseline_audit_detects_violations(self):
        tampered_pods = [
            {
                "spec": {
                    "automountServiceAccountToken": False,
                    "securityContext": {"runAsNonRoot": False, "runAsUser": 0},
                    "containers": [
                        {
                            "image": "registry.internal/ai/inference-base:latest",
                            "securityContext": {"readOnlyRootFilesystem": True},
                            "resources": {"limits": {"cpu": "16"}},
                        }
                    ],
                }
            }
        ]
        drifts = periodic_baseline_audit(self.store, tampered_pods)
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0]["drift_type"], "config")

    def test_daily_cve_reassessment_transitions_to_reassessing(self):
        new_cves = [{"id": "CVE-2026-1111", "severity": "CRITICAL"}]
        drifts = daily_cve_reassessment(self.store, new_cves)
        self.assertEqual(len(drifts), 1)
        entry = self.store.get("reg-active-01")
        self.assertEqual(entry.status, "reassessing")

    def test_due_reassessment_scheduler(self):
        # Set due date in the past
        self.entry_active.reassessment_due = "2020-01-01T00:00:00Z"
        self.entry_active.status = "active"
        import json
        (self.store.base_dir / "reg-active-01.json").write_text(
            json.dumps(self.entry_active.to_dict()), encoding="utf-8"
        )

        actions = due_reassessment_scheduler(self.store)
        self.assertGreaterEqual(len(actions), 1)
        entry = self.store.get("reg-active-01")
        self.assertEqual(entry.status, "reassessing")
        self.assertEqual(entry.runtime_profile, "restricted")

    def test_monthly_compliance_report(self):
        report = generate_monthly_compliance_report(self.store)
        self.assertEqual(report["total_registered_models"], 1)
        self.assertIn("status_distribution", report)


if __name__ == "__main__":
    unittest.main()
