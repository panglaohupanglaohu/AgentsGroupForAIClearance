"""任务界定适应度测试 — 论文 Section 5.3。"""

import pytest

from agents.task_bounded_fitness import (
    FACTORS,
    UsageRecord,
    aggregate_factors,
    compute_fitness,
)


def test_weights_normalized_and_bounded():
    f = {k: 1.0 for k in FACTORS}
    # 负向因子为 1 时 (1-x)=0，因此 exec_cost 和 aging_sensitivity 贡献为 0
    out = compute_fitness(f)
    assert abs(sum(out["weights"].values()) - 1.0) < 1e-9
    assert 0.0 <= out["F"] <= 1.0
    assert out["eval_config_fingerprint"] is not None


def test_failed_runs_are_not_dropped():
    recs = [
        UsageRecord(success=True, reward=1.0, latency_ms=10, cost=0.1, human_intervention=False),
        UsageRecord(success=False, reward=0.8, latency_ms=10, cost=0.1, human_intervention=False),
    ]
    factors = aggregate_factors(recs, schema_quality=1.0)
    assert factors["success_rate"] == 0.5
    # 失败记录 reward 计为 0，平均回报为 (1.0 + 0.0)/2 = 0.5
    assert factors["mean_reward"] == 0.5


def test_reuse_and_aging_calculation():
    recs = [
        UsageRecord(success=True, reward=1.0, latency_ms=10, cost=0.1, human_intervention=False, env_version="v1", team_id="t1"),
        UsageRecord(success=True, reward=1.0, latency_ms=10, cost=0.1, human_intervention=False, env_version="v1", team_id="t2"),
        UsageRecord(success=False, reward=0.0, latency_ms=10, cost=0.1, human_intervention=False, env_version="v2", team_id="t3"),
    ]
    factors = aggregate_factors(recs, schema_quality=0.9, cost_budget=1.0)
    assert factors["reuse_breadth"] == 1.0  # 3 teams / 3 = 1.0
    # v1 rate=1.0, v2 rate=0.0 -> variance = 1.0 - 0.0 = 1.0
    assert factors["aging_sensitivity"] == 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
