# -*- coding: utf-8 -*-
"""T308 — Gate Orchestrator Integration Tests (Blocker Rejection, Approval, Event stream)."""

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.gate_orchestrator import GateOrchestrator
from domain.model_clearance.models import (
    AppStatus,
    DeploymentContext,
    ModelApplication,
    ModelIdentity,
)
from domain.model_clearance.store import ModelClearanceStore


def compliant_deployment() -> DeploymentContext:
    """满足 §7/§8 的合规部署形态；默认值刻意留空 intended_use，此处补齐。"""
    return DeploymentContext(
        intended_use="内部 ROW 研发辅助问答",
        named_owner="platform-ai-owner",
    )


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
            deployment=compliant_deployment(),
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)
        self.assertIn(finished.status, (AppStatus.APPROVED, AppStatus.APPROVED_COND))
        self.assertGreaterEqual(len(self.events), 5)

        persisted = self.store.get("app-orchestrate-01")
        self.assertGreaterEqual(len(persisted.evidence), 5)
        # G0–G8 全部执行
        self.assertEqual(len(persisted.verdicts), 9)

    def test_undocumented_intended_use_needs_info(self):
        """§7.3 要求记录预期用途；留空必须挡在 needs_info，不能默默放行。"""
        app = ModelApplication(
            application_id="app-no-usecase",
            applicant="Engineer C",
            identity=ModelIdentity(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="v3.1",
            ),
            deployment=DeploymentContext(named_owner="owner-x"),
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)
        self.assertEqual(finished.status, AppStatus.NEED_INFO)

    def test_model_review_runs_without_applicant_or_deployment_workflow(self):
        """情报入口只评模型；未知技术证据待补，不伪造申请人或部署事实。"""
        app = ModelApplication(
            application_id="app-model-review",
            applicant="",
            identity=ModelIdentity(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="",
                weights_uri="https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct",
            ),
            deployment=DeploymentContext.unknown(),
            review_scope="model",
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)

        self.assertEqual(finished.status, AppStatus.NEED_INFO)
        self.assertEqual([v.gate for v in finished.verdicts], ["G1", "G2", "G3", "G4", "G7"])
        self.assertEqual(finished.applicant, "")
        self.assertEqual(finished.deployment.named_owner, "")
        self.assertEqual(finished.deployment.intended_use, "")
        self.assertEqual(finished.identity.root_digest, "")
        self.assertTrue(all(v.verdict == "needs_info" for v in finished.verdicts[:4]))
        self.assertNotIn("G8", [v.gate for v in finished.verdicts])

    def test_retry_creates_new_run_from_same_model_snapshot(self):
        from domain.api_routes import retry_clearance_application
        from domain.model_clearance import store as store_module

        previous = ModelApplication(
            application_id="app-model-retry",
            applicant="",
            identity=ModelIdentity(
                model_id="open-model/example",
                revision="",
                weights_uri="https://example.invalid/open-model",
            ),
            deployment=DeploymentContext.unknown(),
            review_scope="model",
        )
        self.store.save(previous)
        previous = self.orchestrator.run_clearance(previous)
        old_instance = store_module._INSTANCE
        store_module._INSTANCE = self.store
        try:
            retried = asyncio.run(retry_clearance_application(previous.application_id))
        finally:
            store_module._INSTANCE = old_instance

        self.assertNotEqual(retried["application_id"], previous.application_id)
        self.assertEqual(retried["identity"]["model_id"], previous.identity.model_id)
        self.assertEqual(retried["identity"]["revision"], "")
        self.assertEqual(retried["review_scope"], "model")
        self.assertEqual(retried["applicant"], "")
        self.assertEqual(retried["status"], "need_info")

    def test_prohibited_deployment_blocks_at_g0(self):
        """§3 硬红线：数据外传 PRC 必须在 G0 即刻阻断，后续门不再执行。"""
        app = ModelApplication(
            application_id="app-prohibited",
            applicant="Engineer D",
            identity=ModelIdentity(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="v3.1",
            ),
            deployment=DeploymentContext(
                intended_use="内部问答",
                named_owner="owner-y",
                data_egress_to_prc=True,
            ),
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)
        self.assertEqual(finished.status, AppStatus.REJECTED)

        gates = [v.gate for v in self.store.get("app-prohibited").verdicts]
        self.assertEqual(gates, ["G0"])

    def test_restricted_license_fails_at_legal_gate(self):
        """许可证受限在 §7.3 法务门失败，且 §8 不再执行（fail-fast）。"""
        app = ModelApplication(
            application_id="app-orchestrate-restricted",
            applicant="Engineer B",
            identity=ModelIdentity(
                model_id="mistralai/Mistral-Large-Instruct-2407",  # License is restricted
                revision="v2407",
            ),
            deployment=compliant_deployment(),
        )
        self.store.save(app)

        finished = self.orchestrator.run_clearance(app)
        self.assertEqual(finished.status, AppStatus.REJECTED)

        gates_evaluated = [v.gate for v in self.store.get("app-orchestrate-restricted").verdicts]
        self.assertIn("G7", gates_evaluated)
        self.assertNotIn("G8", gates_evaluated)


if __name__ == "__main__":
    unittest.main()
