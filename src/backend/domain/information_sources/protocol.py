# -*- coding: utf-8 -*-
"""SourceConnector protocol and registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from .models import FetchBatch, HealthResult, SourceConfig, SourceManifest

ConnectorFactory = Callable[[], "SourceConnector"]


@runtime_checkable
class SourceConnector(Protocol):
    """Pluggable information source connector.

    Schedulers depend only on this protocol — adding a connector must not
    require scheduler code changes.
    """

    async def healthcheck(self, config: SourceConfig) -> HealthResult:
        ...

    async def fetch(
        self,
        *,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        config: SourceConfig,
    ) -> FetchBatch:
        ...


class SourceRegistry:
    """Manifest + factory registry for source connectors."""

    def __init__(self) -> None:
        self._manifests: Dict[str, SourceManifest] = {}
        self._factories: Dict[str, ConnectorFactory] = {}

    def register(self, manifest: SourceManifest, factory: ConnectorFactory) -> None:
        kind = (manifest.kind or "").strip()
        if not kind:
            raise ValueError("manifest.kind is required")
        if not callable(factory):
            raise ValueError("factory must be callable")
        self._manifests[kind] = manifest
        self._factories[kind] = factory

    def list_manifests(self) -> List[SourceManifest]:
        return list(self._manifests.values())

    def get_manifest(self, kind: str) -> Optional[SourceManifest]:
        return self._manifests.get(kind)

    def create(self, kind: str, config: Optional[SourceConfig] = None) -> SourceConnector:
        if kind not in self._factories:
            raise KeyError(f"Unknown source kind: {kind}")
        connector = self._factories[kind]()
        if config is not None and hasattr(connector, "bind_config"):
            connector.bind_config(config)  # type: ignore[attr-defined]
        return connector

    def known_kinds(self) -> List[str]:
        return sorted(self._factories.keys())


_default_registry: Optional[SourceRegistry] = None


def get_source_registry() -> SourceRegistry:
    """Process-wide registry with builtin connectors registered once."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SourceRegistry()
        from .connectors import register_builtin_connectors

        register_builtin_connectors(_default_registry)
    return _default_registry


def reset_source_registry_for_tests() -> None:
    global _default_registry
    _default_registry = None
