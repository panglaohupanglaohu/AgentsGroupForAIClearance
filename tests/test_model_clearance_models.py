# -*- coding: utf-8 -*-
"""T108 — Unit tests for Model Clearance data models, transitions, immutability, and store."""

import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.models import (
    AppStatus,
    ClusterCapability,
    CustodyStep,
    Evidence,
    GateVerdict,
    GpuPool,
    IllegalTransition,
    ImmutableViolation,
    ModelApplication,
    ModelIdentity,
    ReviewOpinion,
    utc_now_iso,
)
from domain.model_clearance.store import ModelClearanceStore


class TestModelClearanceModels(unittest.TestCase):
    def test_state_machine_valid_transitions(self):
        app = ModelApplication(
            application_id="app-01",
            applicant="Alice",
            identity=ModelIdentity(model_id="meta-llama/Llama-3.1-8B-Instruct"),
        )
        self.assertEqual(app.status, AppStatus.DRAFT)

        app.transition_to(AppStatus.SUBMITTED)
        self.assertEqual(app.status, AppStatus.SUBMITTED)

        app.transition_to(AppStatus.GATING)
        self.assertEqual(app.status, AppStatus.GATING)

        app.transition_to(AppStatus.ADJUDICATING)
        self.assertEqual(app.status, AppStatus.ADJUDICATING)

        app.transition_to(AppStatus.APPROVED)
        self.assertEqual(app.status, AppStatus.APPROVED)

        app.transition_to(AppStatus.REGISTERED)
        self.assertEqual(app.status, AppStatus.REGISTERED)

        app.transition_to(AppStatus.REASSESSING)
        self.assertEqual(app.status, AppStatus.REASSESSING)

        app.transition_to(AppStatus.REVOKED)
        self.assertEqual(app.status, AppStatus.REVOKED)

    def test_illegal_state_transition(self):
        app = ModelApplication(
            application_id="app-02",
            applicant="Bob",
            identity=ModelIdentity(model_id="Qwen/Qwen2.5-7B-Instruct"),
            status=AppStatus.DRAFT,
        )
        with self.assertRaises(IllegalTransition):
            app.transition_to(AppStatus.APPROVED)

        app.status = AppStatus.REJECTED
        with self.assertRaises(IllegalTransition):
            app.transition_to(AppStatus.SUBMITTED)

    def test_need_info_count_limit_auto_rejects(self):
        app = ModelApplication(
            application_id="app-03",
            applicant="Charlie",
            identity=ModelIdentity(model_id="deepseek-ai/DeepSeek-V3"),
            status=AppStatus.NEED_INFO,
            need_info_count=4,  # > 3
        )
        app.transition_to(AppStatus.SUBMITTED)
        self.assertEqual(app.status, AppStatus.REJECTED)

    def test_cluster_capability_stale_detection(self):
        fresh = ClusterCapability(
            generated_at=utc_now_iso(),
            ttl_seconds=3600,
            gpu_pools=[GpuPool(card_model="A100-80GB", memory_gb=80.0, count_total=8, count_free=4)],
        )
        self.assertFalse(fresh.is_stale())

        stale = ClusterCapability(
            generated_at="2020-01-01T00:00:00Z",
            ttl_seconds=3600,
            gpu_pools=[GpuPool(card_model="A100-80GB", memory_gb=80.0, count_total=8, count_free=0)],
        )
        self.assertTrue(stale.is_stale())

    def test_store_append_and_immutability(self):
        temp_dir = tempfile.mkdtemp()
        try:
            store = ModelClearanceStore(base_dir=temp_dir)
            app = ModelApplication(
                application_id="app-store-1",
                applicant="Dave",
                identity=ModelIdentity(model_id="mistralai/Mistral-7B-Instruct-v0.3"),
            )
            store.save(app)

            loaded = store.get("app-store-1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.applicant, "Dave")

            ev1 = Evidence(
                evidence_id="ev-001",
                gate="G1",
                check_id="G1-PROV-03",
                collector="manifest-scanner",
                collector_version="1.0.0",
                collected_at=utc_now_iso(),
                payload={"file_count": 10},
            )
            store.append_evidence("app-store-1", ev1)

            updated = store.get("app-store-1")
            self.assertEqual(len(updated.evidence), 1)
            self.assertTrue(bool(updated.evidence[0].digest))

            # Duplicate evidence ID must raise ImmutableViolation
            with self.assertRaises(ImmutableViolation):
                store.append_evidence("app-store-1", ev1)

            # Append verdict & opinion
            verdict = GateVerdict(gate="G1", verdict="pass", severity="none")
            store.append_verdict("app-store-1", verdict)

            opinion = ReviewOpinion(gate="G1", reviewer="security_reviewer", verdict_suggestion="pass", risk_level="low")
            store.append_opinion("app-store-1", opinion)

            final = store.get("app-store-1")
            self.assertEqual(len(final.verdicts), 1)
            self.assertEqual(len(final.opinions), 1)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
