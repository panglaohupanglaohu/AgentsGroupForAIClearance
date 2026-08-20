"""Seed the 开放权重资源 team by cloning 独夫之心 verbatim.

The user's requirement is that members and their skills are IDENTICAL to
dufu_world_intel, so this deep-copies the team and rewrites only the identity
fields (team id, agent ids, bus channel, pipeline tag, display strings).
Idempotent: rerunning replaces the generated team without touching others.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAMS = ROOT / "storage" / "teams" / "teams.json"

SRC_ID = "dufu_world_intel"
DST_ID = "open_weights"
SRC_PREFIX = "dufu_"
DST_PREFIX = "ow_"

DST_NAME = "开放权重资源团队"
DST_DESC = (
    "开放权重模型生态采集、许可证与合规抽取、红队反证与动态 HTML 呈现。"
    "产物：模型发布 → 时间线 → 生态驱动 → 规模/成本数据 → 观点/反证 → 情景 → 准入影响路径 → 引用。"
)

# Only identity/topic wording is rewritten; roles, skills and tools are cloned as-is.
PROMPT_REPLACEMENTS = [
    ("独夫之心世界趋势团队", "开放权重资源团队"),
    ("世界趋势", "开放权重模型生态"),
    ("从公开多语言来源建立世界趋势时间线、因果链、反证与市场传导路径",
     "从公开来源建立开放权重模型发布时间线、许可证与合规线索、反证与准入影响路径"),
]


def rewrite_text(value: str) -> str:
    for old, new in PROMPT_REPLACEMENTS:
        value = value.replace(old, new)
    return value


def main() -> int:
    if not TEAMS.exists():
        print(f"FAIL: {TEAMS} not found")
        return 1

    data = json.loads(TEAMS.read_text(encoding="utf-8"))
    if SRC_ID not in data:
        print(f"FAIL: source team {SRC_ID} not in store")
        return 1

    team = copy.deepcopy(data[SRC_ID])
    team["team_id"] = DST_ID
    team["name"] = DST_NAME
    team["description"] = DST_DESC
    team.setdefault("metadata", {})
    team["metadata"]["pipeline"] = DST_ID
    team["metadata"]["cloned_from"] = SRC_ID

    agents = {}
    for old_id, agent in team.get("agents", {}).items():
        new_id = old_id.replace(SRC_PREFIX, DST_PREFIX, 1) if old_id.startswith(SRC_PREFIX) else f"{DST_PREFIX}{old_id}"
        agent = copy.deepcopy(agent)
        agent["agent_id"] = new_id
        if isinstance(agent.get("system_prompt"), str):
            agent["system_prompt"] = rewrite_text(agent["system_prompt"])
        if isinstance(agent.get("description"), str):
            agent["description"] = rewrite_text(agent["description"])
        for ch in agent.get("channels") or []:
            for key in ("channel", "channel_name"):
                if isinstance(ch.get(key), str):
                    ch[key] = ch[key].replace(SRC_ID, DST_ID)
        for perm in agent.get("permissions") or []:
            if perm.get("agent_id"):
                perm["agent_id"] = new_id
        agents[new_id] = agent
    team["agents"] = agents

    existed = DST_ID in data
    data[DST_ID] = team
    tmp = TEAMS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(TEAMS)

    src_skills = set(data[SRC_ID].get("skills") or {})
    dst_skills = set(team.get("skills") or {})
    assert src_skills == dst_skills, "team-level skills must match the source team"
    for old_id, agent in data[SRC_ID]["agents"].items():
        new_id = old_id.replace(SRC_PREFIX, DST_PREFIX, 1)
        assert agents[new_id]["skills"] == agent["skills"], f"skills differ for {new_id}"
        assert agents[new_id]["role"] == agent["role"], f"role differs for {new_id}"

    print(f"{'updated' if existed else 'created'} team {DST_ID}: {len(agents)} agents, {len(dst_skills)} skills")
    for aid, agent in agents.items():
        print(f"  {aid:<24} {agent['name']:<16} {agent['role']:<14} skills={','.join(agent['skills'])}")
    return 0


sys.exit(main())
