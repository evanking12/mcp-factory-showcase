from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.spectrum_compiled_ingest import SPECTRUM_COMPILED_SUITE_ID  # noqa: E402
from scripts.ops.nightly_groundtruth import write_json  # noqa: E402
from scripts.runs.run_spectrum_compiled_medium01 import (  # noqa: E402
    _parse_job_ids,
    _parse_target_names,
    run_spectrum_compiled_medium01,
)

SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID = "medium-01-product-route"
SPECTRUM_COMPILED_MEDIUM01_PRODUCT_VARIANT_ID = "compiled_medium01_product_route"


def _setup_failure_reason(exc: BaseException) -> str:
    text = str(exc)
    if text.startswith("api_identity_failed:"):
        return "api_identity_unavailable"
    if text.startswith("bridge_identity_failed:"):
        reason = text.split(":", 1)[1].strip()
        return reason or "bridge_identity_unavailable"
    return "medium01_product_runner_setup_failed"


def _write_setup_failure_result(
    *,
    output_root: str | Path | None,
    exc: BaseException,
) -> dict[str, Any]:
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT
        / "sessions"
        / "design_suite"
        / "compiled_ingest"
        / SPECTRUM_COMPILED_SUITE_ID
        / SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID
        / time.strftime("%Y%m%d-%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    reason_code = _setup_failure_reason(exc)
    run_authority = {
        "schema_version": "1.0.0",
        "status": "non_decision_bearing",
        "reason_code": reason_code,
        "failure_domain": "medium01_product_runner_setup",
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "decision_bearing": False,
        "blocking_reasons": [reason_code],
    }
    terminalization = {
        "schema_version": "1.0.0",
        "terminalization_kind": "runner_setup_failed",
        "kind": "runner_setup_failed",
        "reason": {"code": reason_code, "message": str(exc)},
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
    }
    run_record = {
        "job_id": "",
        "status": "error",
        "phase": "setup",
        "target": "suite_setup",
        "failure_domain": "medium01_product_runner_setup",
        "run_dir": str(output_dir),
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "run_authority": run_authority,
        "measurement_terminalization": terminalization,
        "blocking_signal": reason_code,
    }
    summary = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID,
        "entry_surface": "upload",
        "product_route_required": True,
        "green_contract_level": "not_green",
        "product_green_eligible": False,
        "route_authority_required": True,
        "ghidra_required": True,
        "route_authority_present": False,
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "blocking_signal": reason_code,
        "run_records": [run_record],
    }
    report = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID,
        "binary_ingest_proof_succeeded": False,
        "semantic_checkpoint_alignment_succeeded": False,
        "green_contract_level": "not_green",
        "product_green_eligible": False,
        "blocking_signal": reason_code,
        "comparison_note": "Medium01 product-route proof did not start because runner setup failed closed.",
    }
    write_json(output_dir / "run-authority.json", run_authority)
    write_json(output_dir / "measurement-terminalization.json", terminalization)
    write_json(output_dir / "run_result.json", run_record)
    write_json(output_dir / "compiled-ingest-summary.json", summary)
    write_json(output_dir / "compiled-ingest-compare-report.json", report)
    return {
        "output_dir": str(output_dir),
        "summary": summary,
        "report": report,
        "semantic_continuation": None,
        "checkpoint_packet": None,
    }


def run_spectrum_compiled_medium01_product(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
    stop_after_first_failure: bool = False,
    target_names: list[str] | None = None,
    prior_job_id: str = "",
    cross_dll_prior_job_ids: list[str] | None = None,
    poll_sec: int = 2,
    analyze_timeout_sec: int = 240,
    explore_timeout_sec: int = 360,
    stuck_seconds: int = 120,
) -> dict[str, Any]:
    try:
        return run_spectrum_compiled_medium01(
            api_url=api_url,
            api_key=api_key,
            bridge_url=bridge_url,
            bridge_key=bridge_key,
            output_root=output_root,
            stop_after_first_failure=stop_after_first_failure,
            target_names=target_names,
            prior_job_id=prior_job_id,
            cross_dll_prior_job_ids=cross_dll_prior_job_ids,
            product_route_required=True,
            case_id=SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID,
            variant_id=SPECTRUM_COMPILED_MEDIUM01_PRODUCT_VARIANT_ID,
            poll_sec=poll_sec,
            analyze_timeout_sec=analyze_timeout_sec,
            explore_timeout_sec=explore_timeout_sec,
            stuck_seconds=stuck_seconds,
            emit_semantic_continuation_packet=False,
        )
    except RuntimeError as exc:
        if str(exc).startswith(("api_identity_failed:", "bridge_identity_failed:")):
            return _write_setup_failure_result(output_root=output_root, exc=exc)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run compiled Spectrum medium-01 as a Ghidra-required product-route probe."
    )
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--stop-after-first-failure", action="store_true")
    parser.add_argument("--target-names", default="")
    parser.add_argument("--prior-job-id", default="")
    parser.add_argument("--cross-dll-prior-job-ids", default="")
    parser.add_argument("--poll-sec", type=int, default=2)
    parser.add_argument("--analyze-timeout-sec", type=int, default=240)
    parser.add_argument("--explore-timeout-sec", type=int, default=360)
    parser.add_argument("--stuck-seconds", type=int, default=120)
    args = parser.parse_args()

    output_root = Path(args.output_root) if str(args.output_root or "").strip() else None
    result = run_spectrum_compiled_medium01_product(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
        output_root=output_root,
        stop_after_first_failure=bool(args.stop_after_first_failure),
        target_names=_parse_target_names(args.target_names),
        prior_job_id=str(args.prior_job_id or "").strip(),
        cross_dll_prior_job_ids=_parse_job_ids(args.cross_dll_prior_job_ids),
        poll_sec=int(args.poll_sec),
        analyze_timeout_sec=int(args.analyze_timeout_sec),
        explore_timeout_sec=int(args.explore_timeout_sec),
        stuck_seconds=int(args.stuck_seconds),
    )
    summary = dict(result.get("summary") or {})
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "case_id": summary.get("case_id"),
                "green_contract_level": summary.get("green_contract_level"),
                "product_green_eligible": bool(summary.get("product_green_eligible")),
                "route_authority_present": bool(summary.get("route_authority_present")),
                "blocking_signal": str(summary.get("blocking_signal") or ""),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
