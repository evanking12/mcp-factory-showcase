from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (str(SCRIPTS_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from harness_lib import collector  # noqa: E402


REQUIRED_CONTRACT_FILES = (
    "session-meta.json",
    "stage-index.json",
    "transition-index.json",
    "cohesion-report.json",
)

SCHEMA_REPLAY_NORMALIZATION_TARGETS = (
    "stage-01-probe-loop/schema-after.json",
    "stage-02-synthesis/schema-after.json",
    "stage-03-gap-resolution/schema-after.json",
    "stage-04-clarification/schema-after.json",
    "evidence/stage-05-backfill/schema-post-backfill.json",
    "evidence/stage-07-finalize/schema-final.json",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _required_contract_state(session_dir: Path) -> dict[str, Any]:
    missing: list[str] = []
    invalid_json: list[str] = []
    for name in REQUIRED_CONTRACT_FILES:
        path = session_dir / name
        if not path.exists():
            missing.append(name)
            continue
        try:
            _read_json(path)
        except Exception:
            invalid_json.append(name)
    return {
        "valid": not missing and not invalid_json,
        "missing": missing,
        "invalid_json": invalid_json,
    }


def _summarize_authority(session_dir: Path) -> dict[str, Any]:
    schema = _read_json_or_none(session_dir / "schema-handoff-audit.json")
    transition = _read_json_or_none(session_dir / "transition-contract-audit.json")
    run_validity = _read_json_or_none(session_dir / "run-validity.json")
    cohesion = _read_json_or_none(session_dir / "cohesion-report.json")

    schema_summary = schema.get("summary") if isinstance(schema, dict) else {}
    transition_summary = transition.get("summary") if isinstance(transition, dict) else {}
    run_gate_results = run_validity.get("gate_results") if isinstance(run_validity, dict) else {}
    cohesion_gates = cohesion.get("gates") if isinstance(cohesion, dict) else {}

    return {
        "schema_handoff": {
            "exists": isinstance(schema, dict),
            "regression_count": _safe_int((schema_summary or {}).get("regression_count")),
            "drop_to_zero_count": _safe_int((schema_summary or {}).get("drop_to_zero_count")),
            "silent_function_loss_count": _safe_int(
                (schema_summary or {}).get("silent_function_loss_count")
            ),
        },
        "transition_contract": {
            "exists": isinstance(transition, dict),
            "valid": bool((transition_summary or {}).get("valid", False)),
            "fail_count": _safe_int((transition_summary or {}).get("fail_count")),
        },
        "run_validity": {
            "exists": isinstance(run_validity, dict),
            "valid": bool((run_validity or {}).get("valid", False))
            if isinstance(run_validity, dict)
            else False,
            "reasons": list((run_validity or {}).get("reasons") or [])
            if isinstance(run_validity, dict)
            else [],
            "gate_results": run_gate_results if isinstance(run_gate_results, dict) else {},
        },
        "cohesion": {
            "exists": isinstance(cohesion, dict),
            "hard_fail": bool((cohesion_gates or {}).get("hard_fail", False)),
        },
    }


def _authority_deltas(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_schema = before.get("schema_handoff") or {}
    after_schema = after.get("schema_handoff") or {}
    before_transition = before.get("transition_contract") or {}
    after_transition = after.get("transition_contract") or {}
    before_validity = before.get("run_validity") or {}
    after_validity = after.get("run_validity") or {}
    return {
        "run_validity_valid_before": bool(before_validity.get("valid", False)),
        "run_validity_valid_after": bool(after_validity.get("valid", False)),
        "run_validity_changed": bool(before_validity.get("valid", False))
        != bool(after_validity.get("valid", False)),
        "schema_handoff_regression_count_before": _safe_int(before_schema.get("regression_count")),
        "schema_handoff_regression_count_after": _safe_int(after_schema.get("regression_count")),
        "schema_handoff_drop_to_zero_count_before": _safe_int(before_schema.get("drop_to_zero_count")),
        "schema_handoff_drop_to_zero_count_after": _safe_int(after_schema.get("drop_to_zero_count")),
        "transition_contract_fail_count_before": _safe_int(before_transition.get("fail_count")),
        "transition_contract_fail_count_after": _safe_int(after_transition.get("fail_count")),
    }


def _next_unique_name(base: str, used: set[str]) -> str:
    suffix = 2
    while f"{base}_{suffix}" in used:
        suffix += 1
    return f"{base}_{suffix}"


def _normalize_schema_tool_required(params: dict[str, Any]) -> list[dict[str, Any]]:
    props = params.get("properties")
    required = params.get("required")
    if not isinstance(props, dict) or not isinstance(required, list):
        return []

    used = {str(name) for name in props.keys()}
    seen_required: set[str] = set()
    normalized_required: list[str] = []
    changes: list[dict[str, Any]] = []

    for index, raw_name in enumerate(required):
        name = str(raw_name or "").strip()
        if not name:
            normalized_required.append(name)
            continue
        if name not in seen_required:
            seen_required.add(name)
            normalized_required.append(name)
            continue
        if name not in props:
            normalized_required.append(name)
            continue

        replacement = _next_unique_name(name, used | set(normalized_required))
        props[replacement] = dict(props[name]) if isinstance(props[name], dict) else props[name]
        normalized_required.append(replacement)
        used.add(replacement)
        seen_required.add(replacement)
        changes.append(
            {
                "index": index,
                "from": name,
                "to": replacement,
                "reason": "duplicate_required_schema_slot_preserved",
            }
        )

    if changes:
        params["required"] = normalized_required
    return changes


def _normalize_schema_payload(payload: Any, *, rel_path: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return []
    changes: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        params = fn.get("parameters")
        if not isinstance(params, dict):
            continue
        for change in _normalize_schema_tool_required(params):
            changes.append(
                {
                    "path": rel_path,
                    "function": str(fn.get("name") or ""),
                    **change,
                }
            )
    return changes


def _normalize_replay_schema_artifacts(session_dir: Path) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for rel in SCHEMA_REPLAY_NORMALIZATION_TARGETS:
        path = session_dir / rel
        if not path.exists():
            continue
        try:
            payload = _read_json(path)
        except Exception:
            continue
        path_changes = _normalize_schema_payload(payload, rel_path=rel)
        if not path_changes:
            continue
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        changes.extend(path_changes)
    if changes:
        (session_dir / "schema-replay-normalization.json").write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "claim_ceiling": "checkpoint_replay_only",
                    "changes": changes,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return changes


def _classify_replay(
    *,
    source_contract_state: dict[str, Any],
    collect_exit_code: int | None,
    after: dict[str, Any] | None,
) -> str:
    if not source_contract_state.get("valid", False):
        return "source_session_contract_invalid"
    if collect_exit_code is None or after is None:
        return "replay_collect_failed"
    after_schema = after.get("schema_handoff") or {}
    after_validity = after.get("run_validity") or {}
    if _safe_int(after_schema.get("regression_count")) > 0 or _safe_int(
        after_schema.get("drop_to_zero_count")
    ) > 0:
        return "schema_handoff_regression_persists"
    if not bool(after_validity.get("valid", False)):
        return "run_validity_still_false"
    if int(collect_exit_code) != 0:
        return "replay_collect_failed"
    return "checkpoint_replay_green"


def replay_session_closeout(
    *,
    source_session_dir: Path,
    output_root: Path,
    mode: str = "strict",
    component: str = "checkpoint_replay",
    job_id: str = "",
) -> dict[str, Any]:
    source_session_dir = source_session_dir.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    replay_session_dir = output_root / "replayed-session"
    result_path = output_root / "checkpoint-replay-result.json"

    if not source_session_dir.exists() or not source_session_dir.is_dir():
        result = {
            "version": "1.0",
            "source_session_dir": str(source_session_dir),
            "replay_session_dir": str(replay_session_dir),
            "mode": mode,
            "claim_ceiling": "checkpoint_replay_only",
            "product_green_claimed": False,
            "safe_to_compare": False,
            "collect_exit_code": None,
            "before": {},
            "after": {},
            "authority_deltas": {},
            "blocking_signal": "source_session_missing",
        }
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    source_contract_state = _required_contract_state(source_session_dir)
    before = _summarize_authority(source_session_dir)

    if replay_session_dir.exists():
        shutil.rmtree(replay_session_dir)
    shutil.copytree(source_session_dir, replay_session_dir)
    schema_replay_normalization = _normalize_replay_schema_artifacts(replay_session_dir)

    collect_exit_code: int | None = None
    collect_error = ""
    if source_contract_state.get("valid", False):
        try:
            collect_exit_code = collector.collect_session(
                replay_session_dir,
                mode=mode,
                component=component,
                job_id=job_id or f"checkpoint-replay-{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                folder=str(output_root.name),
                note="checkpoint_replay_for_targeted_repairs_v1",
            )
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            collect_error = f"{type(exc).__name__}: {exc}"

    after = _summarize_authority(replay_session_dir)
    blocking_signal = _classify_replay(
        source_contract_state=source_contract_state,
        collect_exit_code=collect_exit_code,
        after=after,
    )

    result = {
        "version": "1.0",
        "source_session_dir": str(source_session_dir),
        "replay_session_dir": str(replay_session_dir),
        "mode": mode,
        "component": component,
        "claim_ceiling": "checkpoint_replay_only",
        "product_green_claimed": False,
        "safe_to_compare": blocking_signal == "checkpoint_replay_green",
        "source_contract_state": source_contract_state,
        "schema_replay_normalization": schema_replay_normalization,
        "collect_exit_code": collect_exit_code,
        "collect_error": collect_error,
        "before": before,
        "after": after,
        "authority_deltas": _authority_deltas(before, after),
        "blocking_signal": blocking_signal,
    }
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay saved-session closeout on a copied session directory."
    )
    parser.add_argument("--source-session-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--mode", choices=("strict", "compatibility"), default="strict")
    parser.add_argument("--component", default="checkpoint_replay")
    parser.add_argument("--job-id", default="")
    args = parser.parse_args(argv)

    result = replay_session_closeout(
        source_session_dir=Path(args.source_session_dir),
        output_root=Path(args.output_root),
        mode=args.mode,
        component=args.component,
        job_id=args.job_id,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("blocking_signal") == "checkpoint_replay_green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
