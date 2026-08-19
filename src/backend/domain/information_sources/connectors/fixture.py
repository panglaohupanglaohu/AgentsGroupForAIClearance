# -*- coding: utf-8 -*-
"""Fixture connector — offline tests and demos (no network)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models import FetchBatch, FetchItem, HealthResult, SourceConfig, SourceManifest
from .base import BaseConnector

MANIFEST = SourceManifest(
    kind="fixture",
    name="Fixture Source",
    description="Offline fixture items from config.options['items']",
    version="1.0.0",
    supports_cursor=True,
    requires_network=False,
    config_schema={
        "items": {"type": "array", "description": "List of {title,url,content,published_at}"},
    },
)


class FixtureConnector(BaseConnector):
    async def healthcheck(self, config: SourceConfig) -> HealthResult:
        items = config.options.get("items") or []
        if not isinstance(items, list):
            return HealthResult(ok=False, message="options.items must be a list")
        return HealthResult(
            ok=True,
            message=f"fixture ready ({len(items)} items)",
            details={"count": len(items)},
        )

    async def fetch(
        self,
        *,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        config: SourceConfig,
    ) -> FetchBatch:
        raw_items: List[Dict[str, Any]] = list(config.options.get("items") or [])
        start = int(cursor or 0)
        batch_size = int(config.options.get("batch_size") or 50)
        slice_items = raw_items[start : start + batch_size]
        out: List[FetchItem] = []
        for row in slice_items:
            if not isinstance(row, dict):
                continue
            published = row.get("published_at")
            if since and published:
                try:
                    pub_dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                    if pub_dt < since:
                        continue
                except ValueError:
                    pass
            out.append(
                FetchItem(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or ""),
                    content=str(row.get("content") or row.get("body") or ""),
                    summary=str(row.get("summary") or ""),
                    published_at=str(published) if published else None,
                    language=str(row.get("language") or config.language or ""),
                    authors=list(row.get("authors") or []),
                    raw=dict(row),
                )
            )
        next_cursor = str(start + batch_size) if start + batch_size < len(raw_items) else None
        return FetchBatch(
            source_id=config.source_id,
            items=out,
            cursor=next_cursor,
            metadata={"kind": "fixture", "total": len(raw_items)},
        )
