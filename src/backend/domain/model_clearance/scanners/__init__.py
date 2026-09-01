# -*- coding: utf-8 -*-
"""Scanner registry — 按 Lenovo Open-Weight Model Assurance Standard 的章节编排.

G0 §3 · G1 §6.1 · G2 §6.2 · G3 §6.3 · G4 §6.4 · G5 §7.1 · G6 §7.2 · G7 §7.3 · G8 §8
"""

from typing import Any, Dict, List, Type

from .base import Scanner
from .deployment_gates import (
    ContinuousAssuranceScanner,
    DeploymentDataFlowScanner,
    ModelAuthorityScanner,
    ProhibitedDeploymentScanner,
    UseCaseLegalScanner,
    _ContextScanner,
)
from .evaluation_gates import BehaviourEvaluationScanner, ThreatIntelRedTeamScanner
from .g1_provenance import ManifestScanner, SignatureScanner, platform_endorse
from .g2_bom_security import BomScanner, CveScanner, FormatScanner
from .g3_g4_g5 import LicenseScanner, RedTeamScanner, ResourceScanner

_GATE_SCANNER_MAP: Dict[str, List[Type[Scanner]]] = {
    "G0": [ProhibitedDeploymentScanner],
    "G1": [ManifestScanner, SignatureScanner],
    "G2": [FormatScanner, BomScanner, CveScanner],
    "G3": [BehaviourEvaluationScanner],
    "G4": [ThreatIntelRedTeamScanner],
    "G5": [DeploymentDataFlowScanner],
    "G6": [ModelAuthorityScanner],
    # 许可证证据并入 §7.3 法务门；ResourceScanner 为 §8 运营可支持性提供容量输入
    "G7": [UseCaseLegalScanner, LicenseScanner],
    "G8": [ContinuousAssuranceScanner, ResourceScanner],
}


def scanners_for(gate: str, context: Dict[str, Any] | None = None) -> List[Scanner]:
    """实例化该门的扫描器；需要部署上下文的扫描器自动注入 context。"""
    out: List[Scanner] = []
    for cls in _GATE_SCANNER_MAP.get(gate, []):
        if issubclass(cls, _ContextScanner):
            out.append(cls(context or {}))
        else:
            out.append(cls())
    return out


__all__ = [
    "Scanner",
    "ManifestScanner",
    "SignatureScanner",
    "platform_endorse",
    "FormatScanner",
    "BomScanner",
    "CveScanner",
    "LicenseScanner",
    "ResourceScanner",
    "RedTeamScanner",
    "BehaviourEvaluationScanner",
    "ThreatIntelRedTeamScanner",
    "ProhibitedDeploymentScanner",
    "DeploymentDataFlowScanner",
    "ModelAuthorityScanner",
    "UseCaseLegalScanner",
    "ContinuousAssuranceScanner",
    "scanners_for",
]
