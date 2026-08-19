# -*- coding: utf-8 -*-
"""T606 — Unit tests for Runtime Baseline Conformance & Invariants Validator."""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.registry import ApprovedRegistryEntry
from domain.model_clearance.runtime_baseline import check_baseline, preflight_verify_weights


def make_valid_pod_dict(locked_digest: str = "sha256-abc123456789") -> dict:
    return {
        "metadata": {"name": "model-pod-01", "namespace": "model-serving"},
        "spec": {
            "automountServiceAccountToken": False,
            "hostNetwork": False,
            "hostPID": False,
            "hostIPC": False,
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 10001,
            },
            "containers": [
                {
                    "name": "inference",
                    "image": "registry.internal/ai/inference-base@sha256:4f8d9b6e12a4b5c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1",
                    "securityContext": {
                        "readOnlyRootFilesystem": True,
                        "allowPrivilegeEscalation": False,
                        "privileged": False,
                        "capabilities": {"drop": ["ALL"]},
                    },
                    "env": [
                        {"name": "DISABLE_PROMPT_LOGGING", "value": "true"},
                        {"name": "MODEL_LOCKED_DIGEST", "value": locked_digest},
                    ],
                    "resources": {
                        "limits": {"cpu": "16", "memory": "64Gi"},
                    },
                }
            ],
        },
    }


class TestRuntimeBaseline(unittest.TestCase):
    def setUp(self):
        self.entry = ApprovedRegistryEntry(
            entry_id="reg-001",
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            revision="v3.1",
            locked_digest="sha256-abc123456789",
            decision_ref="att://01",
            scope=["internal"],
            conditions=[],
            runtime_profile="standard",
            approved_at="2026-08-20T00:00:00Z",
            reassessment_due="2026-11-20T00:00:00Z",
        )

    def test_compliant_pod_has_zero_violations(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        violations = check_baseline(pod, self.entry, namespace_has_deny_all=True)
        self.assertEqual(violations, [])

    def test_run_as_root_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        pod["spec"]["securityContext"]["runAsNonRoot"] = False
        pod["spec"]["securityContext"]["runAsUser"] = 0
        violations = check_baseline(pod, self.entry)
        self.assertIn("runAsNonRoot", violations)
        self.assertIn("nonRootUser", violations)

    def test_read_write_root_fs_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        pod["spec"]["containers"][0]["securityContext"]["readOnlyRootFilesystem"] = False
        violations = check_baseline(pod, self.entry)
        self.assertIn("readOnlyRootFs", violations)

    def test_privileged_and_escalation_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        pod["spec"]["containers"][0]["securityContext"]["allowPrivilegeEscalation"] = True
        pod["spec"]["containers"][0]["securityContext"]["privileged"] = True
        violations = check_baseline(pod, self.entry)
        self.assertIn("noPrivEscalation", violations)
        self.assertIn("notPrivileged", violations)

    def test_host_namespace_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        pod["spec"]["hostNetwork"] = True
        violations = check_baseline(pod, self.entry)
        self.assertIn("noHostNamespaces", violations)

    def test_unpinned_image_tag_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        pod["spec"]["containers"][0]["image"] = "registry.internal/ai/inference-base:latest"
        violations = check_baseline(pod, self.entry)
        self.assertIn("imagePinnedByDigest", violations)

    def test_weight_digest_mismatch_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        violations = check_baseline(
            pod,
            self.entry,
            runtime_weight_digest="sha256-tampered-weights-digest",
        )
        self.assertIn("weightDigestMismatch", violations)

    def test_missing_deny_all_network_policy_detected(self):
        pod = make_valid_pod_dict(self.entry.locked_digest)
        violations = check_baseline(pod, self.entry, namespace_has_deny_all=False)
        self.assertIn("missingDenyAllNetworkPolicy", violations)


if __name__ == "__main__":
    unittest.main()
