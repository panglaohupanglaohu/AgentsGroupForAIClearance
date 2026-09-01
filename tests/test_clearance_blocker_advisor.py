# -*- coding: utf-8 -*-
"""Blocker 分析建议的最小可运行校验。"""

import asyncio
import json
import unittest

from domain.model_clearance.blocker_advisor import (
    advise_blockers,
    build_gate_request,
    parse_advisories,
)
from domain.model_clearance.assurance_record import build_assurance_record
from domain.model_clearance.models import (
    Evidence,
    GateVerdict,
    ModelApplication,
    ModelIdentity,
    utc_now_iso,
)
from domain.model_clearance.policy_evaluator import load_policy


def _app():
    return ModelApplication(
        application_id="app-adv-1",
        applicant="tester",
        identity=ModelIdentity(model_id="acme/open-7b", revision="v1.2"),
        evidence=[Evidence(
            evidence_id="ev-g7",
            gate="G7",
            check_id="G7-USE-01",
            collector="usecase-data-legal",
            collector_version="1.0.0",
            collected_at=utc_now_iso(),
            payload={"_status": "ok", "intended_use_documented": False,
                     "additional_assessment_satisfied": False},
        )],
        verdicts=[GateVerdict(gate="G7", verdict="fail", severity="blocker",
                              failed_checks=["G7-USE-01"])],
    )


class TestBlockerAdvisor(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def test_request_carries_facts_for_every_blocker(self):
        req = build_gate_request("G7", _app(), self.policy)
        ids = [c["check_id"] for c in req["blocker_checks"]]
        self.assertEqual(sorted(ids), ["G7-LIC-02", "G7-USE-01"])
        self.assertEqual(
            next(c for c in req["blocker_checks"] if c["check_id"] == "G7-USE-01")["result"],
            "fail",
        )
        # 证据必须随事实集一起给出，否则模型只能靠猜
        self.assertIn("intended_use_documented", req["observed_evidence"])

    def test_gate_without_verdict_is_skipped(self):
        self.assertIsNone(build_gate_request("G0", _app(), self.policy))

    def test_verdict_fields_from_llm_are_discarded(self):
        """本模块最危险的失效模式：让模型的判定渗进裁决。"""
        req = build_gate_request("G7", _app(), self.policy)
        raw = json.dumps([{
            "check_id": "G7-USE-01",
            "result": "pass",
            "verdict": "approved",
            "severity": "none",
            "analysis": "附加评估缺失",
            "recommendation": "补齐 §10.2 评估",
            "risk_if_ignored": "面向客户用途不可放行",
        }], ensure_ascii=False)
        advs = parse_advisories("G7", req, raw, "test/model")
        a = next(x for x in advs if x.check_id == "G7-USE-01")
        self.assertEqual(a.result, "fail")          # 取自门禁，不取自模型
        self.assertTrue(a.advisory)
        self.assertEqual(a.analysis, "附加评估缺失")
        self.assertNotIn("verdict", a.to_dict())

    def test_unparseable_reply_still_yields_one_row_per_blocker(self):
        req = build_gate_request("G7", _app(), self.policy)
        advs = parse_advisories("G7", req, "模型今天不想回答", "test/model")
        self.assertEqual(len(advs), 2)
        self.assertTrue(all(a.analysis == "" for a in advs))

    def test_llm_failure_is_recorded_not_swallowed(self):
        async def boom(_messages):
            raise RuntimeError("upstream 502")

        advs = asyncio.run(advise_blockers(_app(), policy=self.policy, llm=boom))
        self.assertTrue(advs)
        self.assertTrue(all(a.error for a in advs))
        self.assertTrue(all(a.generated_by == "unavailable" for a in advs))

    def test_advisory_lands_on_the_matching_check_in_the_report(self):
        async def fake(_messages):
            return json.dumps([{
                "check_id": "G7-USE-01",
                "analysis": "缺少 §10.2 附加评估",
                "recommendation": "补交产品与用例评估后重跑 G7",
                "risk_if_ignored": "面向客户用途无法批准",
            }], ensure_ascii=False), "test/model"

        app = _app()
        app.blocker_advisories = asyncio.run(
            advise_blockers(app, policy=self.policy, llm=fake)
        )
        rec = build_assurance_record(app, self.policy)
        g7 = next(m for m in rec["methodology_and_results"] if m["gate"] == "G7")
        target = next(c for c in g7["checks"] if c["check_id"] == "G7-USE-01")
        self.assertEqual(target["advisory"]["recommendation"], "补交产品与用例评估后重跑 G7")
        # 非阻断项不挂建议
        self.assertIsNone(
            next(c for c in g7["checks"] if c["check_id"] == "G7-USE-02")["advisory"]
        )

    def test_advisories_survive_serialization(self):
        async def fake(_messages):
            return json.dumps([{"check_id": "G7-USE-01", "analysis": "x",
                                "recommendation": "y", "risk_if_ignored": "z"}]), "test/model"

        app = _app()
        app.blocker_advisories = asyncio.run(advise_blockers(app, policy=self.policy, llm=fake))
        restored = ModelApplication.from_dict(app.to_dict())
        self.assertEqual(len(restored.blocker_advisories), len(app.blocker_advisories))
        self.assertEqual(restored.blocker_advisories[0].check_id,
                         app.blocker_advisories[0].check_id)


if __name__ == "__main__":
    unittest.main()
