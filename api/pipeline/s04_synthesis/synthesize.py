"""api.pipeline.s04_synthesis.synthesize -- Phase 6: API reference synthesis."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _load_findings, _upload_to_blob, _get_current_invocables,
)
from api.pipeline.core.helpers import (
    _ctx_explored_count, _set_explore_status, _snapshot_schema_stage, _save_stage_context,
)
from api.pipeline.core.prompts import _synthesize
from api.pipeline.core.vocab import _backfill_schema_from_synthesis

logger = logging.getLogger("mcp_factory.api")


def _unique_function_names(findings: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        fn = str(finding.get("function") or "").strip()
        if not fn or fn in seen:
            continue
        seen.add(fn)
        names.append(fn)
    return names


def _function_names_missing_from_report(report: str, findings: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for fn in _unique_function_names(findings):
        if fn not in report:
            missing.append(fn)
    return missing


def _build_missing_function_supplement(ctx, findings: list[dict[str, Any]], missing_names: list[str]) -> str:
    if not missing_names:
        return ""

    inv_by_name = {str(inv.get("name") or ""): inv for inv in (ctx.invocables or [])}
    finding_by_name: dict[str, dict[str, Any]] = {}
    for finding in findings:
        fn = str(finding.get("function") or "").strip()
        if fn and fn not in finding_by_name:
            finding_by_name[fn] = finding

    lines: list[str] = [
        "",
        "## Supplemental Function Coverage",
        "",
        "The synthesis report omitted these finding-backed functions, so they are appended deterministically to preserve contract coverage.",
        "",
    ]
    for fn in missing_names:
        finding = finding_by_name.get(fn) or {}
        inv = inv_by_name.get(fn) or {}
        lines.append(f"### {fn}")
        lines.append(f"- Status: `{finding.get('status', 'unknown')}`")
        lines.append(f"- Summary: {str(finding.get('finding') or 'No finding text recorded.')}")
        working_call = finding.get("working_call")
        if working_call:
            lines.append(f"- Working example: `{working_call}`")
        params = inv.get("parameters") or []
        if params:
            lines.append("- Parameters:")
            for param in params:
                if not isinstance(param, dict):
                    continue
                pname = str(param.get("name") or "param")
                ptype = str(param.get("json_type") or param.get("type") or "string")
                pdesc = str(param.get("description") or "").strip() or "No parameter description recorded."
                lines.append(f"  - `{pname}` (`{ptype}`): {pdesc}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_fallback_api_reference(ctx, findings: list[dict]) -> str:
    """Build a deterministic markdown reference when LLM synthesis returns nothing."""
    inv_by_name = {str(inv.get("name") or ""): inv for inv in (ctx.invocables or [])}
    id_formats = [str(x) for x in ((ctx.vocab or {}).get("id_formats") or []) if str(x).strip()]
    status_values = [str(x) for x in (((ctx.vocab or {}).get("value_semantics") or {}).get("status_values") or []) if str(x).strip()]
    error_codes = (ctx.vocab or {}).get("error_codes") or {}

    init_functions = [name for name in inv_by_name if re.search(r"init(ializ)?|startup|setup|open|connect", name, re.I)]
    successful = [f for f in findings if str(f.get("status") or "") == "success"]
    unresolved = [f for f in findings if str(f.get("status") or "") != "success"]

    lines: list[str] = [
        "# API Reference",
        "",
        "## Overview",
        "Fallback API reference generated from persisted findings because LLM synthesis did not return a document.",
        "",
        "## Data Model",
    ]
    if id_formats:
        lines.append(f"- Observed entity identifiers: {', '.join(id_formats[:8])}")
    if status_values:
        lines.append(f"- Observed status values: {', '.join(status_values[:8])}")
    if not id_formats and not status_values:
        lines.append("- No strong shared entity model was inferred from this run.")

    lines.extend(["", "## Initialization"])
    if init_functions:
        lines.append(f"- Initialize first with `{init_functions[0]}()` before probing dependent functions.")
    else:
        lines.append("- No explicit initialization function was recovered in this run.")

    lines.extend(["", "## Function Reference"])

    categories = {
        "Read": [],
        "Write": [],
        "Utility": [],
    }
    for finding in findings:
        fn = str(finding.get("function") or "")
        if not fn:
            continue
        if re.search(r"process|apply|void|cancel|reserve", fn, re.I):
            categories["Write"].append(finding)
        elif re.search(r"get|lookup|check|calculate", fn, re.I):
            categories["Read"].append(finding)
        else:
            categories["Utility"].append(finding)

    for label in ("Read", "Write", "Utility"):
        entries = categories[label]
        if not entries:
            continue
        lines.extend([f"### {label} Functions", ""])
        for finding in entries:
            fn = str(finding.get("function") or "")
            inv = inv_by_name.get(fn) or {}
            lines.append(f"#### `{fn}`")
            lines.append(f"- Status: `{finding.get('status', 'unknown')}`")
            lines.append(f"- Summary: {str(finding.get('finding') or 'No finding text recorded.')}")
            working_call = finding.get("working_call")
            if working_call:
                lines.append(f"- Working example: `{working_call}`")
            params = inv.get("parameters") or []
            if params:
                lines.append("- Parameters:")
                for param in params:
                    if not isinstance(param, dict):
                        continue
                    pname = str(param.get("name") or "param")
                    ptype = str(param.get("json_type") or param.get("type") or "string")
                    pdesc = str(param.get("description") or "").strip() or "No parameter description recorded."
                    lines.append(f"  - `{pname}` (`{ptype}`): {pdesc}")
            lines.append("")

    lines.extend(["## Error Code Reference", ""])
    if error_codes:
        for code, meaning in error_codes.items():
            lines.append(f"- `{code}`: {meaning}")
    else:
        lines.append("- No DLL-specific error code table was persisted for this run.")

    lines.extend(["", "## Known Limitations", ""])
    if unresolved:
        for finding in unresolved:
            lines.append(
                f"- `{finding.get('function', 'unknown')}` remained `{finding.get('status', 'unknown')}`: "
                f"{finding.get('finding', 'no details recorded')}"
            )
    else:
        lines.append("- No unresolved functions remained in this run.")

    return "\n".join(lines).strip() + "\n"


def _run_phase_6_synthesize(ctx) -> str | None:
    """Generate the API reference markdown from all findings."""
    _syn_findings = _load_findings(ctx.job_id)
    if not _syn_findings:
        return None

    try:
        _ctx_lines = [
            "=== SYNTHESIS PHASE MODEL CONTEXT ===",
            f"Functions: {len(ctx.invocables)}",
            f"Findings: {len(_syn_findings)}",
            "",
            "--- Findings ---",
        ]
        for _f in _syn_findings:
            _status = _f.get("status", "?")
            _fn = _f.get("function", "?")
            _wc = _f.get("working_call") or {}
            _ctx_lines.append(
                f"  {_fn}: {_status}"
                + (f" | working_call={_wc}" if _wc else "")
            )
        _ctx_lines.append("")
        _ctx_lines.append("--- Vocab (domain terms) ---")
        for _k, _v in list((ctx.vocab or {}).items())[:15]:
            _ctx_lines.append(f"  {_k}: {str(_v)[:80]}")
        _save_stage_context(ctx.job_id, "model_context_phase_06_synthesis.txt",
                            "\n".join(_ctx_lines))
    except Exception as _mce:
        logger.debug("[%s] phase6: model context save failed: %s", ctx.job_id, _mce)

    try:
        logger.info("[%s] phase6: synthesizing API reference (%d fns)...",
                    ctx.job_id, len(_syn_findings))
        _set_explore_status(ctx.job_id, _ctx_explored_count(ctx), ctx.total,
                            "Synthesizing API reference...")
        try:
            _syn_snapshot = {
                "function_count": len(ctx.invocables),
                "findings_count": len(_syn_findings),
                "findings": _syn_findings,
                "vocab": ctx.vocab,
            }
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/evidence/stage-04-synthesis/synthesis-input-snapshot.json",
                json.dumps(_syn_snapshot, indent=2).encode(),
            )
        except Exception as _snap_e:
            logger.debug("[%s] synthesis-input-snapshot write failed: %s",
                         ctx.job_id, _snap_e)

        _report = _synthesize(
            ctx.client, ctx.model, _syn_findings,
            vocab=ctx.vocab, sentinels=ctx.sentinels,
        )
        if not _report:
            _report = _build_fallback_api_reference(ctx, _syn_findings)
            try:
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{ctx.job_id}/evidence/stage-04-synthesis/synthesis-fallback.json",
                    json.dumps(
                        {
                            "fallback_used": True,
                            "reason": "llm_synthesis_empty_or_failed",
                            "function_count": len(_syn_findings),
                        },
                        indent=2,
                    ).encode(),
                )
            except Exception as _fb_emit_e:
                logger.debug("[%s] phase6: synthesis fallback marker write failed: %s",
                             ctx.job_id, _fb_emit_e)
        else:
            _missing_names = _function_names_missing_from_report(_report, _syn_findings)
            if _missing_names:
                _report = _report.rstrip() + "\n\n" + _build_missing_function_supplement(
                    ctx,
                    _syn_findings,
                    _missing_names,
                ).lstrip()

        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/api_reference.md",
            _report.encode("utf-8"),
        )
        logger.info("[%s] phase6: api_reference.md saved to blob", ctx.job_id)

        try:
            _fn_names_found = [f.get("function", "") for f in _syn_findings if f.get("function")]
            _coverage_entries = [
                {"function": _fn_c, "in_api_reference": bool(_fn_c and _fn_c in _report)}
                for _fn_c in _fn_names_found
            ]
            _covered_count = sum(1 for e in _coverage_entries if e["in_api_reference"])
            _cov_check = {
                "total_functions": len(_fn_names_found),
                "covered_in_report": _covered_count,
                "coverage_pct": (
                    round(100.0 * _covered_count / len(_fn_names_found), 1)
                    if _fn_names_found else 0.0
                ),
                "functions": _coverage_entries,
            }
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/evidence/stage-04-synthesis/synthesis-coverage-check.json",
                json.dumps(_cov_check, indent=2).encode(),
            )
        except Exception as _cc_e:
            logger.debug("[%s] phase6: synthesis-coverage-check write failed: %s",
                         ctx.job_id, _cc_e)

        _refreshed = _get_current_invocables(ctx.job_id)
        if _refreshed:
            ctx.invocables = _refreshed
            ctx.inv_map = {iv["name"]: iv for iv in ctx.invocables}

        _snapshot_schema_stage(ctx.job_id, "mcp_schema_post_enrichment.json")
        return _report
    except Exception as _syn_e:
        logger.debug("[%s] phase6: synthesis failed: %s", ctx.job_id, _syn_e)
        return None
