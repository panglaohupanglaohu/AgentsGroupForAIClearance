"""生命周期六态与 2-of-3 多数去抖测试 — 论文 Section 5.6。"""

import pytest

from agents.models import LIFECYCLE_TRANSITIONS, SkillLifecycleStage
from agents.skill_classifier import (
    Classification,
    classify_with_history,
)


def test_lifecycle_stages_and_transitions():
    assert SkillLifecycleStage.DRAFT.value == "draft"
    assert SkillLifecycleStage.REVISION.value == "revision"
    assert SkillLifecycleStage.READY.value == "ready"
    assert SkillLifecycleStage.PUBLISHED.value == "published"
    assert SkillLifecycleStage.DEGRADED.value == "degraded"
    assert SkillLifecycleStage.DEPRECATED.value == "deprecated"

    assert "ready" in LIFECYCLE_TRANSITIONS["draft"]
    assert "published" in LIFECYCLE_TRANSITIONS["ready"]
    assert "degraded" in LIFECYCLE_TRANSITIONS["published"]
    assert len(LIFECYCLE_TRANSITIONS["deprecated"]) == 0


def test_two_of_three_majority_debounce():
    # 构造初始为 reserve 的记录
    record = {"classification": "reserve", "window": ["reserve"]}

    # 第1次: 表现达到 general，但窗口为 ['reserve', 'general']，general 只有1次 -> 保持 reserve
    skill_good = {
        "effectiveness": 0.9,
        "adopted_by": ["team1", "team2", "team3"],
        "origin_team_id": "team1",
        "lifecycle_stage": "verified",
    }
    usage_good = {"team_usage": {"team1": 10, "team2": 5}}
    trial_good = {"gate_ok": True, "meets_rubric": True}

    res1 = classify_with_history(record, skill_good, usage_good, trial_good)
    assert res1["classification"] == "reserve"
    assert res1["raw_classification"] == "general"
    assert res1["event"] is None

    # 第2次: 再次达到 general，窗口为 ['reserve', 'general', 'general']，general 达到 2 次 -> 跃迁为 general
    res2 = classify_with_history(res1, skill_good, usage_good, trial_good)
    assert res2["classification"] == "general"
    assert res2["event"] is not None
    assert res2["event"]["type"] == "graduate"
    assert res2["event"]["rule"] == "2-of-3-majority"


def test_safety_violation_bypasses_debounce():
    record = {"classification": "general", "window": ["general", "general"]}
    skill_dangerous = {
        "effectiveness": 0.9,
        "safety_violation": True,  # 安全违规
    }
    res = classify_with_history(record, skill_dangerous)
    assert res["classification"] == "reserve"
    assert res["event"] is not None
    assert res["event"]["rule"] == "safety_bypass_debounce"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
