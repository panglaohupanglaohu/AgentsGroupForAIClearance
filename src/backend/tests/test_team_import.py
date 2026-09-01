"""外部智能体团队整队导入 — POST /api/v1/agent-config/teams/import。"""

import pytest
from fastapi import HTTPException

from agents.api import ImportTeamRequest, _mask_token, import_team, init_agent_config
from agents.team_manager import TeamManager


@pytest.fixture
def tm(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_TEAMS_STORE_DIR", str(tmp_path))
    manager = TeamManager()
    manager._teams.clear()
    init_agent_config(manager)
    return manager


def _req(**kw):
    base = {
        "name": "外部 SRE 团队",
        "description": "从合作方导入",
        "source": "json",
        "agents": [
            {"name": "SRE-01", "role": "值班工程师", "model_id": "gpt-4o"},
            {"name": "SRE-02", "role": "容量规划"},
        ],
    }
    base.update(kw)
    return ImportTeamRequest(**base)


def test_import_creates_team_with_all_agents(tm):
    out = import_team(_req())
    report = out["report"]

    assert report["agents_imported"] == 2
    assert report["renamed"] is False
    team = tm.get_team(report["team_id"])
    assert team is not None
    assert len(team.agents) == 2
    assert {a.name for a in team.agents.values()} == {"SRE-01", "SRE-02"}


def test_import_resolves_model_ids_from_bundle(tm):
    out = import_team(_req(
        models=[{"provider": "openai", "name": "gpt-4o"}],
        agents=[{"name": "A1", "model_id": "gpt-4o"}],
    ))
    team = tm.get_team(out["report"]["team_id"])

    assert out["report"]["models_imported"] == 1
    agent = list(team.agents.values())[0]
    # model_id 应被换成本地生成的 model_id，而不是原始名字
    assert agent.model_id in team.models
    assert not out["report"]["warnings"]


def test_import_warns_on_dangling_model_reference(tm):
    out = import_team(_req(agents=[{"name": "A1", "model_id": "不存在的模型"}]))
    assert any("不存在的模型" in w for w in out["report"]["warnings"])


def test_duplicate_name_is_renamed_not_overwritten(tm):
    first = import_team(_req())
    second = import_team(_req())

    assert second["report"]["renamed"] is True
    assert second["report"]["name"] == "外部 SRE 团队 (2)"
    assert first["report"]["team_id"] != second["report"]["team_id"]
    assert len(tm.list_teams()) == 2


def test_empty_agents_rejected(tm):
    with pytest.raises(HTTPException) as e:
        import_team(_req(agents=[]))
    assert e.value.status_code == 400
    assert tm.list_teams() == []


def test_agent_count_limit_enforced(tm):
    too_many = [{"name": f"A{i}"} for i in range(101)]
    with pytest.raises(HTTPException) as e:
        import_team(_req(agents=too_many))
    assert e.value.status_code == 400
    # 超限时不得留下半成品团队
    assert tm.list_teams() == []


def test_openclaw_source_requires_gateway_url(tm):
    with pytest.raises(HTTPException) as e:
        import_team(_req(source="openclaw"))
    assert e.value.status_code == 400
    assert tm.list_teams() == []


def test_openclaw_token_is_masked_in_response_and_storage(tm):
    secret = "sk-live-super-secret-value"
    out = import_team(_req(
        source="openclaw",
        openclaw_url="https://gw.example.com",
        openclaw_token=secret,
    ))
    team = tm.get_team(out["report"]["team_id"])

    blob = str(out) + str(team.metadata) + str([a.metadata for a in team.agents.values()])
    assert secret not in blob
    assert team.metadata["import"]["openclaw_token_set"] is True
    assert team.metadata["import"]["openclaw_token"] == "sk-l***"


def test_mask_token_never_leaks_full_value():
    assert _mask_token("") == ""
    assert _mask_token("abc") == "***"
    assert _mask_token("abcdefghij") == "abcd***"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
