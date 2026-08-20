# -*- coding: utf-8 -*-
"""T204 — Report schemas for AI 60s and world-intel (Pydantic validation gates)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ClaimLabel(str, Enum):
    FACT = "fact"
    OPINION = "opinion"
    ANALYSIS = "analysis"
    INFERENCE = "inference"
    SCENARIO = "scenario"


class Citation(BaseModel):
    url: str = Field(..., min_length=1)
    title: str = ""
    fetched_at: str = Field(..., min_length=1)
    published_at: Optional[str] = None
    content_hash: Optional[str] = None
    evidence_id: Optional[str] = None


class LabeledClaim(BaseModel):
    text: str = Field(..., min_length=1)
    label: ClaimLabel
    uncertainty: str = Field(..., min_length=1)
    citations: List[Citation] = Field(..., min_length=1)


class ScenarioNode(BaseModel):
    name: Literal["optimistic", "base", "pessimistic"]
    summary: str = Field(..., min_length=1)
    trigger_conditions: List[str] = Field(..., min_length=1)
    uncertainty: str = Field(..., min_length=1)


class AiNews60sReport(BaseModel):
    """Fixed structure for 60-second AI briefing."""

    channel: Literal["ai_news_60s"] = "ai_news_60s"
    headline: str = Field(..., min_length=1, description="一句话总览")
    bullets: List[LabeledClaim] = Field(..., min_length=1, max_length=8)
    why_it_matters: List[LabeledClaim] = Field(..., min_length=1)
    related_companies: List[str] = Field(default_factory=list)
    risks_and_counterpoints: List[LabeledClaim] = Field(..., min_length=1)
    citations: List[Citation] = Field(..., min_length=1)
    # Optional for backwards compatibility with previously published
    # documents; new runs populate this with the inspectable analysis graph.
    analysis: Dict[str, Any] = Field(default_factory=dict)
    data_cutoff: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    disclaimer: str = Field(
        default="本内容仅供研究参考，不构成投资建议。相关公司/赛道映射为信息映射，非荐股。"
    )

    @field_validator("related_companies")
    @classmethod
    def _companies_ok(cls, v: List[str]) -> List[str]:
        return v or []


class WorldIntelReport(BaseModel):
    """Fixed structure for dufu world-trend report."""

    channel: Literal["dufu_world_intel"] = "dufu_world_intel"
    what_happened: LabeledClaim
    timeline: List[LabeledClaim] = Field(..., min_length=1)
    drivers: List[LabeledClaim] = Field(..., min_length=1)
    data_trends: List[LabeledClaim] = Field(..., min_length=1)
    views_and_counterpoints: List[LabeledClaim] = Field(..., min_length=1)
    scenarios: List[ScenarioNode] = Field(..., min_length=3, max_length=3)
    market_transmission: List[LabeledClaim] = Field(..., min_length=1)
    citations: List[Citation] = Field(..., min_length=1)
    # The same inspectable research-deck contract used by AI 60 秒.  Keeping
    # it optional preserves the ability to open older published reports while
    # new world-trend runs can render the complete overview card system.
    analysis: Dict[str, Any] = Field(default_factory=dict)
    data_cutoff: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    disclaimer: str = Field(
        default="本内容仅供研究参考，不构成投资建议。情景与传导路径为分析框架，非预测保证。"
    )

    @field_validator("scenarios")
    @classmethod
    def _scenario_names(cls, v: List[ScenarioNode]) -> List[ScenarioNode]:
        names = {s.name for s in v}
        required = {"optimistic", "base", "pessimistic"}
        if names != required:
            raise ValueError(f"scenarios must include exactly {required}")
        for s in v:
            if not s.trigger_conditions:
                raise ValueError("each scenario requires trigger_conditions")
        return v


class OpenWeightsReport(BaseModel):
    """Fixed structure for the open-weights ecosystem report.

    Field names mirror WorldIntelReport so the shared brief builder and deck
    renderer work unchanged; only the tail section carries admission semantics.
    """

    channel: Literal["open_weights"] = "open_weights"
    what_happened: LabeledClaim
    timeline: List[LabeledClaim] = Field(..., min_length=1)
    drivers: List[LabeledClaim] = Field(..., min_length=1)
    data_trends: List[LabeledClaim] = Field(..., min_length=1)
    views_and_counterpoints: List[LabeledClaim] = Field(..., min_length=1)
    scenarios: List[ScenarioNode] = Field(..., min_length=3, max_length=3)
    license_watch: List[LabeledClaim] = Field(..., min_length=1)
    admission_impact: List[LabeledClaim] = Field(..., min_length=1)
    citations: List[Citation] = Field(..., min_length=1)
    analysis: Dict[str, Any] = Field(default_factory=dict)
    data_cutoff: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    disclaimer: str = Field(
        default="本内容仅供内部治理参考，不构成法律或采购建议。许可证结论须以原文为准。"
    )

    @field_validator("scenarios")
    @classmethod
    def _scenario_names(cls, v: List[ScenarioNode]) -> List[ScenarioNode]:
        names = {s.name for s in v}
        required = {"optimistic", "base", "pessimistic"}
        if names != required:
            raise ValueError(f"scenarios must include exactly {required}")
        for s in v:
            if not s.trigger_conditions:
                raise ValueError("each scenario requires trigger_conditions")
        return v


def validate_report(channel: str, payload: dict):
    if channel == "ai_news_60s":
        return AiNews60sReport.model_validate(payload)
    if channel == "dufu_world_intel":
        return WorldIntelReport.model_validate(payload)
    if channel == "open_weights":
        return OpenWeightsReport.model_validate(payload)
    raise ValueError(f"Unknown report channel: {channel}")
