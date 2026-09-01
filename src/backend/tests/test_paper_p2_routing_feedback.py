"""P2-8 CHALLENGE 议程路由 + P2-9 生态证据回流 — 论文 Eq.(3)(4) / §5.7。"""

import json

import pytest

from agents.plaza_challenge_routing import (
    MAX_PHASE_RUNS,
    ChallengeRouter,
    build_revisit_notice,
    phase_name,
    phase_number,
    route_challenge,
)
from sandbox.eco_feedback import (
    build_next_agenda,
    extract_persistence_evidence,
    load_evidence,
    save_evidence,
)


# ── P2-8 ──────────────────────────────────────────────────

def test_phase_name_number_roundtrip():
    for n in (1, 2, 3, 4):
        assert phase_number(phase_name(n)) == n
    assert phase_name(99) == "decisional"
    assert phase_number("nonsense") == 1


def test_only_challenge_routes():
    assert route_challenge("interpretive", "middle", "agree") is None
    assert route_challenge("interpretive", "middle", "supplement") is None
    assert route_challenge("interpretive", "middle", "challenge") == "reflective"


def test_ring_decides_target():
    assert route_challenge("decisional", "inner", "challenge") == "objective"
    assert route_challenge("decisional", "middle", "challenge") == "reflective"
    assert route_challenge("decisional", "outer", "challenge") == "interpretive"


def test_never_routes_forward_or_sideways():
    # 外环目标是 interpretive；在 objective/reflective 阶段不得向前跳
    assert route_challenge("objective", "outer", "challenge") is None
    assert route_challenge("reflective", "outer", "challenge") is None
    # 同阶段不算回退
    assert route_challenge("reflective", "middle", "challenge") is None


def test_unknown_ring_is_ignored():
    assert route_challenge("decisional", "", "challenge") is None
    assert route_challenge("decisional", "galaxy", "challenge") is None


def test_router_budget_exhausts_and_terminates():
    r = ChallengeRouter()
    assert r.route("decisional", "inner", "challenge") == "objective"
    assert r.route("decisional", "inner", "challenge") == "objective"
    # 第三次超预算 → 拒绝路由，保证收敛
    assert r.route("decisional", "inner", "challenge") is None
    assert r.budget_left("decisional", "objective") == 0
    assert len(r.applied_routes()) == 2
    assert r.routes[-1]["reason"] == "budget_exhausted"


def test_router_budget_is_per_pair():
    r = ChallengeRouter()
    r.route("decisional", "inner", "challenge")
    r.route("decisional", "inner", "challenge")
    # 另一组 (from, target) 仍有独立预算
    assert r.route("decisional", "middle", "challenge") == "reflective"


def test_max_phase_runs_bounds_the_loop():
    # 4 个正常阶段 + 每对最多 2 次回退 × 3 组
    assert MAX_PHASE_RUNS == 10


def test_revisit_notice_mentions_target_layer():
    msg = build_revisit_notice("reflective", "middle", "这个回滚边界没说清")
    assert "风险直觉" in msg and "中环" in msg


# ── P2-9 ──────────────────────────────────────────────────

def _drill_result():
    return {
        "trial_id": "t-1",
        "best_survival_ticks": 86,
        "total_generations": 2,
        "final_ranking": [
            {"agent_id": "a1", "population": "aws-ops", "survival_ticks": 86,
             "alive": True, "skill_genome": ["es_scale", "cost_gov"]},
            {"agent_id": "a2", "population": "aws-ops", "survival_ticks": 61,
             "alive": False, "skill_genome": ["cost_gov"]},
            {"agent_id": "a3", "population": "aws-ops", "survival_ticks": 60,
             "alive": False, "skill_genome": ["es_scale", "cost_gov"]},  # 重复组合
        ],
        "gene_pool": {
            "dominant": [{"skill": "cost_gov", "carriers": 2, "freq": 0.9}],
            "neutral": [{"skill": "es_scale", "carriers": 1, "freq": 0.3}],
            "deprecated": [{"skill": "legacy_tf", "carriers": 4, "freq": 0.0}],
        },
        "integration": {"missing_plan_skills": ["rollback_drill"]},
        "env": {"abundance": 0.55, "predator_pressure": 0.1,
                "niche_capacity": 3, "demanded_skills": ["cost_gov", "monitor_rb"]},
    }


def test_extract_dedups_combinations_and_keeps_survival():
    ev = extract_persistence_evidence(_drill_result())
    combos = ev["persistent_combinations"]
    assert [c["skills"] for c in combos] == [["cost_gov", "es_scale"], ["cost_gov"]]
    assert combos[0]["survival_ticks"] == 86 and combos[0]["alive"] is True


def test_uncovered_merges_plan_gap_and_uncarried_demand():
    ev = extract_persistence_evidence(_drill_result())
    # rollback_drill 来自计划缺口；monitor_rb 是无人携带的环境需求
    assert ev["uncovered_demands"] == ["rollback_drill", "monitor_rb"]
    # cost_gov 有人携带，不应被算作未覆盖
    assert "cost_gov" not in ev["uncovered_demands"]


def test_recurrent_failures_from_deprecated_pool():
    ev = extract_persistence_evidence(_drill_result())
    assert ev["recurrent_failures"] == [{"skill": "legacy_tf", "dead_carriers": 4}]


def test_extract_tolerates_empty_result():
    ev = extract_persistence_evidence({})
    assert ev["persistent_combinations"] == []
    assert ev["uncovered_demands"] == []
    assert ev["best_survival_ticks"] == 0


def test_agenda_contains_three_evidence_classes():
    agenda = build_next_agenda(extract_persistence_evidence(_drill_result()))
    assert "持续留存组合" in agenda
    assert "未覆盖需求" in agenda
    assert "反复失败" in agenda
    assert "资源丰度 0.55" in agenda
    assert build_next_agenda({}) == ""


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_ECO_FEEDBACK_DIR", str(tmp_path))
    ev = extract_persistence_evidence(_drill_result())
    path = save_evidence("aws-ops", ev)
    assert path is not None and path.exists()
    assert load_evidence("aws-ops")["best_survival_ticks"] == 86
    assert load_evidence("never-drilled") == {}


def test_load_survives_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_ECO_FEEDBACK_DIR", str(tmp_path))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert load_evidence("broken") == {}


def test_team_id_is_path_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_ECO_FEEDBACK_DIR", str(tmp_path))
    save_evidence("../../etc/passwd", {"x": 1})
    assert not (tmp_path.parent.parent / "etc").exists()
    assert list(tmp_path.glob("*.json"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
