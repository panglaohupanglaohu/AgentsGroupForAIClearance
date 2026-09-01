"""六道验证门 — 论文 Section 5.1/5.2 的可审计实现.

论文依据:
- Eq.(13): P_i = G_s G_e G_t (预检门), R_i = G_x G_a (执行门), L_i = P_i R_i G_r (全门合取)
- Eq.(14): γ_m(c_i) = (b_m, r_m, E_m) (决策, 理由, 结构化证据三元组)
- Eq.(15): V_i = prio(b_1, ..., b_6), 优先级 reject ≻ revise ≻ pass
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence


class Decision(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    REJECT = "reject"


# 论文 Eq.(15)：reject ≻ revise ≻ pass
_PRIORITY: Dict[Decision, int] = {
    Decision.REJECT: 2,
    Decision.REVISE: 1,
    Decision.PASS: 0,
}

GATE_ORDER: List[str] = [
    "schema",
    "provenance",
    "tool",
    "execution",
    "safety",
    "regression",
]

# 论文 Eq.(13) 三段式分组
PRECHECK_GATES: Sequence[str] = ("schema", "provenance", "tool")    # P_i
EXECUTION_GATES: Sequence[str] = ("execution", "safety")            # R_i
RELEASE_GATES: Sequence[str] = ("regression",)                      # G_r


@dataclass
class GateVerdict:
    """论文 γ_m(c_i) = (b_m, r_m, E_m)."""

    gate: str
    decision: Decision
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    candidate_id: str = ""
    checked_at: float = 0.0
    env_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "decision": self.decision.value if isinstance(self.decision, Enum) else str(self.decision),
            "reason": self.reason,
            "evidence": self.evidence,
            "candidate_id": self.candidate_id,
            "checked_at": self.checked_at,
            "env_version": self.env_version,
        }


@dataclass
class GateReport:
    candidate_id: str
    verdicts: List[GateVerdict] = field(default_factory=list)

    @property
    def aggregate(self) -> Decision:
        worst = Decision.PASS
        for v in self.verdicts:
            if _PRIORITY[v.decision] > _PRIORITY[worst]:
                worst = v.decision
        return worst

    def _group_ok(self, names: Sequence[str]) -> bool:
        group = [v for v in self.verdicts if v.gate in names]
        if not group:
            return False
        return all(v.decision == Decision.PASS for v in group)

    @property
    def P(self) -> bool:
        """Eq.(13) P_i = G_s G_e G_t (预检合取)."""
        return self._group_ok(PRECHECK_GATES)

    @property
    def R(self) -> bool:
        """Eq.(13) R_i = G_x G_a (执行与安全合取)."""
        return self._group_ok(EXECUTION_GATES)

    @property
    def L(self) -> bool:
        """Eq.(13) L_i = P_i R_i G_r (全门发布合取)."""
        return self.P and self.R and self._group_ok(RELEASE_GATES)

    def failed_gates(self) -> List[str]:
        return [v.gate for v in self.verdicts if v.decision != Decision.PASS]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "aggregate": self.aggregate.value,
            "P": self.P,
            "R": self.R,
            "L": self.L,
            "failed_gates": self.failed_gates(),
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


def _entropy(labels: Sequence[str]) -> float:
    """归一化香农熵；单一来源=0，均匀多源→1。论文 7.4 报告 0.922。"""
    cleaned = [x for x in labels if x]
    if len(cleaned) <= 1:
        return 0.0
    counts = Counter(cleaned)
    n = len(cleaned)
    h = -sum((c / n) * math.log2(c / n) for c in counts.values())
    hmax = math.log2(len(counts)) if len(counts) > 1 else 1.0
    return round(h / hmax, 4) if hmax > 0 else 0.0


def gate_schema(skill: Dict[str, Any], ctx: Dict[str, Any]) -> GateVerdict:
    """G_s：必填字段 / 类型 / 基础完整性。"""
    REQUIRED = ["name", "description", "category", "tools", "instructions"]
    missing = [f for f in REQUIRED if not skill.get(f)]
    if missing:
        return GateVerdict("schema", Decision.REVISE, f"缺少必填字段: {missing}", {"missing_fields": missing})
    if not isinstance(skill.get("tools"), list):
        return GateVerdict("schema", Decision.REJECT, "tools 必须是列表", {})
    return GateVerdict("schema", Decision.PASS, "schema 完整", {"checked_fields": REQUIRED})


def gate_provenance(skill: Dict[str, Any], ctx: Dict[str, Any]) -> GateVerdict:
    """G_e：溯源保真 —— 校验 evidence_spans 真实锚定源发言，防止抽取模型幻觉编造。"""
    spans = skill.get("evidence_spans") or []
    if not spans:
        return GateVerdict("provenance", Decision.REVISE, "无 evidence_spans 溯源区间", {})

    transcript = ctx.get("transcript") or {}
    dangling: List[str] = []
    mismatched: List[str] = []
    ok: List[str] = []

    for sp in spans:
        uid = str(sp.get("utterance_id") or "")
        src = transcript.get(uid)
        if src is None:
            dangling.append(uid)
            continue
        quoted = str(sp.get("text") or "").strip()
        src_text = str(src.get("text") or "") if isinstance(src, dict) else str(src)
        if quoted and quoted not in src_text:
            mismatched.append(uid)
        else:
            ok.append(uid)

    if dangling:
        return GateVerdict("provenance", Decision.REJECT, f"引用了不存在的发言: {dangling}", {"dangling": dangling})
    if mismatched:
        return GateVerdict("provenance", Decision.REVISE, f"引文与源发言不符: {mismatched}", {"mismatched": mismatched})

    roles = [transcript[u].get("role") for u in ok if isinstance(transcript.get(u), dict) and transcript[u].get("role")]
    return GateVerdict(
        "provenance",
        Decision.PASS,
        "溯源可核对",
        {"verified_spans": len(ok), "provenance_role_entropy": _entropy(roles)},
    )


def gate_tool(skill: Dict[str, Any], ctx: Dict[str, Any]) -> GateVerdict:
    """G_t：工具落地 —— 工具必须在可 mock 白名单或已知工具集中。"""
    known = ctx.get("known_tools") or set()
    tools = skill.get("tools") or []
    unknown = [t for t in tools if str(t).lower() not in {str(k).lower() for k in known}]
    if unknown:
        return GateVerdict("tool", Decision.REVISE, f"工具不在可用白名单: {unknown}", {"unknown_tools": unknown})
    return GateVerdict("tool", Decision.PASS, "工具可落地", {"tools": tools})


def gate_execution(skill: Dict[str, Any], ctx: Dict[str, Any]) -> GateVerdict:
    """G_x：受控执行 —— 评估沙箱执行或语义执行结果。"""
    sandbox = ctx.get("sandbox_result") or {}
    if not sandbox:
        return GateVerdict("execution", Decision.REVISE, "尚未执行沙箱", {})
    if not sandbox.get("passed"):
        err = sandbox.get("error") or "沙箱执行失败"
        return GateVerdict("execution", Decision.REJECT, f"沙箱执行失败: {err}", sandbox)
    return GateVerdict("execution", Decision.PASS, "沙箱执行通过", sandbox)


def gate_safety(skill: Dict[str, Any], ctx: Dict[str, Any]) -> GateVerdict:
    """G_a：安全合规 —— 危险破坏指令与未授权敏感操作零容忍直接 reject。"""
    DANGEROUS = ("rm -rf /", "drop table", "mkfs", "dd if=", ":(){", "chmod 777 /")
    blob = " ".join(str(skill.get(k, "")) for k in ("instructions", "description", "name"))
    hits = [p for p in DANGEROUS if p in blob.lower()]
    if hits:
        return GateVerdict("safety", Decision.REJECT, f"命中危险破坏模式: {hits}", {"patterns": hits})
    return GateVerdict("safety", Decision.PASS, "无危险操作模式", {})


def gate_regression(skill: Dict[str, Any], ctx: Dict[str, Any]) -> GateVerdict:
    """G_r：回归非退化 —— 论文 Eq.(20) G_r = 1[LCB >= delta_min] * C_i * H_i。"""
    comp = ctx.get("competition_result")
    if comp is None:
        return GateVerdict("regression", Decision.REVISE, "尚未进行版本竞争", {})
    if comp.get("accepted"):
        lcb = comp.get("lcb", 0.0)
        dmin = comp.get("delta_min", 0.0)
        return GateVerdict("regression", Decision.PASS, f"LCB={lcb:.4f} >= delta_min={dmin}", comp)
    return GateVerdict("regression", Decision.REJECT, str(comp.get("reason", "版本竞争未通过")), comp)


_GATES: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], GateVerdict]] = {
    "schema": gate_schema,
    "provenance": gate_provenance,
    "tool": gate_tool,
    "execution": gate_execution,
    "safety": gate_safety,
    "regression": gate_regression,
}


def run_gates(
    skill: Dict[str, Any],
    ctx: Dict[str, Any],
    *,
    candidate_id: str = "",
    env_version: str = "",
) -> GateReport:
    """按论文顺序执行六门。

    前段 reject 后仍执行剩余门以留存全量审计证据（论文 5.2 要求）。
    """
    verdicts: List[GateVerdict] = []
    now = time.time()
    for name in GATE_ORDER:
        fn = _GATES.get(name)
        if fn is None:
            v = GateVerdict(name, Decision.REVISE, f"未知门: {name}", {})
        else:
            try:
                v = fn(skill, ctx)
            except Exception as e:
                v = GateVerdict(name, Decision.REVISE, f"门执行异常: {e}", {})
        v.candidate_id = candidate_id
        v.checked_at = now
        v.env_version = env_version
        verdicts.append(v)
    return GateReport(candidate_id=candidate_id, verdicts=verdicts)
