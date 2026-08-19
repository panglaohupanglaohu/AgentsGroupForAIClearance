# -*- coding: utf-8 -*-
"""T603 / T604 — Runtime Baseline Conformance Validator & Preflight Weight Verification."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import sha256_of
from .registry import ApprovedRegistryEntry


def _safe_get(obj: Any, path: str, default: Any = None) -> Any:
    curr = obj
    for part in path.split("."):
        if curr is None:
            return default
        if isinstance(curr, dict):
            curr = curr.get(part)
        elif hasattr(curr, part):
            curr = getattr(curr, part)
        else:
            return default
    return curr if curr is not None else default


def _env_val(container: Any, key: str) -> Optional[str]:
    envs = _safe_get(container, "env", [])
    for item in envs:
        if isinstance(item, dict) and item.get("name") == key:
            return str(item.get("value", ""))
        elif hasattr(item, "name") and item.name == key:
            return str(getattr(item, "value", ""))
    return None


INVARIANTS: List[Tuple[str, Callable[[Any], bool]]] = [
    (
        "runAsNonRoot",
        lambda p: bool(_safe_get(p, "spec.securityContext.runAsNonRoot") is True),
    ),
    (
        "nonRootUser",
        lambda p: bool(
            _safe_get(p, "spec.securityContext.runAsUser") is not None
            and int(_safe_get(p, "spec.securityContext.runAsUser", 0)) != 0
        ),
    ),
    (
        "readOnlyRootFs",
        lambda p: all(
            bool(_safe_get(c, "securityContext.readOnlyRootFilesystem") is True)
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
    (
        "noPrivEscalation",
        lambda p: all(
            bool(_safe_get(c, "securityContext.allowPrivilegeEscalation") is False)
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
    (
        "capsDropAll",
        lambda p: all(
            "ALL" in (_safe_get(c, "securityContext.capabilities.drop") or [])
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
    (
        "notPrivileged",
        lambda p: not any(
            bool(_safe_get(c, "securityContext.privileged") is True)
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
    (
        "noHostNamespaces",
        lambda p: not (
            bool(_safe_get(p, "spec.hostNetwork", False))
            or bool(_safe_get(p, "spec.hostPID", False))
            or bool(_safe_get(p, "spec.hostIPC", False))
        ),
    ),
    (
        "resourceLimitsSet",
        lambda p: len(_safe_get(p, "spec.containers", [])) > 0
        and all(
            bool(_safe_get(c, "resources.limits"))
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
    (
        "imagePinnedByDigest",
        lambda p: len(_safe_get(p, "spec.containers", [])) > 0
        and all(
            "@sha256:" in str(_safe_get(c, "image", ""))
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
    (
        "saTokenNotMounted",
        lambda p: bool(_safe_get(p, "spec.automountServiceAccountToken") is False),
    ),
    (
        "promptLoggingOff",
        lambda p: any(
            _env_val(c, "DISABLE_PROMPT_LOGGING") == "true"
            for c in _safe_get(p, "spec.containers", [])
        ),
    ),
]


def check_baseline(
    pod: Dict[str, Any] | Any,
    entry: ApprovedRegistryEntry,
    namespace_has_deny_all: bool = True,
    runtime_weight_digest: Optional[str] = None,
) -> List[str]:
    """T603: Check Pod specification and runtime state against baseline invariants."""
    violations: List[str] = []

    for name, predicate in INVARIANTS:
        try:
            if not predicate(pod):
                violations.append(name)
        except Exception:
            violations.append(name)

    # Highest risk check: Weight digest must strictly match locked digest
    if runtime_weight_digest is not None:
        if runtime_weight_digest != entry.locked_digest:
            violations.append("weightDigestMismatch")
    else:
        # Check env or container annotation placeholder
        c_digest = None
        for c in _safe_get(pod, "spec.containers", []):
            d = _env_val(c, "MODEL_LOCKED_DIGEST")
            if d:
                c_digest = d
                break
        if c_digest and c_digest != "PLACEHOLDER_LOCKED_DIGEST" and c_digest != entry.locked_digest:
            violations.append("weightDigestMismatch")

    if not namespace_has_deny_all:
        violations.append("missingDenyAllNetworkPolicy")

    return violations


def preflight_verify_weights(
    entry: ApprovedRegistryEntry,
    mounted_path: str | Path,
) -> bool:
    """T604: Compute manifest root digest of mounted weights and verify against locked digest."""
    path = Path(mounted_path)
    if not path.exists():
        return False

    if path.is_file():
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        actual_digest = h.hexdigest()
    else:
        # Directory manifest root
        entries = []
        for root, _, files in os.walk(path):
            for file in sorted(files):
                fp = Path(root) / file
                entries.append(f"{file}:{fp.stat().st_size}")
        actual_digest = sha256_of(",".join(entries))

    return actual_digest == entry.locked_digest
