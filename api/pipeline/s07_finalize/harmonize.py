"""api.pipeline.s07_finalize.harmonize -- Phase 10: harmonization + finalize."""

from __future__ import annotations

import json
import logging
import os
import queue
import re as _re
import threading
import time
from ast import literal_eval as _literal_eval
from collections import defaultdict

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _load_findings, _patch_finding,
    _persist_job_status, _get_job_status, _get_invocable,
    _upload_to_blob, _download_blob,
)
from api.pipeline.core.finding_status import STATUS_ORDER, normalize_status
from api.pipeline.core.helpers import (
    _set_explore_status, _cancel_requested,
)
from api.pipeline.core.reusable_truth import assess_reusable_truth
logger = logging.getLogger("mcp_factory.api")

_CROSS_VALIDATION_ASSIGNMENT_RE = _re.compile(
    r"(?m)^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>'[^']*'|\"[^\"]*\"|-?\d+)\s*$"
)

_S07_STAGE = "s07_finalize"
_S07_DESCRIPTION_SYNTHESIS_TIMEOUT_SEC = 30.0
_S07_SCHEMA_EVOLUTION_BLOB_TIMEOUT_SEC = 2.0
_S07_FINDINGS_LOAD_TIMEOUT_SEC = max(
    1.0,
    float(os.getenv("MCP_S07_FINDINGS_LOAD_TIMEOUT_SEC", "30") or "30"),
)
_S07_PROMOTE_FINDINGS_TIMEOUT_SEC = max(
    1.0,
    float(os.getenv("MCP_S07_PROMOTE_FINDINGS_TIMEOUT_SEC", "30") or "30"),
)


def _chat_completion_create_bounded(client, *, timeout_sec: float, **kwargs):
    """Run optional chat completion behind a hard wall-clock bound.

    The OpenAI per-request timeout is not always enough to protect worker close
    paths. S-07 description synthesis is optional, so it must degrade instead
    of holding the whole checkpoint open.
    """
    result_q: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _call() -> None:
        try:
            result_q.put(("ok", client.chat.completions.create(**kwargs)))
        except BaseException as exc:  # pragma: no cover - re-raised in caller
            result_q.put(("err", exc))

    worker = threading.Thread(
        target=_call,
        name="s07-description-synthesis",
        daemon=True,
    )
    worker.start()
    try:
        kind, payload = result_q.get(timeout=float(timeout_sec))
    except queue.Empty as exc:
        raise TimeoutError(
            f"s07 description synthesis exceeded {float(timeout_sec):.1f}s"
        ) from exc
    if kind == "err":
        raise payload  # type: ignore[misc]
    return payload


def _download_blob_bounded(container: str, blob_name: str, *, timeout_sec: float) -> bytes | str:
    """Bound optional S-07 artifact reads so diagnostic hashing cannot block closeout."""
    result_q: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _call() -> None:
        try:
            result_q.put(("ok", _download_blob(container, blob_name)))
        except Exception as exc:
            result_q.put(("err", exc))

    worker = threading.Thread(
        target=_call,
        name=f"s07-schema-evolution-read-{blob_name.replace('/', '-')}",
        daemon=True,
    )
    worker.start()
    try:
        kind, payload = result_q.get(timeout=float(timeout_sec))
    except queue.Empty as exc:
        raise TimeoutError(
            f"s07 schema evolution read exceeded {float(timeout_sec):.1f}s for {blob_name}"
        ) from exc
    if kind == "err":
        raise payload  # type: ignore[misc]
    return payload  # type: ignore[return-value]


def _load_findings_bounded(job_id: str, *, timeout_sec: float | None = None) -> list[dict]:
    """Bound S-07 findings reads so optional harmonization cannot trap closeout."""
    timeout = float(timeout_sec if timeout_sec is not None else _S07_FINDINGS_LOAD_TIMEOUT_SEC)
    result_q: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _call() -> None:
        try:
            result_q.put(("ok", _load_findings(job_id)))
        except Exception as exc:
            result_q.put(("err", exc))

    worker = threading.Thread(
        target=_call,
        name=f"s07-load-findings-{job_id}",
        daemon=True,
    )
    worker.start()
    try:
        kind, payload = result_q.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError(f"s07 findings load exceeded {timeout:.1f}s for {job_id}") from exc
    if kind == "err":
        raise payload  # type: ignore[misc]
    return list(payload)  # type: ignore[arg-type]


def _s07_description_synthesis_enabled() -> bool:
    return str(os.getenv("MCP_ENABLE_S07_DESCRIPTION_SYNTHESIS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _deterministic_component_description(ctx) -> str:
    vocab = getattr(ctx, "vocab", {}) or {}
    seed = (
        str(vocab.get("user_context") or "").strip()
        or str(vocab.get("notes") or "").strip()
        or str(getattr(ctx, "component_name", "") or "").strip()
        or str(getattr(ctx, "file_path", "") or "").strip()
    )
    if seed:
        seed = " ".join(seed.split())
        return f"Integration surface for {seed[:80]}."
    return "Integration surface summarized from recovered runtime and static evidence."


def _s07_progress(ctx) -> tuple[int, int]:
    try:
        explored = int(ctx.explored_count())
    except Exception:
        explored = 0
    try:
        total = int(getattr(ctx, "total", 0) or 0)
    except Exception:
        total = 0
    return explored, total


def _set_s07_span_status(ctx, span: str, state: str, message: str) -> None:
    """Expose S-07 internal progress without changing final verdict semantics."""
    try:
        now = time.time()
        current = _get_job_status(ctx.job_id) or {}
        explored, total = _s07_progress(ctx)
        _persist_job_status(
            ctx.job_id,
            {
                **current,
                "explore_phase": "exploring",
                "explore_stage": _S07_STAGE,
                "explore_progress": f"{explored}/{total}",
                "explore_message": message,
                "explore_span": str(span or "").strip(),
                "explore_span_state": str(state or "").strip(),
                "explore_span_message": message,
                "explore_span_updated_at": now,
                "updated_at": now,
            },
            # S-07 span updates are diagnostic breadcrumbs. They must not hold
            # closeout hostage when the durable artifacts already landed.
            sync=False,
        )
    except Exception as exc:
        logger.debug("[%s] s07 span status failed (%s): %s", getattr(ctx, "job_id", ""), span, exc)


def _s07_span_start(ctx, span: str, message: str) -> None:
    _set_s07_span_status(ctx, span, "start", message)


def _s07_span_done(ctx, span: str, message: str) -> None:
    _set_s07_span_status(ctx, span, "done", message)


def _s07_span_fail(ctx, span: str, exc: Exception) -> None:
    _set_s07_span_status(ctx, span, "fail", f"{span} failed: {exc}")


def _direct_truth_is_promotion_safe(finding: dict) -> bool:
    # A preserved direct-target truth may have been demoted earlier before
    # later cross-validation or verification evidence arrived. Do not let stale
    # top-level demotion residue block harmonize from re-evaluating the
    # stronger preserved truth through the fresh semantic-safety gate below.
    direct_truth = finding.get("direct_target_truth")
    if isinstance(direct_truth, dict):
        direct_alignment = str(direct_truth.get("expected_observed_alignment") or "").strip().lower()
        if direct_alignment and direct_alignment not in {"aligned", "unknown"}:
            return False
    return True


def _parse_cross_validation_outputs(cross_validation: str) -> dict[str, object]:
    outputs: dict[str, object] = {}
    for match in _CROSS_VALIDATION_ASSIGNMENT_RE.finditer(str(cross_validation or "")):
        key = str(match.group("key") or "").strip()
        raw_value = str(match.group("value") or "")
        if not key or not raw_value:
            continue
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
            outputs[key] = raw_value[1:-1]
            continue
        try:
            outputs[key] = int(raw_value)
        except ValueError:
            outputs[key] = raw_value
    return outputs


def _parse_cross_validation_call_args(cross_validation: str) -> dict[str, object]:
    text = str(cross_validation or "")
    start = text.find("({")
    if start < 0:
        return {}
    start += 1
    end = text.find("})", start)
    if end < 0:
        return {}
    raw = text[start : end + 1]
    try:
        parsed = _literal_eval(raw)
    except (SyntaxError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _promoted_truth_conflicts_with_cross_validation(
    promoted_wc: dict[str, object],
    cross_validation: str,
) -> bool:
    if not promoted_wc:
        return False
    call_args = _parse_cross_validation_call_args(cross_validation)
    if any(
        key in promoted_wc and promoted_wc.get(key) != observed_value
        for key, observed_value in call_args.items()
    ):
        return False
    observed_outputs = _parse_cross_validation_outputs(cross_validation)
    for key, observed_value in observed_outputs.items():
        if key in promoted_wc and promoted_wc.get(key) != observed_value:
            return True
    return False


def _promoted_truth_is_semantically_safe(
    job_id: str,
    finding: dict,
    promoted_wc: dict[str, object],
) -> bool:
    if not promoted_wc:
        return False
    if _promoted_truth_conflicts_with_cross_validation(
        promoted_wc,
        str(finding.get("cross_validation") or ""),
    ):
        return False
    function_name = str(finding.get("function") or "").strip()
    invocable = _get_invocable(job_id, function_name) if function_name else None
    candidate = dict(finding)
    candidate["status"] = "success"
    candidate["status_canonical"] = "verified_success"
    candidate["working_call"] = dict(promoted_wc)
    direct_truth = candidate.get("direct_target_truth")
    if isinstance(direct_truth, dict):
        candidate["direct_target_truth"] = {
            **direct_truth,
            "working_call": dict(promoted_wc),
        }
    truth_assessment = assess_reusable_truth(candidate, invocable=invocable)
    return bool(truth_assessment.get("seed_eligible"))


def _evaluate_direct_truth_promotions(
    ctx,
    hm_findings: list[dict],
    direct_successes: dict[str, list[dict]],
) -> list[dict]:
    upgrades: list[dict] = []
    for finding in hm_findings:
        fn = finding.get("function") or ""
        direct_truth = finding.get("direct_target_truth") if isinstance(finding.get("direct_target_truth"), dict) else {}
        direct_truth_wc = dict(direct_truth.get("working_call") or {})
        direct_truth_verified = str(direct_truth.get("verification") or "").strip().lower() == "verified"
        direct_truth_rejected = bool(direct_truth.get("rejected_by_verification"))
        current_rank = STATUS_ORDER.get(normalize_status(finding.get("status_canonical") or finding.get("status")), 0)
        best = None
        if fn in direct_successes:
            best = max(
                direct_successes[fn],
                key=lambda probe: len(probe.get("args") or {}),
            )
        probe_wc = dict((best or {}).get("args") or {})
        promoted_wc = direct_truth_wc or probe_wc
        can_promote = (
            bool(promoted_wc)
            and not direct_truth_rejected
            and _direct_truth_is_promotion_safe(finding)
            and _promoted_truth_is_semantically_safe(ctx.job_id, finding, promoted_wc)
            and (direct_truth_verified or best is not None)
            and current_rank < STATUS_ORDER.get("verified_success", 0)
        )
        if can_promote:
            _patch_finding(ctx.job_id, fn, {
                "status": "success",
                "status_canonical": "verified_success",
                "status_legacy": "success",
                "working_call": promoted_wc,
                "verification": "verified" if direct_truth_verified or best is not None else str(finding.get("verification") or ""),
                "direct_target_truth": {
                    **dict(direct_truth or {}),
                    "function": fn,
                    "working_call": promoted_wc,
                    "verification": "verified" if direct_truth_verified or best is not None else str(direct_truth.get("verification") or ""),
                    "source": str((direct_truth or {}).get("source") or "s07_harmonize"),
                    "probe_id": str((best or {}).get("probe_id") or (direct_truth or {}).get("probe_id") or ""),
                },
                "finding": (
                    f"Harmonized: preserved stronger direct-target truth for {fn} with {promoted_wc}."
                ),
                "stop_reason": "harmonized_direct_target_truth",
                "notes": (
                    "Final harmonization promoted preserved direct-target truth over a weaker final finding."
                ),
            })
            upgrades.append({
                "function": fn,
                "probe_id": (best or {}).get("probe_id"),
                "args": promoted_wc,
            })
    return upgrades


def _evaluate_direct_truth_promotions_bounded(
    ctx,
    hm_findings: list[dict],
    direct_successes: dict[str, list[dict]],
    *,
    timeout_sec: float | None = None,
) -> tuple[list[dict], bool]:
    timeout = float(timeout_sec if timeout_sec is not None else _S07_PROMOTE_FINDINGS_TIMEOUT_SEC)
    result_q: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _call() -> None:
        try:
            result_q.put(("ok", _evaluate_direct_truth_promotions(ctx, hm_findings, direct_successes)))
        except Exception as exc:
            result_q.put(("err", exc))

    worker = threading.Thread(
        target=_call,
        daemon=True,
        name=f"s07-promote-findings-{getattr(ctx, 'job_id', '')}",
    )
    worker.start()
    try:
        kind, payload = result_q.get(timeout=timeout)
    except queue.Empty:
        logger.warning("[%s] S-07 direct-truth promotion timed out after %.1fs; continuing closeout", ctx.job_id, timeout)
        return [], False
    if kind == "err":
        logger.debug("[%s] S-07 direct-truth promotion failed: %s", ctx.job_id, payload)
        return [], True
    return list(payload), True  # type: ignore[arg-type]


def _run_phase_10_harmonize(ctx) -> None:
    """Final deterministic harmonization -- upgrade error findings with direct-probe evidence."""
    try:
        _set_explore_status(
            ctx.job_id,
            ctx.explored_count(),
            ctx.total,
            "Finalizing harmonized state...",
            stage=_S07_STAGE,
        )
        _s07_span_start(ctx, "s07_harmonize_load_findings", "S-07 harmonize: loading findings...")
        try:
            _hm_findings = _load_findings_bounded(ctx.job_id)
        except TimeoutError as exc:
            _s07_span_fail(ctx, "s07_harmonize_load_findings", exc)
            logger.warning("[%s] phase10: findings load timed out; skipping optional harmonization", ctx.job_id)
            return
        _s07_span_done(ctx, "s07_harmonize_load_findings", f"S-07 harmonize: loaded {len(_hm_findings)} findings.")

        _s07_span_start(ctx, "s07_harmonize_load_probe_log", "S-07 harmonize: loading probe log...")
        _hm_probe_log: list[dict] = []
        try:
            _hm_raw = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/explore_probe_log.json")
            _hm_probe_log = json.loads(_hm_raw)
        except Exception:
            pass
        _s07_span_done(ctx, "s07_harmonize_load_probe_log", f"S-07 harmonize: loaded {len(_hm_probe_log)} probe rows.")

        _s07_span_start(ctx, "s07_harmonize_index_direct_successes", "S-07 harmonize: indexing direct successes...")
        _direct_successes: dict[str, list[dict]] = defaultdict(list)
        for _pe in _hm_probe_log:
            _fn = _pe.get("function") or ""
            _tool = _pe.get("tool") or ""
            _phase = str(_pe.get("phase") or "")
            _clf = _pe.get("classification") or {}
            if not (_fn and _tool and _fn == _tool):
                continue
            if _phase not in {"explore", "cross_validate"}:
                continue
            if _clf.get("has_return") and int(_clf.get("signed", -1)) == 0:
                _direct_successes[_fn].append(_pe)
        _s07_span_done(
            ctx,
            "s07_harmonize_index_direct_successes",
            f"S-07 harmonize: indexed {len(_direct_successes)} direct-success functions.",
        )

        _s07_span_start(ctx, "s07_harmonize_promote_findings", "S-07 harmonize: evaluating direct-truth promotions...")
        _upgrades, _promotion_completed = _evaluate_direct_truth_promotions_bounded(
            ctx,
            list(_hm_findings),
            dict(_direct_successes),
        )
        _s07_span_done(
            ctx,
            "s07_harmonize_promote_findings",
            (
                f"S-07 harmonize: evaluated promotions ({len(_upgrades)} upgrades)."
                if _promotion_completed
                else "S-07 harmonize: promotion evaluation timed out; continuing closeout."
            ),
        )

        _s07_span_start(ctx, "s07_harmonize_reload_findings", "S-07 harmonize: reloading post-harmonization findings...")
        try:
            _post_hm_findings = _load_findings_bounded(ctx.job_id)
        except TimeoutError as exc:
            _s07_span_fail(ctx, "s07_harmonize_reload_findings", exc)
            _post_hm_findings = list(_hm_findings)
        _s07_span_done(
            ctx,
            "s07_harmonize_reload_findings",
            f"S-07 harmonize: reloaded {len(_post_hm_findings)} findings.",
        )
        _status_counts = {
            "success": sum(1 for _f in _post_hm_findings if _f.get("status") == "success"),
            "error":   sum(1 for _f in _post_hm_findings if _f.get("status") == "error"),
            "other":   sum(1 for _f in _post_hm_findings
                           if _f.get("status") not in {"success", "error"}),
        }

        _cur = _get_job_status(ctx.job_id) or {}
        _open_questions = _cur.get("explore_questions") or []
        _unanswered_questions = [
            q for q in _open_questions
            if isinstance(q, dict)
            and not (bool(q.get("answered")) or bool(str(q.get("answer") or "").strip()))
        ]

        _harmonization = {
            "job_id": ctx.job_id,
            "final_phase_suggestion": (
                "awaiting_clarification" if _unanswered_questions else "done"
            ),
            "patched_error_to_success": _upgrades,
            "counts": _status_counts,
            "open_questions": len(_open_questions),
            "unanswered_questions": len(_unanswered_questions),
        }
        _s07_span_start(ctx, "s07_harmonize_write_report", "S-07 harmonize: writing harmonization report...")
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/harmonization_report.json",
            json.dumps(_harmonization, indent=2).encode(),
        )
        _s07_span_done(ctx, "s07_harmonize_write_report", "S-07 harmonize: harmonization report written.")
        logger.info("[%s] phase10: harmonization complete (%d upgrades, %d unanswered)",
                    ctx.job_id, len(_upgrades), len(_unanswered_questions))
    except Exception as _hm_e:
        _s07_span_fail(ctx, "s07_harmonize_unknown", _hm_e)
        logger.debug("[%s] phase10: harmonization failed: %s", ctx.job_id, _hm_e)


def _run_finalize(ctx) -> None:
    """Synthesize vocab description and apply the AC-4 closure gate."""
    if ctx.vocab and "description" not in ctx.vocab:
        _s07_span_start(ctx, "s07_finalize_description", "S-07 finalize: synthesizing component description...")
        try:
            if not _s07_description_synthesis_enabled():
                ctx.vocab["description"] = _deterministic_component_description(ctx)
                _s07_span_done(
                    ctx,
                    "s07_finalize_description",
                    "S-07 finalize: deterministic description applied.",
                )
                logger.info(
                    "[%s] finalize: deterministic description applied",
                    ctx.job_id,
                )
            else:
                _desc_seed = ctx.vocab.get("user_context") or ctx.vocab.get("notes") or ""
                _vs = ctx.vocab.get("value_semantics") or {}
                _vs_sample = "; ".join(f"{k}: {v}" for k, v in list(_vs.items())[:8])
                _ids = ", ".join(ctx.vocab.get("id_formats") or [])
                _desc_prompt = (
                    "Based on the following accumulated knowledge about a DLL, write ONE sentence "
                    "describing what this component does for a developer integrating it. "
                    "Be specific -- name the business domain, key entities, and operations. "
                    "Do not mention 'DLL' or 'function'. Max 25 words.\n\n"
                    + (f"User context: {_desc_seed}\n" if _desc_seed else "")
                    + (f"Known ID formats: {_ids}\n" if _ids else "")
                    + (f"Value semantics: {_vs_sample}\n" if _vs_sample else "")
                )
                _desc_resp = _chat_completion_create_bounded(
                    ctx.client,
                    timeout_sec=_S07_DESCRIPTION_SYNTHESIS_TIMEOUT_SEC,
                    model=ctx.model,
                    messages=[{"role": "user", "content": _desc_prompt}],
                    temperature=0,
                    max_tokens=60,
                    timeout=min(30.0, _S07_DESCRIPTION_SYNTHESIS_TIMEOUT_SEC),
                )
                _desc_text = (_desc_resp.choices[0].message.content or "").strip().strip('"')
                if _desc_text:
                    ctx.vocab["description"] = _desc_text
                    logger.info("[%s] finalize: synthesized description: %s",
                                ctx.job_id, _desc_text)
                _s07_span_done(ctx, "s07_finalize_description", "S-07 finalize: description synthesis complete.")
        except Exception as _desc_e:
            _s07_span_fail(ctx, "s07_finalize_description", _desc_e)
            logger.debug("[%s] finalize: description synthesis failed: %s",
                         ctx.job_id, _desc_e)

    if ctx.vocab:
        _s07_span_start(ctx, "s07_finalize_vocab_persist", "S-07 finalize: persisting final vocab...")
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/vocab.json",
                json.dumps(ctx.vocab).encode(),
            )
            _s07_span_done(ctx, "s07_finalize_vocab_persist", "S-07 finalize: final vocab persisted.")
        except Exception as _vfin_e:
            _s07_span_fail(ctx, "s07_finalize_vocab_persist", _vfin_e)
            logger.debug("[%s] finalize: final vocab persist failed: %s",
                         ctx.job_id, _vfin_e)

    # T-16 evidence: build schema_evolution.json by comparing schema snapshots
    _s07_span_start(ctx, "s07_finalize_schema_evolution", "S-07 finalize: writing schema evolution evidence...")
    try:
        import hashlib as _hashlib

        def _blob_hash_record(blob_name: str) -> dict:
            try:
                raw = _download_blob_bounded(
                    ARTIFACT_CONTAINER,
                    f"{ctx.job_id}/{blob_name}",
                    timeout_sec=_S07_SCHEMA_EVOLUTION_BLOB_TIMEOUT_SEC,
                )
                return {
                    "present": True,
                    "sha256": _hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest(),
                    "timed_out": False,
                    "error": "",
                }
            except TimeoutError as exc:
                return {"present": False, "sha256": None, "timed_out": True, "error": str(exc)}
            except Exception as exc:
                return {"present": False, "sha256": None, "timed_out": False, "error": type(exc).__name__}

        _evo_checkpoints = [
            ("t0", "mcp_schema_t0.json"),
            ("post_enrichment", "mcp_schema_post_enrichment.json"),
            ("post_discovery", "mcp_schema_post_discovery.json"),
            ("post_gap_resolution", "mcp_schema_post_gap_resolution.json"),
            ("final", "mcp_schema.json"),
        ]
        _evo: list[dict] = []
        _prev_hash: str | None = None
        for label, blob in _evo_checkpoints:
            record = _blob_hash_record(blob)
            h = record.get("sha256")
            _evo.append({
                "stage": label,
                "blob": blob,
                "present": bool(record.get("present")),
                "sha256": h,
                "changed": h is not None and _prev_hash is not None and h != _prev_hash,
                "timed_out": bool(record.get("timed_out")),
                "error": record.get("error") or "",
            })
            if h is not None:
                _prev_hash = h
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/schema_evolution.json",
            json.dumps(_evo, indent=2).encode(),
        )
        logger.info("[%s] finalize: schema_evolution.json written (%d checkpoints)",
                    ctx.job_id, len(_evo))
        _s07_span_done(ctx, "s07_finalize_schema_evolution", "S-07 finalize: schema evolution evidence written.")
    except Exception as _sevo_e:
        _s07_span_fail(ctx, "s07_finalize_schema_evolution", _sevo_e)
        logger.debug("[%s] finalize: schema_evolution.json failed: %s", ctx.job_id, _sevo_e)

    _s07_span_start(ctx, "s07_finalize_status_persist", "S-07 finalize: persisting final status suggestion...")
    current = _get_job_status(ctx.job_id) or {}
    _open_questions = current.get("explore_questions") or []
    _has_unanswered = any(
        isinstance(q, dict)
        and not (bool(q.get("answered")) or bool(str(q.get("answer") or "").strip()))
        for q in _open_questions
    )
    _elapsed_s = max(0.0, time.time() - ctx.run_started_at)
    _was_canceled = _cancel_requested(ctx.job_id)
    _final_phase = "canceled" if _was_canceled else (
        "awaiting_clarification" if _has_unanswered else "done"
    )
    _final_message = (
        "Finalize complete — cancellation acknowledged; awaiting worker close"
        if _was_canceled
        else (
            "Finalize complete — awaiting clarification verdict persistence"
            if _has_unanswered
            else "Finalize complete — awaiting macro verdict persistence"
        )
    )
    _persist_job_status(
        ctx.job_id,
        {
            **current,
            # Harmonize/finalize can determine the likely final verdict shape,
            # but the worker should not advertise a terminal phase until the
            # macro verdict and final job-status close have actually landed.
            "explore_phase": "exploring",
            "explore_stage": _S07_STAGE,
            "explore_progress": f"{ctx.explored_count()}/{ctx.total}",
            "explore_message": _final_message,
            "explore_span": "s07_finalize_status_persist",
            "explore_span_state": "done",
            "explore_span_message": _final_message,
            "explore_span_updated_at": time.time(),
            "explore_last_run_seconds": round(_elapsed_s, 2),
            "sentinel_new_codes_this_run": ctx.sentinel_new_codes_this_run,
            "final_phase_suggestion": _final_phase,
            "updated_at": time.time(),
        },
        # This status is a diagnostic phase suggestion, not the terminal
        # worker verdict. It must never block close-path verdict persistence.
        sync=False,
    )
    logger.info("[%s] finalize: finished %d/%d functions (phase=%s)",
                ctx.job_id, ctx.explored_count(), ctx.total, _final_phase)
