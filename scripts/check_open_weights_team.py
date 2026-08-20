"""Self-check for the 开放权重资源 team: roster parity + a real pipeline run.

Guards that the team stays a faithful clone of 独夫之心 (same members/skills)
and that its pipeline actually produces a schema-valid, renderable document.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from domain.information_sources.documents import DocumentStore  # noqa: E402
from domain.information_sources.evidence import EvidenceStore  # noqa: E402
from domain.information_sources.hugohe3 import validate_csp_html  # noqa: E402
from domain.information_sources.pipelines import run_team_pipeline  # noqa: E402
from domain.information_sources.report_schemas import validate_report  # noqa: E402
from domain.information_sources.scheduler import ACTIVE_SCHEDULE_TEAMS  # noqa: E402

SRC, DST = "dufu_world_intel", "open_weights"


def check_roster_parity() -> None:
    teams = json.loads((ROOT / "storage" / "teams" / "teams.json").read_text(encoding="utf-8"))
    assert DST in teams, f"{DST} team missing from store"
    src, dst = teams[SRC], teams[DST]

    assert set(src["skills"]) == set(dst["skills"]), "team-level skills must match 独夫之心"
    assert len(src["agents"]) == len(dst["agents"]), "member count must match 独夫之心"

    src_by_role = {a["role"]: a for a in src["agents"].values()}
    dst_by_role = {a["role"]: a for a in dst["agents"].values()}
    assert set(src_by_role) == set(dst_by_role), "roles must match 独夫之心"
    for role, agent in dst_by_role.items():
        assert agent["skills"] == src_by_role[role]["skills"], f"skills differ for role {role}"
        assert agent["name"] == src_by_role[role]["name"], f"display name differs for role {role}"
        assert agent["agent_id"] != src_by_role[role]["agent_id"], f"{role} must have its own agent_id"

    assert dst["team_id"] == DST and dst["metadata"]["pipeline"] == DST
    print(f"[ok] roster parity: {len(dst['agents'])} members, {len(dst['skills'])} skills, independent ids")


def check_registration() -> None:
    assert DST in ACTIVE_SCHEDULE_TEAMS, "open_weights must be schedulable"
    print("[ok] registered in ACTIVE_SCHEDULE_TEAMS")


def check_pipeline_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence = EvidenceStore(Path(tmp) / "evidence")
        docs = DocumentStore(Path(tmp) / "docs")
        result = asyncio.run(
            run_team_pipeline(DST, evidence_store=evidence, document_store=docs)
        )

    assert result["channel"] == DST, result["channel"]
    assert result["evidence_count"] > 0, "pipeline produced no evidence"
    assert result["html_bytes"] > 0, "pipeline produced no HTML"
    steps = [s["step"] for s in result["steps"]]
    assert "license_watch_admission_mapper" in steps, steps
    print(
        f"[ok] pipeline ran: {result['evidence_count']} evidence, "
        f"{result['html_bytes']} html bytes, steps={len(steps)}"
    )

    doc = docs.get_latest(DST) if hasattr(docs, "get_latest") else None
    if doc is not None:
        report = validate_report(DST, doc.report)
        assert report.channel == DST
        assert len(report.scenarios) == 3, "three scenarios required"
        assert report.license_watch and report.admission_impact
        validate_csp_html(doc.html)
        print("[ok] published document is schema-valid and CSP-safe")


check_roster_parity()
check_registration()
check_pipeline_run()
print("ALL CHECKS PASSED")
