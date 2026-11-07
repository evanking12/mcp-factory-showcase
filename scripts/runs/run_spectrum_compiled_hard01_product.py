from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.spectrum_compiled_ingest import SPECTRUM_COMPILED_SUITE_ID  # noqa: E402
from scripts.ops.nightly_groundtruth import write_json  # noqa: E402
from scripts.runs.run_spectrum_compiled_hard01 import run_spectrum_compiled_hard01  # noqa: E402

SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID = "hard-01-product-route"
SPECTRUM_COMPILED_HARD01_PRODUCT_VARIANT_ID = "compiled_hard01_product_route"


def _setup_failure_packet(*, output_root: Path, reason_code: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    packet = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID,
        "green_contract_level": "product_green",
        "product_route_required": True,
        "route_authority_required": True,
        "ghidra_required": True,
        "strict_dll": True,
        "product_green_eligible": False,
        "route_authority_present": False,
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "blocking_signal": reason_code,
        "failure_domain": "hard01_product_runner_setup",
        "details": details or {},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(output_root / "compiled-ingest-summary.json", packet)
    write_json(output_root / "compiled-ingest-compare-report.json", packet)
    (output_root / "compiled-ingest.log").write_text(
        f"hard01 product runner setup failed: {reason_code}\n",
        encoding="utf-8",
    )
    return packet


def run_spectrum_compiled_hard01_product(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_urls: str = "",
    bridge_quarantine_registry: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
    stop_after_first_failure: bool = False,
    poll_sec: int = 10,
    analyze_timeout_sec: int = 1800,
    explore_timeout_sec: int = 5400,
    stuck_seconds: int = 900,
) -> dict[str, Any]:
    output_path = Path(output_root) if output_root is not None else None
    try:
        return run_spectrum_compiled_hard01(
            api_url=api_url,
            api_key=api_key,
            bridge_url=bridge_url,
            bridge_urls=bridge_urls,
            bridge_quarantine_registry=bridge_quarantine_registry,
            bridge_key=bridge_key,
            output_root=output_path,
            stop_after_first_failure=stop_after_first_failure,
            product_route_required=True,
            case_id=SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID,
            variant_id=SPECTRUM_COMPILED_HARD01_PRODUCT_VARIANT_ID,
            poll_sec=poll_sec,
            analyze_timeout_sec=analyze_timeout_sec,
            explore_timeout_sec=explore_timeout_sec,
            stuck_seconds=stuck_seconds,
        )
    except Exception as exc:
        if output_path is None:
            output_path = (
                REPO_ROOT
                / "sessions"
                / "design_suite"
                / "compiled_ingest"
                / SPECTRUM_COMPILED_SUITE_ID
                / SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID
                / time.strftime("%Y%m%d-%H%M%S")
            )
        packet = _setup_failure_packet(
            output_root=output_path,
            reason_code=str(exc).split(":", 1)[0].strip() or "hard01_product_runner_setup_failed",
            details={"error": str(exc)},
        )
        return {"output_dir": str(output_path), "summary": packet, "report": packet}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compiled Spectrum hard-01 through the product route.")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-urls", default="")
    parser.add_argument("--bridge-quarantine-registry", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--stop-after-first-failure", action="store_true")
    parser.add_argument("--poll-sec", type=int, default=10)
    parser.add_argument("--analyze-timeout-sec", type=int, default=1800)
    parser.add_argument("--explore-timeout-sec", type=int, default=5400)
    parser.add_argument("--stuck-seconds", type=int, default=900)
    parser.add_argument("--target-names", default="")
    parser.add_argument("--prior-job-id", default="")
    parser.add_argument("--cross-dll-prior-job-ids", default="")
    args = parser.parse_args()

    unsupported = {
        "target_names": str(args.target_names or "").strip(),
        "prior_job_id": str(args.prior_job_id or "").strip(),
        "cross_dll_prior_job_ids": str(args.cross_dll_prior_job_ids or "").strip(),
    }
    if any(unsupported.values()):
        output_root = Path(args.output_root) if str(args.output_root or "").strip() else Path.cwd() / "hard01-product-unsupported"
        packet = _setup_failure_packet(
            output_root=output_root,
            reason_code="hard01_product_target_override_unsupported",
            details=unsupported,
        )
        print(json.dumps(packet, indent=2))
        return 2

    result = run_spectrum_compiled_hard01_product(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_urls=str(args.bridge_urls or "").strip(),
        bridge_quarantine_registry=str(args.bridge_quarantine_registry or "").strip(),
        bridge_key=str(args.bridge_key or os.getenv("GUI_BRIDGE_SECRET", "") or os.getenv("BRIDGE_SECRET", "")).strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
        stop_after_first_failure=bool(args.stop_after_first_failure),
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
                "green_contract_level": summary.get("green_contract_level"),
                "product_green_eligible": bool(summary.get("product_green_eligible")),
                "safe_to_compare": bool(summary.get("safe_to_compare")),
                "authoritative_proving": bool(summary.get("authoritative_proving")),
                "blocking_signal": str(summary.get("blocking_signal") or ""),
                "trace_path": str(summary.get("trace_path") or ""),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
