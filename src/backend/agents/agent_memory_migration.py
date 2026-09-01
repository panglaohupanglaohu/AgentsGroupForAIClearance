# -*- coding: utf-8 -*-
"""Agent 记忆迁移引擎 — v2 导出信封、三策略导入、事务回滚、Will 协议.

schema: ag.memory.export/v2
不依赖 scripts/；import 时不训练、不写全局日志。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows compatibility fallback

from .agent_memory_core import (
    MEMORY_SCHEMA,
    AgentMemoryCore,
    AgentMemoryStore,
    _bigrams,
    _hash_cosine,
    _now_ms,
    _safe_team_agent,
    _uid,
    _vector_lite_enabled,
    get_memory_store,
)
from .agent_memory_lifecycle import (
    AgentMemoryLifecycle,
    MemoryLifecycleError,
    get_memory_lifecycle,
)

EXPORT_SCHEMA_V2 = "ag.memory.export/v2"
EXPORT_SCHEMA_V1 = MEMORY_SCHEMA  # ag.memory/v1
KNOWN_LAYERS = ("log", "perception", "intentions", "affect", "semantic")
DEFAULT_TRANSFER_LAYERS = ("log", "perception", "intentions", "semantic")
STRATEGIES = frozenset({"replace_all", "import_all", "merge", "selective"})
WILL_STATUSES = frozenset({"draft", "ready", "blocked", "executing", "executed", "failed"})
HANDOVER = frozenset({"ask_new_owner", "auto", "drop"})


class MemoryMigrationError(Exception):
    def __init__(self, code: str, detail: str = "", *, tx_id: str = ""):
        self.code = code
        self.detail = detail or code
        self.tx_id = tx_id
        super().__init__(self.detail)


@dataclass
class ValidationReport:
    ok: bool
    schema_version: str = ""
    validation_strength: str = "strong"  # strong | legacy_weak
    counts: Dict[str, int] = field(default_factory=dict)
    layer_hashes: Dict[str, str] = field(default_factory=dict)
    manifest_sha256: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "validation_strength": self.validation_strength,
            "counts": dict(self.counts),
            "layer_hashes": dict(self.layer_hashes),
            "manifest_sha256": self.manifest_sha256,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ── Canonical JSON / hashes ─────────────────────────────────────


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def count_layer(name: str, data: Any) -> int:
    if name == "affect":
        if not isinstance(data, dict):
            return 0
        # residue object counts as one logical record when any signal present
        labels = data.get("labels") or {}
        if labels or data.get("valence") or data.get("arousal"):
            return 1
        return 0
    if isinstance(data, list):
        return len(data)
    return 0


def count_each_layer(layers: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for name in KNOWN_LAYERS:
        out[name] = count_layer(name, (layers or {}).get(name))
    return out


def layer_hashes(layers: Dict[str, Any]) -> Dict[str, str]:
    return {name: sha256_json((layers or {}).get(name)) for name in KNOWN_LAYERS}


def _manifest_body_for_hash(manifest: Dict[str, Any]) -> Dict[str, Any]:
    body = copy.deepcopy(manifest)
    ch = body.get("content_hashes")
    if isinstance(ch, dict):
        ch = dict(ch)
        ch.pop("manifest_sha256", None)
        body["content_hashes"] = ch
    return body


def recompute_manifest_hash(manifest: Dict[str, Any]) -> str:
    return sha256_json(_manifest_body_for_hash(manifest))


# ── Export ──────────────────────────────────────────────────────


def build_export_v2(
    core: AgentMemoryCore,
    *,
    seal_id: Optional[str] = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Read persistence layers directly. AgentMemoryCore.export_all() also builds
    # systems/dynamic views, whose affect residue calculation updates updatedAt;
    # using it here would make two exports hash differently without real input.
    layers = {
        "log": copy.deepcopy(core.log.to_json()),
        "perception": copy.deepcopy(core.perception.to_json()),
        "intentions": copy.deepcopy(core.intentions.to_json()),
        "affect": copy.deepcopy(core.affect.to_json()),
        "semantic": copy.deepcopy(core.semantic.to_json()),
    }
    # ensure all known layers present
    for name in KNOWN_LAYERS:
        layers.setdefault(name, [] if name != "affect" else {})
    raw_meta = core.store.load(core.team_id, core.agent_id, "meta", {})
    meta = copy.deepcopy(raw_meta) if isinstance(raw_meta, dict) else {}
    counts = count_each_layer(layers)
    lhashes = layer_hashes(layers)
    manifest: Dict[str, Any] = {
        "schema_version": EXPORT_SCHEMA_V2,
        "export_id": _uid("mexp"),
        "exported_at": _now_ms(),
        "source_agent": {"team_id": core.team_id, "agent_id": core.agent_id},
        "seal_id": seal_id,
        "record_counts": counts,
        "content_hashes": {"layers": lhashes},
        "layers": layers,
        "provenance": provenance or {},
        # compatibility aliases for older readers
        "schema": EXPORT_SCHEMA_V2,
        "team_id": core.team_id,
        "agent_id": core.agent_id,
        "exportedAt": _now_ms(),
        "meta": meta,
    }
    manifest["content_hashes"]["manifest_sha256"] = recompute_manifest_hash(manifest)
    return manifest


def _upgrade_v1_to_weak_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Accept ag.memory/v1 as weak-validation envelope (no strong hash claim)."""
    layers = copy.deepcopy(bundle.get("layers") or {})
    for name in KNOWN_LAYERS:
        layers.setdefault(name, [] if name != "affect" else {})
    counts = count_each_layer(layers)
    lhashes = layer_hashes(layers)
    src_team = bundle.get("team_id") or (bundle.get("source_agent") or {}).get("team_id") or ""
    src_agent = bundle.get("agent_id") or (bundle.get("source_agent") or {}).get("agent_id") or ""
    weak = {
        "schema_version": EXPORT_SCHEMA_V2,
        "export_id": bundle.get("export_id") or _uid("mexp_legacy"),
        "exported_at": bundle.get("exportedAt") or bundle.get("exported_at") or _now_ms(),
        "source_agent": {"team_id": src_team, "agent_id": src_agent},
        "seal_id": bundle.get("seal_id"),
        "record_counts": counts,
        "content_hashes": {
            "layers": lhashes,
            "manifest_sha256": "",  # deliberately empty for weak
        },
        "layers": layers,
        "provenance": {"legacy_schema": EXPORT_SCHEMA_V1, "validation_strength": "legacy_weak"},
        "schema": EXPORT_SCHEMA_V1,
        "validation_strength": "legacy_weak",
        "meta": bundle.get("meta") if isinstance(bundle.get("meta"), dict) else {},
    }
    return weak


def validate_export_v2(bundle: Any, *, allow_legacy_v1: bool = True) -> ValidationReport:
    report = ValidationReport(ok=False)
    if not isinstance(bundle, dict):
        report.errors.append("bundle_not_object")
        return report

    schema = (
        bundle.get("schema_version")
        or bundle.get("schema")
        or ""
    )
    report.schema_version = str(schema)

    # legacy v1 path
    if schema == EXPORT_SCHEMA_V1:
        if not allow_legacy_v1:
            report.errors.append("legacy_v1_not_allowed")
            return report
        weak = _upgrade_v1_to_weak_bundle(bundle)
        report.ok = True
        report.validation_strength = "legacy_weak"
        report.schema_version = EXPORT_SCHEMA_V1
        report.counts = dict(weak["record_counts"])
        report.layer_hashes = dict(weak["content_hashes"]["layers"])
        report.warnings.append("validation_strength=legacy_weak")
        return report

    if schema != EXPORT_SCHEMA_V2:
        report.errors.append(f"unknown_schema:{schema}")
        return report

    report.validation_strength = "strong"
    src = bundle.get("source_agent")
    if not isinstance(src, dict) or not src.get("team_id") or not src.get("agent_id"):
        report.errors.append("missing_source_agent")

    layers = bundle.get("layers")
    if not isinstance(layers, dict):
        report.errors.append("missing_layers")
        return report

    for name in KNOWN_LAYERS:
        if name not in layers:
            report.errors.append(f"missing_layer:{name}")
        else:
            data = layers[name]
            if name == "affect" and not isinstance(data, dict):
                report.errors.append("affect_not_object")
            elif name != "affect" and not isinstance(data, list):
                report.errors.append(f"layer_not_list:{name}")
    for name in layers:
        if name not in KNOWN_LAYERS:
            report.errors.append(f"unknown_layer:{name}")

    expected_counts = count_each_layer(layers)
    claimed = bundle.get("record_counts") or {}
    if not isinstance(claimed, dict):
        report.errors.append("record_counts_missing")
    else:
        for name in KNOWN_LAYERS:
            try:
                claimed_count = int(claimed.get(name, -1))
            except (TypeError, ValueError):
                report.errors.append(f"count_invalid:{name}")
                continue
            if claimed_count != expected_counts[name]:
                report.errors.append(f"count_mismatch:{name}")

    expected_hashes = layer_hashes(layers)
    ch = bundle.get("content_hashes") or {}
    claimed_layers = (ch.get("layers") if isinstance(ch, dict) else None) or {}
    if not isinstance(claimed_layers, dict):
        report.errors.append("layer_hashes_missing")
    else:
        for name in KNOWN_LAYERS:
            if claimed_layers.get(name) != expected_hashes[name]:
                report.errors.append(f"hash_mismatch:{name}")

    claimed_manifest = (ch.get("manifest_sha256") if isinstance(ch, dict) else None) or ""
    expected_manifest = recompute_manifest_hash(bundle)
    if claimed_manifest != expected_manifest:
        report.errors.append("manifest_hash_mismatch")

    report.counts = expected_counts
    report.layer_hashes = expected_hashes
    report.manifest_sha256 = expected_manifest
    report.ok = not report.errors
    return report


# ── SWEI 导入五道具名门 (论文 Eq.(25)) ────────────────────────────

IMPORT_GATES: Sequence[str] = ("scope", "schema", "integrity", "provenance", "conflict")


def evaluate_import_gates(
    bundle: Dict[str, Any],
    will: Optional[Dict[str, Any]] = None,
    target_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    r"""论文 Eq.(25) g_imp = \bigwedge_{v \in V_imp} g_v 五道具名门.

    1. scope: 包内层是否都在 Will/目标授权范围内
    2. schema: validate_export_v2 格式校验
    3. integrity: manifest 哈希与逐层内容哈希一致
    4. provenance: 目标受益人身份与 Will 声明一致
    5. conflict: 冲突策略属于合法策略集合
    """
    will_dict = will or {}
    gates: Dict[str, Any] = {}

    # 1. g_scope
    allowed = set(will_dict.get("layers") or KNOWN_LAYERS)
    bundle_layers = set((bundle.get("layers") or {}).keys())
    scope_ok = (bundle_layers <= allowed) if bundle_layers else True
    gates["scope"] = {
        "ok": scope_ok,
        "allowed_layers": sorted(allowed),
        "actual_layers": sorted(bundle_layers),
        "extra_layers": sorted(bundle_layers - allowed),
    }

    # 2. g_schema
    rep = validate_export_v2(bundle, allow_legacy_v1=True)
    gates["schema"] = {
        "ok": rep.ok,
        "validation_strength": rep.validation_strength,
        "errors": list(rep.errors),
    }

    # 3. g_integrity
    ch = (bundle.get("content_hashes") if isinstance(bundle, dict) else {}) or {}
    claimed_m_hash = (ch.get("manifest_sha256") if isinstance(ch, dict) else "") or ""
    expected_m_hash = recompute_manifest_hash(bundle) if isinstance(bundle, dict) else ""
    integrity_ok = rep.ok and (claimed_m_hash == expected_m_hash)
    gates["integrity"] = {
        "ok": integrity_ok,
        "manifest_hash_match": claimed_m_hash == expected_m_hash,
        "layer_counts": count_each_layer(bundle.get("layers") or {}) if isinstance(bundle.get("layers"), dict) else {},
    }

    # 4. g_provenance
    beneficiary_claimed = will_dict.get("beneficiary")
    target_agent = (target_state or {}).get("agent_id") if target_state else None
    if beneficiary_claimed and target_agent:
        prov_ok = (beneficiary_claimed == target_agent)
    else:
        prov_ok = True
    gates["provenance"] = {
        "ok": prov_ok,
        "beneficiary_claimed": beneficiary_claimed,
        "target_agent": target_agent,
    }

    # 5. g_conflict
    strat = will_dict.get("strategy")
    if isinstance(strat, dict):
        conflict_ok = all(s in STRATEGIES for s in strat.values())
    elif isinstance(strat, str):
        conflict_ok = strat in STRATEGIES
    else:
        conflict_ok = True
    gates["conflict"] = {
        "ok": conflict_ok,
        "strategy": strat,
    }

    all_ok = all(g.get("ok", False) for g in gates.values())
    return {
        "ok": all_ok,
        "gates": gates,
        "failed_gates": [name for name, g in gates.items() if not g.get("ok")],
    }


# ── Snapshots / transactions ────────────────────────────────────


LAYER_FILES = (
    "log",
    "perception",
    "intentions",
    "affect",
    "semantic",
    "meta",
    "inherited",
    "legacy",
)


def snapshot_exact_files(store: AgentMemoryStore, team_id: str, agent_id: str) -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    for name in LAYER_FILES:
        p = store.path(team_id, agent_id, name)
        if p.is_file():
            snap[name] = p.read_text(encoding="utf-8")
        else:
            snap[name] = None
    return snap


def restore_exact_files(store: AgentMemoryStore, team_id: str, agent_id: str, before: Dict[str, Any]) -> None:
    for name, content in (before or {}).items():
        p = store.path(team_id, agent_id, name)
        if content is None:
            if p.is_file():
                p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(p)


def snapshot_hash(before: Dict[str, Any]) -> str:
    return sha256_json(before)


# ── Inherited partitions ────────────────────────────────────────


def load_inherited(store: AgentMemoryStore, team_id: str, agent_id: str) -> Dict[str, Any]:
    data = store.load(team_id, agent_id, "inherited", None)
    if not isinstance(data, dict):
        return {"schema": "ag.memory.inherited/v1", "partitions": []}
    data.setdefault("schema", "ag.memory.inherited/v1")
    if not isinstance(data.get("partitions"), list):
        data["partitions"] = []
    return data


def save_inherited(store: AgentMemoryStore, team_id: str, agent_id: str, data: Dict[str, Any]) -> None:
    store.save(team_id, agent_id, "inherited", data)


def _stamp_origin(
    item: Any,
    *,
    kind: str,
    source_agent: Dict[str, Any],
    transfer_id: str,
    layer: str,
) -> Any:
    if isinstance(item, dict):
        out = dict(item)
        origin = dict(out.get("origin") or {})
        origin.update(
            {
                "kind": kind,
                "source_agent": {
                    "team_id": source_agent.get("team_id"),
                    "agent_id": source_agent.get("agent_id"),
                },
                "transfer_id": transfer_id,
                "layer": layer,
            }
        )
        out["origin"] = origin
        tags = list(out.get("tags") or [])
        if "传递继承" not in tags:
            tags.append("传递继承")
        out["tags"] = tags
        return out
    return item


def stamp_layers_origin(
    layers: Dict[str, Any],
    *,
    source_agent: Dict[str, Any],
    transfer_id: str,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, data in (layers or {}).items():
        if name == "affect" and isinstance(data, dict):
            if not data:
                out[name] = {}
                continue
            aff = dict(data)
            aff["origin"] = {
                "kind": "inherited",
                "source_agent": {
                    "team_id": source_agent.get("team_id"),
                    "agent_id": source_agent.get("agent_id"),
                },
                "transfer_id": transfer_id,
                "layer": "affect",
            }
            out[name] = aff
        elif isinstance(data, list):
            out[name] = [
                _stamp_origin(
                    x,
                    kind="inherited",
                    source_agent=source_agent,
                    transfer_id=transfer_id,
                    layer=name,
                )
                for x in data
            ]
        else:
            out[name] = data
    return out


def append_inherited_partition(
    store: AgentMemoryStore,
    team_id: str,
    agent_id: str,
    *,
    source_agent: Dict[str, Any],
    transfer_id: str,
    layers: Dict[str, Any],
    schema_version: str = EXPORT_SCHEMA_V2,
) -> Dict[str, Any]:
    """Merge path: append partition without rewriting active local layers."""
    inherited = load_inherited(store, team_id, agent_id)
    # idempotent: same transfer_id → no duplicate
    for p in inherited["partitions"]:
        if p.get("transfer_id") == transfer_id:
            return p
    stamped = stamp_layers_origin(layers, source_agent=source_agent, transfer_id=transfer_id)
    partition = {
        "partition_id": _uid("part"),
        "source_agent": {
            "team_id": source_agent.get("team_id"),
            "agent_id": source_agent.get("agent_id"),
        },
        "transfer_id": transfer_id,
        "imported_at": _now_ms(),
        "schema_version": schema_version,
        "layers": stamped,
        "hashes": layer_hashes(stamped),
        "record_counts": count_each_layer(stamped),
    }
    inherited["partitions"].append(partition)
    save_inherited(store, team_id, agent_id, inherited)
    return partition


def pick_layers(layers: Dict[str, Any], selected: Sequence[str]) -> Dict[str, Any]:
    selected_set = {str(x) for x in selected}
    # map system names to legacy if needed
    mapped = set()
    for s in selected_set:
        if s in KNOWN_LAYERS:
            mapped.add(s)
        elif s in ("episodic",):
            mapped.add("log")
        elif s in ("sensory",):
            mapped.add("perception")
        elif s in ("prospective",):
            mapped.add("intentions")
        elif s in ("affective",):
            mapped.add("affect")
        else:
            mapped.add(s)
    out: Dict[str, Any] = {}
    for name in KNOWN_LAYERS:
        if name in mapped:
            out[name] = copy.deepcopy(layers.get(name))
        else:
            out[name] = [] if name != "affect" else {}
    return out


# ── Import transaction ──────────────────────────────────────────


def _tx_dir(store: AgentMemoryStore) -> Path:
    d = store.root / "_migrations"
    d.mkdir(parents=True, exist_ok=True)
    return d


_THREAD_LOCKS: Dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


@contextmanager
def target_transaction_lock(store: AgentMemoryStore, team_id: str, agent_id: str):
    """Serialize writes to one beneficiary across threads and worker processes."""
    safe_team, safe_agent = _safe_team_agent(team_id, agent_id)
    key = f"{store.root.resolve()}::{safe_team}::{safe_agent}"
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    lock_dir = store.root / "_migration_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{safe_team}__{safe_agent}.lock"
    with thread_lock:
        if fcntl is not None:
            with lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        else:
            yield


def write_tx_record(store: AgentMemoryStore, tx_id: str, payload: Dict[str, Any]) -> None:
    path = _tx_dir(store) / f"{tx_id}.json"
    existing: Dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(payload)
    existing["tx_id"] = tx_id
    _atomic_write_json(path, existing)


def load_tx_record(store: AgentMemoryStore, tx_id: str) -> Optional[Dict[str, Any]]:
    path = _tx_dir(store) / f"{tx_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_layers_identity(
    layers: Dict[str, Any],
    *,
    target_agent: str,
    keep_origin_fields: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, data in (layers or {}).items():
        if name == "affect" and isinstance(data, dict):
            out[name] = copy.deepcopy(data)
            continue
        if not isinstance(data, list):
            out[name] = data
            continue
        items = []
        for item in data:
            if not isinstance(item, dict):
                items.append(item)
                continue
            row = dict(item)
            if name == "log" and not keep_origin_fields:
                row["subject"] = target_agent
            items.append(row)
        out[name] = items
    return out


def _apply_replace_all(core: AgentMemoryCore, layers: Dict[str, Any]) -> None:
    core.log.replace(layers.get("log"))
    core.perception.replace(layers.get("perception"))
    core.intentions.replace(layers.get("intentions"))
    core.affect.replace(layers.get("affect"))
    core.semantic.replace(layers.get("semantic"))


def _commit_files_with_hook(
    store: AgentMemoryStore,
    team_id: str,
    agent_id: str,
    writes: List[tuple],
    *,
    fail_after: Optional[Any] = None,
) -> None:
    """writes: list of (name, data). fail_after: 1-based index or 'last' for tests."""
    total = len(writes)
    for i, (name, data) in enumerate(writes, start=1):
        if fail_after is not None:
            if fail_after == "last" and i == total:
                raise MemoryMigrationError("injected_fail", f"fail_after=last at {name}")
            if isinstance(fail_after, int) and i == fail_after:
                raise MemoryMigrationError("injected_fail", f"fail_after={fail_after} at {name}")
        store.save(team_id, agent_id, name, data)


def _import_transaction_unlocked(
    target: AgentMemoryCore,
    bundle: Dict[str, Any],
    *,
    strategy: str = "merge",
    selected_layers: Optional[Sequence[str]] = None,
    transfer_id: Optional[str] = None,
    fail_after: Optional[Any] = None,
    allow_legacy_v1: bool = True,
) -> Dict[str, Any]:
    store = target.store
    team_id, agent_id = target.team_id, target.agent_id
    strategy = (strategy or "merge").strip()
    if strategy not in STRATEGIES:
        raise MemoryMigrationError("invalid_strategy", f"unknown strategy {strategy}")

    # accept weak-upgraded v1
    validation = validate_export_v2(bundle, allow_legacy_v1=allow_legacy_v1)
    if not validation.ok:
        raise MemoryMigrationError(
            "validation_failed",
            ";".join(validation.errors) or "validation_failed",
        )

    if validation.validation_strength == "legacy_weak":
        working = _upgrade_v1_to_weak_bundle(bundle)
    else:
        working = bundle

    tx_id = transfer_id or _uid("mtx")
    # idempotent committed transfer — check before staging rewrite
    existing_tx = load_tx_record(store, tx_id)
    if existing_tx and existing_tx.get("state") == "committed":
        return {
            "ok": True,
            "tx_id": tx_id,
            "state": "committed",
            "idempotent": True,
            "validation": validation.to_dict(),
            "report": existing_tx.get("report") or {},
            "partition": existing_tx.get("partition"),
        }

    before = snapshot_exact_files(store, team_id, agent_id)
    before_h = snapshot_hash(before)
    now = _now_ms()
    write_tx_record(
        store,
        tx_id,
        {
            "state": "staging",
            "strategy": strategy,
            "target": {"team_id": team_id, "agent_id": agent_id},
            "source_agent": working.get("source_agent"),
            "validation": validation.to_dict(),
            "before_hash": before_h,
            "validated_at": now,
            "staged_at": now,
        },
    )

    try:
        source_agent = working.get("source_agent") or {
            "team_id": working.get("team_id"),
            "agent_id": working.get("agent_id"),
        }
        layers_in = _normalize_layers_identity(
            working.get("layers") or {},
            target_agent=agent_id,
            keep_origin_fields=True,
        )

        # 论文 Section 7.14 记忆污染筛查：导入前隔离恶意/高危记录
        from .memory_contamination import screen_records
        quarantine_info: Dict[str, Any] = {}
        for lname, ldata in list(layers_in.items()):
            if isinstance(ldata, list) and ldata:
                s_res = screen_records(ldata)
                if s_res.flagged:
                    flagged_set = set(s_res.flagged)
                    layers_in[lname] = [
                        r for r in ldata
                        if str(r.get("id") or r.get("record_id") or "") not in flagged_set
                    ]
                    quarantine_info[lname] = {
                        "quarantined": len(s_res.flagged),
                        "flagged_ids": s_res.flagged,
                        "reasons": s_res.reasons,
                    }

        if strategy == "selective":
            if not selected_layers:
                raise MemoryMigrationError("selected_layers_required", "selective 需要非空 selected_layers")
            layers_in = pick_layers(layers_in, selected_layers)

        partition = None
        if strategy in ("merge", "selective"):
            # do not rewrite local active layers — only inherited partition
            # stage: write inherited only (+ meta touch)
            inherited_before = load_inherited(store, team_id, agent_id)
            # simulate multi-file write for fault injection: meta + inherited (+ optional audit file)
            meta = store.load(team_id, agent_id, "meta", {}) or {}
            if not isinstance(meta, dict):
                meta = {}
            meta = dict(meta)
            meta["bound"] = True
            meta["last_import_tx"] = tx_id
            meta["last_import_at"] = now
            meta["last_import_strategy"] = strategy
            if validation.validation_strength == "legacy_weak":
                meta["last_import_validation"] = "legacy_weak"

            # Build candidate inherited without saving yet
            candidate_inherited = copy.deepcopy(inherited_before)
            already = any(p.get("transfer_id") == tx_id for p in candidate_inherited.get("partitions") or [])
            if not already:
                stamped = stamp_layers_origin(
                    layers_in, source_agent=source_agent, transfer_id=tx_id
                )
                partition = {
                    "partition_id": _uid("part"),
                    "source_agent": {
                        "team_id": source_agent.get("team_id"),
                        "agent_id": source_agent.get("agent_id"),
                    },
                    "transfer_id": tx_id,
                    "imported_at": now,
                    "schema_version": working.get("schema_version") or EXPORT_SCHEMA_V2,
                    "layers": stamped,
                    "hashes": layer_hashes(stamped),
                    "record_counts": count_each_layer(stamped),
                }
                candidate_inherited.setdefault("partitions", []).append(partition)
            else:
                for p in candidate_inherited["partitions"]:
                    if p.get("transfer_id") == tx_id:
                        partition = p
                        break

            writes = [
                ("meta", meta),
                ("inherited", candidate_inherited),
                # third synthetic checkpoint file for fail_after tests (audit sidecar)
                (
                    "meta",
                    {**meta, "import_checkpoint": "final"},
                ),
            ]
            # verify candidate hashes before commit
            if partition:
                assert partition.get("hashes") == layer_hashes(partition.get("layers") or {})
            _commit_files_with_hook(
                store, team_id, agent_id, writes, fail_after=fail_after
            )
            # verify committed
            after_inherited = load_inherited(store, team_id, agent_id)
            if partition and not any(
                p.get("transfer_id") == tx_id for p in after_inherited.get("partitions") or []
            ):
                raise MemoryMigrationError("commit_verify_failed", "inherited partition missing after commit")

        elif strategy in ("replace_all", "import_all"):
            # replace active layers; keep provenance in meta; do not wipe inherited
            meta = store.load(team_id, agent_id, "meta", {}) or {}
            if not isinstance(meta, dict):
                meta = {}
            meta = dict(meta)
            meta["bound"] = True
            meta["last_import_tx"] = tx_id
            meta["last_import_at"] = now
            meta["last_import_strategy"] = strategy
            if validation.validation_strength == "legacy_weak":
                meta["last_import_validation"] = "legacy_weak"
            meta["replaced_from"] = source_agent

            writes = [
                ("log", list(layers_in.get("log") or [])),
                ("perception", list(layers_in.get("perception") or [])),
                ("intentions", list(layers_in.get("intentions") or [])),
                ("affect", layers_in.get("affect") if isinstance(layers_in.get("affect"), dict) else {}),
                ("semantic", list(layers_in.get("semantic") or [])),
                ("meta", meta),
            ]
            # verify candidate counts
            cand_counts = count_each_layer(
                {
                    "log": writes[0][1],
                    "perception": writes[1][1],
                    "intentions": writes[2][1],
                    "affect": writes[3][1],
                    "semantic": writes[4][1],
                }
            )
            if sum(cand_counts.values()) < 0:
                raise MemoryMigrationError("invalid_candidate", "negative counts")
            _commit_files_with_hook(
                store, team_id, agent_id, writes, fail_after=fail_after
            )
            # reload core layers from disk
            target.log.replace(store.load(team_id, agent_id, "log", []))
            target.perception.replace(store.load(team_id, agent_id, "perception", []))
            target.intentions.replace(store.load(team_id, agent_id, "intentions", []))
            target.affect.replace(store.load(team_id, agent_id, "affect", {}))
            target.semantic.replace(store.load(team_id, agent_id, "semantic", []))

        report = {
            "strategy": strategy,
            "record_counts": count_each_layer(layers_in),
            "layer_hashes": layer_hashes(layers_in),
            "partition_id": (partition or {}).get("partition_id"),
            "source_agent": source_agent,
            "validation_strength": validation.validation_strength,
        }
        write_tx_record(
            store,
            tx_id,
            {
                "state": "committed",
                "committed_at": _now_ms(),
                "report": report,
                "partition": partition,
            },
        )
        return {
            "ok": True,
            "tx_id": tx_id,
            "state": "committed",
            "validation": validation.to_dict(),
            "report": report,
            "partition": partition,
        }
    except Exception as error:
        restore_exact_files(store, team_id, agent_id, before)
        after = snapshot_exact_files(store, team_id, agent_id)
        if snapshot_hash(after) != before_h:
            # best-effort second restore
            restore_exact_files(store, team_id, agent_id, before)
        write_tx_record(
            store,
            tx_id,
            {
                "state": "rolled_back",
                "rolled_back_at": _now_ms(),
                "error": str(error),
                "error_code": getattr(error, "code", type(error).__name__),
            },
        )
        if isinstance(error, MemoryMigrationError):
            error.tx_id = tx_id
            raise
        raise MemoryMigrationError("import_failed", str(error), tx_id=tx_id) from error


def import_transaction(
    target: AgentMemoryCore,
    bundle: Dict[str, Any],
    *,
    strategy: str = "merge",
    selected_layers: Optional[Sequence[str]] = None,
    transfer_id: Optional[str] = None,
    fail_after: Optional[Any] = None,
    allow_legacy_v1: bool = True,
) -> Dict[str, Any]:
    with target_transaction_lock(target.store, target.team_id, target.agent_id):
        return _import_transaction_unlocked(
            target,
            bundle,
            strategy=strategy,
            selected_layers=selected_layers,
            transfer_id=transfer_id,
            fail_after=fail_after,
            allow_legacy_v1=allow_legacy_v1,
        )


# ── Will protocol ───────────────────────────────────────────────


def _wills_dir(store: AgentMemoryStore) -> Path:
    d = store.root / "_wills"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _will_path(store: AgentMemoryStore, will_id: str) -> Path:
    return _wills_dir(store) / f"{will_id}.json"


def save_will(store: AgentMemoryStore, will: Dict[str, Any]) -> None:
    wid = will.get("will_id")
    if not wid:
        raise MemoryMigrationError("invalid_will", "missing will_id")
    _atomic_write_json(_will_path(store, wid), will)


def load_will(store: AgentMemoryStore, will_id: str) -> Dict[str, Any]:
    p = _will_path(store, will_id)
    if not p.is_file():
        raise MemoryMigrationError("will_not_found", will_id)
    return json.loads(p.read_text(encoding="utf-8"))


def list_wills(
    store: AgentMemoryStore,
    *,
    team_id: str = "",
    agent_id: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    rows = []
    for p in sorted(_wills_dir(store).glob("will_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        testator = data.get("testator") or {}
        if team_id and testator.get("team_id") != team_id:
            continue
        if agent_id and testator.get("agent_id") != agent_id:
            continue
        rows.append(data)
        if len(rows) >= limit:
            break
    return rows


def create_will(
    store: AgentMemoryStore,
    testator_team: str,
    testator_agent: str,
    payload: Dict[str, Any],
    *,
    beneficiary_exists: Optional[Callable[[str, str], bool]] = None,
) -> Dict[str, Any]:
    ben = payload.get("beneficiary") or {}
    if isinstance(ben, str):
        ben = {"team_id": testator_team, "agent_id": ben}
    b_team = ben.get("team_id") or testator_team
    b_agent = ben.get("agent_id") or ""
    if not b_agent or (b_team == testator_team and b_agent == testator_agent):
        raise MemoryMigrationError("invalid_beneficiary", "受益者必须是其他 agent")
    if beneficiary_exists and not beneficiary_exists(b_team, b_agent):
        raise MemoryMigrationError("beneficiary_missing", f"{b_team}/{b_agent}")

    strategy = (payload.get("conflict_strategy") or payload.get("strategy") or "merge").strip()
    if strategy not in STRATEGIES:
        raise MemoryMigrationError("invalid_strategy", strategy)
    layers = (
        payload.get("migration_scope")
        or payload.get("layers")
        or list(DEFAULT_TRANSFER_LAYERS)
    )
    if not layers:
        raise MemoryMigrationError("invalid_scope", "layers empty")
    valid_scope = set(KNOWN_LAYERS) | {"episodic", "sensory", "prospective", "affective"}
    unknown_scope = [str(layer) for layer in layers if str(layer) not in valid_scope]
    if unknown_scope:
        raise MemoryMigrationError("invalid_scope", f"unknown layers: {unknown_scope}")
    ho = payload.get("handover_intentions") or "ask_new_owner"
    if ho not in HANDOVER:
        ho = "ask_new_owner"

    will = {
        "will_id": _uid("will"),
        "schema": "ag.memory.will/v1",
        "testator": {"team_id": testator_team, "agent_id": testator_agent},
        "beneficiary": {"team_id": b_team, "agent_id": b_agent},
        "migration_scope": list(layers),
        "conflict_strategy": strategy,
        "handover_intentions": ho,
        "keep_memorial": bool(payload.get("keep_memorial", True)),
        "note": payload.get("note") or "",
        "status": "draft",
        "created_at": _now_ms(),
        "preflight": None,
        "execution": None,
    }
    save_will(store, will)
    return will


def _prepare_intentions_for_handover(
    layers: Dict[str, Any],
    *,
    policy: str,
    transfer_id: str,
    source_agent_id: str,
    transferred_at: int,
) -> None:
    source_items = layers.get("intentions") or []
    if not isinstance(source_items, list) or policy == "drop":
        layers["intentions"] = []
        return
    prepared = []
    for item in source_items:
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue
        row = copy.deepcopy(item)
        origin_id = str(row.get("id") or "")
        digest = hashlib.sha256(f"{transfer_id}:{origin_id}".encode("utf-8")).hexdigest()[:12]
        row["id"] = f"in_xfer_{digest}"
        row["creator"] = row.get("creator") or source_agent_id
        row["handover"] = {
            "from": source_agent_id,
            "policy": policy,
            "origin_intention_id": origin_id,
            "transferred_at": transferred_at,
        }
        if policy == "ask_new_owner":
            row["requires_confirmation"] = True
            marker = "[待新主人确认]"
            trigger = str(row.get("trigger") or "").strip()
            if marker not in trigger:
                row["trigger"] = f"{trigger} {marker}".strip()
        prepared.append(row)
    layers["intentions"] = prepared


def _apply_affect_transfer_policy(
    src: AgentMemoryCore, layers: Dict[str, Any]
) -> Optional[str]:
    affect = layers.get("affect")
    if not isinstance(affect, dict) or not affect:
        return None
    topology = src.topology()
    style = src.memory_style()
    permeability = float(style.get("affective_permeability") or 0.0)
    policy = str(topology.get("charge_transfer") or "ask").lower()
    if permeability < 0.2:
        policy = "never"
    elif permeability < 0.5 and policy != "never":
        policy = "soft"
    if policy == "never":
        layers["affect"] = {}
        return "affect_stripped_by_memory_style"

    scale = min(permeability, 0.35 if policy == "soft" else 0.5)
    scaled = copy.deepcopy(affect)
    scaled["labels"] = {
        str(label): float(value or 0) * scale
        for label, value in (affect.get("labels") or {}).items()
    }
    scaled["valence"] = float(affect.get("valence") or 0) * scale
    scaled["arousal"] = float(affect.get("arousal") or 0) * scale
    layers["affect"] = scaled
    return f"affect_scaled:{policy}:{scale:.3f}"


def _prepare_export_for_will(
    src: AgentMemoryCore, will: Dict[str, Any]
) -> tuple[Dict[str, Any], List[str]]:
    export = build_export_v2(src)
    scope = will.get("migration_scope") or list(DEFAULT_TRANSFER_LAYERS)
    scoped = pick_layers(export["layers"], scope)
    policy = will.get("handover_intentions") or "ask_new_owner"
    _prepare_intentions_for_handover(
        scoped,
        policy=policy,
        transfer_id=will["will_id"],
        source_agent_id=src.agent_id,
        transferred_at=int(will.get("created_at") or 0),
    )
    notes = []
    affect_note = _apply_affect_transfer_policy(src, scoped)
    if affect_note:
        notes.append(affect_note)
    export["layers"] = scoped
    export["record_counts"] = count_each_layer(scoped)
    export["content_hashes"] = {"layers": layer_hashes(scoped)}
    export["content_hashes"]["manifest_sha256"] = recompute_manifest_hash(export)
    return export, notes


def preflight_will(
    store: AgentMemoryStore,
    will_id: str,
    *,
    core_factory: Optional[Callable[[str, str], AgentMemoryCore]] = None,
) -> Dict[str, Any]:
    will = load_will(store, will_id)
    t = will["testator"]
    b = will["beneficiary"]
    factory = core_factory or (lambda team, agent: AgentMemoryCore(team, agent, store=store))
    src = factory(t["team_id"], t["agent_id"])
    scope = will.get("migration_scope") or list(KNOWN_LAYERS)
    export, policy_notes = _prepare_export_for_will(src, will)

    vreport = validate_export_v2(export, allow_legacy_v1=False)
    conflicts: List[str] = []
    try:
        dst = factory(b["team_id"], b["agent_id"])
        dst_counts = dst.counts() if hasattr(dst, "counts") else {}
        if will.get("conflict_strategy") in ("replace_all", "import_all") and sum(
            int(dst_counts.get(k, 0) or 0) for k in ("log", "perception", "intentions", "semantic")
        ) > 0:
            conflicts.append("replace_will_overwrite_beneficiary_active_memory")
    except Exception as e:
        conflicts.append(f"beneficiary_unreadable:{e}")

    ok = vreport.ok and not any(c.startswith("beneficiary_unreadable") for c in conflicts)
    report = {
        "ok": ok,
        "export_id": export.get("export_id"),
        "validation": vreport.to_dict(),
        "record_counts": export["record_counts"],
        "layer_hashes": export["content_hashes"]["layers"],
        "manifest_sha256": export["content_hashes"]["manifest_sha256"],
        "conflicts": conflicts,
        "policy_notes": policy_notes,
        "strategy": will.get("conflict_strategy"),
        "scope": scope,
        "source": t,
        "beneficiary": b,
        "checked_at": _now_ms(),
        "export_preview": {
            "schema_version": EXPORT_SCHEMA_V2,
            "export_id": export.get("export_id"),
        },
    }
    # stash export for execute (by will file side-car)
    export_path = _wills_dir(store) / f"{will_id}.export.json"
    _atomic_write_json(export_path, export)

    will["status"] = "ready" if ok else "blocked"
    will["preflight"] = report
    will["updated_at"] = _now_ms()
    save_will(store, will)
    return report


def execute_will(
    store: AgentMemoryStore,
    will_id: str,
    *,
    lifecycle: Optional[AgentMemoryLifecycle] = None,
    core_factory: Optional[Callable[[str, str], AgentMemoryCore]] = None,
    fail_after: Optional[Any] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    will = load_will(store, will_id)
    if will.get("status") == "executed" and will.get("execution", {}).get("ok"):
        return {
            "ok": True,
            "will_id": will_id,
            "state": "executed",
            "idempotent": True,
            "execution": will.get("execution"),
        }
    if will.get("status") not in ("ready", "failed", "executing"):
        # allow auto-preflight if still draft
        if will.get("status") == "draft":
            preflight_will(store, will_id, core_factory=core_factory)
            will = load_will(store, will_id)
        if will.get("status") != "ready":
            raise MemoryMigrationError("will_not_ready", f"status={will.get('status')}")

    will["status"] = "executing"
    will["updated_at"] = _now_ms()
    save_will(store, will)

    t = will["testator"]
    b = will["beneficiary"]
    factory = core_factory or (lambda team, agent: AgentMemoryCore(team, agent, store=store))
    lc = lifecycle or AgentMemoryLifecycle(store=store)

    export_path = _wills_dir(store) / f"{will_id}.export.json"
    if export_path.is_file():
        export = json.loads(export_path.read_text(encoding="utf-8"))
    else:
        # rebuild
        preflight_will(store, will_id, core_factory=core_factory)
        export = json.loads(export_path.read_text(encoding="utf-8"))

    src = factory(t["team_id"], t["agent_id"])
    current_export, _ = _prepare_export_for_will(src, will)
    if current_export["content_hashes"]["layers"] != export["content_hashes"]["layers"]:
        will["status"] = "blocked"
        will["execution"] = {
            "ok": False,
            "error": "source_changed_since_preflight",
            "at": _now_ms(),
        }
        will["updated_at"] = _now_ms()
        save_will(store, will)
        raise MemoryMigrationError(
            "source_changed_since_preflight",
            "源 Agent 记忆在预检后发生变化，请重新预检",
        )

    tx_id = idempotency_key or will_id  # will_id as natural idempotency key
    source_before = snapshot_exact_files(store, t["team_id"], t["agent_id"])
    source_before_hash = snapshot_hash(source_before)
    source_state_change_at = None

    with target_transaction_lock(store, b["team_id"], b["agent_id"]):
        target_before = snapshot_exact_files(store, b["team_id"], b["agent_id"])
        dst = factory(b["team_id"], b["agent_id"])
        try:
            result = _import_transaction_unlocked(
                dst,
                export,
                strategy=will.get("conflict_strategy") or "merge",
                selected_layers=will.get("migration_scope"),
                transfer_id=tx_id,
                fail_after=fail_after,
                allow_legacy_v1=False,
            )
        except Exception as error:
            will["status"] = "failed"
            will["execution"] = {
                "ok": False,
                "error": str(error),
                "tx_id": getattr(error, "tx_id", ""),
                "at": _now_ms(),
            }
            will["updated_at"] = _now_ms()
            save_will(store, will)
            raise

        # Source must still match the preflight snapshot before lifecycle finalization.
        if snapshot_hash(snapshot_exact_files(store, t["team_id"], t["agent_id"])) != source_before_hash:
            restore_exact_files(store, b["team_id"], b["agent_id"], target_before)
            write_tx_record(
                store,
                tx_id,
                {
                    "state": "rolled_back",
                    "rolled_back_at": _now_ms(),
                    "error": "source_changed_during_execution",
                    "error_code": "source_changed_during_execution",
                },
            )
            will["status"] = "blocked"
            will["execution"] = {
                "ok": False,
                "error": "source_changed_during_execution",
                "tx_id": tx_id,
                "at": _now_ms(),
            }
            will["updated_at"] = _now_ms()
            save_will(store, will)
            raise MemoryMigrationError(
                "source_changed_during_execution",
                "源 Agent 在迁移过程中发生变化，受益者已回滚",
                tx_id=tx_id,
            )

        # Only after beneficiary commit: seal/archive source. Failure rolls back both sides.
        try:
            if will.get("keep_memorial", True):
                st_now = lc.resolve_state(t["team_id"], t["agent_id"])
                if st_now in ("active", "shared") and not src.is_sealed():
                    lc.transition(t["team_id"], t["agent_id"], "seal", reason="will_execute")
                elif not src.is_sealed():
                    src.seal()
                meta = store.load(t["team_id"], t["agent_id"], "meta", {}) or {}
                if not isinstance(meta, dict):
                    meta = {}
                meta = dict(meta)
                meta["state"] = "archived"
                meta["sealed"] = True
                meta["transferred_to"] = b["agent_id"]
                meta["will_id"] = will_id
                meta["transfer_id"] = result.get("tx_id")
                meta["transferred_at"] = _now_ms()
                store.save(t["team_id"], t["agent_id"], "meta", meta)
                source_state_change_at = _now_ms()
        except Exception as error:
            restore_exact_files(store, b["team_id"], b["agent_id"], target_before)
            restore_exact_files(store, t["team_id"], t["agent_id"], source_before)
            write_tx_record(
                store,
                tx_id,
                {
                    "state": "rolled_back",
                    "rolled_back_at": _now_ms(),
                    "error": str(error),
                    "error_code": "source_finalize_failed",
                },
            )
            try:
                lc._append_audit(
                    t["team_id"],
                    t["agent_id"],
                    {
                        "t": _now_ms(),
                        "action": "will_rollback",
                        "will_id": will_id,
                        "reason": "source_finalize_failed",
                    },
                )
            except Exception:
                pass
            will["status"] = "failed"
            will["execution"] = {
                "ok": False,
                "error": str(error),
                "error_code": "source_finalize_failed",
                "tx_id": tx_id,
                "at": _now_ms(),
            }
            will["updated_at"] = _now_ms()
            save_will(store, will)
            raise MemoryMigrationError(
                "source_finalize_failed", str(error), tx_id=tx_id
            ) from error

    will["status"] = "executed"
    will["execution"] = {
        "ok": True,
        "tx_id": result.get("tx_id"),
        "state": result.get("state"),
        "report": result.get("report"),
        "validation": result.get("validation"),
        "partition": result.get("partition"),
        "source_state_change_at": source_state_change_at,
        "at": _now_ms(),
    }
    will["updated_at"] = _now_ms()
    save_will(store, will)

    # transfer audit record for history UI
    xfer_dir = store.root / "_transfers"
    xfer_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "transfer_id": result.get("tx_id"),
        "will_id": will_id,
        "team_id": t["team_id"],
        "from": t["agent_id"],
        "to": b["agent_id"],
        "handover_intentions": will.get("handover_intentions"),
        "keep_memorial": will.get("keep_memorial", True),
        "layers": will.get("migration_scope"),
        "strategy": will.get("conflict_strategy"),
        "copied": (result.get("report") or {}).get("record_counts"),
        "at": _now_ms(),
        "schema": "ag.transfer/v2",
        "state": "committed",
        "validation": result.get("validation"),
        "partition_id": (result.get("partition") or {}).get("partition_id"),
    }
    _atomic_write_json(xfer_dir / f"{result.get('tx_id')}.json", record)

    return {
        "ok": True,
        "will_id": will_id,
        "state": "executed",
        "execution": will["execution"],
        "transfer": record,
    }


# ── Transfer adapter ────────────────────────────────────────────


class MemoryMigrationService:
    """Facade used by routes / transfer."""

    def __init__(
        self,
        store: Optional[AgentMemoryStore] = None,
        lifecycle: Optional[AgentMemoryLifecycle] = None,
    ):
        self.store = store or get_memory_store()
        self.lc = lifecycle or AgentMemoryLifecycle(store=self.store)

    def export_v2(self, team_id: str, agent_id: str, **kwargs: Any) -> Dict[str, Any]:
        return build_export_v2(AgentMemoryCore(team_id, agent_id, store=self.store), **kwargs)

    def import_bundle(
        self,
        team_id: str,
        agent_id: str,
        bundle: Dict[str, Any],
        *,
        strategy: str = "merge",
        selected_layers: Optional[Sequence[str]] = None,
        transfer_id: Optional[str] = None,
        fail_after: Optional[Any] = None,
    ) -> Dict[str, Any]:
        core = AgentMemoryCore(team_id, agent_id, store=self.store)
        return import_transaction(
            core,
            bundle,
            strategy=strategy,
            selected_layers=selected_layers,
            transfer_id=transfer_id,
            fail_after=fail_after,
        )

    def create_will(self, team_id: str, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        def exists(bt: str, ba: str) -> bool:
            # unbound still ok; destroyed not ok
            if self.lc.is_tombstoned(bt, ba):
                return False
            return True

        return create_will(
            self.store, team_id, agent_id, payload, beneficiary_exists=exists
        )

    def preflight(self, will_id: str) -> Dict[str, Any]:
        return preflight_will(self.store, will_id)

    def execute(self, will_id: str, **kwargs: Any) -> Dict[str, Any]:
        return execute_will(self.store, will_id, lifecycle=self.lc, **kwargs)

    def transfer_via_will(
        self,
        team_id: str,
        from_agent_id: str,
        to_agent_id: str,
        *,
        handover_intentions: str = "ask_new_owner",
        keep_memorial: bool = True,
        layers: Optional[List[str]] = None,
        strategy: str = "merge",
        note: str = "",
    ) -> Dict[str, Any]:
        will = self.create_will(
            team_id,
            from_agent_id,
            {
                "beneficiary": to_agent_id,
                "strategy": strategy or "merge",
                "layers": layers or list(DEFAULT_TRANSFER_LAYERS),
                "handover_intentions": handover_intentions,
                "keep_memorial": keep_memorial,
                "note": note,
            },
        )
        preflight_will(self.store, will["will_id"])
        result = execute_will(self.store, will["will_id"], lifecycle=self.lc)
        return {
            "ok": True,
            "will": load_will(self.store, will["will_id"]),
            "transfer": result.get("transfer"),
            "execution": result.get("execution"),
            "state": result.get("state"),
        }


_migration: Optional[MemoryMigrationService] = None


def get_memory_migration() -> MemoryMigrationService:
    global _migration
    if _migration is None:
        _migration = MemoryMigrationService()
    return _migration


def list_migration_txs(store: Optional[AgentMemoryStore] = None, limit: int = 30) -> List[Dict[str, Any]]:
    store = store or get_memory_store()
    rows = []
    d = _tx_dir(store)
    for p in sorted(d.glob("mtx_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    # also will_* keyed txs
    for p in sorted(d.glob("will_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows[:limit]


def _inherited_item_relevance(query: str, item: Dict[str, Any]) -> float:
    """Soft relevance for inherited items (aligned with log/semantic recall).

    Full-query substring match is too brittle: chat queries are often Chinese
    titles while inherited events carry ids/tags (e.g. es_scale).
    """
    q = (query or "").strip().lower()
    tags = [str(t) for t in (item.get("tags") or [])]
    text = " ".join(
        str(item.get(key) or "")
        for key in ("action", "detail", "claim", "instruction", "trigger", "subject", "place")
    )
    text_l = f"{text} {' '.join(tags)}".lower()
    if not q:
        return 0.3
    score = 0.0
    if q in text_l:
        score += 1.0
    if any(q == t.lower() or q in t.lower() for t in tags):
        score += 0.5
    # token / CJK-chunk overlap (title vs id/keywords)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", q)
    if tokens:
        hit = 0
        for tok in tokens:
            tl = tok.lower()
            if tl in text_l or any(tl in t.lower() for t in tags):
                hit += 1
        score += 0.45 * (hit / len(tokens))
    if len(q) >= 2:
        qb, tb = _bigrams(q), _bigrams(text_l)
        if qb:
            score += sum(1 for b in qb if b in tb) / len(qb)
    if _vector_lite_enabled():
        score += 0.65 * _hash_cosine(q, text_l)
    return score


def inherited_hits_for_recall(
    store: AgentMemoryStore,
    team_id: str,
    agent_id: str,
    query: str = "",
    *,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """Flatten inherited partitions for recall UI / runtime provenance.

    Uses soft relevance (token/bigram/hash) rather than exact full-query match.
    If query scores nothing but partitions exist, fall back to recent items so
    merge inheritance remains visible in injection.
    """
    inherited = load_inherited(store, team_id, agent_id)
    scored: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    q = (query or "").strip()
    for part in inherited.get("partitions") or []:
        layers = part.get("layers") or {}
        for layer_name in ("log", "semantic", "intentions"):
            items = layers.get(layer_name) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                origin = item.get("origin") or {
                    "kind": "inherited",
                    "source_agent": part.get("source_agent"),
                    "transfer_id": part.get("transfer_id"),
                }
                entry = {
                    "summary": item.get("detail")
                    or item.get("claim")
                    or item.get("instruction")
                    or item.get("action")
                    or "",
                    "layer": layer_name,
                    "origin": origin,
                    "item": item,
                    "score": _inherited_item_relevance(q, item),
                }
                fallback.append(entry)
                if not q or entry["score"] > 0:
                    scored.append(entry)
    pool = scored if scored else fallback
    pool.sort(key=lambda h: float(h.get("score") or 0.0), reverse=True)
    out = []
    for h in pool[: max(1, int(k))]:
        h = dict(h)
        h.pop("score", None)
        out.append(h)
    return out if pool else []
