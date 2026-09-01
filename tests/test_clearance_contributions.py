# -*- coding: utf-8 -*-
"""控制台组装的情报来源 → 参考证据（advisory）的行为约束.

红线：外部智能体团队的采集与分析只作风险信号，
不得进入门禁规则求值，不得让任何一道门自动通过或失败。
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.contributions import resolve_contributions
from domain.model_clearance.gate_orchestrator import GateOrchestrator
from domain.model_clearance.models import (
    DeploymentContext,
    Evidence,
    EvidenceContribution,
    ModelApplication,
    ModelIdentity,
)
from domain.model_clearance.policy_evaluator import evaluate_gate
from domain.model_clearance.store import ModelClearanceStore


def compliant_deployment() -> DeploymentContext:
    return DeploymentContext(
        intended_use="内部 ROW 研发辅助问答",
        named_owner="platform-ai-owner",
    )


class TestAdvisoryEvidenceIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = ModelClearanceStore(base_dir=self.temp_dir)
        self.orchestrator = GateOrchestrator(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_advisory_payload_cannot_satisfy_gate_rules(self):
        """伪造 _status=ok 的参考情报不得让缺证的门禁通过。"""
        forged = Evidence(
            evidence_id="ev-forged",
            gate="G1",
            check_id="G1-ADVISORY",
            collector="external:team:open_weights",
            collector_version="1.0.0",
            collected_at="2026-08-30T00:00:00Z",
            payload={"_status": "ok", "signature_verified": True, "revision_immutable": True},
            advisory=True,
        )
        verdict = evaluate_gate("G1", [forged])
        self.assertNotEqual(verdict.verdict, "pass")
        # 仍应留痕，便于复核
        self.assertIn("ev-forged", verdict.evidence_refs)

    def test_advisory_evidence_does_not_flip_a_passing_gate(self):
        """挂上情报前后，门禁裁决必须完全一致。"""
        base = ModelApplication(
            application_id="app-no-adv",
            applicant="Engineer A",
            identity=ModelIdentity(model_id="meta-llama/Llama-3.1-8B-Instruct", revision="v3.1"),
            deployment=compliant_deployment(),
        )
        self.store.save(base)
        base = self.orchestrator.run_clearance(base)

        withadv = ModelApplication(
            application_id="app-with-adv",
            applicant="Engineer A",
            identity=ModelIdentity(model_id="meta-llama/Llama-3.1-8B-Instruct", revision="v3.1"),
            deployment=compliant_deployment(),
            contributions=[
                EvidenceContribution(gate="G1", kind="team", ref_id="open_weights", label="开放权重资源团队"),
                EvidenceContribution(gate="G7", kind="team", ref_id="open_weights", label="开放权重资源团队"),
            ],
        )
        self.store.save(withadv)
        withadv = self.orchestrator.run_clearance(withadv)

        self.assertEqual(base.status, withadv.status)
        self.assertEqual(
            [(v.gate, v.verdict) for v in base.verdicts],
            [(v.gate, v.verdict) for v in withadv.verdicts],
        )

    def test_contributions_attach_advisory_evidence_to_the_bound_gate(self):
        app = ModelApplication(
            application_id="app-adv-attach",
            applicant="Engineer A",
            identity=ModelIdentity(model_id="meta-llama/Llama-3.1-8B-Instruct", revision="v3.1"),
            deployment=compliant_deployment(),
            contributions=[
                EvidenceContribution(gate="G1", kind="team", ref_id="open_weights", label="开放权重资源团队"),
            ],
        )
        self.store.save(app)
        app = self.orchestrator.run_clearance(app)

        advisory = [e for e in app.evidence if e.advisory]
        self.assertEqual(len(advisory), 1)
        self.assertEqual(advisory[0].gate, "G1")
        self.assertTrue(advisory[0].collector.startswith("external:team:"))
        self.assertEqual(advisory[0].payload.get("label"), "开放权重资源团队")

    def test_missing_channel_is_recorded_not_silently_dropped(self):
        """情报通道没有文档时必须留一条 missing 记录，不能静默丢弃。"""
        evs = resolve_contributions(
            [EvidenceContribution(gate="G4", kind="team", ref_id="__no_such_channel__")],
            "G4",
        )
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0].advisory)
        self.assertEqual(evs[0].payload.get("_status"), "missing")

    def test_missing_run_is_recorded_not_silently_dropped(self):
        evs = resolve_contributions(
            [EvidenceContribution(gate="G2", kind="run", ref_id="__no_such_run__")],
            "G2",
        )
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0].advisory)
        self.assertEqual(evs[0].payload.get("_status"), "missing")

    def test_digest_keeps_the_collection_and_processing_trace(self):
        """采集/处理阶段是评审人判断情报可信度的依据，不能在摘要时丢掉。"""
        from domain.model_clearance.contributions import _digest_report

        digest = _digest_report({
            "evidence_score": 0.8,
            "reasoning_steps": [
                {"stage": "采集", "status": "ok", "detail": "抓取 26 个源"},
                {"stage": "清洗", "status": "ok", "detail": "去重后 118 条"},
            ],
            "html": "<div>不应出现在证据里</div>",
        })
        self.assertEqual(len(digest["reasoning_steps"]), 2)
        self.assertEqual(digest["reasoning_steps"][0]["stage"], "采集")
        self.assertNotIn("html", digest)

    def test_contributions_survive_persistence_roundtrip(self):
        app = ModelApplication(
            application_id="app-roundtrip",
            applicant="Engineer A",
            identity=ModelIdentity(model_id="meta-llama/Llama-3.1-8B-Instruct", revision="v3.1"),
            contributions=[EvidenceContribution(gate="G2", kind="document", ref_id="doc-1", label="x")],
        )
        self.store.save(app)
        loaded = self.store.get("app-roundtrip")
        self.assertEqual(len(loaded.contributions), 1)
        self.assertEqual(loaded.contributions[0].gate, "G2")
        self.assertEqual(loaded.contributions[0].kind, "document")


class TestContributionApiValidation(unittest.IsolatedAsyncioTestCase):
    """API 层必须拒绝伪造的门禁/来源类型，不能把脏引用写进申请档案。"""

    async def _create(self, contributions):
        from domain.api_routes import ClearanceAppCreate, create_clearance_application

        return await create_clearance_application(
            ClearanceAppCreate(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="v3.1",
                contributions=contributions,
            )
        )

    async def test_rejects_unknown_gate(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            await self._create([{"gate": "G99", "kind": "team", "ref_id": "open_weights"}])
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_rejects_unknown_kind(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            await self._create([{"gate": "G1", "kind": "rootkit", "ref_id": "x"}])
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_accepts_valid_contribution(self):
        app = await self._create(
            [{"gate": "G1", "kind": "team", "ref_id": "open_weights", "label": "开放权重资源团队"}]
        )
        self.assertEqual(len(app["contributions"]), 1)
        self.assertEqual(app["contributions"][0]["gate"], "G1")

    async def test_contributors_endpoint_lists_gates_and_teams(self):
        from domain.api_routes import list_clearance_contributors

        data = await list_clearance_contributors()
        self.assertEqual([g["gate"] for g in data["gates"]], [f"G{i}" for i in range(9)])
        self.assertIn("open_weights", [t["ref_id"] for t in data["teams"]])
        for t in data["teams"]:
            self.assertIn("has_analysis", t)
        # 采集运行过程也必须可组装
        self.assertIn("runs", data)

    async def test_accepts_run_contribution(self):
        app = await self._create([{"gate": "G2", "kind": "run", "ref_id": "run-1", "label": "一次采集"}])
        self.assertEqual(app["contributions"][0]["kind"], "run")


if __name__ == "__main__":
    unittest.main()
