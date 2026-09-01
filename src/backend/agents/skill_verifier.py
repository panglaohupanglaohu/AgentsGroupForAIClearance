# -*- coding: utf-8 -*-
"""技能验证框架 — 自动生成测试场景 → 沙箱执行 → 评估 pass_rate.

对应 SkillClaw: Verification In the Wild.
状态 badge: 🔵未验证 / 🟡测试中 / ✅已验证 / ❌验证失败
"""

from __future__ import annotations

import logging
import json
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import SkillDefinition, SkillLifecycleStage
from .domain_events import DomainEvent, EventType, SkillSnapshot
from .event_bus import get_event_bus

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACT_ROOT = _REPO_ROOT / "storage" / "skill_verifications"


@dataclass
class VerificationResult:
    """单次验证结果."""
    skill_id: str = ""
    pass_rate: float = 0.0
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    test_details: List[Dict[str, Any]] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # pending / testing / verified / failed
    error_detail: str = ""
    process_log: List[Dict[str, Any]] = field(default_factory=list)
    runtime_mode: str = ""
    runtime_ready: bool = False
    docker_image: str = ""
    command: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    artifact_dir: str = ""
    evidence_run_id: str = ""
    verification_evidence: Dict[str, Any] = field(default_factory=dict)
    # P4.1: Token Gate 字段
    tokens_consumed: int = 0
    run_id: str = ""
    gate: Dict[str, Any] = field(default_factory=dict)
    requires_review: bool = False
    # 论文 Section 5.1/5.2 六道验证门报告
    six_gates_report: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "pass_rate": self.pass_rate,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "test_details": self.test_details,
            "verified_at": self.verified_at,
            "status": self.status,
            "error_detail": self.error_detail,
            "process_log": self.process_log,
            "runtime_mode": self.runtime_mode,
            "runtime_ready": self.runtime_ready,
            "docker_image": self.docker_image,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "artifact_dir": self.artifact_dir,
            "evidence_run_id": self.evidence_run_id,
            "verification_evidence": self.verification_evidence,
            "tokens_consumed": self.tokens_consumed,
            "run_id": self.run_id,
            "gate": self.gate,
            "requires_review": self.requires_review,
            "six_gates_report": self.six_gates_report,
        }


class SkillVerifier:
    """技能验证器 — 构造测试 → 沙箱执行 → 评估，全程可追溯."""

    def __init__(self, skill_library=None, chat_harness=None):
        self._skill_library = skill_library
        self._chat_harness = chat_harness
        self._results: Dict[str, VerificationResult] = {}
        self._process_log: List[Dict[str, Any]] = []  # 透明化执行日志

    async def verify_skill(self, team_id: str, skill_id: str, provider_config=None) -> VerificationResult:
        """验证技能: 生成测试材料 → 沙箱执行验证脚本 → 评估 pass_rate.

        P4: 包裹 token_scope，使 _generate_tests 的 LLM token 归因到 run_id。
        """
        from .token_context import token_scope, new_run_id
        run_id = new_run_id("skill_verify")
        with token_scope(run_id=run_id, phase="skill_verify",
                         skill_id=skill_id, team_id=team_id,
                         agent_id=getattr(skill, 'owner_agent', '') if 'skill' in dir() else ''):
            return await self._verify_skill_impl(team_id, skill_id, provider_config, run_id)

    async def _verify_skill_impl(self, team_id: str, skill_id: str, provider_config=None, run_id: str = "") -> VerificationResult:
        """验证技能实现（由 verify_skill 调用，在 token_scope 内执行）。"""
        self._process_log = []
        result = VerificationResult(skill_id=skill_id, status="testing")
        result.process_log = self._process_log

        self._process_log.append({"step": "init", "msg": f"开始验证技能: {skill_id}", "team_id": team_id})

        if not self._skill_library:
            result.status = "failed"
            result.error_detail = "技能库未初始化"
            self._process_log.append({"step": "error", "msg": "技能库未初始化"})
            return result

        skill = self._skill_library._find_skill(team_id, skill_id)
        if not skill:
            result.status = "failed"
            result.error_detail = f"技能 {skill_id} 未找到"
            self._process_log.append({"step": "error", "msg": f"技能 {skill_id} 未找到"})
            return result

        self._process_log.append({"step": "found_skill", "msg": f"技能名: {skill.name}", "desc": skill.description[:200]})

        runtime = self._describe_runtime()
        result.runtime_mode = str(runtime.get("mode", ""))
        result.runtime_ready = bool(runtime.get("ready", False))
        result.docker_image = str(runtime.get("docker_image", ""))
        self._process_log.append({
            "step": "sandbox_runtime",
            "msg": f"验证运行时: {result.runtime_mode or 'unknown'} ({runtime.get('ready_reason', '')})",
            "runtime": runtime,
        })

        # Step 1: 生成测试场景
        self._process_log.append({"step": "generate_tests", "msg": "生成技能验证场景..."})
        test_scenarios = await self._generate_tests(skill, provider_config=provider_config)
        self._process_log.append({"step": "tests_generated", "msg": f"生成 {len(test_scenarios)} 个测试场景", "scenarios": [t.get("scenario","")[:100] for t in test_scenarios]})

        # Step 1.5: 进程内语义检查（不依赖沙箱；mock tools / 步骤 / 场景对齐）
        semantic_checks = self._semantic_checks(skill, test_scenarios)
        self._process_log.append({
            "step": "semantic_eval",
            "msg": f"语义检查 {sum(1 for c in semantic_checks if c.get('passed'))}/{len(semantic_checks)} 通过",
        })

        # Step 2: 沙箱执行验证脚本（结构 + 增强语义 runner）
        artifact_dir = self._create_artifact_dir(skill_id)
        result.artifact_dir = str(artifact_dir)
        evidence = self._run_sandbox_verification(skill, test_scenarios, artifact_dir, runtime)
        result.verification_evidence = evidence
        result.command = str(evidence.get("command", ""))
        result.exit_code = int(evidence.get("exit_code", -1))
        result.stdout = str(evidence.get("stdout", ""))
        result.stderr = str(evidence.get("stderr", ""))

        sandbox_checks = list(evidence.get("checks") or [])

        # Step 2.5: Twin A/B 全量对照（baseline vs treatment 熟练度 + instructions 覆盖）
        twin_report: Dict[str, Any] = {}
        twin_checks: List[Dict[str, Any]] = []
        hard_offline = any(
            (not c.get("passed")) and c.get("hard_fail")
            for c in semantic_checks
        )
        if not hard_offline:
            self._process_log.append({"step": "twin_ab", "msg": "启动数字孪生 A/B 对照评估..."})
            try:
                from .skill_twin_ab import run_skill_twin_ab, twin_ab_to_checks
                twin_report = await run_skill_twin_ab(
                    skill,
                    skill_library=self._skill_library,
                    team_id=team_id,
                )
                twin_checks = twin_ab_to_checks(twin_report)
                if twin_report.get("skipped"):
                    self._process_log.append({
                        "step": "twin_ab_skip",
                        "msg": f"孪生 A/B 跳过: {twin_report.get('reason')} — {twin_report.get('detail', '')}",
                    })
                elif twin_report.get("status") == "error":
                    self._process_log.append({
                        "step": "twin_ab_error",
                        "msg": f"孪生 A/B 错误: {twin_report.get('error')}",
                        "passed": False,
                    })
                else:
                    self._process_log.append({
                        "step": "twin_ab_done",
                        "msg": (
                            f"孪生 A/B: {twin_report.get('target_skill')} "
                            f"{twin_report.get('baseline', {}).get('target_rate', 0):.1%}→"
                            f"{twin_report.get('treatment', {}).get('target_rate', 0):.1%} "
                            f"(+{twin_report.get('target_gain_pp', 0)}pp) "
                            f"{'PASS' if twin_report.get('passed') else 'FAIL'}"
                        ),
                        "passed": bool(twin_report.get("passed")),
                    })
            except Exception as te:
                logger.warning("twin ab integration failed: %s", te)
                twin_report = {"status": "error", "error": str(te), "passed": False}
                twin_checks = [{
                    "name": "twin_ab_run",
                    "passed": False,
                    "message": str(te),
                    "source": "twin_ab",
                    "layer": "twin-ab",
                    "required": False,
                    "hard_fail": False,
                }]
                self._process_log.append({
                    "step": "twin_ab_error",
                    "msg": f"孪生 A/B 异常: {te}",
                    "passed": False,
                })
        else:
            self._process_log.append({
                "step": "twin_ab_skip",
                "msg": "语义 hard_fail，跳过孪生 A/B",
            })

        # 合并：语义 → 沙箱 → twin A/B（同名去重保留先出现）
        seen_names: set = set()
        checks: List[Dict[str, Any]] = []
        for c in semantic_checks + sandbox_checks + twin_checks:
            name = str(c.get("name") or "")
            if name and name in seen_names:
                continue
            if name:
                seen_names.add(name)
            checks.append(c)
        evidence["checks"] = checks
        evidence["semantic_checks"] = semantic_checks
        evidence["twin_ab"] = twin_report
        result.verification_evidence = evidence

        result.total_tests = len(checks)
        for i, check in enumerate(checks):
            passed = bool(check.get("passed"))
            if passed:
                result.passed += 1
            else:
                result.failed += 1
            result.test_details.append({
                "scenario": str(check.get("name") or f"check_{i + 1}"),
                "passed": passed,
                "test_index": i + 1,
                "message": str(check.get("message", "")),
                "source": str(check.get("source") or "sandbox"),
                "layer": str(check.get("layer") or check.get("source") or "sandbox"),
            })
            self._process_log.append({
                "step": "check",
                "msg": f"{'PASS' if passed else 'FAIL'} [{check.get('source', 'sandbox')}] {check.get('name', f'check_{i + 1}')}: {check.get('message', '')}",
                "passed": passed,
            })

        # Step 3: 计算通过率
        if result.total_tests > 0:
            result.pass_rate = result.passed / result.total_tests
        self._process_log.append({"step": "calc_rate", "msg": f"通过率: {result.pass_rate*100:.0f}% ({result.passed}/{result.total_tests})"})

        # Step 4: 确定结果
        # 语义可独立过；若 twin A/B 实际跑了则要求 twin_ab_target_gain 通过
        sandbox_ok = bool(evidence.get("sandbox_ok", False))
        sandbox_exit_ok = int(evidence.get("exit_code", -1)) == 0
        semantic_ok = bool(semantic_checks) and all(
            c.get("passed") for c in semantic_checks if c.get("required", True)
        )
        hard_fail = any(
            (not c.get("passed")) and c.get("hard_fail")
            for c in semantic_checks
        )
        twin_ran = bool(twin_report) and not twin_report.get("skipped") and twin_report.get("status") == "ok"
        twin_pass = bool(twin_report.get("passed")) if twin_ran else True

        if hard_fail:
            result.status = "failed"
            result.error_detail = "语义硬失败（离线占位/空指令等不可验证内容）"
            self._process_log.append({"step": "done", "msg": f"验证失败 — {result.error_detail}"})
        elif result.pass_rate >= 0.7 and ((sandbox_ok and sandbox_exit_ok) or semantic_ok) and twin_pass:
            result.status = "verified"
            skill.lifecycle_stage = SkillLifecycleStage.VERIFIED
            # quality: blend pass_rate with twin gain when available
            if twin_ran:
                gain = float(twin_report.get("target_gain") or 0)
                skill.quality_score = round(min(1.0, 0.5 * result.pass_rate + 0.5 * min(1.0, gain / 0.2)), 4)
            else:
                skill.quality_score = result.pass_rate
            self._skill_library._persist_skill(skill, team_id)
            parts = []
            if sandbox_ok and sandbox_exit_ok:
                parts.append("sandbox")
            if semantic_ok:
                parts.append("semantic")
            if twin_ran:
                parts.append("twin-ab")
            mode = "+".join(parts) or "unknown"
            self._process_log.append({"step": "done", "msg": f"验证通过 ({mode}) — 技能已标记为 VERIFIED"})
        else:
            result.status = "failed"
            sandbox_err = str(evidence.get("error") or "").strip()
            if hard_fail:
                result.error_detail = "语义硬失败"
            elif not sandbox_ok and sandbox_err:
                # 运行时阻断（如 docker missing）优先于通过率文案，便于回演化证据
                result.error_detail = sandbox_err
                if result.pass_rate < 0.7:
                    result.error_detail = (
                        f"{sandbox_err} · 通过率 {result.pass_rate*100:.0f}% 低于 70% 阈值"
                    )
            elif twin_ran and not twin_pass:
                result.error_detail = (
                    f"孪生 A/B 未达增益阈值 "
                    f"(+{twin_report.get('target_gain_pp', 0)}pp，"
                    f"需 ≥{float(twin_report.get('gain_threshold', 0.05))*100:.0f}pp)"
                )
            elif result.pass_rate < 0.7:
                result.error_detail = f"通过率 {result.pass_rate*100:.0f}% 低于 70% 阈值"
            elif not sandbox_ok and not semantic_ok:
                result.error_detail = sandbox_err or "sandbox failed and semantic checks insufficient"
            else:
                result.error_detail = "验证未达通过条件"
            self._process_log.append({"step": "done", "msg": f"验证失败 — {result.error_detail}"})

        # P4.1: Token Gate 闸门 — verified→granted 前评估本次 run 的 token 合规
        gate_report: Dict[str, Any] = {}
        if run_id and result.status == "verified":
            try:
                from .token_ledger import LEDGER
                from .token_policy import ENGINE, TokenBudget
                run_data = LEDGER.run(run_id)
                result.tokens_consumed = run_data.get("total", 0)
                result.run_id = run_id
                # 技能验证默认预算：max_tokens=20000, min_efficiency=0.0（不强制效率）
                budget = TokenBudget(max_tokens=20000, min_efficiency=0.0)
                gate_report = ENGINE.evaluate(run_data, budget)
                result.gate = gate_report
                decision = gate_report.get("decision", "pass")
                if decision == "block":
                    # block 拦截授予：降级为 failed，不进入 granted
                    result.status = "failed"
                    result.error_detail = (
                        f"Token Gate 拦截 (block): {gate_report.get('violations', [])}. "
                        f"tokens={run_data.get('total', 0)}"
                    )
                    skill.lifecycle_stage = SkillLifecycleStage.VERIFIED  # 保留 verified 但不进 granted
                    self._skill_library._persist_skill(skill, team_id)
                    self._process_log.append({
                        "step": "gate_block", "msg": f"Token Gate 拦截授予: {gate_report}",
                    })
                elif decision == "warn":
                    # warn 允许授予但标记需人工复核
                    result.requires_review = True
                    self._process_log.append({
                        "step": "gate_warn", "msg": f"Token Gate 警告但允许授予: {gate_report}",
                    })
                else:
                    self._process_log.append({
                        "step": "gate_pass", "msg": f"Token Gate 通过: {gate_report}",
                    })
            except Exception as ge:
                logger.warning("Token Gate 评估失败（不阻断授予）: %s", ge)
                self._process_log.append({"step": "gate_skip", "msg": f"Gate 评估跳过: {ge}"})

        # 论文 Section 5.1/5.2 六门统一裁决
        try:
            from .skill_gates import run_gates
            skill_dict = skill.to_dict() if hasattr(skill, "to_dict") else {
                "name": skill.name,
                "description": skill.description,
                "category": getattr(skill.category, "value", str(skill.category)),
                "tools": list(skill.tools or []),
                "instructions": skill.instructions,
                "evidence_spans": getattr(skill, "evidence_spans", []),
            }
            six_report = run_gates(
                skill_dict,
                ctx={
                    "known_tools": self._KNOWN_TOOLS,
                    "sandbox_result": {"passed": sandbox_ok and sandbox_exit_ok, "error": evidence.get("error", "")},
                    "competition_result": None,
                },
                candidate_id=skill_id,
                env_version=str(runtime.get("version", "")),
            )
            result.six_gates_report = six_report.to_dict()
            self._process_log.append({
                "step": "six_gates",
                "msg": f"六门裁决: {six_report.aggregate.value} (P={six_report.P}, R={six_report.R}, L={six_report.L})",
                "report": six_report.to_dict(),
            })
        except Exception as gate_err:
            logger.warning("六门裁决执行异常（不阻断）: %s", gate_err)

        result.evidence_run_id = await self._record_evidence_run(team_id, skill, result, evidence)
        if result.evidence_run_id:
            result.verification_evidence["evidence_run_id"] = result.evidence_run_id
            self._process_log.append({
                "step": "evidence_run",
                "msg": f"EvidenceRun 已写入: {result.evidence_run_id}",
            })

        # 落盘 last_verify：供演化引擎加厚证据 + 验证失败「一键回演化」
        try:
            self._persist_last_verify(skill, team_id, result, twin_report)
        except Exception as pe:
            logger.warning("persist last_verify failed: %s", pe)

        self._results[skill_id] = result

        # Emit event
        bus = get_event_bus()
        event = DomainEvent.create(
            event_type=EventType.SKILL_UPDATED,
            payload=SkillSnapshot.from_skill_definition(skill),
            source="skill_verifier",
            correlation_id=f"verify:{skill_id}",
        )
        bus.publish(event)

        logger.info("Skill %s verification: %s (pass_rate=%.2f)",
                     skill_id, result.status, result.pass_rate)
        return result

    @staticmethod
    def _summarize_twin(twin: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact twin report for history / before-after compare charts."""
        twin = twin or {}
        if not twin:
            return {}
        b = twin.get("baseline") or {}
        t = twin.get("treatment") or {}
        return {
            "status": twin.get("status"),
            "skipped": bool(twin.get("skipped")),
            "passed": twin.get("passed"),
            "reason": twin.get("reason"),
            "detail": twin.get("detail"),
            "error": twin.get("error"),
            "target_skill": twin.get("target_skill"),
            "scenario_id": twin.get("scenario_id"),
            "n_seeds": twin.get("n_seeds"),
            "baseline_rate": b.get("target_rate") if isinstance(b, dict) else twin.get("baseline_rate"),
            "treatment_rate": t.get("target_rate") if isinstance(t, dict) else twin.get("treatment_rate"),
            "baseline_all_rate": b.get("all_rate") if isinstance(b, dict) else twin.get("baseline_all_rate"),
            "treatment_all_rate": t.get("all_rate") if isinstance(t, dict) else twin.get("treatment_all_rate"),
            "baseline_uses": b.get("target_uses") if isinstance(b, dict) else twin.get("baseline_uses"),
            "treatment_uses": t.get("target_uses") if isinstance(t, dict) else twin.get("treatment_uses"),
            "target_gain": twin.get("target_gain"),
            "target_gain_pp": twin.get("target_gain_pp"),
            "all_gain_pp": twin.get("all_gain_pp"),
            "gain_threshold": twin.get("gain_threshold"),
            "criteria": (twin.get("criteria") or "")[:200],
        }

    @staticmethod
    def _twin_metrics_for_evidence(twin: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Flat twin fields for EvidenceRun.metrics_after (publish gate)."""
        twin = twin or {}
        if not twin:
            return {}
        skipped = bool(twin.get("skipped"))
        status = str(twin.get("status") or "")
        ran = (not skipped) and (
            status in ("ok", "error") or twin.get("target_gain") is not None
        )
        if not ran and not skipped:
            return {}
        out: Dict[str, Any] = {
            "twin_ran": bool(ran),
            "twin_skipped": skipped,
            "twin_status": status,
            "twin_passed": twin.get("passed"),
            "twin_n_seeds": twin.get("n_seeds"),
        }
        if twin.get("target_gain") is not None:
            out["twin_target_gain"] = twin.get("target_gain")
        if twin.get("target_gain_pp") is not None:
            out["twin_target_gain_pp"] = twin.get("target_gain_pp")
        if twin.get("gain_threshold") is not None:
            out["twin_gain_threshold"] = twin.get("gain_threshold")
        return out

    def _persist_last_verify(
        self,
        skill,
        team_id: str,
        result: VerificationResult,
        twin_report: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write last_verify + twin history/compare into skill.config."""
        if not self._skill_library or not skill:
            return
        twin_summary = self._summarize_twin(twin_report)
        failed_checks: List[Dict[str, Any]] = []
        for t in (result.test_details or []):
            if t.get("passed"):
                continue
            failed_checks.append({
                "name": t.get("scenario") or t.get("name") or "check",
                "message": (t.get("message") or "")[:300],
                "layer": t.get("layer") or t.get("source") or "",
            })
            if len(failed_checks) >= 10:
                break
        now = datetime.now(timezone.utc).isoformat()
        cfg = dict(getattr(skill, "config", None) or {})
        last_verify = {
            "status": result.status,
            "pass_rate": float(result.pass_rate or 0),
            "passed": int(result.passed or 0),
            "failed": int(result.failed or 0),
            "error_detail": (result.error_detail or "")[:500],
            "failed_checks": failed_checks,
            "twin_ab": twin_summary,
            "skill_version": int(getattr(skill, "version", 1) or 1),
            "at": now,
        }
        cfg["last_verify"] = last_verify

        # twin_history ring buffer (for multi-run sparklines)
        if twin_summary and not twin_summary.get("skipped"):
            hist = list(cfg.get("twin_history") or [])
            hist.append({
                "at": now,
                "skill_version": last_verify["skill_version"],
                "verify_status": result.status,
                **twin_summary,
            })
            cfg["twin_history"] = hist[-8:]

        # 演化前后对比：若 apply_evolution 冻结了 twin_before_evolve
        before = dict(cfg.get("twin_before_evolve") or {})
        twin_compare: Dict[str, Any] = {}
        if before and twin_summary and not twin_summary.get("skipped"):
            b_gain = before.get("target_gain_pp")
            a_gain = twin_summary.get("target_gain_pp")
            delta = None
            if b_gain is not None and a_gain is not None:
                try:
                    delta = round(float(a_gain) - float(b_gain), 2)
                except (TypeError, ValueError):
                    delta = None
            twin_compare = {
                "before": before,
                "after": {
                    **twin_summary,
                    "skill_version": last_verify["skill_version"],
                    "at": now,
                },
                "delta_gain_pp": delta,
                "improved": (delta is not None and delta > 0),
                "at": now,
            }
            cfg["twin_compare"] = twin_compare
        skill.config = cfg

        # 同步到本次响应，前端可直接画图
        if isinstance(result.verification_evidence, dict):
            result.verification_evidence["twin_ab"] = twin_report or twin_summary
            result.verification_evidence["twin_summary"] = twin_summary
            if twin_compare:
                result.verification_evidence["twin_compare"] = twin_compare
            if cfg.get("twin_history"):
                result.verification_evidence["twin_history"] = list(cfg.get("twin_history") or [])[-6:]

        self._skill_library._persist_skill(skill, team_id)
        self._process_log.append({
            "step": "last_verify_saved",
            "msg": (
                f"已写入 last_verify status={result.status}"
                + (f" · twin_compare Δ{twin_compare.get('delta_gain_pp')}pp" if twin_compare else "")
            ),
        })

    async def _record_evidence_run(
        self,
        team_id: str,
        skill: SkillDefinition,
        result: VerificationResult,
        evidence: Dict[str, Any],
    ) -> str:
        """Persist the sandbox verification as a shared EvidenceRun."""
        try:
            from .evidence_store import EvidenceRun, get_evidence_store

            run = EvidenceRun.create(
                evidence_type="skill_verify",
                status=result.status,
                summary=f"技能验证: {skill.name} -> {result.status}",
                team_id=team_id,
                agent_id="skill_verifier",
                skill_id=skill.skill_id,
                request_id=f"skill-verify:{skill.skill_id}:{result.verified_at}",
                runtime={
                    "mode": result.runtime_mode,
                    "ready": result.runtime_ready,
                    "docker_image": result.docker_image,
                    "raw": evidence.get("runtime", {}),
                },
                command=result.command,
                exit_code=result.exit_code,
                artifact_dir=result.artifact_dir,
                stdout=result.stdout,
                stderr=result.stderr,
                metrics_after={
                    "pass_rate": result.pass_rate,
                    "passed": result.passed,
                    "failed": result.failed,
                    "total_tests": result.total_tests,
                    # twin A/B flat fields for publish gate (optional when skipped)
                    **self._twin_metrics_for_evidence(evidence.get("twin_ab") or {}),
                },
                detail={
                    "error_detail": result.error_detail,
                    "test_details": result.test_details,
                    "checks": evidence.get("checks", []),
                    "process_log": list(result.process_log),
                    "sandbox_ok": evidence.get("sandbox_ok", False),
                    "runtime_ready": result.runtime_ready,
                    "twin_ab": self._summarize_twin(evidence.get("twin_ab") or {}),
                    "twin_summary": self._summarize_twin(evidence.get("twin_ab") or {}),
                },
            )
            await get_evidence_store().append_evidence(run)
            return run.evidence_id
        except Exception as exc:
            logger.warning("Failed to record skill verification EvidenceRun: %s", exc)
            self._process_log.append({
                "step": "evidence_run_error",
                "msg": f"EvidenceRun 写入失败: {exc}",
            })
            return ""

    def _describe_runtime(self) -> Dict[str, Any]:
        try:
            from sandbox.python_runner import describe_sandbox_runtime
            return dict(describe_sandbox_runtime())
        except Exception as exc:
            logger.warning("Sandbox runtime describe failed: %s", exc)
            return {
                "mode": "unavailable",
                "ready": False,
                "ready_reason": str(exc),
                "docker_image": "",
                "self_check_blocked": True,
            }

    def _create_artifact_dir(self, skill_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", skill_id or "skill").strip("-")[:80] or "skill"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        artifact_dir = _ARTIFACT_ROOT / safe_id / stamp
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def _run_sandbox_verification(
        self,
        skill: SkillDefinition,
        test_scenarios: List[Dict[str, str]],
        artifact_dir: Path,
        runtime: Dict[str, Any],
    ) -> Dict[str, Any]:
        runner_code = self._build_sandbox_validation_code(skill, test_scenarios)
        runner_path = artifact_dir / "verification_runner.py"
        inputs_path = artifact_dir / "verification_input.json"
        runner_path.write_text(runner_code, encoding="utf-8")
        inputs_path.write_text(json.dumps({
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "tests": test_scenarios,
            "runtime": runtime,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        command = f"sandbox.run_python artifact={self._display_path(runner_path)}"
        self._process_log.append({"step": "sandbox_exec", "msg": f"执行沙箱验证脚本: {command}"})

        try:
            from sandbox.python_runner import get_sandbox
            sandbox = get_sandbox()
            sandbox_result = sandbox.run_python(runner_code, cwd=_REPO_ROOT, timeout=30)
        except Exception as exc:
            sandbox_result = None
            evidence = {
                "runtime": runtime,
                "runtime_mode": runtime.get("mode", ""),
                "runtime_ready": bool(runtime.get("ready", False)),
                "docker_image": runtime.get("docker_image", ""),
                "artifact_dir": str(artifact_dir),
                "runner_path": str(runner_path),
                "input_path": str(inputs_path),
                "command": command,
                "sandbox_ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": str(exc),
                "checks": [{"name": "sandbox_execution", "passed": False, "message": str(exc)}],
            }
            self._write_evidence(artifact_dir, evidence)
            return evidence

        sandbox_payload = sandbox_result.to_dict()
        parsed = self._parse_sandbox_stdout(sandbox_result.stdout)
        checks = list(parsed.get("checks") or [])
        if not checks:
            checks = [{
                "name": "sandbox_output_parse",
                "passed": False,
                "message": "sandbox did not return verification checks",
            }]

        evidence = {
            "runtime": runtime,
            "runtime_mode": runtime.get("mode", ""),
            "runtime_ready": bool(runtime.get("ready", False)),
            "docker_image": runtime.get("docker_image", ""),
            "artifact_dir": str(artifact_dir),
            "runner_path": str(runner_path),
            "input_path": str(inputs_path),
            "command": command,
            "sandbox_ok": bool(sandbox_result.ok),
            "exit_code": int(sandbox_result.exit_code),
            "stdout": self._clip(sandbox_result.stdout),
            "stderr": self._clip(sandbox_result.stderr),
            "error": sandbox_result.error,
            "elapsed_sec": sandbox_payload.get("elapsed_sec", 0),
            "checks": checks,
            "parsed_summary": parsed.get("summary", {}),
            "sandbox_result": sandbox_payload,
        }
        self._write_evidence(artifact_dir, evidence)
        return evidence

    def _write_evidence(self, artifact_dir: Path, evidence: Dict[str, Any]) -> None:
        try:
            (artifact_dir / "verification_result.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to write skill verification evidence: %s", exc)

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(_REPO_ROOT))
        except ValueError:
            return str(path)

    def _parse_sandbox_stdout(self, stdout: str) -> Dict[str, Any]:
        for line in reversed((stdout or "").splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict) and "checks" in payload:
                return payload
        return {}

    def _clip(self, text: str, limit: int = 4000) -> str:
        text = text or ""
        if len(text) <= limit:
            return text
        return text[:1000] + "\n...(truncated)...\n" + text[-limit + 1000:]

    # Known tools the platform can mock / inject (soft allowlist)
    _KNOWN_TOOLS = frozenset({
        "read_file", "write_file", "web_search", "run_in_terminal", "grep_search",
        "testFailure", "browser", "http_request", "kubectl", "terraform",
        "aws_cli", "shell", "python", "git", "docker",
    })

    def _semantic_checks(
        self,
        skill: SkillDefinition,
        test_scenarios: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """In-process semantic verification (no sandbox).

        Layers:
        - structural intent (steps, acceptance, rollback)
        - tool grounding / mock allowlist
        - scenario ↔ instruction keyword alignment
        - reject offline-placeholder / 回退草稿
        """
        checks: List[Dict[str, Any]] = []

        def add(name: str, passed: bool, message: str, *, required: bool = True,
                hard_fail: bool = False, layer: str = "semantic") -> None:
            checks.append({
                "name": name,
                "passed": bool(passed),
                "message": str(message),
                "source": "semantic",
                "layer": layer,
                "required": required,
                "hard_fail": hard_fail,
            })

        instructions = (skill.instructions or "").strip()
        description = (skill.description or "").strip()
        name = (skill.name or "").strip()
        tools = [str(t).strip() for t in (skill.required_tools or []) if str(t).strip()]
        lowered = instructions.lower()
        blob = f"{name}\n{description}\n{instructions}"

        # Hard fail: offline / fallback placeholders
        offline_markers = ("离线占位", "非正式技能名", "【回退草稿】", "[回退草稿]", "deterministic-offline")
        is_offline = any(m in blob for m in offline_markers)
        add(
            "not_offline_placeholder",
            not is_offline,
            "reject offline/fallback placeholder skills" if is_offline else "not an offline placeholder",
            hard_fail=True,
            layer="semantic-hard",
        )

        add(
            "instructions_min_length",
            len(instructions) >= 40,
            f"instruction length={len(instructions)} (want ≥40 for semantic)",
            hard_fail=len(instructions) < 15,
        )

        # Step / procedure structure
        step_pats = [
            r"(?:^|\n)\s*\d+\s*[\.\)、]",
            r"(?:^|\n)\s*[-*•]\s+\S",
            r"步骤\s*\d+",
            r"(?:首先|然后|接着|最后|1\)|2\))",
        ]
        step_hits = sum(1 for p in step_pats if re.search(p, instructions))
        add(
            "has_procedure_steps",
            step_hits >= 1 or len(re.findall(r"(?:^|\n)\s*\d+[\.\)、]", instructions)) >= 2,
            f"procedure markers={step_hits}",
            layer="semantic-structure",
        )

        # Acceptance / verify / rollback signals (domain-agnostic)
        accept_kw = ("验收", "通过", "成功", "验证", "check", "verify", "pass", "assert", "验收口径")
        rollback_kw = ("回滚", "回退", "失败", "熔断", "超时", "rollback", "fallback", "retry", "abort")
        add(
            "has_acceptance_signal",
            any(k in instructions or k in lowered for k in accept_kw),
            "acceptance/verify language present",
            required=False,
            layer="semantic-structure",
        )
        add(
            "has_failure_or_rollback",
            any(k in instructions or k in lowered for k in rollback_kw),
            "failure/rollback/timeout language present",
            required=False,
            layer="semantic-structure",
        )

        # Tool grounding + mock allowlist
        if tools:
            grounded = []
            for t in tools:
                tlow = t.lower()
                if tlow in lowered or t in instructions or tlow.replace("_", " ") in lowered:
                    grounded.append(t)
            need = max(1, (len(tools) + 1) // 2)
            add(
                "tools_grounded_in_instructions",
                len(grounded) >= need,
                f"tools mentioned in instructions: {grounded or 'none'} / declared={tools}",
                layer="semantic-tools",
            )
            unknown = [
                t for t in tools
                if t.lower() not in self._KNOWN_TOOLS
                and not re.match(r"^[a-z][a-z0-9_]{1,40}$", t.lower())
            ]
            add(
                "tools_mockable",
                len(unknown) == 0,
                f"unknown/unmockable tools: {unknown}" if unknown else f"all {len(tools)} tools mockable/allowlisted",
                required=False,
                layer="semantic-tools",
            )
            # Mock execution: each tool "invokable" as stub
            mock_ok = True
            mock_log = []
            for t in tools:
                # stub success for known or snake_case tools
                ok = t.lower() in self._KNOWN_TOOLS or bool(re.match(r"^[a-z][a-z0-9_]{1,40}$", t.lower()))
                mock_log.append(f"{t}={'ok' if ok else 'skip'}")
                if not ok:
                    mock_ok = False
            add(
                "mock_tools_execute",
                mock_ok or len(tools) == 0,
                "mock tool stubs: " + ", ".join(mock_log[:8]),
                layer="semantic-tools",
            )
        else:
            add(
                "tools_optional",
                True,
                "no required_tools — semantic tool layer skipped",
                required=False,
                layer="semantic-tools",
            )

        # Scenario alignment with instructions (keyword overlap)
        scenarios = [
            s for s in (test_scenarios or [])
            if (s.get("scenario") or s.get("prompt") or "").strip()
        ]
        add(
            "scenarios_present",
            len(scenarios) > 0,
            f"scenarios={len(scenarios)}",
            layer="semantic-scenario",
        )
        if scenarios:
            # Chinese bigrams + latin tokens from instructions
            instr_tokens = set(re.findall(r"[\u4e00-\u9fff]{2}|[a-zA-Z]{3,}", instructions))
            aligned = 0
            for i, sc in enumerate(scenarios[:5]):
                text = f"{sc.get('scenario') or ''} {sc.get('prompt') or ''}"
                sc_tokens = set(re.findall(r"[\u4e00-\u9fff]{2}|[a-zA-Z]{3,}", text))
                overlap = instr_tokens & sc_tokens if instr_tokens else set()
                # also accept shared name words
                if name:
                    for part in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", name):
                        if part in text or part.lower() in text.lower():
                            overlap.add(part)
                ok = len(overlap) >= 1 or (name and name[:4] in text)
                if ok:
                    aligned += 1
                add(
                    f"scenario_{i+1}_aligned",
                    ok,
                    f"overlap={list(overlap)[:5]}" if overlap else "no keyword overlap with instructions",
                    required=False,
                    layer="semantic-scenario",
                )
            add(
                "scenarios_mostly_aligned",
                aligned >= max(1, len(scenarios[:5]) // 2),
                f"aligned {aligned}/{min(5, len(scenarios))} scenarios",
                layer="semantic-scenario",
            )

        return checks

    def _build_sandbox_validation_code(
        self,
        skill: SkillDefinition,
        test_scenarios: List[Dict[str, str]],
    ) -> str:
        payload = {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions,
            "required_tools": list(skill.required_tools or []),
        }
        known_tools = sorted(self._KNOWN_TOOLS)
        return textwrap.dedent(f"""
            import json
            import re
            SKILL = {json.dumps(payload, ensure_ascii=False)}
            SCENARIOS = {json.dumps(test_scenarios, ensure_ascii=False)}
            KNOWN_TOOLS = set({json.dumps(known_tools)})
            checks = []

            def add(name, passed, message, source="sandbox"):
                checks.append({{
                    "name": name,
                    "passed": bool(passed),
                    "message": str(message),
                    "source": source,
                }})

            instructions = (SKILL.get("instructions") or "").strip()
            description = (SKILL.get("description") or "").strip()
            tools = list(SKILL.get("required_tools") or [])
            markers = [
                "步骤", "执行", "检查", "验证", "输出", "输入", "如果", "规则", "流程",
                "step", "check", "verify", "return", "use", "must", "should", "ensure",
            ]
            lowered = instructions.lower()

            add(
                "instructions_present",
                len(instructions) >= 20,
                f"instruction length={{len(instructions)}}",
            )
            add(
                "description_present",
                bool(description or SKILL.get("name")),
                "description or skill name is present",
            )
            add(
                "actionable_language",
                any(marker in lowered or marker in instructions for marker in markers),
                "instructions include actionable workflow language",
            )
            placeholder_terms = ["todo", "tbd", "placeholder", "待补", "待完善"]
            add(
                "not_placeholder",
                not any(term in lowered or term in instructions for term in placeholder_terms),
                "instructions are not placeholder text",
            )
            valid_scenarios = [
                item for item in SCENARIOS
                if (item.get("scenario") or item.get("prompt") or "").strip()
            ]
            add(
                "scenarios_defined",
                len(valid_scenarios) > 0,
                f"valid scenarios={{len(valid_scenarios)}}",
            )
            add(
                "scenario_prompts_defined",
                all((item.get("prompt") or item.get("scenario") or "").strip() for item in SCENARIOS) if SCENARIOS else False,
                "each generated scenario has a prompt or scenario",
            )

            # Sandbox mock: each required tool is "callable" as a stub
            mock_results = []
            for t in tools:
                tname = str(t)
                ok = tname.lower() in KNOWN_TOOLS or bool(re.match(r"^[a-z][a-z0-9_]{{1,40}}$", tname.lower()))
                mock_results.append({{"tool": tname, "ok": ok}})
            add(
                "sandbox_mock_tools",
                all(m["ok"] for m in mock_results) if mock_results else True,
                json.dumps(mock_results, ensure_ascii=False)[:200] if mock_results else "no tools",
                source="sandbox-mock",
            )
            # numbered steps in sandbox re-check
            step_n = len(re.findall(r"(?:^|\\n)\\s*\\d+[\\.\\)、]", instructions))
            add(
                "sandbox_has_numbered_steps",
                step_n >= 2 or any(x in instructions for x in ("步骤", "首先", "然后")),
                f"numbered_steps={{step_n}}",
            )

            passed = sum(1 for check in checks if check["passed"])
            total = len(checks)
            pass_rate = passed / total if total else 0
            payload = {{
                "checks": checks,
                "summary": {{
                    "passed": passed,
                    "total": total,
                    "pass_rate": pass_rate,
                    "threshold": 0.7,
                }},
            }}
            print(json.dumps(payload, ensure_ascii=False))
        """).strip() + "\n"

    async def _generate_tests(self, skill: SkillDefinition, provider_config=None) -> List[Dict[str, str]]:
        """通过 LLM 生成测试场景."""
        if not self._chat_harness:
            # Fallback: simple structural test
            return [
                {"scenario": "structural_check", "prompt": f"验证技能 {skill.name} 的指令是否完整且可操作"},
            ]

        try:
            result = await self._chat_harness.chat(
                prompt=f"为以下技能生成3个测试场景:\n\n名称: {skill.name}\n描述: {skill.description}\n指令: {skill.instructions[:2000]}",
                system_prompt=VERIFY_PROMPT,
                agent_id="skill_verifier",
                config_override=provider_config,
            )
            # chat() returns TurnResult object with .response attribute
            response_text = getattr(result, 'response', '') if result else ''
            if response_text:
                import json
                try:
                    tests = json.loads(response_text)
                    if isinstance(tests, list):
                        return tests[:5]
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.error("Test generation failed: %s", e)

        return [{"scenario": "basic_validation", "prompt": f"使用技能「{skill.name}」完成一个基本任务"}]

    async def _execute_test(self, skill: SkillDefinition, test: Dict[str, str]) -> bool:
        """执行单个测试场景 — 通过 LLM 评估."""
        if not self._chat_harness:
            # Structural validation: check skill has instructions
            return bool(skill.instructions and len(skill.instructions) > 20)

        try:
            result = await self._chat_harness.chat(
                prompt=f"使用以下技能指令处理测试场景:\n\n技能指令: {skill.instructions[:2000]}\n\n测试场景: {test.get('prompt', test.get('scenario', ''))}",
                system_prompt="你是一个技能测试执行器。执行给定的技能指令，输出 PASS 或 FAIL。",
                agent_id="skill_verifier",
            )
            # chat() returns TurnResult object with .response attribute
            response_text = getattr(result, 'response', '') if result else ''
            if response_text:
                return "PASS" in response_text.strip().upper()
        except Exception as e:
            logger.error("Test execution failed: %s", e)

        return False

    def get_result(self, skill_id: str) -> Optional[VerificationResult]:
        """获取验证结果."""
        return self._results.get(skill_id)

    def get_all_results(self) -> Dict[str, Dict[str, Any]]:
        """获取所有验证结果."""
        return {k: v.to_dict() for k, v in self._results.items()}


VERIFY_PROMPT = """为给定技能生成3个测试场景，以JSON数组格式输出:
[
  {"scenario": "场景描述", "prompt": "测试任务描述", "expected": "期望输出特征"}
]

测试场景应覆盖:
1. 正常情况 (happy path)
2. 边界情况 (edge case)
3. 异常处理 (error handling)

只输出JSON数组，不要其他文字。"""


# ── Singleton ────────────────────────────────────────────────────

_verifier: Optional[SkillVerifier] = None


def get_skill_verifier() -> SkillVerifier:
    global _verifier
    if _verifier is None:
        _verifier = SkillVerifier()
    return _verifier


def init_skill_verifier(skill_library=None, chat_harness=None) -> SkillVerifier:
    global _verifier
    _verifier = SkillVerifier(skill_library=skill_library, chat_harness=chat_harness)
    logger.info("SkillVerifier initialized")
    return _verifier
