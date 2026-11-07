from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_bytes_if_exists(path: Path | None) -> bytes | None:
    if path is None or not path.exists():
        return None
    return path.read_bytes()


def _resolve(root: Path, rel: str | None) -> Path | None:
    if not rel:
        return None
    return root / rel


def _row_base(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": str(row.get("check_id") or row.get("difference_claim_id") or ""),
        "surface": str(row.get("surface") or ""),
        "bucket": str(row.get("bucket") or ""),
        "baseline_source": row.get("baseline_source"),
        "candidate_source": row.get("candidate_source"),
        "expected_contract": str(row.get("expected_contract") or ""),
        "verdict": "blocked_regression",
        "difference_claim_id": row.get("difference_claim_id"),
        "notes": [],
    }


def _simplify_stage_index(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in list(payload.get("stages") or []):
        if not isinstance(row, dict):
            continue
        stage_id = str(row.get("id") or "")
        if not stage_id.startswith("S-"):
            continue
        rows.append(
            {
                "id": stage_id,
                "status": str(row.get("status") or ""),
                "skip_reason": str(row.get("skip_reason") or ""),
            }
        )
    return rows


def _unexpected_stage_ids(payload: dict[str, Any]) -> list[str]:
    unexpected: list[str] = []
    for row in list(payload.get("stages") or []):
        if not isinstance(row, dict):
            continue
        stage_id = str(row.get("id") or "")
        if stage_id and not stage_id.startswith("S-"):
            unexpected.append(stage_id)
    return sorted(unexpected)


def _simplify_transition_index(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in list(payload.get("transitions") or []):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "id": str(row.get("id") or ""),
                "status": str(row.get("status") or ""),
            }
        )
    return rows


def _evaluate_preserved_check(row: dict[str, Any], baseline_root: Path, candidate_root: Path) -> dict[str, Any]:
    result = _row_base(row)
    mode = str(row.get("compare_mode") or "").strip()
    baseline_path = _resolve(baseline_root, row.get("baseline_source"))
    candidate_path = _resolve(candidate_root, row.get("candidate_source"))

    if mode == "all_candidate_paths_exist":
        missing = [
            rel
            for rel in list(row.get("candidate_paths") or [])
            if not (candidate_root / str(rel)).exists()
        ]
        if missing:
            result["notes"].append(f"missing candidate paths: {missing}")
            return result
        result["verdict"] = "preserved_contract_pass"
        return result

    if mode == "stage_index_equivalent":
        if not baseline_path or not candidate_path or not baseline_path.exists() or not candidate_path.exists():
            result["notes"].append("stage-index source missing")
            return result
        baseline_payload = _read_json(baseline_path)
        candidate_payload = _read_json(candidate_path)
        unexpected = _unexpected_stage_ids(candidate_payload)
        if unexpected:
            result["notes"].append(f"unexpected non-7-stage rows in candidate stage-index: {unexpected}")
            return result
        if _simplify_stage_index(baseline_payload) != _simplify_stage_index(candidate_payload):
            result["notes"].append("stage-index semantic drift")
            return result
        result["verdict"] = "preserved_contract_pass"
        return result

    if mode == "transition_index_equivalent":
        if not baseline_path or not candidate_path or not baseline_path.exists() or not candidate_path.exists():
            result["notes"].append("transition-index source missing")
            return result
        if _simplify_transition_index(_read_json(baseline_path)) != _simplify_transition_index(_read_json(candidate_path)):
            result["notes"].append("transition-index semantic drift")
            return result
        result["verdict"] = "preserved_contract_pass"
        return result

    if mode == "stage_row_equivalent":
        row_id = str(row.get("row_id") or "")
        if not baseline_path or not candidate_path or not baseline_path.exists() or not candidate_path.exists():
            result["notes"].append("stage-row source missing")
            return result
        baseline_rows = {item["id"]: item for item in _simplify_stage_index(_read_json(baseline_path))}
        candidate_rows = {item["id"]: item for item in _simplify_stage_index(_read_json(candidate_path))}
        if baseline_rows.get(row_id) != candidate_rows.get(row_id):
            result["notes"].append(f"stage row drift for {row_id}")
            return result
        result["verdict"] = "preserved_contract_pass"
        return result

    if mode == "reader_checks_all_pass":
        if not candidate_path or not candidate_path.exists():
            result["notes"].append("reader check artifact missing")
            return result
        payload = _read_json(candidate_path)
        rows = list(payload.get("checks") or [])
        observed_ids = {str(item.get("id") or "") for item in rows if str(item.get("id") or "")}
        required_ids = {str(item) for item in list(row.get("required_reader_ids") or []) if str(item)}
        missing_ids = sorted(required_ids - observed_ids)
        if missing_ids:
            result["notes"].append(f"required reader ids missing: {missing_ids}")
            return result
        failing = [str(item.get("id") or "") for item in rows if not bool(item.get("pass"))]
        if failing:
            result["notes"].append(f"reader checks failed: {failing}")
            return result
        result["verdict"] = "preserved_contract_pass"
        return result

    if mode == "root_integrity_pass":
        if not candidate_path or not candidate_path.exists():
            result["notes"].append("root integrity artifact missing")
            return result
        payload = _read_json(candidate_path)
        clean_root = str(payload.get("clean_root_or_not") or "").strip().lower()
        stale_or_mixed = str(payload.get("stale_or_mixed_root") or "").strip().lower()
        if clean_root not in {"pass", "true", "clean"} or stale_or_mixed not in {"pass", "false", "clean"}:
            result["notes"].append("root integrity contract not satisfied")
            return result
        result["verdict"] = "preserved_contract_pass"
        return result

    result["notes"].append(f"unknown compare mode: {mode}")
    return result


def _evaluate_delta_row(
    row: dict[str, Any],
    baseline_root: Path,
    candidate_root: Path,
    *,
    improvement: bool,
) -> dict[str, Any]:
    result = _row_base(row)
    mode = str(row.get("compare_mode") or "file_diff_exists").strip()
    baseline_path = _resolve(baseline_root, row.get("baseline_source"))
    candidate_path = _resolve(candidate_root, row.get("candidate_source"))

    if not improvement and not str(row.get("justification") or "").strip():
        result["verdict"] = "unclassified_difference"
        result["notes"].append("missing explicit difference justification")
        return result

    if mode == "candidate_exists":
        if candidate_path is None or not candidate_path.exists():
            result["notes"].append("candidate artifact missing")
            result["verdict"] = "blocked_regression"
            return result
        result["verdict"] = "improvement_confirmed" if improvement else "explicit_difference_accepted"
        return result

    if mode == "file_diff_exists":
        baseline_bytes = _read_bytes_if_exists(baseline_path)
        candidate_bytes = _read_bytes_if_exists(candidate_path)
        if candidate_bytes is None:
            result["notes"].append("candidate artifact missing")
            result["verdict"] = "blocked_regression"
            return result
        if baseline_bytes is None:
            result["verdict"] = "improvement_confirmed" if improvement else "explicit_difference_accepted"
            result["notes"].append("baseline artifact absent; candidate treated as additive")
            return result
        if baseline_bytes == candidate_bytes:
            result["verdict"] = "blocked_regression" if improvement else "unclassified_difference"
            result["notes"].append("expected changed surface did not differ")
            return result
        result["verdict"] = "improvement_confirmed" if improvement else "explicit_difference_accepted"
        return result

    result["notes"].append(f"unknown compare mode: {mode}")
    result["verdict"] = "blocked_regression"
    return result


def compare_phase1_migration(
    baseline_session_root: str | Path,
    candidate_session_root: str | Path,
    difference_claims_artifact: str | Path,
) -> dict[str, Any]:
    baseline_root = Path(baseline_session_root)
    candidate_root = Path(candidate_session_root)
    claims_path = Path(difference_claims_artifact)
    claims = _read_json(claims_path)

    preserved_rows = [
        _evaluate_preserved_check(row, baseline_root, candidate_root)
        for row in list(claims.get("preserved_contract_checks") or [])
    ]
    improvement_rows = [
        _evaluate_delta_row(row, baseline_root, candidate_root, improvement=True)
        for row in list(claims.get("improvement_claims") or [])
    ]
    explicit_rows = [
        _evaluate_delta_row(row, baseline_root, candidate_root, improvement=False)
        for row in list(claims.get("difference_claims") or [])
    ]

    classified_surfaces = {
        str(row.get("surface") or "").strip()
        for row in list(claims.get("improvement_claims") or []) + list(claims.get("difference_claims") or [])
        if str(row.get("surface") or "").strip()
    }
    required_classification = {
        str(item).strip()
        for item in list(claims.get("required_classification_surfaces") or [])
        if str(item).strip()
    }
    unclassified_surfaces = sorted(required_classification - classified_surfaces)
    blocked_regressions = [
        row for row in preserved_rows + improvement_rows + explicit_rows if row["verdict"] == "blocked_regression"
    ]
    unclassified_differences = [
        row for row in preserved_rows + improvement_rows + explicit_rows if row["verdict"] == "unclassified_difference"
    ]
    unclassified_differences.extend(
        [
            {
                "check_id": f"required-classification:{surface}",
                "surface": surface,
                "bucket": "required_classification",
                "baseline_source": None,
                "candidate_source": None,
                "expected_contract": "surface must be explicitly classified before closeout",
                "verdict": "unclassified_difference",
                "difference_claim_id": None,
                "notes": ["surface missing from improvement or explicit-difference claims"]
            }
            for surface in unclassified_surfaces
        ]
    )

    overall_verdict = "preserved_contract_pass"
    if blocked_regressions:
        overall_verdict = "blocked_regression"
    elif unclassified_differences:
        overall_verdict = "unclassified_difference"
    elif any(row["verdict"] == "improvement_confirmed" for row in improvement_rows):
        overall_verdict = "improvement_confirmed"
    elif any(row["verdict"] == "explicit_difference_accepted" for row in explicit_rows):
        overall_verdict = "explicit_difference_accepted"

    return {
        "version": "1.0",
        "baseline_session_root": str(baseline_root),
        "candidate_session_root": str(candidate_root),
        "difference_claims_artifact": str(claims_path),
        "overall_verdict": overall_verdict,
        "preserved_contract_checks": preserved_rows,
        "improvement_checks": improvement_rows,
        "explicit_difference_checks": explicit_rows,
        "blocked_regressions": blocked_regressions,
        "unclassified_differences": unclassified_differences,
    }


def write_comparison_result(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
