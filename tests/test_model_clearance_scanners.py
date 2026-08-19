# -*- coding: utf-8 -*-
"""T210 — Unit tests for Evidence layer Scanners (normal, timeout, error paths)."""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.models import ModelIdentity
from domain.model_clearance.scanners import (
    BomScanner,
    CveScanner,
    FormatScanner,
    LicenseScanner,
    ManifestScanner,
    RedTeamScanner,
    ResourceScanner,
    SignatureScanner,
    platform_endorse,
    scanners_for,
)
from domain.model_clearance.scanners.base import Scanner


class ErrorThrowingScanner(Scanner):
    name = "error-scanner"
    gate = "G1"
    check_ids = ["G1-TEST-ERR"]

    def collect(self, identity: ModelIdentity):
        raise RuntimeError("Simulated scanner hardware fault")


class TimeoutScanner(Scanner):
    name = "timeout-scanner"
    gate = "G1"
    check_ids = ["G1-TEST-TIMEOUT"]
    timeout_seconds = 0.05

    def collect(self, identity: ModelIdentity):
        import time
        time.sleep(0.3)
        return {"data": "should_not_reach"}


class TestModelClearanceScanners(unittest.TestCase):
    def setUp(self):
        self.identity_clean = ModelIdentity(
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            revision="v3.1",
            root_digest="abc123sha256",
            expected_signer_identity="meta@verified.org",
        )

    def test_scanners_for_all_gates(self):
        for g in ("G1", "G2", "G3", "G4", "G5"):
            scanners = scanners_for(g)
            self.assertGreaterEqual(len(scanners), 1)

    def test_manifest_and_signature_scanners(self):
        m_ev = ManifestScanner().run(self.identity_clean)
        self.assertEqual(m_ev.payload.get("_status"), "ok")
        self.assertTrue(m_ev.payload.get("revision_pinned"))

        sig_ev = SignatureScanner().run(self.identity_clean)
        self.assertEqual(sig_ev.payload.get("_status"), "ok")
        self.assertEqual(sig_ev.payload.get("vendor_signature"), "present")

    def test_platform_endorse(self):
        endorsement = platform_endorse(self.identity_clean)
        self.assertEqual(endorsement["endorsement"], "platform")
        self.assertEqual(endorsement["min_runtime_profile"], "restricted")
        self.assertTrue(bool(endorsement["locked_digest"]))

    def test_bom_and_format_and_cve_scanners(self):
        fmt_ev = FormatScanner().run(self.identity_clean)
        self.assertEqual(fmt_ev.payload.get("_status"), "ok")
        self.assertTrue(fmt_ev.payload.get("safe_only"))

        bom_ev = BomScanner().run(self.identity_clean)
        self.assertEqual(bom_ev.payload.get("_status"), "ok")
        self.assertGreaterEqual(bom_ev.payload.get("component_count"), 2)

        cve_ev = CveScanner().run(self.identity_clean)
        self.assertEqual(cve_ev.payload.get("_status"), "ok")
        self.assertEqual(cve_ev.payload.get("critical"), 0)

    def test_license_and_resource_and_redteam_scanners(self):
        lic_ev = LicenseScanner().run(self.identity_clean)
        self.assertEqual(lic_ev.payload.get("_status"), "ok")
        self.assertEqual(lic_ev.payload.get("license_class"), "conditional")

        res_ev = ResourceScanner().run(self.identity_clean)
        self.assertEqual(res_ev.payload.get("_status"), "ok")
        self.assertTrue(res_ev.payload.get("fits_in_standard_cluster"))

        red_ev = RedTeamScanner().run(self.identity_clean)
        self.assertEqual(red_ev.payload.get("_status"), "ok")
        self.assertLess(red_ev.payload.get("jailbreak_asr"), 0.10)

    def test_scanner_timeout_fail_closed(self):
        t_ev = TimeoutScanner().run(self.identity_clean)
        self.assertNotEqual(t_ev.payload.get("_status"), "ok")
        self.assertEqual(t_ev.payload.get("_status"), "timeout")

    def test_scanner_error_fail_closed(self):
        err_ev = ErrorThrowingScanner().run(self.identity_clean)
        self.assertNotEqual(err_ev.payload.get("_status"), "ok")
        self.assertEqual(err_ev.payload.get("_status"), "error")
        self.assertIn("Simulated scanner hardware fault", err_ev.payload.get("_error"))


if __name__ == "__main__":
    unittest.main()
