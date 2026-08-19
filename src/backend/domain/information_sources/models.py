# -*- coding: utf-8 -*-
"""Information source domain models (connector-agnostic)."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceKind(str, Enum):
    FIXTURE = "fixture"
    RSS = "rss"
    WEB = "web"
    JSON_API = "json_api"


@dataclass
class SourceConfig:
    """Runtime configuration for a single source instance."""

    source_id: str
    kind: str
    name: str = ""
    url: str = ""
    enabled: bool = True
    # Arbitrary connector options (paths, selectors, headers env refs, etc.)
    options: Dict[str, Any] = field(default_factory=dict)
    # Credential references only — never raw secrets (e.g. env:API_TOKEN)
    secret_refs: Dict[str, str] = field(default_factory=dict)
    language: str = ""
    region: str = ""
    update_interval_seconds: int = 3600
    license_note: str = ""
    robots_policy: str = "unknown"  # allow | disallow | unknown
    reputation_score: float = 0.5
    timeout_seconds: float = 15.0
    max_bytes: int = 1_000_000
    allowed_hosts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class HealthResult:
    ok: bool
    message: str = ""
    latency_ms: Optional[float] = None
    checked_at: str = field(default_factory=utc_now_iso)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FetchItem:
    """One normalized document unit from a connector."""

    title: str = ""
    url: str = ""
    content: str = ""
    summary: str = ""
    published_at: Optional[str] = None
    language: str = ""
    authors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        payload = f"{self.url}\n{self.title}\n{self.content}".encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["content_hash"] = self.content_hash()
        return d


@dataclass
class FetchBatch:
    source_id: str
    items: List[FetchItem] = field(default_factory=list)
    cursor: Optional[str] = None
    fetched_at: str = field(default_factory=utc_now_iso)
    errors: List[str] = field(default_factory=list)
    partial: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "items": [i.to_dict() for i in self.items],
            "cursor": self.cursor,
            "fetched_at": self.fetched_at,
            "errors": list(self.errors),
            "partial": self.partial,
            "metadata": dict(self.metadata),
        }


@dataclass
class SourceManifest:
    """Describes a connector implementation for the registry."""

    kind: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    config_schema: Dict[str, Any] = field(default_factory=dict)
    supports_cursor: bool = True
    requires_network: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
