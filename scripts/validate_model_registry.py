#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T102 — Model license registry validation script."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

REQUIRED = [
    "model_id",
    "display_name",
    "vendor",
    "license_id",
    "license_url",
    "license_class",
    "weights_url",
    "source_url",
]
ENUM_CLASS = {"commercial_ok", "conditional", "restricted"}


def validate_registry(path: str | Path) -> int:
    path = Path(path)
    if not path.exists():
        print(f"FAIL: File not found: {path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: Invalid JSON in {path}: {exc}", file=sys.stderr)
        return 1

    errors: List[str] = []
    models = data.get("models")
    if not isinstance(models, list):
        print("FAIL: 'models' must be a list", file=sys.stderr)
        return 1

    if len(models) < 20:
        errors.append(f"Model count ({len(models)}) is less than required minimum of 20")

    seen_ids = set()
    for i, m in enumerate(models):
        if not isinstance(m, dict):
            errors.append(f"[{i}] item is not an object")
            continue

        for field in REQUIRED:
            val = m.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"[{i}] ({m.get('model_id', 'unknown')}) missing required field '{field}'")

        lic_cls = m.get("license_class")
        if lic_cls not in ENUM_CLASS:
            errors.append(f"[{i}] invalid license_class '{lic_cls}' (expected {ENUM_CLASS})")

        for url_field in ("license_url", "weights_url", "source_url"):
            u = m.get(url_field)
            if u and not str(u).startswith("https://"):
                errors.append(f"[{i}] {url_field} must start with https://, got '{u}'")

        mid = m.get("model_id")
        if mid:
            if mid in seen_ids:
                errors.append(f"[{i}] duplicate model_id: '{mid}'")
            seen_ids.add(mid)

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print(f"OK: {path} passed validation with {len(models)} models.")
    return 0


if __name__ == "__main__":
    default_path = Path(__file__).resolve().parents[1] / "config" / "model_license_registry.json"
    target = sys.argv[1] if len(sys.argv) > 1 else str(default_path)
    sys.exit(validate_registry(target))
