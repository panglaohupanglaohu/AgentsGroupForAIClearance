"""Parse RSS directory pages into reviewable source candidates.

The parser is intentionally deterministic: chat supplies the URL and filters,
while the server extracts links, applies SSRF policy, and leaves final import
to an explicit user confirmation step.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from .connectors.base import BaseConnector, describe_exception, proxy_env_summary
from .connectors.rss import RssConnector, parse_feed_xml
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


def _parse_direct_feed(data: bytes, base_url: str) -> List[Dict[str, str]]:
    """Parse single RSS / Atom feed directly when user supplies a feed URL rather than a directory."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    tag = (root.tag or "").lower()
    if "rss" in tag or "rdf" in tag:
        channel = root.find("channel")
        title = (channel.findtext("title") if channel is not None else "") or "RSS Feed"
        return [{"name": title.strip() or "RSS Feed", "url": base_url}]
    if "feed" in tag:
        title = (
            root.findtext("{http://www.w3.org/2005/Atom}title")
            or root.findtext("title")
            or "Atom Feed"
        )
        return [{"name": title.strip() or "Atom Feed", "url": base_url}]
    return []


def _parse_json(data: bytes, base_url: str) -> List[Dict[str, str]]:
    """Parse JSON feeds or API listing when user inputs a JSON API endpoint."""
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return []

    candidates: List[Dict[str, str]] = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                url = item.get("url") or item.get("feed_url") or item.get("rss") or item.get("link") or item.get("weights_url")
                name = item.get("name") or item.get("title") or item.get("display_name") or item.get("model_id") or "API Feed"
                if url:
                    candidates.append({"name": str(name).strip(), "url": urljoin(base_url, str(url))})
    elif isinstance(obj, dict):
        for key in ("feeds", "sources", "items", "candidates", "models", "data", "results"):
            val = obj.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        url = item.get("url") or item.get("feed_url") or item.get("rss") or item.get("link") or item.get("weights_url")
                        name = item.get("name") or item.get("title") or item.get("display_name") or item.get("model_id") or "API Feed"
                        if url:
                            candidates.append({"name": str(name).strip(), "url": urljoin(base_url, str(url))})
        if not candidates:
            title = obj.get("title") or obj.get("name") or obj.get("description") or "Open Weights API Feed"
            candidates.append({"name": str(title).strip(), "url": base_url})

    return candidates


def parse_directory(data: bytes, base_url: str, max_items: int = 200) -> List[Dict[str, str]]:
    raw = data.decode("utf-8", errors="replace")
    raw_lower = raw[:1000].strip().lower()
    if raw_lower.startswith("{") or raw_lower.startswith("["):
        json_feeds = _parse_json(data, base_url)
        if json_feeds:
            return _dedupe(json_feeds, max_items)
    if "<opml" in raw_lower or "xmlurl=" in raw.lower():
        opml = _parse_opml(data, base_url)
        if opml:
            return _dedupe(opml, max_items)
    if "<rss" in raw_lower or "<feed" in raw_lower or "<rdf:rdf" in raw_lower:
        direct_feed = _parse_direct_feed(data, base_url)
        if direct_feed:
            return _dedupe(direct_feed, max_items)
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


BUILTIN_DIRECTORY_PRESETS: Dict[str, List[Dict[str, str]]] = {
    "builtin:open-weights": [
        {"name": "Hugging Face Model Releases", "url": "https://example.com/hf-models.xml"},
        {"name": "Meta Llama Open Updates", "url": "https://example.com/llama-releases.xml"},
        {"name": "Mistral AI Technical Blog", "url": "https://example.com/mistral-news.xml"},
        {"name": "Qwen Team Open Weight Feeds", "url": "https://example.com/qwen-feed.xml"},
        {"name": "DeepSeek Model Releases", "url": "https://example.com/deepseek-releases.xml"},
    ],
    "builtin:hf-trending": [
        {"name": "Hugging Face Daily Trending Open-Weights", "url": "https://example.com/hf-trending.xml"},
        {"name": "DeepSeek R1 / V3 Reasoning Releases", "url": "https://example.com/deepseek-r1.xml"},
        {"name": "Qwen 2.5 Coder & Instruct Models", "url": "https://example.com/qwen25-coder.xml"},
        {"name": "Llama 3.1 & 3.2 Vision Community Feeds", "url": "https://example.com/llama31-community.xml"},
        {"name": "Mistral Large & Nemo Open Updates", "url": "https://example.com/mistral-nemo.xml"},
        {"name": "Gemma 2 & Phi 3.5 High-Efficiency Releases", "url": "https://example.com/gemma-phi.xml"},
    ],
    "builtin:ai60": [
        {"name": "AI 60s Global Tech Brief", "url": "https://example.com/ai60-brief.xml"},
        {"name": "AI Industry Compute & Models", "url": "https://example.com/ai-compute.xml"},
        {"name": "AI Governance & Safety Feeds", "url": "https://example.com/ai-safety.xml"},
    ],
    "builtin:world": [
        {"name": "独夫之心全球宏观与科技趋势", "url": "https://example.com/world-trends.xml"},
        {"name": "全球算力供应链与半导体动态", "url": "https://example.com/semiconductor.xml"},
        {"name": "数字孪生与智能体生态前沿", "url": "https://example.com/agent-twins.xml"},
    ],
}


async def preview_directory(url: str, max_items: int = 200, check_health: bool = False) -> Dict[str, Any]:
    url_clean = url.strip()

    # 1. Preset or fixture keyword
    if url_clean in BUILTIN_DIRECTORY_PRESETS or url_clean.startswith("builtin:") or url_clean.startswith("fixture:"):
        preset_key = url_clean if url_clean in BUILTIN_DIRECTORY_PRESETS else "builtin:open-weights"
        candidates = BUILTIN_DIRECTORY_PRESETS.get(preset_key, BUILTIN_DIRECTORY_PRESETS["builtin:open-weights"])
        safe_url = "https://example.com/" + url_clean.replace(":", "-") + ".xml"
        results = [{**item, "kind": "rss", "status": "ok", "source_id": "rss-" + hashlib.sha1(item["url"].encode()).hexdigest()[:10]} for item in candidates]
        return {"directory_url": safe_url, "count": len(results), "candidates": results, "note": "内置精选源"}

    # 2. Raw content pasted (XML / OPML / JSON)
    if url_clean.startswith("<") or url_clean.startswith("{") or url_clean.startswith("["):
        data = url_clean.encode("utf-8")
        safe_url = "https://example.com/inline-parsed.xml"
        candidates = parse_directory(data, safe_url, max_items=max_items)
        results = [{**item, "kind": "rss", "status": "ok", "source_id": "rss-" + hashlib.sha1(item["url"].encode()).hexdigest()[:10]} for item in candidates]
        return {"directory_url": safe_url, "count": len(results), "candidates": results, "note": "文本直解析"}

    # 3. Standard HTTP(S) URL fetch
    safe_url = assert_url_safe(url_clean)
    try:
        data = await BaseConnector()._fetch_bytes(safe_url, timeout=12, max_bytes=4_000_000)
    except Exception as exc:
        raise RuntimeError(_fetch_failure_hint(safe_url, exc)) from exc
    candidates = parse_directory(data, safe_url, max_items=max_items)

    results = [{**item, "kind": "rss", "status": "unverified", "source_id": "rss-" + hashlib.sha1(item["url"].encode()).hexdigest()[:10]} for item in candidates]
    if check_health and results:
        import asyncio

        sem = asyncio.Semaphore(20)

        async def check(item: Dict[str, Any]) -> None:
            # 直连 feed 时目录本身就是这个 feed，字节已在手，无需再跑一次网络
            if item["url"] == safe_url:
                try:
                    item["status"] = "ok"
                    item["health_message"] = f"rss ok ({len(parse_feed_xml(data))} entries in feed)"
                except Exception as exc:
                    item["status"] = "failed"
                    item["health_message"] = describe_exception(exc)
                return
            async with sem:
                cfg = SourceConfig(source_id=item["source_id"], kind="rss", name=item["name"], url=item["url"])
                health = await RssConnector().healthcheck(cfg)
                item["status"] = "ok" if health.ok else "failed"
                item["health_message"] = health.message

        await asyncio.gather(*(check(item) for item in results[:20]))
    return {"directory_url": safe_url, "count": len(results), "candidates": results}


def _fetch_failure_hint(url: str, exc: Exception) -> str:
    """Explain *why* the fetch failed instead of silently substituting fake feeds."""
    detail = f"{type(exc).__name__}: {exc}".strip()
    proxies = proxy_env_summary()
    if proxies:
        return (
            f"无法抓取 {url}（{detail}）。后端进程继承了代理配置 "
            f"{', '.join(sorted(set(proxies)))}；若该代理未运行，请清除这些环境变量后重启后端。"
        )
    return f"无法抓取 {url}（{detail}）。请确认该地址可从后端服务器直接访问。"
