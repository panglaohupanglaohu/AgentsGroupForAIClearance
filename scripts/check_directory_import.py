"""Self-check for RSS directory import robustness (no framework, no network).

Guards two regressions:
  1. A failed healthcheck must never report an empty reason (httpx timeouts
     stringify to '', which surfaced in the UI as a bare "failed").
  2. Previewing a URL that *is* the feed must not re-fetch it over the network.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "backend"))

from domain.information_sources.connectors import base as connector_base  # noqa: E402
from domain.information_sources.connectors.base import describe_exception  # noqa: E402
from domain.information_sources import directory_parser  # noqa: E402

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>HuggingFace Trending Models</title>
  <link>https://example.invalid/feed.xml</link>
  <item><title>A</title><link>https://example.invalid/a</link></item>
  <item><title>B</title><link>https://example.invalid/b</link></item>
</channel></rss>
"""

URL = "https://example.invalid/feed.xml"


def check_describe_exception() -> None:
    assert describe_exception(TimeoutError()) != "", "timeout must not stringify to empty"
    assert "TimeoutError" in describe_exception(TimeoutError())
    assert describe_exception(ValueError("boom")) == "ValueError: boom"
    print("[ok] describe_exception never returns a blank reason")


def check_direct_feed_reuses_bytes() -> None:
    fetch_calls = []

    async def fake_fetch(self, url, *, timeout, max_bytes, allowed_hosts=None):
        fetch_calls.append(url)
        return FEED

    original_fetch = connector_base.BaseConnector._fetch_bytes
    original_assert = directory_parser.assert_url_safe
    connector_base.BaseConnector._fetch_bytes = fake_fetch
    directory_parser.assert_url_safe = lambda u, **kw: u
    try:
        result = asyncio.run(directory_parser.preview_directory(URL, check_health=True))
    finally:
        connector_base.BaseConnector._fetch_bytes = original_fetch
        directory_parser.assert_url_safe = original_assert

    assert result["count"] == 1, f"expected 1 candidate, got {result['count']}"
    item = result["candidates"][0]
    assert item["status"] == "ok", f"expected ok, got {item['status']}"
    assert "2 entries" in item["health_message"], item["health_message"]
    assert len(fetch_calls) == 1, f"direct feed must be fetched once, got {len(fetch_calls)}"
    print(f"[ok] direct feed verified from cached bytes ({item['health_message']}), 1 network fetch")


check_describe_exception()
check_direct_feed_reuses_bytes()
print("ALL CHECKS PASSED")
