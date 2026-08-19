# -*- coding: utf-8 -*-
"""Builtin source connectors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .fixture import MANIFEST as FIXTURE_MANIFEST
from .fixture import FixtureConnector
from .rss import MANIFEST as RSS_MANIFEST
from .rss import RssConnector
from .web import JSON_API_MANIFEST, WEB_MANIFEST, JsonApiConnector, WebConnector

if TYPE_CHECKING:
    from ..protocol import SourceRegistry


def register_builtin_connectors(registry: "SourceRegistry") -> None:
    registry.register(FIXTURE_MANIFEST, FixtureConnector)
    registry.register(RSS_MANIFEST, RssConnector)
    registry.register(WEB_MANIFEST, WebConnector)
    registry.register(JSON_API_MANIFEST, JsonApiConnector)


__all__ = [
    "FixtureConnector",
    "RssConnector",
    "WebConnector",
    "JsonApiConnector",
    "register_builtin_connectors",
]
