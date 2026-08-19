# -*- coding: utf-8 -*-
"""T308 — Gate Orchestrator Integration Tests (Blocker Rejection, Approval, Event stream)."""

import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.gate_orchestrator import GateOrchestrator
from domain.model_clearance.models import AppStatus, ModelApplication, ModelIdentity
from domain.model_clearance.store import ModelClearanceStore


class TestClearanceOrchestrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = ModelClearanceStore(base_dir=self.temp_dir)
        self.events = []
        self.orchestrator = GateOrchestrator(
            store=self.store,
            event_sink=lambda e: self.events.append(e),
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_model_conditional_approval(self):
        app = ModelApplication(
            application_id="app-orchestrate-01",
            applicant="Engineer A",
            identity=ModelIdentity(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="v3.1",
            ),
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)
        self.assertIn(finished.status, (AppStatus.APPROVED, AppStatus.APPROVED_COND))
        self.assertGreaterEqual(len(self.events), 5)

        # Confirm evidence and verdicts persisted in store
        persisted = self.store.get("app-orchestrate-01")
        self.assertGreaterEqual(len(persisted.evidence), 5)
        self.assertGreaterEqual(len(persisted.verdicts), 5)

    def test_restricted_model_early_fail_rejection(self):
        app = ModelApplication(
            application_id="app-orchestrate-restricted",
            applicant="Engineer B",
            identity=ModelIdentity(
                model_id="mistralai/Mistral-Large-Instruct-2407",  # License is restricted
                revision="v2407",
            ),
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)
        self.assertEqual(finished.status, AppStatus.REJECTED)

        # Confirm G3 was rejected and subsequent gates G4/G5 were skipped (fail-fast)
        persisted = self.store.get("app-orchestrate-restricted")
        gates_evaluated = [v.gate for v in persisted.verdicts]
        self.assertIn("G3", gates_evaluated)
        self.assertNotIn("G5", gates_evaluated)


if __name__ == "__main__":
    unittest.main()
