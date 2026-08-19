# -*- coding: utf-8 -*-
"""RSS/Atom connector (stdlib XML parse + httpx fetch)."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional
from xml.etree.ElementTree import Element

from ..models import FetchBatch, FetchItem, HealthResult, SourceConfig, SourceManifest
from ..ssrf import SSRFBlockedError
from .base import BaseConnector

MANIFEST = SourceManifest(
    kind="rss",
    name="RSS / Atom",
    description="Fetch and parse standard RSS 2.0 / Atom feeds",
    version="1.0.0",
    supports_cursor=True,
    requires_network=True,
    config_schema={"url": {"type": "string", "required": True}},
)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _text(el: Optional[Element]) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _rich_text(el: Optional[Element]) -> str:
    """Collect description/content including nested HTML markup as a string.

    RSS ``description`` / Atom ``content`` often store full HTML either as
    CDATA text or as nested XML. Prefer serializing children so the evidence
    cleaner can strip tags and extract a lede.
    """
    if el is None:
        return ""
    if len(el) == 0:
        return (el.text or "").strip()
    chunks: List[str] = [el.text or ""]
    for child in el:
        chunks.append(ET.tostring(child, encoding="unicode"))
        chunks.append(child.tail or "")
    return "".join(chunks).strip()


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _item_body(item: Element) -> tuple[str, str]:
    """Return (summary, content) for an RSS item."""
    desc = _rich_text(item.find("description"))
    content = ""
    for child in item:
        local = _local(child.tag).lower()
        if local in {"encoded", "content"}:
            content = _rich_text(child)
            if content:
                break
    if not content:
        content = desc
    return desc, content


def parse_feed_xml(data: bytes) -> List[FetchItem]:
    root = ET.fromstring(data)
    items: List[FetchItem] = []
    root_tag = _local(root.tag).lower()

    if root_tag == "rss" or root.find("channel") is not None:
        channel = root.find("channel") if root_tag == "rss" else root
        if channel is None:
            channel = root
        for item in channel.findall("item"):
            summary, content = _item_body(item)
            items.append(
                FetchItem(
                    title=_text(item.find("title")),
                    url=_text(item.find("link")),
                    content=content or summary,
                    summary=summary,
                    published_at=_text(item.find("pubDate")) or _text(item.find("published")),
                    raw={"format": "rss"},
                )
            )
        return items

    # Atom
    for entry in root.findall("atom:entry", _ATOM_NS) or root.findall("entry"):
        link = ""
        for link_el in entry.findall("atom:link", _ATOM_NS) or entry.findall("link"):
            href = link_el.attrib.get("href") or _text(link_el)
            rel = link_el.attrib.get("rel", "alternate")
            if href and rel in ("alternate", ""):
                link = href
                break
            if href and not link:
                link = href
        title_el = entry.find("atom:title", _ATOM_NS) or entry.find("title")
        summary_el = entry.find("atom:summary", _ATOM_NS) or entry.find("summary")
        content_el = entry.find("atom:content", _ATOM_NS) or entry.find("content")
        published_el = (
            entry.find("atom:updated", _ATOM_NS)
            or entry.find("updated")
            or entry.find("atom:published", _ATOM_NS)
            or entry.find("published")
        )
        summary = _rich_text(summary_el)
        content = _rich_text(content_el) or summary
        items.append(
            FetchItem(
                title=_text(title_el),
                url=link,
                content=content,
                summary=summary,
                published_at=_text(published_el),
                raw={"format": "atom"},
            )
        )
    return items


class RssConnector(BaseConnector):
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
            items = parse_feed_xml(data)
            ms = (time.perf_counter() - t0) * 1000
            return HealthResult(
                ok=True,
                message=f"rss ok ({len(items)} entries in feed)",
                latency_ms=round(ms, 1),
                details={"bytes": len(data)},
            )
        except Exception as exc:
            return HealthResult(
                ok=False,
                message=str(exc),
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

    async def fetch(
        self,
        *,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        config: SourceConfig,
    ) -> FetchBatch:
        errors: List[str] = []
        try:
            url = self.safe_url(config)
            data = await self._fetch_bytes(
                url,
                timeout=config.timeout_seconds,
                max_bytes=config.max_bytes,
                allowed_hosts=config.allowed_hosts or None,
            )
            items = parse_feed_xml(data)
            # Cursor = last seen content hash; skip until after cursor
            if cursor:
                seen = False
                filtered: List[FetchItem] = []
                for it in items:
                    h = it.content_hash()
                    if not seen:
                        if h == cursor:
                            seen = True
                        continue
                    filtered.append(it)
                if seen:
                    items = filtered
            if items:
                new_cursor = items[-1].content_hash()
            else:
                new_cursor = cursor
            return FetchBatch(
                source_id=config.source_id,
                items=items,
                cursor=new_cursor,
                metadata={"kind": "rss", "url": url},
            )
        except SSRFBlockedError as exc:
            errors.append(f"ssrf: {exc}")
        except Exception as exc:
            errors.append(str(exc))
        return FetchBatch(
            source_id=config.source_id,
            items=[],
            cursor=cursor,
            errors=errors,
            partial=True,
            metadata={"kind": "rss"},
        )
