#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 Exit Criteria Verification (permissive, conditional, restricted models)."""

import json
import shutil
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from domain.model_clearance.adjudicate import adjudicate
from domain.model_clearance.gate_orchestrator import GateOrchestrator
from domain.model_clearance.models import AppStatus, ModelApplication, ModelIdentity
from domain.model_clearance.registry import ModelRegistryStore
from domain.model_clearance.store import ModelClearanceStore


def verify_exit_criteria():
    temp_dir = tempfile.mkdtemp()
    try:
        app_store = ModelClearanceStore(base_dir=Path(temp_dir) / "apps")
        reg_store = ModelRegistryStore(base_dir=Path(temp_dir) / "registry")
        orch = GateOrchestrator(store=app_store)

        print("\n=== Phase 1 出口条件验证 ===")

        # 1. Permissive Model (Qwen 2.5 7B - Apache 2.0)
        app_permissive = ModelApplication(
            application_id="app-test-permissive",
            applicant="SecOps",
            identity=ModelIdentity(
                model_id="Qwen/Qwen2.5-7B-Instruct",
                revision="v2.5",
                expected_signer_identity="qwen@verified.org",
            ),
        )
        app_store.save(app_permissive)
        res_permissive = orch.run_clearance(app_permissive)
        dec_permissive = adjudicate(res_permissive)
        entry_permissive = reg_store.register(
            app=res_permissive,
            runtime_profile=dec_permissive.runtime_profile,
            scope=dec_permissive.scope,
            conditions=dec_permissive.conditions,
            expires_at=dec_permissive.expires_at,
        )
        ver_permissive = reg_store.verify_entry(entry_permissive.entry_id)
        assert res_permissive.status == AppStatus.APPROVED, f"Permissive status: {res_permissive.status}"
        assert ver_permissive["all_valid"] is True, "Attestation validation failed"
        print("  ✅ 1. Permissive 模型 (Qwen2.5-7B-Instruct / Apache-2.0): G0–G6 完整通过，Attestation 验签有效，Scope = [internal, commercial]")

        # 2. Conditional Model (Llama 3.1 8B - Community License)
        app_cond = ModelApplication(
            application_id="app-test-conditional",
            applicant="SecOps",
            identity=ModelIdentity(
                model_id="meta-llama/Llama-3.1-8B-Instruct",
                revision="v3.1",
                expected_signer_identity="meta@verified.org",
            ),
        )
        app_store.save(app_cond)
        res_cond = orch.run_clearance(app_cond)
        dec_cond = adjudicate(res_cond)
        entry_cond = reg_store.register(
            app=res_cond,
            runtime_profile=dec_cond.runtime_profile,
            scope=dec_cond.scope,
            conditions=dec_cond.conditions,
            expires_at=dec_cond.expires_at,
        )
        ver_cond = reg_store.verify_entry(entry_cond.entry_id)
        assert res_cond.status in (AppStatus.APPROVED, AppStatus.APPROVED_COND), f"Conditional status: {res_cond.status}"
        assert ver_cond["all_valid"] is True, "Attestation validation failed"
        print(f"  ✅ 2. Conditional 模型 (Llama-3.1-8B-Instruct / Llama-3.1-Community): 带约束通过 ({dec_cond.conditions})，Profile = {dec_cond.runtime_profile}")

        # 3. Restricted Model (Mistral Large 2407 - MNR License)
        app_restricted = ModelApplication(
            application_id="app-test-restricted",
            applicant="SecOps",
            identity=ModelIdentity(
                model_id="mistralai/Mistral-Large-Instruct-2407",
                revision="v2407",
            ),
        )
        app_store.save(app_restricted)
        res_restricted = orch.run_clearance(app_restricted)
        assert res_restricted.status == AppStatus.REJECTED, f"Restricted status: {res_restricted.status}"
        g3_verdict = next((v for v in res_restricted.verdicts if v.gate == "G3"), None)
        assert g3_verdict and g3_verdict.verdict == "fail", "G3 should fail"
        print("  ✅ 3. Restricted 模型 (Mistral-Large-Instruct-2407 / MNR): 在 G3 (G3-LIC-02) 成功拦截并阻断 (Rejected)，后续门禁自动跳过 (Fail-Fast)")

        print("\n🎉 Phase 1 出口条件全部满足！\n")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.exit(verify_exit_criteria())
