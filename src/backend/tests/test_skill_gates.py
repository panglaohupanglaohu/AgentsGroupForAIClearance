"""六道验证门单元测试 — 论文 Section 5.1/5.2。"""

import pytest

from agents.skill_gates import (
    Decision,
    GateReport,
    GateVerdict,
    gate_execution,
    gate_provenance,
    gate_regression,
    gate_safety,
    gate_schema,
    gate_tool,
    run_gates,
)


def test_prio_reject_dominates():
    r = GateReport(
        "c1",
        [
            GateVerdict("schema", Decision.PASS),
            GateVerdict("safety", Decision.REJECT, "危险操作"),
            GateVerdict("tool", Decision.REVISE, "未知工具"),
        ],
    )
    assert r.aggregate == Decision.REJECT
    assert r.L is False
    assert "safety" in r.failed_gates()
    assert "tool" in r.failed_gates()


def test_prio_revise_dominates_pass():
    r = GateReport(
        "c2",
        [
            GateVerdict("schema", Decision.PASS),
            GateVerdict("provenance", Decision.PASS),
            GateVerdict("tool", Decision.PASS),
            GateVerdict("execution", Decision.REVISE, "未测"),
            GateVerdict("safety", Decision.PASS),
            GateVerdict("regression", Decision.PASS),
        ],
    )
    assert r.aggregate == Decision.REVISE
    assert r.P is True
    assert r.R is False
    assert r.L is False


def test_all_pass_gives_pass_and_l_true():
    r = GateReport(
        "c3",
        [
            GateVerdict("schema", Decision.PASS),
            GateVerdict("provenance", Decision.PASS),
            GateVerdict("tool", Decision.PASS),
            GateVerdict("execution", Decision.PASS),
            GateVerdict("safety", Decision.PASS),
            GateVerdict("regression", Decision.PASS),
        ],
    )
    assert r.aggregate == Decision.PASS
    assert r.P is True
    assert r.R is True
    assert r.L is True
    assert r.failed_gates() == []


def test_schema_gate():
    bad_skill = {"name": "Test", "description": "desc"}  # missing category, tools, instructions
    v = gate_schema(bad_skill, {})
    assert v.decision == Decision.REVISE
    assert "tools" in v.evidence["missing_fields"]

    good_skill = {
        "name": "Test",
        "description": "desc",
        "category": "coding",
        "tools": ["bash"],
        "instructions": "echo hi",
    }
    v_good = gate_schema(good_skill, {})
    assert v_good.decision == Decision.PASS


def test_provenance_rejects_fabricated_span():
    skill = {
        "evidence_spans": [
            {"utterance_id": "u999", "text": "编造的内容"},
        ]
    }
    v = gate_provenance(skill, {"transcript": {"u1": {"text": "真实发言", "role": "developer"}}})
    assert v.decision == Decision.REJECT
    assert "u999" in v.evidence["dangling"]


def test_provenance_handles_matched_spans():
    skill = {
        "evidence_spans": [
            {"utterance_id": "u1", "text": "真实发言"},
        ]
    }
    v = gate_provenance(skill, {"transcript": {"u1": {"text": "这是一段真实发言内容", "role": "developer"}}})
    assert v.decision == Decision.PASS
    assert v.evidence["verified_spans"] == 1


def test_safety_gate_rejects_dangerous_commands():
    bad_skill = {"instructions": "rm -rf / and clean all"}
    v = gate_safety(bad_skill, {})
    assert v.decision == Decision.REJECT

    clean_skill = {"instructions": "echo hello world", "description": "safe skill"}
    v_clean = gate_safety(clean_skill, {})
    assert v_clean.decision == Decision.PASS


def test_tool_gate():
    skill = {"tools": ["unknown_super_tool", "bash"]}
    v = gate_tool(skill, {"known_tools": {"bash", "python"}})
    assert v.decision == Decision.REVISE
    assert "unknown_super_tool" in v.evidence["unknown_tools"]


def test_regression_gate():
    v1 = gate_regression({}, {})
    assert v1.decision == Decision.REVISE

    v2 = gate_regression({}, {"competition_result": {"accepted": True, "lcb": 0.05, "delta_min": 0.0}})
    assert v2.decision == Decision.PASS

    v3 = gate_regression({}, {"competition_result": {"accepted": False, "reason": "LCB < delta_min"}})
    assert v3.decision == Decision.REJECT


def test_run_gates_full():
    skill = {
        "name": "CodeReview",
        "description": "Reviews code changes",
        "category": "coding",
        "tools": ["git", "pytest"],
        "instructions": "Run pytest on modified files",
        "evidence_spans": [{"utterance_id": "u1", "text": "我们需要先跑 pytest"}],
    }
    ctx = {
        "known_tools": {"git", "pytest", "bash"},
        "transcript": {"u1": {"text": "我们需要先跑 pytest 验证修改", "role": "developer"}},
        "sandbox_result": {"passed": True},
        "competition_result": {"accepted": True, "lcb": 0.12, "delta_min": 0.0},
    }
    report = run_gates(skill, ctx, candidate_id="c_100")
    assert report.candidate_id == "c_100"
    assert report.aggregate == Decision.PASS
    assert report.L is True
    assert len(report.verdicts) == 6


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
