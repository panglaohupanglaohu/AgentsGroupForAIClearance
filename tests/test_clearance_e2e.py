# -*- coding: utf-8 -*-
"""T506 — End-to-end integration tests for Model Clearance pipeline & attestation verification."""

import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.adjudicate import adjudicate
from domain.model_clearance.gate_orchestrator import GateOrchestrator
from domain.model_clearance.models import (
    AppStatus,
    DeploymentContext,
    ModelApplication,
    ModelIdentity,
)
from domain.model_clearance.registry import ModelRegistryStore
from domain.model_clearance.store import ModelClearanceStore


class TestClearanceE2E(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.app_store = ModelClearanceStore(base_dir=Path(self.temp_dir) / "apps")
        self.reg_store = ModelRegistryStore(base_dir=Path(self.temp_dir) / "registry")
        self.orchestrator = GateOrchestrator(store=self.app_store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_e2e_approval_and_cryptographic_verification(self):
        # 1. Create Application（§7/§8 要求的部署上下文必须随申请提交）
        app = ModelApplication(
            application_id="app-e2e-llama",
            applicant="Platform AI SecOps",
            identity=ModelIdentity(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="v3.1",
                expected_signer_identity="meta@verified.org",
            ),
            deployment=DeploymentContext(
                intended_use="内部 ROW 研发辅助问答",
                named_owner="platform-ai-secops",
            ),
        )
        self.app_store.save(app)

        # 2. Run Gate Orchestrator
        finished_app = self.orchestrator.run_clearance(app)
        self.assertIn(finished_app.status, (AppStatus.APPROVED, AppStatus.APPROVED_COND))

        # 3. Adjudicate and Register
        decision = adjudicate(finished_app)
        entry = self.reg_store.register(
            app=finished_app,
            runtime_profile=decision.runtime_profile,
            scope=decision.scope,
            conditions=decision.conditions,
            expires_at=decision.expires_at,
        )
        self.assertEqual(entry.model_id, "meta-llama/Llama-3.1-8B-Instruct")
        self.assertEqual(entry.status, "active")
        self.assertGreaterEqual(len(entry.attestations), 5)

        # 4. Verify Attestation Cryptographic Integrity (T504)
        verify_res = self.reg_store.verify_entry(entry.entry_id)
        self.assertTrue(verify_res["found"])
        self.assertTrue(verify_res["all_valid"])
        self.assertGreaterEqual(len(verify_res["attestations"]), 5)
        for att in verify_res["attestations"]:
            self.assertTrue(att["signature_valid"])

        # 5. Revoke Entry
        revoked = self.reg_store.revoke(entry.entry_id, reason="Security policy update")
        self.assertEqual(revoked.status, "revoked")
        self.assertEqual(len(self.reg_store.list_active()), 0)


if __name__ == "__main__":
    unittest.main()
