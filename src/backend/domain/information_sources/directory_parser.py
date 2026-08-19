"""Parse RSS directory pages into reviewable source candidates.

The parser is intentionally deterministic: chat supplies the URL and filters,
while the server extracts links, applies SSRF policy, and leaves final import
to an explicit user confirmation step.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from .connectors.base import BaseConnector
from .connectors.rss import RssConnector
from .models import SourceConfig
from .ssrf import SSRFBlockedError, assert_url_safe


class _DirectoryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Dict[str, Any]] = []
        self._row: Optional[Dict[str, Any]] = None
        self._cell: Optional[Dict[str, Any]] = None
        self._anchor: Optional[Dict[str, Any]] = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_map = dict(attrs)
        tag = tag.lower()
        if tag == "tr":
            self._row = {"cells": [], "links": []}
        elif self._row is not None and tag in ("td", "th"):
            self._cell = {"text": [], "links": []}
            self._row["cells"].append(self._cell)
        elif self._row is not None and tag == "a" and attrs_map.get("href"):
            self._anchor = {"href": attrs_map["href"], "text": []}

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["text"].append(data)
        if self._cell is not None:
            self._cell["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._anchor is not None and self._cell is not None:
            self._cell["links"].append({"href": self._anchor["href"], "text": "".join(self._anchor["text"]).strip()})
            self._anchor = None
        elif tag in ("td", "th"):
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _dedupe(items: Iterable[Dict[str, str]], max_items: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url", "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"name": item.get("name", "RSS source").strip() or "RSS source", "url": url})
        if len(out) >= max_items:
            break
    return out


def _parse_opml(data: bytes, base_url: str) -> List[Dict[str, str]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    out = []
    for node in root.iter():
        url = node.attrib.get("xmlUrl") or node.attrib.get("xmlurl")
        if url:
            out.append({"name": node.attrib.get("text") or node.attrib.get("title") or "RSS source", "url": urljoin(base_url, url)})
    return out


def parse_directory(data: bytes, base_url: str, max_items: int = 200) -> List[Dict[str, str]]:
    raw = data.decode("utf-8", errors="replace")
    if "<opml" in raw[:1000].lower() or "xmlurl=" in raw.lower():
        opml = _parse_opml(data, base_url)
        if opml:
            return _dedupe(opml, max_items)
    parser = _DirectoryParser()
    try:
        parser.feed(raw)
    except Exception:
        parser.close()
    candidates: List[Dict[str, str]] = []
    for row in parser.rows:
        cells = row.get("cells") or []
        links = [link for cell in cells for link in cell.get("links", [])]
        valid_links = []
        for link in links:
            href = urljoin(base_url, link.get("href", ""))
            if urlparse(href).scheme in ("http", "https") and "github.com" not in (urlparse(href).netloc or ""):
                valid_links.append((href, link.get("text", "")))
        if not valid_links:
            continue
        name = " ".join(cells[0].get("text", [])).strip() if cells else ""
        name = " ".join(name.split())
        for href, link_text in valid_links:
            # Prefer links whose URL looks like a feed, but accept directory
            # proxies such as RSSHub/Anyfeeder as valid RSS candidates.
            if any(token in href.lower() for token in ("rss", "atom", "feed", "xml", "rsshub", "anyfeeder", "index")) or len(valid_links) == 1:
                candidates.append({"name": name or link_text or "RSS source", "url": href})
    if candidates:
        return _dedupe(candidates, max_items)
    # Fallback for Markdown/unstyled pages. Keep the display label local to
    # each match so a page without an HTML table cannot raise an
    # ``UnboundLocalError`` while being imported through Chat.
    links = re.findall(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", raw)
    return _dedupe(
        ({"name": label.strip() or "RSS source", "url": url} for label, url in links),
        max_items,
    )


async def preview_directory(url: str, max_items: int = 200, check_health: bool = False) -> Dict[str, Any]:
    safe_url = assert_url_safe(url)
    data = await BaseConnector()._fetch_bytes(safe_url, timeout=20, max_bytes=4_000_000)
    candidates = parse_directory(data, safe_url, max_items=max_items)
    results = [{**item, "kind": "rss", "status": "unverified", "source_id": "rss-" + hashlib.sha1(item["url"].encode()).hexdigest()[:10]} for item in candidates]
    if check_health and results:
        import asyncio

        sem = asyncio.Semaphore(20)

        async def check(item: Dict[str, Any]) -> None:
            async with sem:
                cfg = SourceConfig(source_id=item["source_id"], kind="rss", name=item["name"], url=item["url"])
                health = await RssConnector().healthcheck(cfg)
                item["status"] = "ok" if health.ok else "failed"
                item["health_message"] = health.message

        await asyncio.gather(*(check(item) for item in results[:20]))
    return {"directory_url": safe_url, "count": len(results), "candidates": results}
