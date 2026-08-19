#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run all Model Clearance backend test suites."""

import subprocess
import sys
from pathlib import Path

TEST_SCRIPTS = [
    "scripts/validate_model_registry.py",
    "tests/test_model_clearance_models.py",
    "tests/test_model_clearance_scanners.py",
    "tests/test_clearance_policy.py",
    "tests/test_clearance_agents.py",
    "tests/test_clearance_orchestrator.py",
    "tests/test_clearance_e2e.py",
    "tests/test_runtime_baseline.py",
    "tests/test_clearance_continuous.py",
    "tests/test_workflow_pipeline_mode.py",
]


def main():
    root = Path(__file__).resolve().parents[1]
    py_exec = sys.executable
    all_passed = True

    print("==================================================")
    print(" Running Model Clearance & Admission Test Suites")
    print("==================================================")

    for script in TEST_SCRIPTS:
        full_path = root / script
        rel_name = script
        cmd = [py_exec, str(full_path)]
        res = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  ✅ PASS: {rel_name}")
        else:
            print(f"  ❌ FAIL: {rel_name}")
            print("--- STDOUT ---")
            print(res.stdout)
            print("--- STDERR ---")
            print(res.stderr)
            all_passed = False

    print("==================================================")
    if all_passed:
        print(" 🎉 ALL 10 TEST SUITES PASSED SUCCESSFULLY!")
        return 0
    else:
        print(" ⚠️ SOME TEST SUITES FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
