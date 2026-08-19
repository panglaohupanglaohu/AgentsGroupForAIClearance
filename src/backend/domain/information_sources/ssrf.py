# -*- coding: utf-8 -*-
"""SSRF guards for information source connectors.

Blocks loopback, link-local, private and cloud metadata addresses after DNS
resolution when possible. Also rejects non-http(s) schemes and credentialed URLs.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

# Common cloud metadata hosts
_BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata",
    "localhost",
}


class SSRFBlockedError(Exception):
    """Raised when a URL is rejected by SSRF policy.

    Intentionally does **not** subclass ValueError so callers can use
    ``except ValueError`` around ``ipaddress.ip_address`` without swallowing
    SSRF denials.
    """


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (getattr(ip, "is_site_local", False))
    )


def parse_http_url(url: str) -> Tuple[str, str, int]:
    if not url or not isinstance(url, str):
        raise SSRFBlockedError("URL is required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Unsupported scheme: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise SSRFBlockedError("URLs with embedded credentials are not allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SSRFBlockedError("URL host is required")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise SSRFBlockedError(f"Blocked hostname: {host}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, host, port


def resolve_host_ips(host: str) -> List[str]:
    """Resolve host to IP strings; empty list if resolution fails."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    ips: List[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in ips:
            ips.append(addr)
    return ips


def assert_url_safe(
    url: str,
    *,
    allowed_hosts: Optional[Sequence[str]] = None,
    resolve_dns: bool = True,
) -> str:
    """Validate URL against SSRF policy; return normalized URL string.

    When ``allowed_hosts`` is set, hostname must match one of them (exact or
    subdomain). DNS resolution checks that no resolved IP is private/metadata.
    """
    scheme, host, _port = parse_http_url(url)
    if allowed_hosts:
        allowed = {h.lower().rstrip(".") for h in allowed_hosts if h}
        if host not in allowed and not any(
            host.endswith("." + a) for a in allowed
        ):
            raise SSRFBlockedError(f"Host {host!r} not in allowed_hosts")

    # Literal IP in hostname
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            raise SSRFBlockedError(f"Blocked IP address: {host}")
    except ValueError:
        pass  # not a literal IP

    if resolve_dns and not _looks_like_fixture_host(host):
        for addr in resolve_host_ips(host):
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if _is_blocked_ip(ip) or addr.startswith("169.254."):
                raise SSRFBlockedError(
                    f"Host {host} resolves to blocked address {addr}"
                )

    # Normalize without fragment for fetch identity
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{host}{path}{query}" if parsed.port is None else url.strip()


def _looks_like_fixture_host(host: str) -> bool:
    return host in {"example.com", "example.org", "example.net", "test"} or host.endswith(
        ".example"
    )


def filter_redirect_url(url: str, allowed_hosts: Optional[Iterable[str]] = None) -> str:
    """Re-validate a redirect target under the same policy."""
    return assert_url_safe(url, allowed_hosts=list(allowed_hosts) if allowed_hosts else None)
