# -*- coding: utf-8 -*-
"""Scanners registry for Gate G1 to G5."""

from typing import Dict, List, Type

from .base import Scanner
from .g1_provenance import ManifestScanner, SignatureScanner, platform_endorse
from .g2_bom_security import BomScanner, CveScanner, FormatScanner
from .g3_g4_g5 import LicenseScanner, RedTeamScanner, ResourceScanner

_GATE_SCANNER_MAP: Dict[str, List[Type[Scanner]]] = {
    "G1": [ManifestScanner, SignatureScanner],
    "G2": [FormatScanner, BomScanner, CveScanner],
    "G3": [LicenseScanner],
    "G4": [ResourceScanner],
    "G5": [RedTeamScanner],
}


def scanners_for(gate: str) -> List[Scanner]:
    scanner_classes = _GATE_SCANNER_MAP.get(gate, [])
    return [cls() for cls in scanner_classes]


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
    "scanners_for",
]
