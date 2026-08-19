# -*- coding: utf-8 -*-
"""Versioned information documents (AI 60s / world trends HTML packets)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import utc_now_iso

_DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "storage" / "information_documents"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, data: str) -> None:
    _ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


@dataclass
class InformationDocument:
    document_id: str
    channel: str  # ai_news_60s | dufu_world_intel
    version: int
    title: str
    run_id: str
    as_of: str  # data cutoff — never inject into simulations after this for future leakage
    created_at: str = field(default_factory=utc_now_iso)
    html: str = ""
    report: Dict[str, Any] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)
    evidence_urls: List[str] = field(default_factory=list)
    content_hashes: List[str] = field(default_factory=list)
    status: str = "published"  # draft | published | rejected
    schema_version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_html: bool = True) -> Dict[str, Any]:
        """Serialize a document, optionally excluding its potentially large HTML body."""
        payload = asdict(self)
        if not include_html:
            payload.pop("html", None)
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InformationDocument":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class DocumentStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else _DEFAULT_ROOT
        _ensure_dir(self.root)

    def next_version(self, channel: str) -> int:
        channel_dir = self.root / channel
        if not channel_dir.exists():
            return 1
        versions = []
        for p in channel_dir.glob("v*.json"):
            try:
                versions.append(int(p.stem[1:]))
            except ValueError:
                continue
        return (max(versions) + 1) if versions else 1

    def save(self, doc: InformationDocument) -> InformationDocument:
        path = self.root / doc.channel / f"v{doc.version}.json"
        _atomic_write(path, json.dumps(doc.to_dict(), ensure_ascii=False, indent=2))
        # latest pointer
        _atomic_write(
            self.root / doc.channel / "latest.json",
            json.dumps(
                {"document_id": doc.document_id, "version": doc.version, "path": str(path)},
                ensure_ascii=False,
                indent=2,
            ),
        )
        # html sidecar for embedding
        if doc.html:
            _atomic_write(self.root / doc.channel / f"v{doc.version}.html", doc.html)
        return doc

    def create_published(
        self,
        *,
        channel: str,
        title: str,
        run_id: str,
        as_of: str,
        html: str,
        report: Dict[str, Any],
        evidence_ids: List[str],
        evidence_urls: List[str],
        content_hashes: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InformationDocument:
        version = self.next_version(channel)
        doc = InformationDocument(
            document_id=f"{channel}-{version}-{uuid.uuid4().hex[:6]}",
            channel=channel,
            version=version,
            title=title,
            run_id=run_id,
            as_of=as_of,
            html=html,
            report=report,
            evidence_ids=list(evidence_ids),
            evidence_urls=list(evidence_urls),
            content_hashes=list(content_hashes),
            status="published",
            metadata=metadata or {},
        )
        return self.save(doc)

    def get_latest(self, channel: str) -> Optional[InformationDocument]:
        latest = self.root / channel / "latest.json"
        if not latest.exists():
            return None
        meta = json.loads(latest.read_text(encoding="utf-8"))
        return self.get_version(channel, int(meta["version"]))

    def get_version(self, channel: str, version: int) -> Optional[InformationDocument]:
        path = self.root / channel / f"v{version}.json"
        if not path.exists():
            return None
        return InformationDocument.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def get_by_id(self, document_id: str) -> Optional[InformationDocument]:
        for channel_dir in self.root.iterdir() if self.root.exists() else []:
            if not channel_dir.is_dir():
                continue
            for path in channel_dir.glob("v*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("document_id") == document_id:
                        return InformationDocument.from_dict(data)
                except Exception:
                    continue
        return None

    def list_documents(
        self,
        channel: Optional[str] = None,
        *,
        before: Optional[str] = None,
        limit: int = 50,
    ) -> List[InformationDocument]:
        channels = [channel] if channel else (
            [p.name for p in self.root.iterdir() if p.is_dir()] if self.root.exists() else []
        )
        docs: List[InformationDocument] = []
        for ch in channels:
            ch_dir = self.root / ch
            if not ch_dir.exists():
                continue
            for path in sorted(ch_dir.glob("v*.json"), reverse=True):
                try:
                    doc = InformationDocument.from_dict(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except Exception:
                    continue
                if before and doc.as_of > before:
                    continue
                docs.append(doc)
        docs.sort(key=lambda d: d.created_at, reverse=True)
        return docs[:limit]

    def documents_for_context(
        self,
        *,
        before: str,
        channels: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[InformationDocument]:
        """Return published docs with as_of <= before (no future leakage)."""
        out: List[InformationDocument] = []
        for ch in channels or ["ai_news_60s", "dufu_world_intel"]:
            for doc in self.list_documents(ch, before=before, limit=limit):
                if doc.status == "published" and doc.as_of <= before:
                    out.append(doc)
        out.sort(key=lambda d: d.as_of, reverse=True)
        return out[:limit]


_doc_store: Optional[DocumentStore] = None


def get_document_store() -> DocumentStore:
    global _doc_store
    if _doc_store is None:
        _doc_store = DocumentStore()
    return _doc_store
