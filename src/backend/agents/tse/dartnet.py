"""DART-Net 命名装配与四阶段表征架构 — 论文 Section 4.4。

论文依据:
- Stage 1: Utterance Encoding (BLAKE2b 确定性发言编码)
- Stage 2: Temporal Modeling (三层空洞因果 TCN, k=3, d=[1,2,4])
- Stage 3: Field-Query Attention (五字段跨注意力定位技能时刻)
- Stage 4: Constrained Decoding (Pydantic / JSON schema 约束解码)
- Eq.(8): R_L = 1 + (k - 1) * (2^L - 1)  (感受野公式, k=3, L=3 -> R_L=15)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config import TSEConfig
from .decoder import ConstrainedSkillDecoder
from .encoder import UtteranceEncoder
from .pipeline import TSEPipeline, get_tse_pipeline
from .skill_attention import SkillQueryAttention
from .tcn import TCNTemporalModule
from .transcript import PlazaTranscript, parse_transcript

STAGES: Tuple[str, ...] = (
    "utterance_encoding",
    "temporal_modeling",
    "field_query_attention",
    "constrained_decoding",
)


def receptive_field(k: int = 3, layers: int = 3) -> int:
    """论文 Eq.(8) R_L = 1 + (k - 1) * (2^L - 1).

    当 k=3, L=3 时，R_L = 1 + 2 * 7 = 15。
    """
    if layers <= 0:
        return 1
    return 1 + (k - 1) * ((2 ** layers) - 1)


class DARTNet:
    """DART-Net (Dialogue-Aware Representation and Translation Network) 门面封装."""

    def __init__(self, config: Optional[TSEConfig] = None):
        self.config = config or TSEConfig()
        self.pipeline: TSEPipeline = get_tse_pipeline(self.config)

    def receptive_field(self) -> int:
        return receptive_field(k=self.config.kernel_size, layers=len(self.config.dilations))

    def forward(
        self,
        transcript: PlazaTranscript,
        *,
        collect_timing: bool = True,
    ) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """执行 Stage 1-3 前向计算，返回表征与阶段耗时."""
        t0 = time.perf_counter()
        stages_out = self.pipeline.encode_stages(transcript)
        t_total = (time.perf_counter() - t0) * 1000

        timings = dict(stages_out.get("timings", {}))
        if collect_timing:
            timings["total_forward_ms"] = round(t_total, 3)

        return stages_out, timings


def forward_dartnet(
    transcript_or_text: Any,
    *,
    config: Optional[TSEConfig] = None,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """便捷函数：对讨论文本或 Transcript 执行 DART-Net 表征."""
    if isinstance(transcript_or_text, str):
        transcript = parse_transcript(transcript_or_text)
    else:
        transcript = transcript_or_text
    net = DARTNet(config)
    return net.forward(transcript)
