"""DART-Net 命名装配、12-Niche 三环与共识公式测试 — 论文 Section 4.2 / 4.4 / Eq.(5) / Eq.(8)。"""

import pytest

from agents.plaza import NICHE_RINGS, ring_of, role_coverage
from agents.plaza_consensus import FistToFiveVote, collect_fist_to_five
from agents.tse.dartnet import DARTNet, forward_dartnet, receptive_field


def test_receptive_field_formula():
    # 论文 Eq.(8): R_L = 1 + (k - 1)(2^L - 1)
    # k=3, L=3 -> 1 + 2 * 7 = 15
    assert receptive_field(k=3, layers=3) == 15
    assert receptive_field(k=3, layers=1) == 3
    assert receptive_field(k=3, layers=2) == 7


def test_dartnet_forward():
    text = (
        "## 议题：构建 Docker 部署流水线\n"
        "- **架构师** (architect): 我们需要定义分步流程\n"
        "- **开发人员** (developer): 第一步拉取代码，第二步构建镜像\n"
        "- **QA** (qa_engineer): 必须有完整的回归测试步骤\n"
    )
    stages_out, timings = forward_dartnet(text)
    assert "embeddings" in stages_out
    assert "temporal" in stages_out
    assert "skill_repr" in stages_out
    assert "total_forward_ms" in timings
    assert timings["total_forward_ms"] > 0


def test_12_niche_rings_mapping():
    assert ring_of("goal") == "inner"
    assert ring_of("tool") == "inner"
    assert ring_of("step") == "inner"
    assert ring_of("precondition") == "inner"

    assert ring_of("detection") == "middle"
    assert ring_of("failure_mode") == "middle"
    assert ring_of("risk") == "middle"
    assert ring_of("rollback") == "middle"

    assert ring_of("provenance") == "outer"
    assert ring_of("version") == "outer"
    assert ring_of("audit") == "outer"
    assert ring_of("change") == "outer"

    assert ring_of("unknown_niche") == "outer"


def test_role_coverage_metric():
    required = {"goal", "tool", "risk", "rollback"}
    activated = {"goal", "tool", "risk", "rollback"}
    assert role_coverage(required, activated) == 1.0

    partial = {"goal", "tool"}
    assert role_coverage(required, partial) == 0.5


def test_fist_to_five_consensus_formula():
    # 1. 强共识: 无 1 指, 平均 >= 4.0, rho >= 0.8
    votes_strong = [
        FistToFiveVote("a1", "Alice", 5),
        FistToFiveVote("a2", "Bob", 4),
        FistToFiveVote("a3", "Charlie", 4),
    ]
    res_strong = collect_fist_to_five(votes_strong)
    assert res_strong.consensus_reached is True
    assert res_strong.consensus_level == "strong"
    assert res_strong.rho == 1.0
    assert res_strong.mu >= 4.0

    # 2. 阻塞: 出现 1 指
    votes_blocked = [
        FistToFiveVote("a1", "Alice", 5),
        FistToFiveVote("a2", "Bob", 5),
        FistToFiveVote("a3", "Charlie", 1, reason="根本性反对"),
    ]
    res_blocked = collect_fist_to_five(votes_blocked)
    assert res_blocked.consensus_reached is False
    assert res_blocked.consensus_level == "blocked"
    assert "a3" in res_blocked.blocking_agents


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
