"""记忆污染筛查 — 论文 Section 7.14。

论文依据:
- 实验 7.14：恶意记录注入干净事件流，筛查规则必须保持高召回（Recall=100%），
  宁可误标不可漏放（Precision~50%, F1~66.7%）。
- 恶意模式识别: Prompt Injection, 角色篡改, 破坏性指令, 凭据泄露, XSS, 路径穿越, 异常大记录与控制字符。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

# 高召回规则集（正则，不区分大小写）
_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE), "prompt_injection"),
    (re.compile(r"(you\s+are\s+now|from\s+now\s+on)\s+", re.IGNORECASE), "role_override"),
    (re.compile(r"rm\s+-rf\s+/|drop\s+table|mkfs|dd\s+if=", re.IGNORECASE), "destructive_cmd"),
    (re.compile(r"(api[_-]?key|password|secret|token)\s*[:=]", re.IGNORECASE), "secret_leak"),
    (re.compile(r"<\s*script|javascript:", re.IGNORECASE), "xss"),
    (re.compile(r"\.\./\.\./"), "path_traversal"),
]


@dataclass
class ScreenResult:
    flagged: List[str] = field(default_factory=list)
    clean: List[str] = field(default_factory=list)
    reasons: Dict[str, List[str]] = field(default_factory=dict)

    def metrics(self, truth_malicious: Sequence[str]) -> Dict[str, float]:
        """论文 Eq.(28)(29) 评估指标，用于实验评测。"""
        flagged_set = set(self.flagged)
        truth_set = set(truth_malicious)
        tp = len(flagged_set & truth_set)
        fn = len(truth_set - flagged_set)
        fp = len(flagged_set - truth_set)
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        f1 = (2.0 * recall * precision / (recall + precision)) if (recall + precision) > 0 else 0.0
        return {
            "tp": float(tp),
            "fp": float(fp),
            "fn": float(fn),
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f1": round(f1, 4),
        }


def screen_records(
    records: Sequence[Dict[str, Any]],
    *,
    id_key: str = "id",
) -> ScreenResult:
    """对记忆记录流进行污染筛查，高召回优先."""
    flagged: List[str] = []
    clean: List[str] = []
    reasons: Dict[str, List[str]] = {}

    for i, rec in enumerate(records):
        rid = str(rec.get(id_key) or rec.get("record_id") or f"rec_{i}")
        blob = " ".join(str(v) for v in rec.values() if isinstance(v, (str, int, float)))
        hits = [label for pat, label in _PATTERNS if pat.search(blob)]

        # 启发式规则：异常长记录或低位控制字符
        if len(blob) > 20000:
            hits.append("oversized")
        if any(ord(c) < 9 for c in blob[:5000]):
            hits.append("control_chars")

        if hits:
            flagged.append(rid)
            reasons[rid] = sorted(set(hits))
        else:
            clean.append(rid)

    return ScreenResult(flagged=flagged, clean=clean, reasons=reasons)
