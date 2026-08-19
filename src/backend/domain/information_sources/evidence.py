# -*- coding: utf-8 -*-
"""T203 — Normalize, dedupe, evidence storage for source fetches."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .models import FetchBatch, FetchItem, SourceConfig, utc_now_iso

_DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "storage" / "information_evidence"
_ENTITY_RE = re.compile(r"\b[A-Z]{1,5}\b|\b[\u4e00-\u9fff]{2,12}\b")
_HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_SCRIPT_STYLE_RE = re.compile(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_SPACE_RE = re.compile(r"\s+")
# 作者/编辑行、图注、无关前缀 — 快讯不应带这些
_BYLINE_LINE_RE = re.compile(
    r"^\s*(?:作者|编辑|记者|编译|来源|责编|撰文|审核|校对|摄影|图|视频|文)\s*"
    r"(?:[|/｜：:\s].*)?$",
    re.M,
)
_BYLINE_INLINE_RE = re.compile(
    r"(?:作者|编辑|记者|编译|来源|责编|撰文)\s*[|/｜：:]\s*[^\n。；;]{1,40}"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z\u4e00-\u9fff])")


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


def normalize_timestamp(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Already ISO-ish
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    # Common RSS date formats — keep original if unparseable
    return text


def extract_entities(text: str, limit: int = 20) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()
    for m in _ENTITY_RE.finditer(text or ""):
        tok = m.group(0)
        if tok.lower() in {"http", "https", "www", "com", "the", "and", "for"}:
            continue
        if tok not in seen:
            seen.add(tok)
            found.append(tok)
        if len(found) >= limit:
            break
    return found


def clean_feed_text(value: Optional[str], *, max_chars: int = 12000) -> str:
    """Convert RSS HTML descriptions into compact, readable plain text.

    Feeds frequently put full article HTML in ``description``. Keeping those
    tags in an evidence claim makes the dashboard unreadable and can let a
    single item dominate the layout. The original URL and raw connector
    metadata remain available for audit; the display/analysis text is bounded.
    """
    text = str(value or "")
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    text = _SPACE_RE.sub(" ", text).strip()
    return text[:max_chars].rstrip() if max_chars > 0 else text


def strip_bylines(text: str) -> str:
    """Remove author/editor bylines common in Chinese news HTML dumps."""
    cleaned = _BYLINE_INLINE_RE.sub(" ", text or "")
    cleaned = _BYLINE_LINE_RE.sub(" ", cleaned)
    return _SPACE_RE.sub(" ", cleaned).strip()


def _hard_truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rstrip(" ，,;；:：")
    # Prefer cutting at a clause boundary
    for sep in ("。", "；", "，", "、", " ", "—", "-"):
        idx = cut.rfind(sep)
        if idx >= max(12, max_chars // 3):
            cut = cut[: idx + (1 if sep in "。；" else 0)]
            break
    return cut.rstrip(" ，,;；:：") + "…"


def _is_good_headline(title: str) -> bool:
    t = (title or "").strip()
    if len(t) < 6 or len(t) > 100:
        return False
    if t.startswith("http") or t.startswith("www."):
        return False
    if _BYLINE_LINE_RE.match(t):
        return False
    # Pure punctuation / noise
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t):
        return False
    return True


def _token_overlap_ratio(a: str, b: str) -> float:
    """Rough char-bigram overlap for CJK-friendly near-duplicate detection."""
    a = re.sub(r"\s+", "", a or "")
    b = re.sub(r"\s+", "", b or "")
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    def bigrams(s: str) -> set:
        if len(s) < 2:
            return {s}
        return {s[i : i + 2] for i in range(len(s) - 1)}
    ba, bb = bigrams(a), bigrams(b)
    inter = len(ba & bb)
    return inter / max(1, min(len(ba), len(bb)))


def first_substantive_sentence(text: str, *, min_len: int = 12, max_len: int = 100) -> str:
    """Pick the first informative sentence, skipping bylines and fluff."""
    body = strip_bylines(clean_feed_text(text, max_chars=4000))
    if not body:
        return ""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(body) if p and p.strip()]
    for part in parts:
        part = strip_bylines(part).strip(" 　·•-|｜")
        if len(part) < min_len:
            continue
        if _BYLINE_LINE_RE.match(part):
            continue
        if re.match(r"^(图|视频|资料|点击|阅读原文|更多|导读|摘要)[:：\s]", part):
            continue
        if len(part) > max_len:
            return _hard_truncate(part, max_len)
        return part
    return _hard_truncate(body, max_len) if body else ""


def extract_news_brief(
    *,
    title: str = "",
    summary: str = "",
    content: str = "",
    max_chars: int = 120,
) -> str:
    """Extract a 快讯-style brief: clean title + one key fact, no HTML/bylines.

    Priority:
      1. Good headline (optionally enriched with a non-overlapping lede fact)
      2. First substantive sentence from summary/content
      3. Truncated cleaned body
    """
    title_clean = strip_bylines(clean_feed_text(title, max_chars=120))
    body_src = summary or content or ""
    lede = first_substantive_sentence(body_src, min_len=10, max_len=min(100, max_chars))

    if _is_good_headline(title_clean):
        if lede and _token_overlap_ratio(lede, title_clean) < 0.55:
            # Title already states the claim; only append if lede adds a number/fact
            if re.search(r"\d", lede) and not re.search(r"\d", title_clean):
                brief = f"{title_clean}（{lede}）"
            elif len(title_clean) < 36 and len(lede) <= 48:
                brief = f"{title_clean}：{lede}"
            else:
                brief = title_clean
        else:
            brief = title_clean
        return _hard_truncate(brief, max_chars) or "（无可用摘要）"

    if lede:
        return _hard_truncate(lede, max_chars)
    body = strip_bylines(clean_feed_text(body_src, max_chars=max_chars * 2))
    if body:
        return _hard_truncate(body, max_chars)
    if title_clean:
        return _hard_truncate(title_clean, max_chars)
    return "（无可用摘要）"


def content_hash(url: str, title: str, content: str) -> str:
    payload = f"{url}\n{title}\n{content}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class EvidenceRecord:
    """Traceable evidence unit produced from a fetch item."""

    evidence_id: str
    source_id: str
    run_id: str
    url: str
    title: str
    content: str
    summary: str
    content_hash: str
    fetched_at: str
    published_at: Optional[str] = None
    normalized_published_at: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    language: str = ""
    source_reputation: float = 0.5
    license_note: str = ""
    robots_policy: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class NormalizeResult:
    records: List[EvidenceRecord]
    duplicates_skipped: int = 0
    run_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "duplicates_skipped": self.duplicates_skipped,
            "records": [r.to_dict() for r in self.records],
        }


class EvidenceStore:
    """Filesystem evidence store with content-hash dedupe index."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.index_path = self.root / "hash_index.json"
        _ensure_dir(self.root)
        self._hashes: Set[str] = self._load_index()

    def _load_index(self) -> Set[str]:
        if not self.index_path.exists():
            return set()
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return set(data.get("hashes") or [])
        except Exception:
            return set()

    def _save_index(self) -> None:
        _atomic_write(
            self.index_path,
            json.dumps({"hashes": sorted(self._hashes)}, ensure_ascii=False, indent=2),
        )

    def normalize_and_store(
        self,
        batch: FetchBatch,
        config: SourceConfig,
        *,
        run_id: Optional[str] = None,
    ) -> NormalizeResult:
        run_id = run_id or str(uuid.uuid4())[:12]
        out: List[EvidenceRecord] = []
        dup = 0
        for item in batch.items:
            rec = self._from_item(item, batch, config, run_id)
            if rec.content_hash in self._hashes:
                dup += 1
                continue
            self._hashes.add(rec.content_hash)
            path = self.root / "records" / f"{rec.evidence_id}.json"
            _atomic_write(path, json.dumps(rec.to_dict(), ensure_ascii=False, indent=2))
            out.append(rec)
        self._save_index()
        # Also store run summary
        summary = {
            "run_id": run_id,
            "source_id": config.source_id,
            "fetched_at": batch.fetched_at,
            "items_in": len(batch.items),
            "stored": len(out),
            "duplicates_skipped": dup,
            "errors": batch.errors,
            "evidence_ids": [r.evidence_id for r in out],
        }
        _atomic_write(
            self.root / "runs" / f"{run_id}.json",
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        return NormalizeResult(records=out, duplicates_skipped=dup, run_id=run_id)

    def _from_item(
        self,
        item: FetchItem,
        batch: FetchBatch,
        config: SourceConfig,
        run_id: str,
    ) -> EvidenceRecord:
        h = item.content_hash() if hasattr(item, "content_hash") else content_hash(
            item.url, item.title, item.content
        )
        title = clean_feed_text(item.title, max_chars=240)
        content = clean_feed_text(item.content, max_chars=12000)
        # Prefer a short extracted brief over raw HTML-ish description dumps.
        brief = extract_news_brief(
            title=title,
            summary=item.summary or "",
            content=item.content or content,
            max_chars=160,
        )
        summary = brief or clean_feed_text(item.summary or content, max_chars=160)
        text = f"{title}\n{content}"
        return EvidenceRecord(
            evidence_id=str(uuid.uuid4())[:12],
            source_id=config.source_id,
            run_id=run_id,
            url=item.url,
            title=title,
            content=content,
            summary=summary,
            content_hash=h,
            fetched_at=batch.fetched_at or utc_now_iso(),
            published_at=item.published_at,
            normalized_published_at=normalize_timestamp(item.published_at),
            entities=extract_entities(text),
            language=item.language or config.language,
            source_reputation=float(config.reputation_score),
            license_note=config.license_note,
            robots_policy=config.robots_policy,
            raw={"item_raw": item.raw, "batch_meta": batch.metadata},
        )

    def get(self, evidence_id: str) -> Optional[EvidenceRecord]:
        path = self.root / "records" / f"{evidence_id}.json"
        if not path.exists():
            return None
        return EvidenceRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_for_run(self, run_id: str) -> List[EvidenceRecord]:
        summary_path = self.root / "runs" / f"{run_id}.json"
        if not summary_path.exists():
            return []
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        out = []
        for eid in data.get("evidence_ids") or []:
            rec = self.get(eid)
            if rec:
                out.append(rec)
        return out

    def list_recent(self, limit: int = 50) -> List[EvidenceRecord]:
        records_dir = self.root / "records"
        if not records_dir.exists():
            return []
        files = sorted(records_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: List[EvidenceRecord] = []
        for path in files[:limit]:
            try:
                out.append(EvidenceRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return out

    def list_recent_for_sources(self, source_ids: Set[str], limit: int = 50) -> List[EvidenceRecord]:
        """Return latest cached evidence for selected sources, even if old.

        A noisy source can otherwise push a quiet but selected RSS source past
        a global ``list_recent`` window.  The scheduler uses this method only
        as a continuity fallback after a deduplicated fetch, never as a way to
        mix unrelated sources into a report.
        """
        records_dir = self.root / "records"
        allowed = {str(source_id) for source_id in source_ids if source_id}
        if not records_dir.exists() or not allowed or limit <= 0:
            return []
        files = sorted(records_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: List[EvidenceRecord] = []
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if str(data.get("source_id") or "") not in allowed:
                    continue
                out.append(EvidenceRecord.from_dict(data))
            except Exception:
                continue
            if len(out) >= limit:
                break
        return out


_store: Optional[EvidenceStore] = None


def get_evidence_store() -> EvidenceStore:
    global _store
    if _store is None:
        _store = EvidenceStore()
    return _store
