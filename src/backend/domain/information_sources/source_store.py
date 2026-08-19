# -*- coding: utf-8 -*-
"""Persist user-configured information sources."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

from .models import SourceConfig

_DEFAULT = Path(__file__).resolve().parents[4] / "storage" / "information_sources" / "sources.json"


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class SourceConfigStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _DEFAULT

    def _load(self) -> List[SourceConfig]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [SourceConfig.from_dict(x) for x in data.get("sources") or []]

    def _save(self, sources: List[SourceConfig]) -> None:
        _atomic_write(
            self.path,
            json.dumps({"sources": [s.to_dict() for s in sources]}, ensure_ascii=False, indent=2),
        )

    def list(self) -> List[SourceConfig]:
        sources = self._load()
        if not sources:
            sources = self.seed_defaults()
        return sources

    def get(self, source_id: str) -> Optional[SourceConfig]:
        for s in self.list():
            if s.source_id == source_id:
                return s
        return None

    def seed_defaults(self) -> List[SourceConfig]:
        """Seed offline fixture sources so the data-intelligence page is usable."""
        defaults = [
            SourceConfig(
                source_id="fixture-ai-demo",
                kind="fixture",
                name="AI Demo Fixture",
                enabled=True,
                reputation_score=0.8,
                license_note="demo",
                language="zh",
                region="global",
                options={
                    "items": [
                        {
                            "title": "开源模型发布（演示）",
                            "url": "https://example.com/ai/demo-1",
                            "content": "演示用：开源权重与基准更新（非真实事件）。",
                            "published_at": "2026-07-01T00:00:00+00:00",
                        },
                        {
                            "title": "企业 AI 落地调查（演示）",
                            "url": "https://example.com/ai/demo-2",
                            "content": "演示用：采用率与合规障碍摘要。",
                            "published_at": "2026-07-02T00:00:00+00:00",
                        },
                    ]
                },
            ),
            SourceConfig(
                source_id="fixture-world-demo",
                kind="fixture",
                name="World Trends Demo Fixture",
                enabled=True,
                reputation_score=0.8,
                license_note="demo",
                language="zh",
                region="global",
                options={
                    "items": [
                        {
                            "title": "多边会谈进展（演示）",
                            "url": "https://example.com/world/demo-1",
                            "content": "演示用：贸易与安全议题阶段性共识。",
                            "published_at": "2026-07-01T00:00:00+00:00",
                        },
                        {
                            "title": "能源价格观察（演示）",
                            "url": "https://example.com/world/demo-2",
                            "content": "演示用：基准价格波动与制造业成本。",
                            "published_at": "2026-07-02T00:00:00+00:00",
                        },
                    ]
                },
            ),
        ]
        self._save(defaults)
        return defaults

    def create(self, data: dict) -> SourceConfig:
        sources = self._load()
        if not sources:
            sources = self.seed_defaults()
        sid = data.get("source_id") or str(uuid.uuid4())[:10]
        cfg = SourceConfig.from_dict({**data, "source_id": sid})
        sources.append(cfg)
        self._save(sources)
        return cfg

    def update(self, source_id: str, patch: dict) -> Optional[SourceConfig]:
        sources = self._load()
        out = None
        for i, s in enumerate(sources):
            if s.source_id == source_id:
                merged = {**s.to_dict(), **patch, "source_id": source_id}
                out = SourceConfig.from_dict(merged)
                sources[i] = out
                break
        if out:
            self._save(sources)
        return out

    def delete(self, source_id: str) -> bool:
        sources = self._load()
        new = [s for s in sources if s.source_id != source_id]
        if len(new) == len(sources):
            return False
        self._save(new)
        return True


_src_store: Optional[SourceConfigStore] = None


def get_source_config_store() -> SourceConfigStore:
    global _src_store
    if _src_store is None:
        _src_store = SourceConfigStore()
    return _src_store
