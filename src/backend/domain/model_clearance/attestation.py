# -*- coding: utf-8 -*-
"""T501 / T504 — in-toto v1 Attestation generation & DSSE Envelope verification (T5 Principle)."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

from .models import GateVerdict, ModelApplication, canonical_json, sha256_of, utc_now_iso

PLATFORM_SIGNING_KEY = "ag-platform-clearance-key-2026"


def dsse_sign(statement: Dict[str, Any], key: str = PLATFORM_SIGNING_KEY) -> Dict[str, Any]:
    """Wrap an in-toto statement in a DSSE envelope with simulated cryptographic signature."""
    payload_bytes = canonical_json(statement).encode("utf-8")
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")

    sig_input = f"DSSEv1 30 application/vnd.in-toto+json {len(payload_bytes)} {payload_b64} {key}"
    sig_digest = sha256_of(sig_input)
    sig_b64 = base64.b64encode(sig_digest.encode("utf-8")).decode("ascii")

    return {
        "payloadType": "application/vnd.in-toto+json",
        "payload": payload_b64,
        "signatures": [
            {
                "keyid": f"keyid:{sha256_of(key)[:16]}",
                "sig": sig_b64,
            }
        ],
    }


def dsse_verify(envelope: Dict[str, Any], key: str = PLATFORM_SIGNING_KEY) -> bool:
    """Verify a DSSE envelope."""
    try:
        payload_b64 = envelope.get("payload", "")
        payload_bytes = base64.b64decode(payload_b64.encode("ascii"))
        signatures = envelope.get("signatures", [])
        if not signatures:
            return False

        sig_input = f"DSSEv1 30 application/vnd.in-toto+json {len(payload_bytes)} {payload_b64} {key}"
        expected_sig_digest = sha256_of(sig_input)
        expected_sig_b64 = base64.b64encode(expected_sig_digest.encode("utf-8")).decode("ascii")

        return signatures[0].get("sig") == expected_sig_b64
    except Exception:
        return False


def issue_gate_attestation(app: ModelApplication, verdict: GateVerdict, policy_version: int = 1) -> Dict[str, Any]:
    """T501: Issue signed in-toto statement for gate verdict."""
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "name": app.identity.model_id,
                "digest": {"sha256": app.identity.root_digest or "digest-pending"},
            }
        ],
        "predicateType": "https://modelclearance/gate-verdict/v1",
        "predicate": {
            "application_id": app.application_id,
            "gate": verdict.gate,
            "verdict": verdict.verdict,
            "severity": verdict.severity,
            "failed_checks": verdict.failed_checks,
            "evidence_refs": verdict.evidence_refs,
            "policy_version": policy_version,
            "decided_by": verdict.decided_by,
            "decided_at": verdict.decided_at,
        },
    }
    return dsse_sign(statement, key=PLATFORM_SIGNING_KEY)


def extract_attestation_statement(envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        raw = base64.b64decode(envelope["payload"].encode("ascii")).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None
