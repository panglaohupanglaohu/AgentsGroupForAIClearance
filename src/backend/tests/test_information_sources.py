# -*- coding: utf-8 -*-
"""T201 — Pluggable source connector contract, SSRF, isolation."""

from __future__ import annotations

import pytest

from domain.information_sources import (
    FetchBatch,
    SourceConfig,
    SourceRegistry,
    SSRFBlockedError,
    assert_url_safe,
    fetch_many,
    get_source_registry,
    reset_source_registry_for_tests,
)
from domain.information_sources.connectors.rss import parse_feed_xml
@pytest.fixture(autouse=True)
def _clean_registry():
    reset_source_registry_for_tests()
    yield
    reset_source_registry_for_tests()


def test_registry_registers_builtin_kinds():
    reg = get_source_registry()
    kinds = set(reg.known_kinds())
    assert {"fixture", "rss", "web", "json_api"} <= kinds


def test_new_connector_does_not_require_scheduler_change():
    """Register a custom kind; scheduler still uses protocol only."""
    from domain.information_sources.models import FetchItem, HealthResult

    class EchoConnector:
        async def healthcheck(self, config):
            return HealthResult(ok=True, message="echo")

        async def fetch(self, *, since=None, cursor=None, config=None):
            return FetchBatch(
                source_id=config.source_id,
                items=[FetchItem(title="echo", url="https://example.com", content="x")],
            )

    reg = SourceRegistry()
    from domain.information_sources.models import SourceManifest
    from domain.information_sources.connectors import register_builtin_connectors

    register_builtin_connectors(reg)
    reg.register(
        SourceManifest(kind="echo", name="Echo", requires_network=False),
        EchoConnector,
    )
    assert "echo" in reg.known_kinds()


@pytest.mark.asyncio
async def test_fixture_fetch_and_health():
    reg = get_source_registry()
    cfg = SourceConfig(
        source_id="fix-1",
        kind="fixture",
        name="Demo",
        options={
            "items": [
                {
                    "title": "A",
                    "url": "https://example.com/a",
                    "content": "hello",
                    "published_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "title": "B",
                    "url": "https://example.com/b",
                    "content": "world",
                },
            ],
            "batch_size": 1,
        },
    )
    connector = reg.create("fixture", cfg)
    health = await connector.healthcheck(cfg)
    assert health.ok is True
    batch = await connector.fetch(config=cfg, cursor="0")
    assert len(batch.items) == 1
    assert batch.items[0].title == "A"
    assert batch.cursor == "1"
    batch2 = await connector.fetch(config=cfg, cursor="1")
    assert batch2.items[0].title == "B"


@pytest.mark.asyncio
async def test_single_source_failure_does_not_abort_others():
    reg = get_source_registry()
    ok_cfg = SourceConfig(
        source_id="ok",
        kind="fixture",
        options={"items": [{"title": "ok", "url": "https://example.com/ok", "content": "1"}]},
    )
    bad_cfg = SourceConfig(
        source_id="bad",
        kind="not_registered_kind",
        url="https://example.com",
    )
    results = await fetch_many([ok_cfg, bad_cfg], registry=reg)
    by_id = {r.source_id: r for r in results}
    assert len(by_id["ok"].items) == 1
    assert by_id["bad"].errors
    assert by_id["bad"].partial is True


def test_ssrf_blocks_loopback_and_metadata():
    with pytest.raises(SSRFBlockedError):
        assert_url_safe("http://127.0.0.1/secret", resolve_dns=False)
    with pytest.raises(SSRFBlockedError):
        assert_url_safe("http://localhost/x", resolve_dns=False)
    with pytest.raises(SSRFBlockedError):
        assert_url_safe("http://169.254.169.254/latest/meta-data", resolve_dns=False)
    with pytest.raises(SSRFBlockedError):
        assert_url_safe("http://10.0.0.5/internal", resolve_dns=False)
    with pytest.raises(SSRFBlockedError):
        assert_url_safe("file:///etc/passwd", resolve_dns=False)
    with pytest.raises(SSRFBlockedError):
        assert_url_safe("https://user:pass@example.com/", resolve_dns=False)


def test_ssrf_allows_public_example():
    url = assert_url_safe("https://example.com/path?q=1", resolve_dns=False)
    assert url.startswith("https://example.com/")


def test_ssrf_allowed_hosts_enforced():
    with pytest.raises(SSRFBlockedError):
        assert_url_safe(
            "https://evil.example/x",
            allowed_hosts=["good.example"],
            resolve_dns=False,
        )
    assert assert_url_safe(
        "https://good.example/x",
        allowed_hosts=["good.example"],
        resolve_dns=False,
    )


def test_rss_parse_stdlib():
    xml = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <title>Feed</title>
      <item>
        <title>Item One</title>
        <link>https://example.com/1</link>
        <description>Body</description>
        <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    items = parse_feed_xml(xml)
    assert len(items) == 1
    assert items[0].title == "Item One"
    assert items[0].url == "https://example.com/1"


def test_item_content_hash_stable():
    from domain.information_sources.models import FetchItem

    a = FetchItem(title="t", url="https://example.com", content="c")
    b = FetchItem(title="t", url="https://example.com", content="c")
    assert a.content_hash() == b.content_hash()


def test_feed_html_is_cleaned_and_bounded_for_evidence_display():
    from domain.information_sources.evidence import clean_feed_text

    cleaned = clean_feed_text("<p><strong>作者</strong>&nbsp;：测试</p><script>alert(1)</script>")
    assert cleaned == "作者 ：测试"
    assert "<p>" not in cleaned
    assert "alert" not in cleaned
    assert len(clean_feed_text("x" * 100, max_chars=20)) == 20


def test_extract_news_brief_prefers_title_and_strips_bylines():
    from domain.information_sources.evidence import extract_news_brief

    html_body = (
        "<p><strong>作者 |&nbsp;</strong>谢芸子 黄绎达</p>"
        "<p><strong>编辑 |</strong>&nbsp;张帆</p>"
        "<p>开云的转型初见成效。</p>"
        "<p>7月28日，法国开云集团Kering发布2026年上半年财报，实现营收72.2亿欧元，"
        "可比口径下同比增长1%。</p>"
        "<p>更关键的信号藏在第二季度——单季营收36.52亿欧元，同比增长2%。</p>"
    )
    brief = extract_news_brief(
        title="开云集团上半年营收72.2亿欧元 二季度实现三年来首次单季正增长",
        summary=html_body,
        content=html_body,
        max_chars=120,
    )
    assert "<p>" not in brief
    assert "作者" not in brief
    assert "编辑" not in brief
    assert "开云" in brief
    assert len(brief) <= 121
    # Should not dump the whole article
    assert "中东局势" not in brief
