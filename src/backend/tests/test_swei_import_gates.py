"""SWEI 导入五道具名门测试 — 论文 Eq.(25)。"""

from pathlib import Path
import pytest

from agents.agent_memory_migration import (
    EXPORT_SCHEMA_V2,
    build_export_v2,
    evaluate_import_gates,
)
from agents.agent_memory_core import AgentMemoryCore, AgentMemoryStore


def _seed(core: AgentMemoryCore, tag: str) -> None:
    core.log.append({
        "action": f"决策{tag}",
        "detail": f"关键扩容决策 {tag}",
        "importance": 8,
        "tags": ["扩容", tag],
    })
    core.perception.perceive({"modality": "system", "payload": f"alert-{tag}"})
    core.intentions.add({"instruction": f"复查 RI {tag}", "trigger": "周一"})
    core.semantic.add(f"规则-{tag}", strength=0.6, tags=[tag])
    core.affect.feel("谨慎", 1.0, valence=-0.2, arousal=0.4)


def test_import_gates_pass_on_valid_bundle(tmp_path: Path):
    store = AgentMemoryStore(tmp_path)
    core = AgentMemoryCore("team1", "agent1", store=store)
    _seed(core, "initial")
    bundle = build_export_v2(core)

    will = {
        "beneficiary": "agent2",
        "layers": ["log", "perception", "intentions", "affect", "semantic"],
        "strategy": {"log": "merge", "semantic": "merge"},
    }
    target_state = {"agent_id": "agent2", "team_id": "team1"}

    res = evaluate_import_gates(bundle, will=will, target_state=target_state)
    assert res["ok"] is True
    assert res["failed_gates"] == []
    for gname in ("scope", "schema", "integrity", "provenance", "conflict"):
        assert res["gates"][gname]["ok"] is True


def test_import_gates_catch_scope_and_provenance_violations(tmp_path: Path):
    store = AgentMemoryStore(tmp_path)
    core = AgentMemoryCore("team1", "agent1", store=store)
    _seed(core, "test")
    bundle = build_export_v2(core)

    # 1. 范围越界
    will_narrow = {
        "beneficiary": "agent2",
        "layers": ["log"],  # bundle 含更多层
        "strategy": "merge",
    }
    res_scope = evaluate_import_gates(bundle, will=will_narrow, target_state={"agent_id": "agent2"})
    assert res_scope["ok"] is False
    assert "scope" in res_scope["failed_gates"]

    # 2. 受益人身份不匹配
    will_wrong_beneficiary = {
        "beneficiary": "agent_authorized",
        "layers": ["log", "perception", "intentions", "affect", "semantic"],
        "strategy": "merge",
    }
    res_prov = evaluate_import_gates(bundle, will=will_wrong_beneficiary, target_state={"agent_id": "agent_attacker"})
    assert res_prov["ok"] is False
    assert "provenance" in res_prov["failed_gates"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

