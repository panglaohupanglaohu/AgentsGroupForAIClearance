# -*- coding: utf-8 -*-
"""Plain web page / public JSON API connectors."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, List, Optional

from ..models import FetchBatch, FetchItem, HealthResult, SourceConfig, SourceManifest
from ..ssrf import SSRFBlockedError
from .base import BaseConnector, describe_exception

_TAG_RE = re.compile(r"<[^>]+>")

WEB_MANIFEST = SourceManifest(
    kind="web",
    name="Web page",
    description="Fetch a public HTML/text page within allowed hosts",
    version="1.0.0",
    supports_cursor=False,
    requires_network=True,
    config_schema={"url": {"type": "string", "required": True}},
)

JSON_API_MANIFEST = SourceManifest(
    kind="json_api",
    name="Public JSON API",
    description="Fetch a public JSON endpoint and map items via options.item_path",
    version="1.0.0",
    supports_cursor=True,
    requires_network=True,
    config_schema={
        "url": {"type": "string", "required": True},
        "item_path": {"type": "string", "description": "Dot path to list of items"},
    },
)


def _strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text or "").strip()


def _dig(data: Any, path: str) -> Any:
    cur = data
    if not path:
        return cur
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


class WebConnector(BaseConnector):
    async def healthcheck(self, config: SourceConfig) -> HealthResult:
        t0 = time.perf_counter()
        try:
            url = self.safe_url(config)
            data = await self._fetch_bytes(
                url,
                timeout=min(config.timeout_seconds, 10.0),
                max_bytes=min(config.max_bytes, 200_000),
                allowed_hosts=config.allowed_hosts or None,
            )
            return HealthResult(
                ok=True,
                message=f"web ok ({len(data)} bytes)",
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        except Exception as exc:
            return HealthResult(ok=False, message=describe_exception(exc))

    async def fetch(
        self,
        *,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        config: SourceConfig,
    ) -> FetchBatch:
        try:
            url = self.safe_url(config)
            data = await self._fetch_bytes(
                url,
                timeout=config.timeout_seconds,
                max_bytes=config.max_bytes,
                allowed_hosts=config.allowed_hosts or None,
            )
            text = data.decode("utf-8", errors="replace")
            title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            title = _strip_html(title_match.group(1)) if title_match else url
            body = _strip_html(text)[:50_000]
            item = FetchItem(
                title=title,
                url=url,
                content=body,
                summary=body[:500],
                language=config.language,
                raw={"format": "web", "bytes": len(data)},
            )
            return FetchBatch(
                source_id=config.source_id,
                items=[item],
                cursor=item.content_hash(),
                metadata={"kind": "web", "url": url},
            )
        except Exception as exc:
            return FetchBatch(
                source_id=config.source_id,
                items=[],
                cursor=cursor,
                errors=[str(exc)],
                partial=True,
                metadata={"kind": "web"},
            )


class JsonApiConnector(BaseConnector):
    async def healthcheck(self, config: SourceConfig) -> HealthResult:
        t0 = time.perf_counter()
        try:
            url = self.safe_url(config)
            data = await self._fetch_bytes(
                url,
                timeout=min(config.timeout_seconds, 10.0),
                max_bytes=min(config.max_bytes, 200_000),
                allowed_hosts=config.allowed_hosts or None,
            )
            json.loads(data.decode("utf-8"))
            return HealthResult(
                ok=True,
                message="json_api ok",
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        except Exception as exc:
            return HealthResult(ok=False, message=describe_exception(exc))

    async def fetch(
        self,
        *,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        config: SourceConfig,
    ) -> FetchBatch:
        try:
            url = self.safe_url(config)
            data = await self._fetch_bytes(
                url,
                timeout=config.timeout_seconds,
                max_bytes=config.max_bytes,
                allowed_hosts=config.allowed_hosts or None,
            )
            payload = json.loads(data.decode("utf-8"))
            path = str(config.options.get("item_path") or "")
            rows = _dig(payload, path) if path else payload
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                raise ValueError("JSON root/item_path must be a list or object")
            items: List[FetchItem] = []
            title_key = str(config.options.get("title_key") or "title")
            url_key = str(config.options.get("url_key") or "url")
            content_key = str(config.options.get("content_key") or "content")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                items.append(
                    FetchItem(
                        title=str(row.get(title_key) or ""),
                        url=str(row.get(url_key) or url),
                        content=str(row.get(content_key) or json.dumps(row, ensure_ascii=False)),
                        summary=str(row.get("summary") or "")[:500],
                        published_at=(
                            str(row.get("published_at")) if row.get("published_at") else None
                        ),
                        language=config.language,
                        raw={"format": "json_api", "row_keys": list(row.keys())[:20]},
                    )
                )
            new_cursor = items[-1].content_hash() if items else cursor
            return FetchBatch(
                source_id=config.source_id,
                items=items,
                cursor=new_cursor,
                metadata={"kind": "json_api", "url": url, "count": len(items)},
            )
        except Exception as exc:
            return FetchBatch(
                source_id=config.source_id,
                items=[],
                cursor=cursor,
                errors=[str(exc)],
                partial=True,
                metadata={"kind": "json_api"},
            )
