# -*- coding: utf-8 -*-
"""Blocker 检查项的 LLM 分析与建议.

红线与 §5/§9 保持一致：本模块只产出说明性文字，**判定不从 LLM 取**。
调用方永远只读 analysis / recommendation / risk_if_ignored 三个字符串字段，
不存在任何一条代码路径能让模型输出改变 GateVerdict 或 Decision —— 这是结构性
保证，不是靠提示词约束。产出一律 ``advisory=True`` 并署名生成模型。

标准 §5 要求保障过程「可记录、可重复」，因此建议一经生成即随申请持久化，
报告每次渲染读同一份文本，而不是每次重新问模型。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from .models import BlockerAdvisory, ModelApplication, utc_now_iso
from .policy_evaluator import load_policy
from .standard import GATE_BY_ID

ADVISOR_VERSION = "1.0.0"

# 单条证据里塞进提示词的字段上限，避免把整份扫描结果喂给模型。
_MAX_PAYLOAD_KEYS = 24
_MAX_VALUE_CHARS = 200

_SYSTEM_PROMPT = (
    "你是 Lenovo 开放权重模型准入评审的分析助理，服务于 Open-Weight Model Assurance Standard。"
    "你的职责只有两件：解释某个阻断性检查项当前结果的含义，以及给出可执行的下一步建议。"
    "硬性约束："
    "1) 你无权改变任何判定，禁止输出「应通过」「可放行」「建议改判」之类的结论；"
    "2) 只依据用户消息中给出的事实作答，缺少信息就直说缺什么，禁止臆造证据、编号或数值；"
    "3) 用简体中文，措辞适合写进评审记录，不要客套话。"
)


def _trim_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in list(payload.items())[:_MAX_PAYLOAD_KEYS]:
        if k.startswith("_"):
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)[:_MAX_VALUE_CHARS]
        elif isinstance(v, str):
            v = v[:_MAX_VALUE_CHARS]
        out[k] = v
    return out


def build_gate_request(
    gate: str, app: ModelApplication, policy: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """把一道门的阻断项、标准要求与实际证据打包成可复核的提问事实集。"""
    spec = policy.get("gates", {}).get(gate, {})
    blockers = list(spec.get("blocker_checks", []))
    if not blockers:
        return None

    verdict = next((v for v in app.verdicts if v.gate == gate), None)
    if verdict is None:
        return None

    rules = {r.get("id"): r for r in spec.get("rules", []) if r.get("id")}
    failed = set(verdict.failed_checks)
    meta = GATE_BY_ID.get(gate, {})

    evidence: Dict[str, Any] = {}
    for e in app.evidence:
        if e.gate == gate and not e.advisory and e.payload:
            evidence.update(_trim_payload(e.payload))

    checks = []
    for cid in blockers:
        rule = rules.get(cid) or {}
        checks.append({
            "check_id": cid,
            "requirement": rule.get("message", ""),
            "rule_expression": rule.get("expr", ""),
            "result": "fail" if cid in failed else "pass",
        })
    return {
        "gate": gate,
        "section": meta.get("section", ""),
        "gate_name": meta.get("name", ""),
        "gate_verdict": verdict.verdict,
        "standard_summary": meta.get("summary", ""),
        "observed_evidence": evidence,
        "blocker_checks": checks,
    }


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    body = fenced.group(1) if fenced else text
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict)]


def parse_advisories(
    gate: str, request: Dict[str, Any], raw_text: str, generated_by: str
) -> List[BlockerAdvisory]:
    """只提取三个说明性字段；模型给出的任何判定字段一律丢弃。"""
    by_id = {c["check_id"]: c for c in request["blocker_checks"]}
    parsed = {}
    for item in _extract_json_array(raw_text):
        cid = str(item.get("check_id", "")).strip()
        if cid in by_id:
            parsed[cid] = item

    out: List[BlockerAdvisory] = []
    for cid, check in by_id.items():
        item = parsed.get(cid, {})
        out.append(BlockerAdvisory(
            gate=gate,
            check_id=cid,
            result=check["result"],
            analysis=str(item.get("analysis", "")).strip(),
            recommendation=str(item.get("recommendation", "")).strip(),
            risk_if_ignored=str(item.get("risk_if_ignored", "")).strip(),
            generated_by=generated_by,
            generated_at=utc_now_iso(),
            advisor_version=ADVISOR_VERSION,
        ))
    return out


async def _default_llm(messages: List[Dict[str, str]]) -> tuple[str, str]:
    """返回 (正文, 生成方署名)。上游报错时抛出，由调用方按缺证处理。"""
    from agents.chat_harness import LLMClient, get_chat_harness

    harness = get_chat_harness()
    config = harness.resolve_effective_config("clearance_blocker_advisor")
    model = harness.resolve_effective_model(config, agent_id="clearance_blocker_advisor")
    resp = await LLMClient(config).chat_completion(
        messages, model=model, temperature=0.1, max_tokens=2048
    )
    if resp.get("error"):
        raise RuntimeError(str(resp.get("message", "LLM 调用失败"))[:200])
    content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    return content, f"{config.provider.value}/{model}"


async def advise_blockers(
    app: ModelApplication,
    *,
    policy: Optional[Dict[str, Any]] = None,
    llm=None,
) -> List[BlockerAdvisory]:
    """为所有已评估门禁的阻断项生成分析与建议。每道门一次调用，并发执行。"""
    policy = policy or load_policy()
    llm = llm or _default_llm

    requests = [
        r for r in (build_gate_request(g, app, policy) for g in GATE_BY_ID)
        if r is not None
    ]
    if not requests:
        return []

    async def one(req: Dict[str, Any]) -> List[BlockerAdvisory]:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": (
                "以下是一道准入门禁的事实集（JSON）。请针对其中每一条 blocker_checks，"
                "给出该检查项当前结果的分析与下一步建议。\n\n"
                + json.dumps(req, ensure_ascii=False, indent=1)
                + "\n\n只输出 JSON 数组，每个元素形如："
                '{"check_id":"...","analysis":"不超过120字","recommendation":"不超过80字，'
                '写成可执行动作","risk_if_ignored":"不超过50字"}。'
                "不要输出数组以外的任何文字。"
            )},
        ]
        try:
            text, signature = await llm(messages)
        except Exception as exc:
            signature = "unavailable"
            text = ""
            return [
                BlockerAdvisory(
                    gate=req["gate"], check_id=c["check_id"], result=c["result"],
                    analysis="", recommendation="",
                    risk_if_ignored="",
                    generated_by=signature, generated_at=utc_now_iso(),
                    advisor_version=ADVISOR_VERSION,
                    error=str(exc)[:200],
                )
                for c in req["blocker_checks"]
            ]
        return parse_advisories(req["gate"], req, text, signature)

    groups = await asyncio.gather(*[one(r) for r in requests])
    return [a for group in groups for a in group]
