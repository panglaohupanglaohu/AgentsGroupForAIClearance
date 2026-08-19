# -*- coding: utf-8 -*-
"""T201 — Base Scanner contract."""

from __future__ import annotations

import concurrent.futures
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from ..models import Evidence, ModelIdentity, canonical_json, sha256_of, utc_now_iso


class Scanner(ABC):
    name: str = "base-scanner"
    version: str = "1.0.0"
    gate: str = "G1"
    check_ids: List[str] = []
    timeout_seconds: int = 30

    @abstractmethod
    def collect(self, identity: ModelIdentity) -> Dict[str, Any]:
        """Collect raw technical findings for the model identity."""
        raise NotImplementedError

    def run(self, identity: ModelIdentity) -> Evidence:
        start_t = time.time()
        payload: Dict[str, Any] = {}

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.collect, identity)
                payload = future.result(timeout=self.timeout_seconds)
                if not isinstance(payload, dict):
                    payload = {"data": payload}
                payload["_status"] = "ok"
        except concurrent.futures.TimeoutError:
            payload = {
                "_status": "timeout",
                "_error": f"Scanner {self.name} timed out after {self.timeout_seconds}s",
            }
        except Exception as exc:
            payload = {
                "_status": "error",
                "_error": str(exc),
            }

        payload["_duration_sec"] = round(time.time() - start_t, 4)
        check_id = self.check_ids[0] if self.check_ids else f"{self.gate}-01"
        evidence_id = f"ev-{uuid.uuid4().hex[:12]}"

        return Evidence(
            evidence_id=evidence_id,
            gate=self.gate,
            check_id=check_id,
            collector=self.name,
            collector_version=self.version,
            collected_at=utc_now_iso(),
            payload=payload,
            digest=sha256_of(canonical_json(payload)),
        )
