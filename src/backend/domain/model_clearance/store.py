# -*- coding: utf-8 -*-
"""T104 — Append-only disk store for model admission applications and evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    Evidence,
    GateVerdict,
    ImmutableViolation,
    ModelApplication,
    ReviewOpinion,
    canonical_json,
    sha256_of,
    utc_now_iso,
)

_DEFAULT_STORAGE = Path(__file__).resolve().parents[4] / "storage" / "model_clearance"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class ModelClearanceStore:
    def __init__(self, base_dir: Optional[Path | str] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else _DEFAULT_STORAGE
        self.apps_dir = self.base_dir / "applications"
        self.apps_dir.mkdir(parents=True, exist_ok=True)

    def _app_path(self, application_id: str) -> Path:
        return self.apps_dir / f"{application_id}.json"

    def save(self, app: ModelApplication) -> None:
        app.updated_at = utc_now_iso()
        path = self._app_path(app.application_id)
        _atomic_write(path, json.dumps(app.to_dict(), ensure_ascii=False, indent=2))

    def load(self, application_id: str) -> Optional[ModelApplication]:
        return self.get(application_id)

    def get(self, application_id: str) -> Optional[ModelApplication]:
        path = self._app_path(application_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ModelApplication.from_dict(data)
        except Exception:
            return None

    def list(self, limit: int = 50) -> List[ModelApplication]:
        apps: List[ModelApplication] = []
        if not self.apps_dir.exists():
            return apps
        for p in sorted(self.apps_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                apps.append(ModelApplication.from_dict(data))
                if len(apps) >= limit:
                    break
            except Exception:
                continue
        return apps

    def append_evidence(self, app_id: str, ev: Evidence) -> None:
        app = self.get(app_id)
        if app is None:
            raise KeyError(f"Application {app_id} not found")

        if any(e.evidence_id == ev.evidence_id for e in app.evidence):
            raise ImmutableViolation(f"Evidence {ev.evidence_id} already exists, overwrite forbidden")

        if not ev.digest:
            ev.digest = sha256_of(canonical_json(ev.payload))

        app.evidence.append(ev)
        self.save(app)

    def append_evidence_batch(self, app_id: str, evidences: List[Evidence]) -> None:
        app = self.get(app_id)
        if app is None:
            raise KeyError(f"Application {app_id} not found")

        existing_ids = {e.evidence_id for e in app.evidence}
        for ev in evidences:
            if ev.evidence_id in existing_ids:
                raise ImmutableViolation(f"Evidence {ev.evidence_id} already exists, overwrite forbidden")
            if not ev.digest:
                ev.digest = sha256_of(canonical_json(ev.payload))
            app.evidence.append(ev)
            existing_ids.add(ev.evidence_id)

        self.save(app)

    def append_verdict(self, app_id: str, verdict: GateVerdict) -> None:
        app = self.get(app_id)
        if app is None:
            raise KeyError(f"Application {app_id} not found")
        app.verdicts.append(verdict)
        self.save(app)

    def append_opinion(self, app_id: str, opinion: ReviewOpinion) -> None:
        app = self.get(app_id)
        if app is None:
            raise KeyError(f"Application {app_id} not found")
        app.opinions.append(opinion)
        self.save(app)


_INSTANCE: Optional[ModelClearanceStore] = None


def get_clearance_store() -> ModelClearanceStore:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ModelClearanceStore()
    return _INSTANCE
