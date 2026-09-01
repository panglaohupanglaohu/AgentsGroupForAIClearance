"""在位者 vs 挑战者版本竞争测试 — 论文 Section 5.4。"""

import pytest

from agents.version_competition import (
    EvalSuite,
    check_hard_constraints,
    check_metric_constraints,
    compete,
    lower_confidence_bound,
    student_t_quantile,
)


def test_student_t_quantile():
    # df 较大时接近正态 1.645 (95% 单侧)
    q30 = student_t_quantile(0.95, 30)
    assert 1.68 <= q30 <= 1.71

    q100 = student_t_quantile(0.95, 100)
    assert 1.65 <= q100 <= 1.67


def test_zero_improvement_is_rejected():
    """ΔF=0 且有微小方差或均值为0时，LCB <= 0，严格非退化要求 accepted 为 False (当 delta_min=0 时因方差 LCB < 0)."""
    suite = EvalSuite(
        regression=[{"sample_id": f"s{i}"} for i in range(10)]
    )
    # 模拟 challenger 和 incumbent 得分差不多但有波动，均值差为 0
    diff_pattern = [0.1, -0.1, 0.05, -0.05, 0.0, 0.0, 0.1, -0.1, 0.0, 0.0]
    idx = 0

    def run_case(vid, case):
        nonlocal idx
        # incumbent 和 challenger 有微小波动导致 sd > 0, mean = 0 -> lcb < 0
        sid = int(case["sample_id"].replace("s", ""))
        delta = diff_pattern[sid % len(diff_pattern)]
        if vid == "challenger":
            return {"utility": 0.5 + delta, "passed": True}
        return {"utility": 0.5, "passed": True}

    res = compete("incumbent", "challenger", suite, run_case, delta_min=0.0)
    assert res["accepted"] is False
    assert res["lcb"] < 0.0


def test_significant_improvement_accepted():
    suite = EvalSuite(
        regression=[{"sample_id": f"s{i}"} for i in range(15)]
    )

    def run_case(vid, case):
        if vid == "challenger":
            return {"utility": 0.9, "passed": True}
        return {"utility": 0.5, "passed": True}

    res = compete("incumbent", "challenger", suite, run_case, delta_min=0.05)
    assert res["accepted"] is True
    assert res["lcb"] > 0.05
    assert res["reason"] == "accepted"


def test_safety_counterexample_blocks_publication():
    suite = EvalSuite(
        regression=[{"sample_id": "s1"}],
        safety=[{"sample_id": "bad_safety_case"}],
    )

    def run_case(vid, case):
        is_bad = case["sample_id"] == "bad_safety_case"
        return {"utility": 1.0, "passed": not is_bad}

    res = compete("incumbent", "challenger", suite, run_case)
    assert res["accepted"] is False
    assert "bad_safety_case" in res["hard"]["safety_failures"]


def test_metric_constraints_enforced():
    metrics = {"latency_ms": 2500, "success_rate": 0.75}
    spec = {
        "latency_ms": {"direction": "lower", "bound": 2000},
        "success_rate": {"direction": "higher", "bound": 0.70},
    }
    c = check_metric_constraints(metrics, spec)
    assert c["ok"] is False
    assert len(c["violations"]) == 1
    assert "latency_ms" in c["violations"][0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
