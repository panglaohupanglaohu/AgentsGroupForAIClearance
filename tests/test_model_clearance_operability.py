# -*- coding: utf-8 -*-
"""T909 — Tests for Lenovo Operability, Control Matrix, Kill-Switch, Rollback & Audit."""

import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.adjudicate import adjudicate
from domain.model_clearance.gate_orchestrator import GateOrchestrator
from domain.model_clearance.models import AppStatus, ModelApplication, ModelIdentity
from domain.model_clearance.registry import ModelRegistryStore
from domain.model_clearance.store import ModelClearanceStore

# Import audit sampling
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_sampling import run_audit_sampling


class TestModelClearanceOperability(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.app_store = ModelClearanceStore(base_dir=Path(self.temp_dir) / "apps")
        self.reg_store = ModelRegistryStore(base_dir=Path(self.temp_dir) / "registry")
        self.orch = GateOrchestrator(store=self.app_store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_origin_unknown_controlled_admission(self):
        """Test that a model with unknown upstream origin/signature can pass via Platform Endorsement & Restricted Profile."""
        app = ModelApplication(
            application_id="app-origin-unknown",
            applicant="Lenovo-AI-Infra",
            identity=ModelIdentity(
                model_id="custom-community/Unsigned-Finance-8B",
                revision="v1.0-pinned",
                expected_signer_identity=None,  # No vendor signature
            ),
        )
        self.app_store.save(app)
        res_app = self.orch.run_clearance(app)

        # Adjudication
        decision = adjudicate(res_app)
        self.assertIn(decision.verdict, ("approved", "approved_with_conditions"))
        # Platform endorsement triggers restricted profile for controlled governance
        self.assertEqual(decision.runtime_profile, "restricted")

        entry = self.reg_store.register(
            app=res_app,
            runtime_profile=decision.runtime_profile,
            scope=decision.scope,
            conditions=decision.conditions,
            expires_at=decision.expires_at,
            service_owner="finance-ai-ops@lenovo.com",
            security_owner="ai-sec@lenovo.com",
            oncall_rotation="lenovo-fin-l2",
        )

        self.assertEqual(entry.status, "active")
        self.assertEqual(entry.runtime_profile, "restricted")
        self.assertEqual(entry.service_owner, "finance-ai-ops@lenovo.com")
        self.assertEqual(entry.security_owner, "ai-sec@lenovo.com")
        self.assertEqual(entry.kill_switch_ref, "ops://clearance/kill-switch")
        self.assertEqual(entry.rollback_runbook_ref, "runbook://clearance/rollback-baseline")
        self.assertEqual(len(entry.digest_history), 1)

        # Verify attestations
        ver = self.reg_store.verify_entry(entry.entry_id)
        self.assertTrue(ver["found"])
        self.assertTrue(ver["all_valid"])

    def test_kill_switch_and_rollback_lifecycle(self):
        """Test emergency kill-switch revocation and rollback to last known good baseline."""
        app = ModelApplication(
            application_id="app-lifecycle-test",
            applicant="SecOps",
            identity=ModelIdentity(
                model_id="Qwen/Qwen2.5-7B-Instruct",
                revision="v2.5",
            ),
        )
        self.app_store.save(app)
        res_app = self.orch.run_clearance(app)
        dec = adjudicate(res_app)
        entry = self.reg_store.register(
            app=res_app,
            runtime_profile=dec.runtime_profile,
            scope=dec.scope,
            conditions=dec.conditions,
            expires_at=dec.expires_at,
        )

        self.assertEqual(entry.status, "active")

        # 1. Emergency Kill-Switch
        revoked_entry = self.reg_store.emergency_revoke(
            entry_id=entry.entry_id,
            operator="secops-commander",
            reason="Detected prompt exfiltration anomaly",
        )
        self.assertIsNotNone(revoked_entry)
        self.assertEqual(revoked_entry.status, "revoked")
        self.assertTrue(any(log["action"] == "emergency_revoke" for log in revoked_entry.operations_audit_log))

        # 2. Rollback to safe digest and restore active state
        new_safe_digest = "sha256-fallback-verified-digest-999"
        rolled_back_entry = self.reg_store.rollback_to_last_known_good(
            entry_id=entry.entry_id,
            target_digest=new_safe_digest,
            operator="infra-recovery-lead",
            reason="Restoring to verified base digest",
        )
        self.assertIsNotNone(rolled_back_entry)
        self.assertEqual(rolled_back_entry.status, "active")
        self.assertEqual(rolled_back_entry.locked_digest, new_safe_digest)
        self.assertGreaterEqual(len(rolled_back_entry.digest_history), 2)

    def test_weekly_audit_sampling_success(self):
        """Test that audit sampling inspects and confirms active model health."""
        # Register 2 active models
        for i in range(2):
            app = ModelApplication(
                application_id=f"app-audit-{i}",
                applicant="Tester",
                identity=ModelIdentity(model_id=f"Test/Model-{i}", revision=f"v{i}"),
            )
            self.app_store.save(app)
            res = self.orch.run_clearance(app)
            dec = adjudicate(res)
            self.reg_store.register(
                app=res,
                runtime_profile=dec.runtime_profile,
                scope=dec.scope,
                conditions=dec.conditions,
                expires_at=dec.expires_at,
            )

        audit_res = run_audit_sampling(store=self.reg_store, sample_ratio=1.0)
        self.assertEqual(audit_res["total_active"], 2)
        self.assertEqual(audit_res["sampled_count"], 2)
        self.assertTrue(audit_res["all_healthy"])
        self.assertEqual(len(audit_res["issues_found"]), 0)


if __name__ == "__main__":
    unittest.main()
