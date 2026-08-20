# -*- coding: utf-8 -*-
"""Shared helpers for builtin connectors."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

from ..models import SourceConfig
from ..ssrf import SSRFBlockedError, assert_url_safe

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


def proxy_env_summary() -> list[str]:
    """Return `KEY=value` for every proxy variable this process inherited."""
    return [f"{k}={os.environ[k]}" for k in _PROXY_ENV_KEYS if os.environ.get(k)]


def describe_exception(exc: BaseException) -> str:
    """Never surface a blank failure reason — httpx timeouts stringify to ''."""
    detail = str(exc).strip()
    if detail:
        return f"{type(exc).__name__}: {detail}"
    return f"{type(exc).__name__}（无附加信息，通常为连接/读取超时）"


class BaseConnector:
    """Optional base with config binding and safe URL helper."""

    def __init__(self) -> None:
        self._config: Optional[SourceConfig] = None

    def bind_config(self, config: SourceConfig) -> None:
        self._config = config

    def safe_url(self, config: SourceConfig, url: Optional[str] = None) -> str:
        target = url or config.url
        return assert_url_safe(
            target,
            allowed_hosts=config.allowed_hosts or None,
            resolve_dns=True,
        )

    async def _fetch_bytes(
        self,
        url: str,
        *,
        timeout: float,
        max_bytes: int,
        allowed_hosts: Optional[list] = None,
    ) -> bytes:
        """HTTP GET with size/timeout limits and redirect SSRF re-check.

        Uses httpx when available; raises RuntimeError with actionable message
        if the dependency is missing (fixture connector does not need network).
        """
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for network connectors; install project deps"
            ) from exc

        async def attempt(trust_env: bool) -> bytes:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(timeout),
                trust_env=trust_env,
                headers={"User-Agent": "ModelClearance-SourceConnector/0.1"},
            ) as client:
                current = url
                for _ in range(5):
                    assert_url_safe(current, allowed_hosts=allowed_hosts, resolve_dns=True)
                    resp = await client.get(current)
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise SSRFBlockedError("Redirect without Location")
                        # Relative redirect
                        if loc.startswith("/"):
                            from urllib.parse import urlparse

                            p = urlparse(current)
                            loc = f"{p.scheme}://{p.netloc}{loc}"
                        current = assert_url_safe(
                            loc, allowed_hosts=allowed_hosts, resolve_dns=True
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.content
                    if len(data) > max_bytes:
                        raise ValueError(
                            f"Response exceeds max_bytes={max_bytes} ({len(data)} bytes)"
                        )
                    return data
                raise SSRFBlockedError("Too many redirects")

        try:
            return await attempt(trust_env=True)
        except httpx.ConnectError:
            # 继承来的 HTTP(S)_PROXY 常常指向早已停掉的本地代理，直连重试一次再判失败
            if not proxy_env_summary():
                raise
            return await attempt(trust_env=False)
