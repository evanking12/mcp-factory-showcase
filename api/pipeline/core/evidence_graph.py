"""api.pipeline.core.evidence_graph — Shared cross-DLL evidence and dependency graph.

Replaces chained prior_job_id with a durable, queryable store that stages
read from and write to.  Stored as JSON in blob storage, loaded into memory
per campaign.

Data model
----------
- **Entity index**: entity_id -> {type, first_seen_dll, first_seen_job, last_confirmed_job, related_functions[]}
- **Function knowledge**: dll_fingerprint -> function_name -> {canonical_status, working_call, failure_codes, prerequisites[], confidence, last_updated_job}
- **Cross-DLL dependency edges**: producer (dll, fn) -> consumer (dll, fn) with entity_type linkage
- **Vocab union**: merged id_formats, error_codes, init_sequence across DLLs with provenance
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from api.pipeline.core.finding_status import STATUS_ORDER as _STATUS_ORDER

logger = logging.getLogger("mcp_factory.api")

EVIDENCE_GRAPH_VERSION = "1.1"

# Confidence thresholds for cross-DLL edge types
EDGE_CONFIDENCE_VOCAB_OVERLAP = 0.3
EDGE_CONFIDENCE_WORKING_CALL_ENTITY = 0.6
EDGE_CONFIDENCE_VERIFIED_PRODUCER = 0.9
EDGE_CONFIDENCE_ORDERING_THRESHOLD = 0.5

STALE_AFTER_RUNS_DEFAULT = 3


def normalize_entity_id(raw: str) -> str:
    """Normalize an entity ID for consistent graph lookups.

    Strips whitespace, uppercases, and normalizes dashes/underscores to
    prevent CUST-001 vs cust-001 vs CUST_001 from fragmenting edges.
    """
    s = str(raw).strip().upper()
    s = re.sub(r"[\s]+", "", s)
    s = s.replace("_", "-")
    return s


@dataclass
class EntityRecord:
    entity_id: str
    entity_type: str = "unknown"
    first_seen_dll: str = ""
    first_seen_job: str = ""
    last_confirmed_job: str = ""
    related_functions: list[str] = field(default_factory=list)
    confidence: float = 1.0
    campaign_id: str = ""

    def confirm(self, job_id: str, function_name: str = "", campaign_id: str = "") -> None:
        self.last_confirmed_job = job_id
        if campaign_id:
            self.campaign_id = campaign_id
        if function_name and function_name not in self.related_functions:
            self.related_functions.append(function_name)


@dataclass
class FunctionKnowledge:
    function_name: str
    dll_fingerprint: str
    canonical_status: str = "unknown"
    working_call: dict | None = None
    failure_codes: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    confidence: float = 0.0
    last_updated_job: str = ""
    updated_at: float = 0.0
    campaign_id: str = ""
    last_confirmed_at: float = 0.0
    confirmation_count: int = 0

    def update_from_finding(self, finding: dict[str, Any], job_id: str, campaign_id: str = "") -> None:
        status = str(finding.get("status_canonical") or finding.get("status") or "unknown")
        rank_map = dict(_STATUS_ORDER)
        new_rank = rank_map.get(status, 0)
        old_rank = rank_map.get(self.canonical_status, 0)
        if new_rank >= old_rank:
            self.canonical_status = status
            wc = finding.get("working_call")
            if isinstance(wc, dict):
                self.working_call = wc
            max_rank = max(rank_map.values()) if rank_map else 5
            self.confidence = max(self.confidence, new_rank / max_rank if max_rank else 0.0)
        self.last_updated_job = job_id
        self.updated_at = time.time()
        if campaign_id:
            self.campaign_id = campaign_id
        if new_rank >= old_rank and status in ("verified_success", "success"):
            self.last_confirmed_at = time.time()
            self.confirmation_count += 1


@dataclass
class DependencyEdge:
    producer_dll: str
    producer_fn: str
    consumer_dll: str
    consumer_fn: str
    entity_type: str = ""
    evidence_job: str = ""
    confidence: float = 0.5


@dataclass
class VocabEntry:
    key: str
    value: Any = None
    source_dll: str = ""
    source_job: str = ""
    campaign_id: str = ""


@dataclass
class ConflictRecord:
    """Records a conflict between two DLLs' claims about the same entity/function."""
    entity_id: str = ""
    function_name: str = ""
    dll_a: str = ""
    dll_b: str = ""
    a_claim: str = ""
    b_claim: str = ""
    resolution: str = ""
    resolved_by_tier: int = 0
    timestamp: float = field(default_factory=time.time)


class EvidenceGraph:
    """In-memory cross-DLL evidence graph with JSON persistence."""

    def __init__(self) -> None:
        self.version: str = EVIDENCE_GRAPH_VERSION
        self.schema_version: str = "1.0.0"
        self.entities: dict[str, EntityRecord] = {}
        self.functions: dict[str, dict[str, FunctionKnowledge]] = {}
        self.edges: list[DependencyEdge] = []
        self.vocab_union: dict[str, VocabEntry] = {}
        self.conflicts: list[ConflictRecord] = []
        self.created_at: float = time.time()
        self.updated_at: float = time.time()

    # ── Entity index ──────────────────────────────────────────────────────

    def record_entity(
        self,
        entity_id: str,
        *,
        entity_type: str = "unknown",
        dll_fingerprint: str = "",
        job_id: str = "",
        function_name: str = "",
    ) -> EntityRecord:
        entity_id = normalize_entity_id(entity_id)
        if entity_id not in self.entities:
            self.entities[entity_id] = EntityRecord(
                entity_id=entity_id,
                entity_type=entity_type,
                first_seen_dll=dll_fingerprint,
                first_seen_job=job_id,
            )
        rec = self.entities[entity_id]
        rec.confirm(job_id, function_name)
        return rec

    def entities_for_dll(self, dll_fingerprint: str) -> list[EntityRecord]:
        return [
            e for e in self.entities.values()
            if e.first_seen_dll == dll_fingerprint
            or any(dll_fingerprint in fn for fn in e.related_functions)
        ]

    # ── Function knowledge ────────────────────────────────────────────────

    def get_function(self, dll_fingerprint: str, function_name: str) -> FunctionKnowledge | None:
        return self.functions.get(dll_fingerprint, {}).get(function_name)

    def update_function(
        self,
        dll_fingerprint: str,
        function_name: str,
        finding: dict[str, Any],
        job_id: str,
    ) -> FunctionKnowledge:
        dll_fns = self.functions.setdefault(dll_fingerprint, {})
        if function_name not in dll_fns:
            dll_fns[function_name] = FunctionKnowledge(
                function_name=function_name,
                dll_fingerprint=dll_fingerprint,
            )
        fk = dll_fns[function_name]
        fk.update_from_finding(finding, job_id)

        # Extract entity IDs from working_call args and record them
        wc = finding.get("working_call")
        if isinstance(wc, dict):
            _id_re = re.compile(r"[A-Z]{2,}[-_][A-Z0-9]{2,}[-_]?[A-Z0-9]*", re.I)
            for v in wc.values():
                if isinstance(v, str):
                    for m in _id_re.findall(v):
                        self.record_entity(
                            normalize_entity_id(m),
                            dll_fingerprint=dll_fingerprint,
                            job_id=job_id,
                            function_name=function_name,
                        )
        return fk

    def functions_for_dll(self, dll_fingerprint: str) -> dict[str, FunctionKnowledge]:
        return dict(self.functions.get(dll_fingerprint, {}))

    def stale_functions(
        self, dll_fingerprint: str, max_age_sec: float = 86400.0,
        stale_after_runs: int = STALE_AFTER_RUNS_DEFAULT,
    ) -> list[str]:
        """Return function names whose knowledge is stale.

        A function is stale if:
        - It has never been confirmed (last_confirmed_at == 0), OR
        - last_confirmed_at is older than max_age_sec, OR
        - confirmation_count is below stale_after_runs and updated_at is old
        """
        cutoff = time.time() - max_age_sec
        result: list[str] = []
        for fn, fk in self.functions.get(dll_fingerprint, {}).items():
            if fk.last_confirmed_at == 0.0 and fk.updated_at < cutoff:
                result.append(fn)
            elif fk.last_confirmed_at > 0 and fk.last_confirmed_at < cutoff:
                result.append(fn)
            elif fk.confirmation_count < stale_after_runs and fk.updated_at < cutoff:
                result.append(fn)
        return result

    # ── Dependency edges ──────────────────────────────────────────────────

    def add_edge(
        self,
        producer_dll: str,
        producer_fn: str,
        consumer_dll: str,
        consumer_fn: str,
        entity_type: str = "",
        job_id: str = "",
        confidence: float = 0.5,
    ) -> DependencyEdge:
        for e in self.edges:
            if (e.producer_dll == producer_dll and e.producer_fn == producer_fn
                    and e.consumer_dll == consumer_dll and e.consumer_fn == consumer_fn):
                e.confidence = max(e.confidence, confidence)
                e.evidence_job = job_id
                return e
        edge = DependencyEdge(
            producer_dll=producer_dll,
            producer_fn=producer_fn,
            consumer_dll=consumer_dll,
            consumer_fn=consumer_fn,
            entity_type=entity_type,
            evidence_job=job_id,
            confidence=confidence,
        )
        self.edges.append(edge)
        return edge

    def dependencies_for_dll(self, dll_fingerprint: str) -> list[DependencyEdge]:
        """Edges where this DLL is a consumer (its functions depend on other DLLs)."""
        return [e for e in self.edges if e.consumer_dll == dll_fingerprint]

    def dependents_of_dll(self, dll_fingerprint: str) -> list[DependencyEdge]:
        """Edges where this DLL is a producer (other DLLs depend on it)."""
        return [e for e in self.edges if e.producer_dll == dll_fingerprint]

    def topological_dll_order(self) -> list[str]:
        """DAG sort of DLLs by dependency edges. Raises ValueError on cycle."""
        dlls: set[str] = set()
        for e in self.edges:
            dlls.add(e.producer_dll)
            dlls.add(e.consumer_dll)
        for dll_fp in self.functions:
            dlls.add(dll_fp)

        adj: dict[str, set[str]] = {d: set() for d in dlls}
        in_degree: dict[str, int] = {d: 0 for d in dlls}
        for e in self.edges:
            if e.producer_dll != e.consumer_dll:
                if e.consumer_dll not in adj[e.producer_dll]:
                    adj[e.producer_dll].add(e.consumer_dll)
                    in_degree[e.consumer_dll] += 1

        queue = [d for d in dlls if in_degree[d] == 0]
        order: list[str] = []
        while queue:
            queue.sort()
            node = queue.pop(0)
            order.append(node)
            for nbr in sorted(adj[node]):
                in_degree[nbr] -= 1
                if in_degree[nbr] == 0:
                    queue.append(nbr)
        if len(order) != len(dlls):
            raise ValueError("Cycle detected in DLL dependency graph")
        return order

    # ── Vocab union ───────────────────────────────────────────────────────

    def merge_vocab(self, vocab: dict[str, Any], dll_fingerprint: str, job_id: str) -> None:
        for key, value in vocab.items():
            if key.startswith("_"):
                continue
            existing = self.vocab_union.get(key)
            if existing is None:
                self.vocab_union[key] = VocabEntry(key=key, value=value, source_dll=dll_fingerprint, source_job=job_id)
            elif key == "id_formats" and isinstance(value, list) and isinstance(existing.value, list):
                merged = list(existing.value)
                for v in value:
                    if v not in merged:
                        merged.append(v)
                existing.value = merged
            elif key == "error_codes" and isinstance(value, dict) and isinstance(existing.value, dict):
                existing.value = {**existing.value, **value}

    def vocab_slice_for_dll(self, dll_fingerprint: str) -> dict[str, Any]:
        """Return the subset of unified vocab relevant to a DLL (currently: all)."""
        return {k: ve.value for k, ve in self.vocab_union.items()}

    # ── Context slice for a specific DLL run ──────────────────────────────

    def context_slice(self, dll_fingerprint: str) -> dict[str, Any]:
        """Produce the evidence-graph context slice a DLL run should start from."""
        entities = [asdict(e) for e in self.entities_for_dll(dll_fingerprint)]
        known_fns = {
            fn: {
                "canonical_status": fk.canonical_status,
                "working_call": fk.working_call,
                "prerequisites": fk.prerequisites,
                "confidence": fk.confidence,
            }
            for fn, fk in self.functions_for_dll(dll_fingerprint).items()
        }
        deps = [asdict(e) for e in self.dependencies_for_dll(dll_fingerprint)]
        vocab = self.vocab_slice_for_dll(dll_fingerprint)
        return {
            "entities": entities,
            "known_functions": known_fns,
            "dependencies": deps,
            "vocab": vocab,
        }

    # ── Persistence ───────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        self.updated_at = time.time()
        return {
            "version": self.version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entities": {eid: asdict(er) for eid, er in self.entities.items()},
            "functions": {
                dll_fp: {fn: asdict(fk) for fn, fk in fns.items()}
                for dll_fp, fns in self.functions.items()
            },
            "edges": [asdict(e) for e in self.edges],
            "vocab_union": {k: asdict(ve) for k, ve in self.vocab_union.items()},
            "conflicts": [asdict(c) for c in self.conflicts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceGraph":
        g = cls()
        g.version = data.get("version", EVIDENCE_GRAPH_VERSION)
        g.schema_version = data.get("schema_version", "1.0.0")
        g.created_at = data.get("created_at", time.time())
        g.updated_at = data.get("updated_at", time.time())

        for eid, edata in data.get("entities", {}).items():
            g.entities[eid] = EntityRecord(
                entity_id=edata.get("entity_id", eid),
                entity_type=edata.get("entity_type", "unknown"),
                first_seen_dll=edata.get("first_seen_dll", ""),
                first_seen_job=edata.get("first_seen_job", ""),
                last_confirmed_job=edata.get("last_confirmed_job", ""),
                related_functions=list(edata.get("related_functions", [])),
                confidence=float(edata.get("confidence", 1.0)),
                campaign_id=edata.get("campaign_id", ""),
            )

        for dll_fp, fns in data.get("functions", {}).items():
            g.functions[dll_fp] = {}
            for fn, fdata in fns.items():
                g.functions[dll_fp][fn] = FunctionKnowledge(
                    function_name=fdata.get("function_name", fn),
                    dll_fingerprint=fdata.get("dll_fingerprint", dll_fp),
                    canonical_status=fdata.get("canonical_status", "unknown"),
                    working_call=fdata.get("working_call"),
                    failure_codes=list(fdata.get("failure_codes", [])),
                    prerequisites=list(fdata.get("prerequisites", [])),
                    confidence=float(fdata.get("confidence", 0.0)),
                    last_updated_job=fdata.get("last_updated_job", ""),
                    updated_at=float(fdata.get("updated_at", 0.0)),
                    campaign_id=fdata.get("campaign_id", ""),
                    last_confirmed_at=float(fdata.get("last_confirmed_at", 0.0)),
                    confirmation_count=int(fdata.get("confirmation_count", 0)),
                )

        for edata in data.get("edges", []):
            g.edges.append(DependencyEdge(
                producer_dll=edata.get("producer_dll", ""),
                producer_fn=edata.get("producer_fn", ""),
                consumer_dll=edata.get("consumer_dll", ""),
                consumer_fn=edata.get("consumer_fn", ""),
                entity_type=edata.get("entity_type", ""),
                evidence_job=edata.get("evidence_job", ""),
                confidence=float(edata.get("confidence", 0.5)),
            ))

        for k, vedata in data.get("vocab_union", {}).items():
            g.vocab_union[k] = VocabEntry(
                key=vedata.get("key", k),
                value=vedata.get("value"),
                source_dll=vedata.get("source_dll", ""),
                source_job=vedata.get("source_job", ""),
                campaign_id=vedata.get("campaign_id", ""),
            )

        for cdata in data.get("conflicts", []):
            g.conflicts.append(ConflictRecord(
                entity_id=cdata.get("entity_id", ""),
                function_name=cdata.get("function_name", ""),
                dll_a=cdata.get("dll_a", ""),
                dll_b=cdata.get("dll_b", ""),
                a_claim=cdata.get("a_claim", ""),
                b_claim=cdata.get("b_claim", ""),
                resolution=cdata.get("resolution", ""),
                resolved_by_tier=int(cdata.get("resolved_by_tier", 0)),
                timestamp=float(cdata.get("timestamp", 0.0)),
            ))

        return g

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "EvidenceGraph":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            logger.warning("evidence_graph: failed to load from %s, starting fresh", path)
            return cls()

    def save_blob(self, container: str, blob_path: str = "evidence_graph.json") -> None:
        from api.infra.storage import _upload_to_blob
        _upload_to_blob(container, blob_path, json.dumps(self.to_dict(), indent=2).encode())
        logger.info("evidence_graph: saved to blob %s/%s", container, blob_path)

    @classmethod
    def load_blob(cls, container: str, blob_path: str = "evidence_graph.json") -> "EvidenceGraph":
        from api.infra.storage import _download_blob
        try:
            raw = _download_blob(container, blob_path)
            data = json.loads(raw)
            logger.info("evidence_graph: loaded from blob %s/%s", container, blob_path)
            return cls.from_dict(data)
        except Exception:
            logger.debug("evidence_graph: no existing graph at %s/%s", container, blob_path)
            return cls()

    # ── Ingestion helpers ─────────────────────────────────────────────────

    def ingest_findings(
        self,
        dll_fingerprint: str,
        findings: list[dict[str, Any]],
        job_id: str,
    ) -> int:
        """Bulk-ingest findings from a completed run. Returns count of updates."""
        updated = 0
        for f in findings:
            fn = str(f.get("function") or "").strip()
            if not fn:
                continue
            self.update_function(dll_fingerprint, fn, f, job_id)
            updated += 1
        return updated

    def ingest_invocables(
        self,
        dll_fingerprint: str,
        invocables: dict[str, Any] | list[dict[str, Any]],
        job_id: str,
    ) -> int:
        """Extract depends_on edges from invocable metadata."""
        edge_count = 0
        items = invocables.values() if isinstance(invocables, dict) else invocables
        for inv in items:
            if not isinstance(inv, dict):
                continue
            fn = str(inv.get("name") or "").strip()
            deps = inv.get("depends_on") or []
            if not isinstance(deps, list):
                continue
            for dep_fn in deps:
                if isinstance(dep_fn, str) and dep_fn.strip():
                    self.add_edge(
                        producer_dll=dll_fingerprint,
                        producer_fn=dep_fn.strip(),
                        consumer_dll=dll_fingerprint,
                        consumer_fn=fn,
                        entity_type="intra_dll_dependency",
                        job_id=job_id,
                    )
                    edge_count += 1
        return edge_count

    def detect_cross_dll_edges(self) -> list[DependencyEdge]:
        """Detect cross-DLL dependencies by entity ID overlap in working_calls.

        Confidence tiers:
        - EDGE_CONFIDENCE_VOCAB_OVERLAP (0.3): string overlap in vocab only
        - EDGE_CONFIDENCE_WORKING_CALL_ENTITY (0.6): shared entity in working_call args
        - EDGE_CONFIDENCE_VERIFIED_PRODUCER (0.9): producer verified + consumer uses returned handle
        """
        new_edges: list[DependencyEdge] = []
        entity_producers: dict[str, list[tuple[str, str]]] = {}
        entity_consumers: dict[str, list[tuple[str, str]]] = {}

        for dll_fp, fns in self.functions.items():
            for fn, fk in fns.items():
                if not fk.working_call:
                    continue
                for v in fk.working_call.values():
                    if not isinstance(v, str):
                        continue
                    norm_v = normalize_entity_id(v)
                    for eid, er in self.entities.items():
                        if eid in norm_v or eid in v.upper():
                            if er.first_seen_dll == dll_fp:
                                entity_producers.setdefault(eid, []).append((dll_fp, fn))
                            else:
                                entity_consumers.setdefault(eid, []).append((dll_fp, fn))

        for eid in set(entity_producers) & set(entity_consumers):
            for prod_dll, prod_fn in entity_producers[eid]:
                for cons_dll, cons_fn in entity_consumers[eid]:
                    if prod_dll == cons_dll:
                        continue
                    # Determine confidence based on evidence quality
                    prod_fk = self.get_function(prod_dll, prod_fn)
                    if prod_fk and prod_fk.canonical_status in ("verified_success", "success"):
                        conf = EDGE_CONFIDENCE_VERIFIED_PRODUCER
                    else:
                        conf = EDGE_CONFIDENCE_WORKING_CALL_ENTITY
                    edge = self.add_edge(
                        producer_dll=prod_dll,
                        producer_fn=prod_fn,
                        consumer_dll=cons_dll,
                        consumer_fn=cons_fn,
                        entity_type=eid,
                        confidence=conf,
                    )
                    new_edges.append(edge)

        return new_edges

    def record_conflict(
        self,
        entity_id: str = "",
        function_name: str = "",
        dll_a: str = "",
        dll_b: str = "",
        a_claim: str = "",
        b_claim: str = "",
        resolution: str = "",
        resolved_by_tier: int = 0,
    ) -> ConflictRecord:
        """Record an evidence conflict between two DLLs for audit."""
        cr = ConflictRecord(
            entity_id=entity_id,
            function_name=function_name,
            dll_a=dll_a,
            dll_b=dll_b,
            a_claim=a_claim,
            b_claim=b_claim,
            resolution=resolution,
            resolved_by_tier=resolved_by_tier,
        )
        self.conflicts.append(cr)
        logger.warning(
            "evidence_graph: conflict on %s between %s and %s — %s vs %s → %s",
            entity_id or function_name, dll_a, dll_b, a_claim, b_claim, resolution,
        )
        return cr

    def re_probe_recommendations(self, dll_fingerprint: str) -> list[dict[str, Any]]:
        """Functions in this DLL that should be re-probed based on cross-DLL evidence."""
        recs: list[dict[str, Any]] = []
        for edge in self.dependencies_for_dll(dll_fingerprint):
            producer_fk = self.get_function(edge.producer_dll, edge.producer_fn)
            if producer_fk and producer_fk.canonical_status in ("verified_success", "inferred_success"):
                consumer_fk = self.get_function(dll_fingerprint, edge.consumer_fn)
                if consumer_fk and consumer_fk.canonical_status in ("failure", "unknown"):
                    recs.append({
                        "function": edge.consumer_fn,
                        "reason": f"prerequisite {edge.producer_fn} in {edge.producer_dll} now {producer_fk.canonical_status}",
                        "producer_working_call": producer_fk.working_call,
                    })
        return recs
