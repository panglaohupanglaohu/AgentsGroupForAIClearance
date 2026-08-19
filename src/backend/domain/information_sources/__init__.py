# -*- coding: utf-8 -*-
"""Pluggable information sources domain (T201)."""

from .models import (
    FetchBatch,
    FetchItem,
    HealthResult,
    SourceConfig,
    SourceKind,
    SourceManifest,
)
from .protocol import (
    SourceConnector,
    SourceRegistry,
    get_source_registry,
    reset_source_registry_for_tests,
)
from .scheduler import fetch_many, fetch_one
from .ssrf import SSRFBlockedError, assert_url_safe

__all__ = [
    "FetchBatch",
    "FetchItem",
    "HealthResult",
    "SourceConfig",
    "SourceConnector",
    "SourceKind",
    "SourceManifest",
    "SourceRegistry",
    "SSRFBlockedError",
    "assert_url_safe",
    "fetch_many",
    "fetch_one",
    "get_source_registry",
    "reset_source_registry_for_tests",
]
