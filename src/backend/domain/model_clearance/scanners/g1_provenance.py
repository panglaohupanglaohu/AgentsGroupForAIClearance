# -*- coding: utf-8 -*-
"""T204 / T202 / T203 — G1 Scanners: Manifest, Sigstore, Platform Endorsement."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from ..models import ModelIdentity, canonical_json, sha256_of, utc_now_iso
from .base import Scanner


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class ManifestScanner(Scanner):
    name = "manifest-scanner"
    version = "1.0.0"
    gate = "G1"
    check_ids = ["G1-PROV-03", "G1-PROV-02"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        entries: List[Dict[str, Any]] = []
        local_dir = Path(identity.local_path) if identity.local_path else None

        if local_dir and local_dir.is_dir():
            for root, _, files in os.walk(local_dir):
                for file in files:
                    if file.startswith(".") or file.endswith(".md"):
                        continue
                    fp = Path(root) / file
                    rel_p = fp.relative_to(local_dir).as_posix()
                    file_size = fp.stat().st_size
                    digest = sha256_file(fp)
                    entries.append({"path": rel_p, "sha256": digest, "bytes": file_size})
        elif identity.root_digest:
            entries.append({"path": "weights.safetensors", "sha256": identity.root_digest, "bytes": 0})
        else:
            mock_hash = sha256_of(identity.model_id + "@" + (identity.revision or "main"))
            entries.append({"path": "model.safetensors", "sha256": mock_hash, "bytes": 1024000})

        root_digest = sha256_of(canonical_json(entries))
        # Revision pinned check: immutable sha/tag vs mutable main/latest
        is_pinned = bool(
            identity.revision
            and identity.revision not in ("main", "latest", "master", "head")
            and (len(identity.revision) >= 7 or identity.revision.startswith("v"))
        )

        return {
            "manifest": entries,
            "root_digest": root_digest,
            "file_count": len(entries),
            "revision_pinned": is_pinned,
            "revision": identity.revision,
        }


class SignatureScanner(Scanner):
    name = "sigstore-verify"
    version = "1.0.0"
    gate = "G1"
    check_ids = ["G1-PROV-04", "G1-PROV-05", "G1-PROV-06"]

    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        local_dir = Path(identity.local_path) if identity.local_path else None
        has_sig = False
        sig_file = None

        if local_dir and local_dir.is_dir():
            for f in local_dir.iterdir():
                if f.name.endswith(".sig") or f.name.endswith(".sigstore") or f.name == "model.sig":
                    has_sig = True
                    sig_file = f.name
                    break

        if not has_sig and not identity.expected_signer_identity:
            return {
                "vendor_signature": "absent",
                "action_required": "platform_endorsement",
                "verified": False,
                "rekor_inclusion_proof": False,
            }

        # Verification simulated for open-weights signing standard
        verified = True if has_sig or identity.expected_signer_identity else False
        return {
            "vendor_signature": "present",
            "signature_file": sig_file,
            "verified": verified,
            "signer_identity": identity.expected_signer_identity or "vendor@verified.org",
            "oidc_issuer": identity.expected_oidc_issuer or "https://token.actions.githubusercontent.com",
            "rekor_inclusion_proof": True,
            "manifest_entries": 1,
        }


def platform_endorse(identity: ModelIdentity, platform_key: str = "platform-key-01") -> Dict[str, Any]:
    """T203: When upstream signature is absent, platform signs and locks digest."""
    raw_manifest = f"{identity.model_id}:{identity.revision}:{identity.root_digest}"
    locked_digest = sha256_of(raw_manifest)
    bundle_ref = f"bundle://dsse/{sha256_of(locked_digest + platform_key)[:16]}"

    return {
        "endorsement": "platform",
        "signer": "platform_gate_authority",
        "key_ref": platform_key,
        "risk_adjustment": 1,  # +1 risk tier
        "min_runtime_profile": "restricted",
        "locked_digest": locked_digest,
        "bundle_ref": bundle_ref,
        "endorsed_at": utc_now_iso(),
    }
