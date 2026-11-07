"""api.pipeline.checkpoint – Checkpoint system for resumable pipeline runs.

Saves, loads, and merges per-stage checkpoint data so that:
  1. Verified findings are "locked in" and skipped in subsequent runs
  2. Pipeline can resume from any stage boundary
  3. Focused runs target only failing functions
  4. Development iteration is fast (skip S-00/S-01 when sentinels are stable)

Storage layout:
  {job_id}/checkpoints/latest.json       — full pipeline checkpoint
  {job_id}/checkpoints/s{NN}_{name}.json — per-stage checkpoint
  {job_id}/checkpoints/functions/{fn}.json — per-function checkpoint (S-02)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _upload_to_blob, _download_blob
from api.pipeline.core.cluster_checkpoint import (
    CLUSTER_CHECKPOINTS_BY_ID,
    CLUSTER_CHECKPOINT_SCHEMA_VERSION,
    backfill_cluster_checkpoint_rows,
)
from api.pipeline.core.prerequisite_state_groups import (
    backfill_prerequisite_state_group_rows,
)
from api.pipeline.core.reusable_truth import assess_reusable_truth

logger = logging.getLogger("mcp_factory.api")

_RESUME_STAGE_ORDER = [
    "s00_setup",
    "s00_setup_baseline",
    "s00_static_evidence",
    "s00_admission_handoff",
    "s01_unlock",
    "s02_probe",
    "s02_probe_ordering",
    "s02_invocation_execution",
    "s02_evidence_capture",
    "s03_reconcile",
    "s04_synthesis",
    "s05_enrichment",
    "s05_schema_backfill",
    "s05_verification_replay",
    "s05_read_to_write_chaining",
    "s06_gaps",
    "s07_finalize",
]


@dataclass
class FunctionCheckpoint:
    """Per-function checkpoint data from the probe loop."""
    name: str
    status: str  # "success", "error", "skipped"
    working_call: dict | None = None
    finding: str = ""
    verified: bool = False
    stage: str = "s02"
    timestamp: float = 0.0

    def is_skippable(self) -> bool:
        """True if this function can be safely skipped in subsequent runs."""
        return self.status in {"success", "verified_success"} and self.working_call is not None


@dataclass
class StageCheckpoint:
    """Per-stage checkpoint data."""
    stage_id: str  # e.g. "s00_setup"
    completed: bool = False
    timestamp: float = 0.0
    data: dict = field(default_factory=dict)


@dataclass
class PipelineCheckpoint:
    """Full pipeline checkpoint — aggregates all stage and function checkpoints."""
    job_id: str
    source_job_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Per-stage data
    stages: dict[str, StageCheckpoint] = field(default_factory=dict)

    # Per-function data (from S-02 probe loop)
    functions: dict[str, FunctionCheckpoint] = field(default_factory=dict)

    # Accumulated pipeline context
    sentinels: dict = field(default_factory=dict)
    vocab: dict = field(default_factory=dict)
    unlock_result: dict = field(default_factory=dict)
    write_unlock_block: str = ""
    winning_init_sequence: list = field(default_factory=list)
    dll_strings: dict = field(default_factory=dict)
    static_hints_block: str = ""
    static_analysis_result: dict = field(default_factory=dict)
    static_enrichment: dict = field(default_factory=dict)
    call_graph: dict = field(default_factory=dict)
    ghidra_data_types: list = field(default_factory=list)

    # Cross-DLL shared context keyed by dll_fingerprint
    cross_dll_context: dict = field(default_factory=dict)

    # Evidence candidate registry snapshot (progressive specialization)
    evidence_candidates_snapshot: dict = field(default_factory=dict)

    # Lower-than-stage cluster checkpoints for semantically coherent rerun units
    cluster_checkpoints: dict = field(default_factory=dict)
    prerequisite_state_groups: dict = field(default_factory=dict)

    def skippable_functions(self) -> set[str]:
        """Return set of function names that can be skipped."""
        return {
            name for name, fc in self.functions.items()
            if fc.is_skippable()
        }

    def success_count(self) -> int:
        return sum(1 for fc in self.functions.values() if fc.status == "success")

    def total_count(self) -> int:
        return len(self.functions)


@dataclass(frozen=True)
class ClusterSeedPlan:
    """Validated bounded-rerun seed plan derived from a saved cluster checkpoint."""
    cluster_id: str
    adjacent_cluster_id: str = ""
    focus_functions: tuple[str, ...] = ()
    seed_functions: tuple[str, ...] = ()
    allowed_artifact_families: tuple[str, ...] = ()
    lineage_sources: tuple[str, ...] = ()
    reuse_eligibility: tuple[str, ...] = ()
    confidence: float = 0.0
    source_job_id: str = ""
    schema_version: str = CLUSTER_CHECKPOINT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "adjacent_cluster_id": self.adjacent_cluster_id,
            "focus_functions": list(self.focus_functions),
            "seed_functions": list(self.seed_functions),
            "allowed_artifact_families": list(self.allowed_artifact_families),
            "lineage_sources": list(self.lineage_sources),
            "reuse_eligibility": list(self.reuse_eligibility),
            "confidence": self.confidence,
            "source_job_id": self.source_job_id,
            "schema_version": self.schema_version,
        }


@dataclass
class CampaignCheckpoint:
    """Campaign-level checkpoint for multi-DLL campaigns.

    Resume points:
    - discovery_complete: all _analyze_worker calls finished
    - plan_built: campaign_plan.json and evidence_graph.json persisted
    - dll_explore_complete:{dll_id}: per-DLL explore finished
    - consolidation_complete: run_s_post finished
    """
    campaign_id: str
    phase: str = ""
    completed_dll_ids: list[str] = field(default_factory=list)
    evidence_graph_epoch: str = ""
    resume_points: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    schema_version: str = "1.0.0"

    def mark_resume_point(self, point: str) -> None:
        if point not in self.resume_points:
            self.resume_points.append(point)
        self.updated_at = time.time()

    def has_resume_point(self, point: str) -> bool:
        return point in self.resume_points

    def is_dll_complete(self, dll_id: str) -> bool:
        return dll_id in self.completed_dll_ids

    def mark_dll_complete(self, dll_id: str) -> None:
        if dll_id not in self.completed_dll_ids:
            self.completed_dll_ids.append(dll_id)
        self.mark_resume_point(f"dll_explore_complete:{dll_id}")

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "phase": self.phase,
            "completed_dll_ids": self.completed_dll_ids,
            "evidence_graph_epoch": self.evidence_graph_epoch,
            "resume_points": self.resume_points,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CampaignCheckpoint":
        return cls(
            campaign_id=d.get("campaign_id", ""),
            phase=d.get("phase", ""),
            completed_dll_ids=list(d.get("completed_dll_ids", [])),
            evidence_graph_epoch=d.get("evidence_graph_epoch", ""),
            resume_points=list(d.get("resume_points", [])),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            schema_version=d.get("schema_version", "1.0.0"),
        )


def save_campaign_checkpoint(ckpt: CampaignCheckpoint) -> str:
    """Save campaign checkpoint to blob storage."""
    ckpt.updated_at = time.time()
    blob_path = f"campaigns/{ckpt.campaign_id}/campaign_checkpoint.json"
    _upload_to_blob(ARTIFACT_CONTAINER, blob_path, json.dumps(ckpt.to_dict(), indent=2).encode())
    return blob_path


def load_campaign_checkpoint(campaign_id: str) -> CampaignCheckpoint | None:
    """Load campaign checkpoint from blob storage, or return None if not found."""
    blob_path = f"campaigns/{campaign_id}/campaign_checkpoint.json"
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, blob_path)
        return CampaignCheckpoint.from_dict(json.loads(raw))
    except Exception:
        return None


def save_checkpoint(checkpoint: PipelineCheckpoint, *, write_stage_snapshots: bool = True) -> str:
    """Save checkpoint to blob storage. Returns the blob path."""
    checkpoint.updated_at = time.time()
    blob_path = f"{checkpoint.job_id}/checkpoints/latest.json"
    checkpoint.cluster_checkpoints = backfill_cluster_checkpoint_rows(
        checkpoint.cluster_checkpoints,
        function_states=checkpoint.functions,
        source_job_id=checkpoint.source_job_id or checkpoint.job_id,
    )
    checkpoint.prerequisite_state_groups = backfill_prerequisite_state_group_rows(
        checkpoint.prerequisite_state_groups,
        function_states=checkpoint.functions,
        source_job_id=checkpoint.source_job_id or checkpoint.job_id,
    )

    data = {
        "job_id": checkpoint.job_id,
        "source_job_id": checkpoint.source_job_id,
        "created_at": checkpoint.created_at,
        "updated_at": checkpoint.updated_at,
        "sentinels": {
            (f"0x{k:08X}" if isinstance(k, int) else str(k)): v
            for k, v in checkpoint.sentinels.items()
        },
        "vocab": checkpoint.vocab,
        "unlock_result": checkpoint.unlock_result,
        "write_unlock_block": checkpoint.write_unlock_block,
        "winning_init_sequence": checkpoint.winning_init_sequence,
        "dll_strings": checkpoint.dll_strings,
        "static_hints_block": checkpoint.static_hints_block,
        "static_analysis_result": checkpoint.static_analysis_result,
        "static_enrichment": checkpoint.static_enrichment,
        "call_graph": checkpoint.call_graph,
        "ghidra_data_types": checkpoint.ghidra_data_types,
        "cross_dll_context": checkpoint.cross_dll_context,
        "evidence_candidates": checkpoint.evidence_candidates_snapshot,
        "cluster_checkpoints": checkpoint.cluster_checkpoints,
        "prerequisite_state_groups": checkpoint.prerequisite_state_groups,
        "stages": {
            sid: {
                "stage_id": sc.stage_id,
                "completed": sc.completed,
                "timestamp": sc.timestamp,
                "data": sc.data,
            }
            for sid, sc in checkpoint.stages.items()
        },
        "functions": {
            name: {
                "name": fc.name,
                "status": fc.status,
                "working_call": fc.working_call,
                "finding": fc.finding,
                "verified": fc.verified,
                "stage": fc.stage,
                "timestamp": fc.timestamp,
            }
            for name, fc in checkpoint.functions.items()
        },
    }

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER, blob_path,
            json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        logger.info("[%s] checkpoint saved: %d functions, %d stages",
                     checkpoint.job_id, len(checkpoint.functions), len(checkpoint.stages))
    except Exception as exc:
        logger.warning("[%s] checkpoint save failed: %s", checkpoint.job_id, exc)

    # Also save per-stage checkpoints
    for sid, sc in checkpoint.stages.items():
        try:
            stage_blob = f"{checkpoint.job_id}/checkpoints/{sid}.json"
            _upload_to_blob(
                ARTIFACT_CONTAINER, stage_blob,
                json.dumps(asdict(sc), indent=2).encode("utf-8"),
            )
            if write_stage_snapshots:
                stage_snapshot_blob = f"{checkpoint.job_id}/checkpoints/stage_snapshots/{sid}.json"
                try:
                    _download_blob(ARTIFACT_CONTAINER, stage_snapshot_blob)
                except Exception:
                    stage_snapshot = dict(data)
                    stage_snapshot["checkpoint_kind"] = "pipeline_stage_snapshot"
                    stage_snapshot["stage_snapshot_id"] = sid
                    stage_snapshot["stage_snapshot"] = asdict(sc)
                    _upload_to_blob(
                        ARTIFACT_CONTAINER,
                        stage_snapshot_blob,
                        json.dumps(stage_snapshot, indent=2, ensure_ascii=False).encode("utf-8"),
                    )
        except Exception:
            pass

    return blob_path


def load_checkpoint(
    job_id: str,
    checkpoint_id: str = "",
    checkpoint_stage: str = "",
) -> PipelineCheckpoint | None:
    """Load checkpoint from blob storage.

    If checkpoint_id is empty, loads from the job's own latest checkpoint.
    If checkpoint_id is another job_id, loads that job's checkpoint (cross-job seeding).
    """
    source_id = checkpoint_id or job_id
    stage_id = str(checkpoint_stage or "").strip()
    if stage_id:
        blob_path = f"{source_id}/checkpoints/stage_snapshots/{stage_id}.json"
    else:
        blob_path = f"{source_id}/checkpoints/latest.json"

    try:
        raw = _download_blob(ARTIFACT_CONTAINER, blob_path)
        data = json.loads(raw)
    except Exception:
        logger.debug("[%s] no checkpoint found at %s", job_id, blob_path)
        return None

    cp = PipelineCheckpoint(
        job_id=job_id,
        source_job_id=data.get("source_job_id") or source_id,
        created_at=data.get("created_at", 0),
        updated_at=data.get("updated_at", 0),
        vocab=data.get("vocab", {}),
        unlock_result=data.get("unlock_result", {}),
        write_unlock_block=data.get("write_unlock_block", ""),
        winning_init_sequence=data.get("winning_init_sequence", []),
        dll_strings=data.get("dll_strings", {}),
        static_hints_block=data.get("static_hints_block", ""),
        static_analysis_result=data.get("static_analysis_result", {}),
        static_enrichment=data.get("static_enrichment", {}),
        call_graph=data.get("call_graph", {}),
        ghidra_data_types=data.get("ghidra_data_types", []),
        cross_dll_context=data.get("cross_dll_context", {}),
        evidence_candidates_snapshot=data.get("evidence_candidates", {}),
        cluster_checkpoints={},
        prerequisite_state_groups={},
    )

    # Restore sentinels (stored as hex string keys)
    for k, v in data.get("sentinels", {}).items():
        try:
            int_key = int(k, 16) if isinstance(k, str) and k.startswith("0x") else int(k)
            cp.sentinels[int_key] = v
        except (ValueError, TypeError):
            pass

    # Restore stage checkpoints
    for sid, sdata in data.get("stages", {}).items():
        cp.stages[sid] = StageCheckpoint(
            stage_id=sdata.get("stage_id", sid),
            completed=sdata.get("completed", False),
            timestamp=sdata.get("timestamp", 0),
            data=sdata.get("data", {}),
        )

    # Restore function checkpoints
    for name, fdata in data.get("functions", {}).items():
        cp.functions[name] = FunctionCheckpoint(
            name=fdata.get("name", name),
            status=fdata.get("status", "unknown"),
            working_call=fdata.get("working_call"),
            finding=fdata.get("finding", ""),
            verified=fdata.get("verified", False),
            stage=fdata.get("stage", "s02"),
            timestamp=fdata.get("timestamp", 0),
        )

    cp.cluster_checkpoints = backfill_cluster_checkpoint_rows(
        data.get("cluster_checkpoints"),
        function_states=cp.functions,
        source_job_id=cp.source_job_id or source_id,
    )
    cp.prerequisite_state_groups = backfill_prerequisite_state_group_rows(
        data.get("prerequisite_state_groups"),
        function_states=cp.functions,
        source_job_id=cp.source_job_id or source_id,
    )

    cp = apply_resume_boundary(cp, stage_id)
    logger.info("[%s] checkpoint loaded from %s: %d functions (%d skippable), %d stages",
                job_id, source_id, len(cp.functions), len(cp.skippable_functions()), len(cp.stages))
    return cp


def apply_resume_boundary(
    checkpoint: PipelineCheckpoint | None,
    checkpoint_stage: str = "",
) -> PipelineCheckpoint | None:
    """Clear completion markers at and after a loaded resume boundary.

    Stage snapshots are archival boundaries. When a run loads `s02_probe`, that
    snapshot should seed the run with state through S-02, but S-02 itself must
    still be eligible to rerun on the new job when the caller wants a real
    replay-backed probe surface.
    """
    if checkpoint is None:
        return None

    stage_id = str(checkpoint_stage or "").strip()
    if not stage_id:
        return checkpoint

    try:
        boundary_idx = _RESUME_STAGE_ORDER.index(stage_id)
    except ValueError:
        return checkpoint

    for sid in _RESUME_STAGE_ORDER[boundary_idx:]:
        checkpoint.stages.pop(sid, None)

    return checkpoint


def seed_context_from_checkpoint(
    ctx,
    checkpoint: PipelineCheckpoint,
    cluster_seed_plan: ClusterSeedPlan | None = None,
    seed_function_allowlist: set[str] | None = None,
) -> int:
    """Seed an ExploreContext with checkpoint data.

    Returns the number of findings seeded.
    """
    from api.infra.storage import _load_findings
    from api.pipeline.core.finding_status import STATUS_ORDER, normalize_status

    seeded = 0
    bounded_seed_functions = (
        {name for name in (cluster_seed_plan.seed_functions or ()) if str(name).strip()}
        if cluster_seed_plan is not None
        else None
    )
    if seed_function_allowlist is not None:
        allowlist = {
            str(name).strip()
            for name in seed_function_allowlist
            if str(name).strip()
        }
        if bounded_seed_functions is None:
            bounded_seed_functions = allowlist
        else:
            bounded_seed_functions = bounded_seed_functions & allowlist

    if checkpoint.sentinels:
        ctx.sentinels = dict(checkpoint.sentinels)

    if checkpoint.vocab:
        ctx.vocab = dict(checkpoint.vocab)

    if checkpoint.unlock_result:
        ctx.unlock_result = dict(checkpoint.unlock_result)

    if checkpoint.write_unlock_block and "ACTIVE" in checkpoint.write_unlock_block:
        ctx.write_unlock_block = checkpoint.write_unlock_block
        # Enrich with actual init+unlock call sequences from prior findings
        try:
            import re as _re
            from api.infra.storage import _load_findings
            _src = checkpoint.source_job_id or checkpoint.job_id
            _prior = _load_findings(_src)
            _seq_parts = []
            for _f in (_prior if isinstance(_prior, list) else []):
                _fn = _f.get("function", "")
                _wc = _f.get("working_call")
                if _f.get("status") != "success" or not _wc:
                    continue
                if _re.search(r"init(ializ)?|unlock", _fn, _re.I):
                    _seq_parts.append(f"{_fn}({_wc})")
            if _seq_parts:
                ctx.write_unlock_block += (
                    f"\nEXACT PREREQUISITE CALLS: {' -> '.join(_seq_parts)}. "
                    "Use these EXACT argument values (the unlock code is cryptographic).\n"
                )
                logger.info("[%s] enriched write_unlock_block with prior findings: %s",
                            ctx.job_id, _seq_parts)
        except Exception as _enrich_err:
            logger.warning("[%s] write_unlock_block enrichment failed: %s", ctx.job_id, _enrich_err)
        logger.info("[%s] loaded write_unlock_block from checkpoint (ACTIVE): %.200s",
                    ctx.job_id, ctx.write_unlock_block.replace('\n', ' ')[:200])
    elif checkpoint.write_unlock_block:
        logger.info("[%s] discarding stale write_unlock_block (not ACTIVE): %.120s",
                    ctx.job_id, checkpoint.write_unlock_block.replace('\n', ' ')[:120])

    # If no write_unlock_block but checkpoint has a successful unlock function,
    # reconstruct the block so write functions know the init+unlock sequence.
    if not ctx.write_unlock_block and checkpoint.unlock_result.get("unlocked"):
        _seq = checkpoint.unlock_result.get("sequence", [])
        if _seq:
            _steps = " -> ".join(
                f"{s.get('fn', '?')}({s.get('args', {})})" for s in _seq
            )
            ctx.write_unlock_block = (
                f"\nWRITE MODE ACTIVE (from checkpoint): "
                f"Call this sequence BEFORE any write function: {_steps}. "
                "Write functions should succeed after this sequence. "
                "Probe with real ID values from STATIC ANALYSIS HINTS.\n"
            )
            logger.info("[%s] reconstructed write_unlock_block from checkpoint unlock_result",
                        ctx.job_id)

    # Also reconstruct from successful unlock-like functions in checkpoint
    if not ctx.write_unlock_block:
        import re as _re
        _init_fns = []
        _unlock_fns = []
        for _fn, _fc in checkpoint.functions.items():
            if _fc.status == "success" and _fc.working_call is not None:
                if _re.search(r"init(ializ)?", _fn, _re.I):
                    _init_fns.append((_fn, _fc.working_call))
                elif _re.search(r"unlock", _fn, _re.I):
                    _unlock_fns.append((_fn, _fc.working_call))
        if _init_fns or _unlock_fns:
            _steps = []
            for _fn, _wc in _init_fns:
                _steps.append(f"{_fn}({_wc})")
            for _fn, _wc in _unlock_fns:
                _steps.append(f"{_fn}({_wc})")
            if _steps:
                ctx.write_unlock_block = (
                    f"\nWRITE MODE: Call this prerequisite sequence BEFORE any write function: "
                    f"{' -> '.join(_steps)}. "
                    "After calling these, write functions should succeed. "
                    "Use real ID values from STATIC ANALYSIS HINTS.\n"
                )
                logger.info("[%s] reconstructed write_unlock_block from checkpoint functions: %s",
                            ctx.job_id, _steps)

    logger.info("[%s] write_unlock_block after checkpoint seeding: len=%d, preview=%.100s",
                ctx.job_id, len(ctx.write_unlock_block), ctx.write_unlock_block[:100] if ctx.write_unlock_block else "(empty)")

    # Last resort: try loading findings from the checkpoint source job
    if not ctx.write_unlock_block:
        _src = checkpoint.source_job_id or checkpoint.job_id
        logger.info("[%s] attempting write_unlock_block reconstruction from findings of %s",
                    ctx.job_id, _src)
        try:
            import re as _re
            from api.infra.storage import _load_findings
            _prior = _load_findings(_src)
            logger.info("[%s] loaded %d prior findings from %s (type=%s)",
                        ctx.job_id, len(_prior) if isinstance(_prior, list) else -1,
                        _src, type(_prior).__name__)
            _init_fns = []
            _unlock_fns = []
            for _f in (_prior if isinstance(_prior, list) else []):
                _fn = _f.get("function", "")
                _wc = _f.get("working_call")
                if _f.get("status") != "success" or not _wc:
                    continue
                if _re.search(r"init(ializ)?", _fn, _re.I):
                    _init_fns.append((_fn, _wc))
                elif _re.search(r"unlock", _fn, _re.I):
                    _unlock_fns.append((_fn, _wc))
            if _init_fns or _unlock_fns:
                _steps = []
                for _fn, _wc in _init_fns:
                    _steps.append(f"{_fn}({_wc})")
                for _fn, _wc in _unlock_fns:
                    _steps.append(f"{_fn}({_wc})")
                if _steps:
                    ctx.write_unlock_block = (
                        f"\nWRITE MODE ACTIVE (from prior findings): "
                        f"Call this EXACT sequence BEFORE any write function: {' -> '.join(_steps)}. "
                        "Use these EXACT argument values — the unlock code is cryptographic. "
                        "After this sequence, write functions should succeed.\n"
                    )
                    logger.info("[%s] reconstructed write_unlock_block from prior findings: %s",
                                ctx.job_id, _steps)
        except Exception as _e:
            logger.warning("[%s] could not load prior findings for write_unlock_block: %s",
                           ctx.job_id, _e)

    # Merge cross-DLL shared vocab when entity overlap is detected
    if checkpoint.cross_dll_context:
        _current_id_formats = set()
        for fmt in (ctx.vocab.get("id_formats") or []):
            if isinstance(fmt, str):
                _current_id_formats.add(fmt.strip().lower())
        for _dll_fp, _xctx in checkpoint.cross_dll_context.items():
            if not isinstance(_xctx, dict):
                continue
            _overlap = _xctx.get("entity_overlap") or []
            _shared_keys = _xctx.get("shared_vocab_keys") or []
            if _overlap or (_current_id_formats and _shared_keys):
                for _vk in _shared_keys:
                    if _vk in ("id_formats", "error_codes", "notes"):
                        _xval = _xctx.get(f"vocab_{_vk}")
                        if _xval and _vk not in ctx.vocab:
                            ctx.vocab[_vk] = _xval
                _xsentinels = _xctx.get("shared_sentinels") or {}
                for _sk, _sv in _xsentinels.items():
                    try:
                        _int_key = int(_sk, 16) if isinstance(_sk, str) and _sk.startswith("0x") else int(_sk)
                        if _int_key not in ctx.sentinels:
                            ctx.sentinels[_int_key] = _sv
                    except (ValueError, TypeError):
                        pass
                logger.info("[%s] merged cross-DLL context from %s: overlap=%s",
                            ctx.job_id, _dll_fp, _overlap)

    if checkpoint.dll_strings:
        ctx.dll_strings = dict(checkpoint.dll_strings)

    if checkpoint.static_hints_block:
        ctx.static_hints_block = checkpoint.static_hints_block
    if checkpoint.static_analysis_result:
        ctx.static_analysis_result = dict(checkpoint.static_analysis_result)
    if checkpoint.static_enrichment:
        ctx.static_enrichment = dict(checkpoint.static_enrichment)
    if checkpoint.call_graph:
        ctx.call_graph = dict(checkpoint.call_graph)
    if checkpoint.ghidra_data_types:
        ctx.ghidra_data_types = list(checkpoint.ghidra_data_types)

    if checkpoint.evidence_candidates_snapshot:
        try:
            from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

            snapshot_to_restore = checkpoint.evidence_candidates_snapshot
            if cluster_seed_plan is not None:
                snapshot_to_restore = _filter_evidence_candidate_snapshot(
                    checkpoint.evidence_candidates_snapshot,
                    cluster_seed_plan.allowed_artifact_families,
                )
            restored = EvidenceCandidateRegistry.from_dict(snapshot_to_restore)
            existing = getattr(ctx, "evidence_candidates", None)
            if existing is None:
                ctx.evidence_candidates = restored
            else:
                existing.merge_from(restored)
                for fn_name in checkpoint.evidence_candidates_snapshot.get("init_satisfied", []) or []:
                    existing.mark_init_satisfied(str(fn_name))
        except Exception:
            pass

    existing_findings = _load_findings(ctx.job_id)
    inv_map = getattr(ctx, "inv_map", {}) or {}
    existing_strength: dict[str, tuple[int, bool]] = {}
    for row in existing_findings:
        fn_name = str((row or {}).get("function") or "").strip()
        if not fn_name:
            continue
        normalized = normalize_status(
            (row or {}).get("status_canonical") or (row or {}).get("status")
        )
        rank = STATUS_ORDER.get(normalized, 0)
        has_working_call = bool((row or {}).get("working_call"))
        prev = existing_strength.get(fn_name)
        if prev is None or rank > prev[0] or (rank == prev[0] and has_working_call and not prev[1]):
            existing_strength[fn_name] = (rank, has_working_call)

    # Mark successful functions as already explored
    seeded_findings_payload: list[dict[str, Any]] = []
    for name, fc in checkpoint.functions.items():
        if bounded_seed_functions is not None and name not in bounded_seed_functions:
            continue
        seed_row = {
            "function": name,
            "status": "success" if fc.status in {"success", "verified_success"} else (
                "error" if fc.status == "error" else "unknown"
            ),
            "working_call": fc.working_call,
            "finding": fc.finding or f"Seeded from checkpoint {checkpoint.source_job_id or checkpoint.job_id}",
            "verification": "verified" if (fc.verified or fc.status == "verified_success") else "",
            "notes": f"Seeded from checkpoint {checkpoint.source_job_id or checkpoint.job_id}",
            "source": "checkpoint_resume",
        }
        truth_assessment = assess_reusable_truth(seed_row, invocable=inv_map.get(name))
        if fc.is_skippable() and truth_assessment.get("seed_eligible"):
            ctx.already_explored.add(name)
            seeded += 1
        if not truth_assessment.get("seed_eligible"):
            continue
        seeded_status = str(seed_row["status"])
        seeded_rank = STATUS_ORDER.get(normalize_status(seeded_status), 0)
        seeded_has_working_call = bool(fc.working_call)
        existing = existing_strength.get(name)
        if existing is not None:
            existing_rank, existing_has_working_call = existing
            if existing_rank > seeded_rank:
                continue
            if existing_rank == seeded_rank and (existing_has_working_call or not seeded_has_working_call):
                continue
        seeded_findings_payload.append(
            {
                **seed_row,
                "reusable_truth_eligible": True,
                "reusable_truth_score": float(truth_assessment.get("score") or 0.0),
                "reusable_truth_reasons": list(truth_assessment.get("reasons") or []),
            }
        )

    if seeded_findings_payload:
        try:
            from api.infra.storage import _seed_findings

            _seed_findings(ctx.job_id, seeded_findings_payload)
        except Exception:
            pass

    logger.info("[%s] seeded %d findings from checkpoint", ctx.job_id, seeded)
    return seeded


def _cluster_strings(values: Any) -> tuple[str, ...]:
    items = []
    for value in (values or ()):
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)
    return tuple(items)


def _checkpoint_cluster_row(checkpoint: PipelineCheckpoint, cluster_id: str) -> dict[str, Any] | None:
    row = (checkpoint.cluster_checkpoints or {}).get(cluster_id)
    return row if isinstance(row, dict) else None


def _cluster_seed_confidence(
    checkpoint: PipelineCheckpoint,
    producer_functions: tuple[str, ...],
) -> float:
    if not producer_functions:
        return 0.0
    trusted = 0
    for fn_name in producer_functions:
        fc = checkpoint.functions.get(fn_name)
        if fc is not None and fc.is_skippable():
            trusted += 1
    return round(trusted / max(1, len(producer_functions)), 2)


def resolve_cluster_seed_plan(
    checkpoint: PipelineCheckpoint,
    cluster_checkpoint_id: str,
    *,
    adjacent_cluster_id: str = "",
    min_confidence: float = 0.5,
) -> ClusterSeedPlan | None:
    """Return a bounded rerun seed plan if checkpoint reuse is safe."""
    cluster_id = str(cluster_checkpoint_id or "").strip()
    if not cluster_id:
        return None

    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    snapshot = _checkpoint_cluster_row(checkpoint, cluster_id)
    if canonical is None or snapshot is None:
        return None

    schema_version = str(snapshot.get("schema_version") or CLUSTER_CHECKPOINT_SCHEMA_VERSION).strip()
    if schema_version != CLUSTER_CHECKPOINT_SCHEMA_VERSION:
        return None

    snapshot_functions = _cluster_strings(snapshot.get("function_names"))
    if snapshot_functions != canonical.function_names:
        return None

    snapshot_families = _cluster_strings(snapshot.get("live_artifact_families"))
    if snapshot_families != canonical.live_artifact_families:
        return None

    selected_clusters = [canonical]
    adjacent_id = str(adjacent_cluster_id or "").strip()
    if adjacent_id:
        if adjacent_id not in canonical.adjacent_clusters:
            return None
        adjacent_canonical = CLUSTER_CHECKPOINTS_BY_ID.get(adjacent_id)
        adjacent_snapshot = _checkpoint_cluster_row(checkpoint, adjacent_id)
        if adjacent_canonical is None or adjacent_snapshot is None:
            return None
        adjacent_schema_version = str(
            adjacent_snapshot.get("schema_version") or CLUSTER_CHECKPOINT_SCHEMA_VERSION
        ).strip()
        if adjacent_schema_version != CLUSTER_CHECKPOINT_SCHEMA_VERSION:
            return None
        if _cluster_strings(adjacent_snapshot.get("function_names")) != adjacent_canonical.function_names:
            return None
        selected_clusters.append(adjacent_canonical)

    focus_functions: list[str] = []
    seed_functions: list[str] = []
    allowed_families: list[str] = []
    lineage_sources: list[str] = []
    reuse_rules: list[str] = []

    for cluster in selected_clusters:
        for fn_name in cluster.function_names:
            if fn_name not in focus_functions:
                focus_functions.append(fn_name)
        for fn_name in cluster.producer_functions:
            if fn_name not in seed_functions:
                seed_functions.append(fn_name)
        for family in cluster.live_artifact_families:
            if family not in allowed_families:
                allowed_families.append(family)
        for source in cluster.lineage_sources:
            if source not in lineage_sources:
                lineage_sources.append(source)
        for rule in cluster.reuse_eligibility:
            if rule not in reuse_rules:
                reuse_rules.append(rule)

    confidence = _cluster_seed_confidence(checkpoint, tuple(seed_functions))
    if confidence < float(min_confidence):
        return None

    source_job_id = str(checkpoint.source_job_id or checkpoint.job_id or "").strip()
    if not source_job_id:
        return None

    return ClusterSeedPlan(
        cluster_id=cluster_id,
        adjacent_cluster_id=adjacent_id,
        focus_functions=tuple(focus_functions),
        seed_functions=tuple(seed_functions),
        allowed_artifact_families=tuple(allowed_families),
        lineage_sources=tuple(lineage_sources),
        reuse_eligibility=tuple(reuse_rules),
        confidence=confidence,
        source_job_id=source_job_id,
        schema_version=CLUSTER_CHECKPOINT_SCHEMA_VERSION,
    )


def _filter_evidence_candidate_snapshot(
    snapshot: dict[str, Any],
    allowed_artifact_families: tuple[str, ...],
) -> dict[str, Any]:
    allowed = {str(kind or "").strip() for kind in allowed_artifact_families if str(kind or "").strip()}
    if not allowed:
        return {"candidates": {}, "init_satisfied": list(snapshot.get("init_satisfied", []) or [])}

    filtered_candidates: dict[str, Any] = {}
    for kind, entries in dict(snapshot.get("candidates") or {}).items():
        if str(kind or "").strip() not in allowed:
            continue
        filtered_candidates[str(kind)] = list(entries or [])
    return {
        "candidates": filtered_candidates,
        "init_satisfied": list(snapshot.get("init_satisfied", []) or []),
    }


def update_checkpoint_from_context(checkpoint: PipelineCheckpoint, ctx) -> None:
    """Update checkpoint with current pipeline context after a stage completes."""
    checkpoint.sentinels = dict(ctx.sentinels)
    checkpoint.vocab = dict(ctx.vocab)
    checkpoint.unlock_result = dict(ctx.unlock_result)
    checkpoint.write_unlock_block = ctx.write_unlock_block
    checkpoint.dll_strings = dict(ctx.dll_strings)
    checkpoint.static_hints_block = ctx.static_hints_block
    checkpoint.static_analysis_result = dict(getattr(ctx, "static_analysis_result", {}) or {})
    checkpoint.static_enrichment = dict(getattr(ctx, "static_enrichment", {}) or {})
    checkpoint.call_graph = dict(getattr(ctx, "call_graph", {}) or {})
    checkpoint.ghidra_data_types = list(getattr(ctx, "ghidra_data_types", []) or [])
    ecr = getattr(ctx, "evidence_candidates", None)
    if ecr is not None:
        try:
            checkpoint.evidence_candidates_snapshot = ecr.to_dict()
        except Exception:
            pass
    checkpoint.cluster_checkpoints = backfill_cluster_checkpoint_rows(
        checkpoint.cluster_checkpoints,
        function_states=checkpoint.functions,
        source_job_id=checkpoint.source_job_id or checkpoint.job_id,
    )


def record_function_checkpoint(
    checkpoint: PipelineCheckpoint,
    fn_name: str,
    status: str,
    working_call: dict | None = None,
    finding: str = "",
    verified: bool = False,
    stage: str = "s02",
) -> None:
    """Record a function-level checkpoint after probing or verification."""
    checkpoint.functions[fn_name] = FunctionCheckpoint(
        name=fn_name,
        status=status,
        working_call=working_call,
        finding=finding,
        verified=verified,
        stage=stage,
        timestamp=time.time(),
    )


def mark_stage_complete(
    checkpoint: PipelineCheckpoint,
    stage_id: str,
    data: dict | None = None,
) -> None:
    """Mark a stage as completed in the checkpoint."""
    checkpoint.stages[stage_id] = StageCheckpoint(
        stage_id=stage_id,
        completed=True,
        timestamp=time.time(),
        data=data or {},
    )


def is_stage_complete(checkpoint: PipelineCheckpoint | None, stage_id: str) -> bool:
    """Check if a stage was already completed in a loaded checkpoint."""
    if checkpoint is None:
        return False
    sc = checkpoint.stages.get(stage_id)
    return sc is not None and sc.completed


def should_skip_function(
    checkpoint: PipelineCheckpoint | None,
    fn_name: str,
    focus_functions: list[str] | None = None,
) -> bool:
    """Determine if a function should be skipped in the probe loop.

    Skip if:
    1. Checkpoint has it as skippable (success + working_call) AND
    2. It's NOT in the focus_functions list (if provided)
    """
    if checkpoint is None:
        return False

    fc = checkpoint.functions.get(fn_name)
    if fc is None or not fc.is_skippable():
        return False

    if focus_functions and fn_name in focus_functions:
        return False

    return True
