"""api.pipeline.core.macro_coordinator -- Cross-run pipeline coordination.

The macro coordinator sits ABOVE the stage-level micro coordinators (MC-3
through MC-6). While MCs make post-stage decisions within a single run,
the macro coordinator makes cross-run decisions:

  1. Should the pipeline loop again? (circular enrichment)
  2. What strategy adjustments to apply for the next iteration?
  3. Is the pipeline "done" or "awaiting clarification"? (AC-4 closure gate)

Currently this is invoked at the END of _explore_worker in runner.py.
The user can also trigger re-runs manually via prior_job_id.

The macro coordinator does NOT call LLMs — it uses deterministic rules
over the end-of-run context to produce a verdict.
"""
from __future__ import annotations

import json
import logging
import re as _re
import time
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger("mcp_factory.pipeline.macro_coordinator")

_ENTRY_POINT_RE = _re.compile(
    r"^(entry|_?DllMain|_?DllEntryPoint|_?CRT|_?wmain|_?main)$", _re.I
)


# ── Verdict dataclass ────────────────────────────────────────────────────────

@dataclass
class RunVerdict:
    """End-of-run decision from the macro coordinator."""

    status: str  # "done" | "loop_again" | "awaiting_clarification"

    coverage_pct: float = 0.0          # legacy: verified_rate alias
    verified_count: int = 0
    total_count: int = 0
    unresolved_functions: list[str] = field(default_factory=list)

    verified_rate: float = 0.0         # verified_success / total
    discovered_rate: float = 0.0       # (verified + functional + inferred) / total
    functional_count: int = 0          # functional_precondition_unmet count
    inferred_count: int = 0            # inferred_success count

    strategy_adjustments: dict[str, Any] = field(default_factory=dict)
    clarification_questions: list[str] = field(default_factory=list)
    floor_verdict: dict[str, Any] = field(default_factory=dict)

    reasoning: str = ""


# ── Coverage calculation ─────────────────────────────────────────────────────

@dataclass
class CoverageMetrics:
    """Taxonomy-aware coverage breakdown."""
    verified: int = 0
    functional: int = 0
    inferred: int = 0
    failure: int = 0
    unknown: int = 0
    total: int = 0
    verified_rate: float = 0.0
    discovered_rate: float = 0.0


def _compute_coverage(ctx) -> CoverageMetrics:
    """Count functions by taxonomy status and return full metrics.

    Deduplicates findings to latest-per-function before counting.
    Excludes DLL entry points (DllMain, entry) from both numerator and
    denominator since they are not user-callable API functions.
    """
    from api.infra.storage import _load_findings
    from api.pipeline.core.helpers import (
        FINDING_VERIFIED_STATUSES,
        FINDING_DISCOVERED_STATUSES,
    )
    from api.pipeline.core.scoring_scope import canonical_status_map, target_scope_names

    raw = _load_findings(getattr(ctx, "job_id", ""))
    scope_names = [
        name for name in target_scope_names(getattr(ctx, "runtime", None))
        if not _ENTRY_POINT_RE.match(name)
    ]
    status_map = canonical_status_map(raw, scope_names)
    if not scope_names:
        status_map = {
            fn: status
            for fn, status in status_map.items()
            if not _ENTRY_POINT_RE.match(fn)
        }
    total = len(status_map)
    if total == 0:
        return CoverageMetrics()

    m = CoverageMetrics(total=total)
    for s in status_map.values():
        if s in FINDING_VERIFIED_STATUSES:
            m.verified += 1
        elif s == "functional_precondition_unmet":
            m.functional += 1
        elif s == "inferred_success":
            m.inferred += 1
        elif s in ("error", "failure"):
            m.failure += 1
        else:
            m.unknown += 1

    m.verified_rate = round(100.0 * m.verified / total, 1)
    discovered = m.verified + m.functional + m.inferred
    m.discovered_rate = round(100.0 * discovered / total, 1)
    return m


def _unresolved_function_names(ctx) -> list[str]:
    """Return names of functions that are NOT verified/discovered (excluding entry points).

    Deduplicates to latest-per-function to avoid inflated unresolved lists.
    """
    from api.infra.storage import _load_findings
    from api.pipeline.core.helpers import (
        FINDING_DISCOVERED_STATUSES,
    )
    from api.pipeline.core.scoring_scope import canonical_status_map, target_scope_names

    raw = _load_findings(getattr(ctx, "job_id", ""))
    scope_names = [
        name for name in target_scope_names(getattr(ctx, "runtime", None))
        if not _ENTRY_POINT_RE.match(name)
    ]
    status_map = canonical_status_map(raw, scope_names)
    if not scope_names:
        status_map = {
            fn: status
            for fn, status in status_map.items()
            if not _ENTRY_POINT_RE.match(fn)
        }
    return [
        fn for fn, status in status_map.items()
        if status not in FINDING_DISCOVERED_STATUSES
    ]


# ── Strategy adjustment logic ────────────────────────────────────────────────

def _suggest_strategy_adjustments(ctx, verified: int, total: int) -> dict[str, Any]:
    """Suggest parameter tweaks for a hypothetical next run."""
    adjustments: dict[str, Any] = {}

    unresolved = _unresolved_function_names(ctx)
    if not unresolved:
        return adjustments

    write_patterns = {"pay", "redeem", "unlock", "process", "write", "commit",
                      "transfer", "debit", "credit", "update", "set", "create"}
    unresolved_lower = [fn.lower() for fn in unresolved]
    write_failures = [fn for fn in unresolved_lower
                      if any(p in fn for p in write_patterns)]

    if write_failures:
        adjustments["focus_write_unlock"] = True
        if len(write_failures) == len(unresolved):
            adjustments["reasoning"] = (
                f"All {len(unresolved)} unresolved functions are write-type. "
                "Next run should focus on write-unlock with expanded init mode sweep."
            )
        else:
            non_write = [fn for fn in unresolved if fn.lower() not in write_failures]
            adjustments["reasoning"] = (
                f"{len(write_failures)} of {len(unresolved)} unresolved are write-type. "
                f"Non-write failures: {non_write}. "
                "Next run should prioritize write-unlock and re-probe non-write failures."
            )

    adjustments["focus_functions"] = unresolved[:6]
    adjustments["skip_to_stage"] = "s02_probe"
    adjustments["unresolved_count"] = len(unresolved)

    return adjustments


# ── Closure gate (AC-4) ─────────────────────────────────────────────────────

def _has_open_clarification_questions(ctx) -> list[str]:
    """Extract any clarification questions generated by S-06.

    Reads from job status (explore_questions) since that's where S-06
    persists gap questions. Handles both string and dict-format questions.
    """
    from api.infra.storage import _get_job_status

    job_status = _get_job_status(getattr(ctx, "job_id", "")) or {}
    raw_questions = job_status.get("explore_questions") or []

    result: list[str] = []
    for q in raw_questions:
        if isinstance(q, str) and q.strip():
            result.append(q.strip())
        elif isinstance(q, dict):
            if q.get("answered") or str(q.get("answer") or "").strip():
                continue
            text = q.get("technical_question") or q.get("question") or ""
            fn = q.get("function") or ""
            if text:
                result.append(f"[{fn}] {text}" if fn else text)
    return result


# ── Main entry point ─────────────────────────────────────────────────────────

def evaluate_run(ctx) -> RunVerdict:
    """Evaluate the completed pipeline run and produce a verdict.

    Called at the end of _explore_worker in runner.py.

    Returns a RunVerdict that the caller can:
      - Log as a blob artifact
      - Display in the UI
      - Use to auto-trigger a follow-up run (if status == "loop_again")
    """
    cov = _compute_coverage(ctx)
    unresolved = _unresolved_function_names(ctx)
    questions = _has_open_clarification_questions(ctx)
    floor_state = getattr(ctx, "floor_iteration_state", None)
    if floor_state is not None:
        floor_status = str(getattr(floor_state, "status", "") or "").strip().lower()
        previous_ceiling = list(getattr(floor_state, "previous_ceiling_functions", []) or [])
        next_ceiling = list(getattr(floor_state, "next_ceiling_functions", []) or [])
        reopened = list(getattr(floor_state, "reopened_functions", []) or [])
        carryover_status = str(getattr(floor_state, "carryover_status", "") or "").strip().lower()
        if floor_status == "done":
            status = "done"
            reasoning = (
                f"Floor-to-ceiling iteration resolved the active ceiling "
                f"({len(previous_ceiling)} -> {len(next_ceiling)})."
            )
        elif floor_status == "loop_again":
            status = "loop_again"
            reasoning = (
                f"Floor-to-ceiling iteration narrowed the active ceiling "
                f"({len(previous_ceiling)} -> {len(next_ceiling)}), carryover={carryover_status or 'n/a'}."
            )
        else:
            status = "done"
            reasoning = (
                f"Floor-to-ceiling iteration stopped after preservation failure or stagnation "
                f"(reopened={len(reopened)}, carryover={carryover_status or 'n/a'})."
            )
        adjustments = dict(getattr(floor_state, "next_cycle_recommendation", {}) or {})
        verdict = RunVerdict(
            status=status,
            coverage_pct=cov.verified_rate,
            verified_count=cov.verified,
            total_count=cov.total,
            unresolved_functions=next_ceiling or unresolved,
            verified_rate=cov.verified_rate,
            discovered_rate=cov.discovered_rate,
            functional_count=cov.functional,
            inferred_count=cov.inferred,
            strategy_adjustments=adjustments,
            clarification_questions=questions,
            floor_verdict={
                "iteration_index": int(getattr(floor_state, "iteration_index", 1) or 1),
                "floor_scope": str(getattr(floor_state, "floor_scope", "") or ""),
                "previous_ceiling_functions": previous_ceiling,
                "next_ceiling_functions": next_ceiling,
                "ceiling_shrank": bool(getattr(floor_state, "ceiling_shrank", False)),
                "localized_more": bool(getattr(floor_state, "localized_more", False)),
                "reopened_functions": reopened,
                "carryover_status": carryover_status,
                "preservation_ok": not reopened,
            },
            reasoning=reasoning,
        )

        logger.info(
            "[%s] Macro coordinator floor verdict: %s (ceiling %d -> %d)",
            getattr(ctx, "job_id", "?"),
            verdict.status,
            len(previous_ceiling),
            len(next_ceiling),
        )
        return verdict

    if cov.verified_rate >= 100.0:
        status = "done"
        reasoning = f"Full coverage: {cov.verified}/{cov.total} functions verified."
    elif questions:
        status = "awaiting_clarification"
        reasoning = (
            f"Verified {cov.verified_rate}% ({cov.verified}/{cov.total}), "
            f"discovered {cov.discovered_rate}%. "
            f"{len(questions)} clarification question(s) for the user."
        )
    elif cov.discovered_rate >= 95.0:
        status = "done"
        reasoning = (
            f"Discovered {cov.discovered_rate}% ({cov.verified} verified + "
            f"{cov.functional} functional + {cov.inferred} inferred / {cov.total}). "
            f"Verified rate {cov.verified_rate}%. Nearly everything understood."
        )
    elif cov.verified_rate >= 85.0:
        status = "done"
        reasoning = (
            f"Verified {cov.verified_rate}% ({cov.verified}/{cov.total}). "
            f"Discovered {cov.discovered_rate}%. "
            f"Above 85% threshold — remaining {len(unresolved)} function(s) "
            f"likely require manual context or are genuinely unprobeable."
        )
    else:
        status = "loop_again"
        reasoning = (
            f"Verified {cov.verified_rate}% ({cov.verified}/{cov.total}). "
            f"Discovered {cov.discovered_rate}% "
            f"({cov.functional} functional, {cov.inferred} inferred). "
            f"Below 85% threshold — another iteration may improve coverage."
        )

    adjustments = _suggest_strategy_adjustments(ctx, cov.verified, cov.total)

    verdict = RunVerdict(
        status=status,
        coverage_pct=cov.verified_rate,
        verified_count=cov.verified,
        total_count=cov.total,
        unresolved_functions=unresolved,
        verified_rate=cov.verified_rate,
        discovered_rate=cov.discovered_rate,
        functional_count=cov.functional,
        inferred_count=cov.inferred,
        strategy_adjustments=adjustments,
        clarification_questions=questions,
        floor_verdict={},
        reasoning=reasoning,
    )

    logger.info(
        "[%s] Macro coordinator verdict: %s (verified=%.1f%% discovered=%.1f%% %d/%d)",
        getattr(ctx, "job_id", "?"),
        verdict.status,
        verdict.verified_rate,
        verdict.discovered_rate,
        verdict.verified_count,
        verdict.total_count,
    )

    return verdict


# ── Persistence ──────────────────────────────────────────────────────────────

def persist_verdict(ctx, verdict: RunVerdict) -> None:
    """Save the verdict as a blob artifact.

    The runner owns terminal job-status persistence. Keeping this helper out of
    status.json avoids blocking worker close on large nonterminal status merges.
    """
    from api.infra.config import ARTIFACT_CONTAINER
    from api.infra.storage import _upload_to_blob

    job_id = getattr(ctx, "job_id", "")
    if not job_id:
        return

    payload = {
        "status": verdict.status,
        "coverage_pct": verdict.coverage_pct,
        "verified_count": verdict.verified_count,
        "total_count": verdict.total_count,
        "verified_rate": verdict.verified_rate,
        "discovered_rate": verdict.discovered_rate,
        "functional_count": verdict.functional_count,
        "inferred_count": verdict.inferred_count,
        "unresolved_functions": verdict.unresolved_functions,
        "strategy_adjustments": verdict.strategy_adjustments,
        "clarification_questions": verdict.clarification_questions,
        "floor_verdict": verdict.floor_verdict,
        "reasoning": verdict.reasoning,
        "timestamp": time.time(),
    }

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/macro_verdict.json",
            json.dumps(payload, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] macro verdict blob write failed: %s", job_id, exc)


def _load_mc_decision_history(job_id: str) -> dict[str, list[dict]]:
    """Load all micro coordinator decisions for a job.

    Returns {"mc3-post-reconcile": [...], "mc4-post-synthesis": [...], ...}.
    """
    from api.infra.config import ARTIFACT_CONTAINER
    from api.infra.storage import _download_blob

    mc_ids = [
        "mc3-post-reconcile",
        "mc4-post-synthesis",
        "mc5-post-verification",
        "mc6-post-gap-resolution",
    ]
    history: dict[str, list[dict]] = {}
    for mc_id in mc_ids:
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/mc-decisions/{mc_id}.json")
            history[mc_id] = json.loads(raw)
        except Exception:
            history[mc_id] = []
    return history
