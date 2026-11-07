from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops.nightly_groundtruth import (  # noqa: E402
    ApiClient,
    build_lane_identity_packet,
    build_lane_readiness_packet,
    collect_api_identity,
    collect_bridge_identity,
    collect_runner_identity,
    ensure_local_api_freshness,
    ensure_local_bridge_freshness,
    fetch_api_readiness,
    fetch_bridge_readiness,
    log_line,
    resolve_api_url,
    run_one,
    run_post_restart_readiness_probe,
    verify_api_identity,
    verify_bridge_identity,
    wait_job,
    write_json,
)
from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    ensure_spectrum_compiled_package_built,
)
from runtime.runtime_contract import local_bridge_base_url  # noqa: E402

RUNNER_VERSION = "1.0.0"
CANARY_TOTAL_BUDGET_SEC = 600
ANALYZE_ONLY_BUDGET_SEC = 60
BRIDGE_EXECUTION_BUDGET_SEC = 120
CANARY_DLL_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "spectrum_transaction_release_settlement_suite"
    / "bin"
    / "spectrum_session_bootstrap.dll"
)
CANARY_TARGET_NAME = "session_bootstrap"
CANARY_CHECKPOINT = "SP_OpenOperatorSession"


def _load_repo_env_value(name: str) -> str:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{name}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return stripped[len(prefix):].strip()
    return ""


def _bridge_headers(bridge_key: str) -> dict[str, str]:
    return {"X-Bridge-Key": bridge_key} if str(bridge_key or "").strip() else {}


def _default_output_root() -> Path:
    return REPO_ROOT / "sessions" / "proving_lane_canary"


def _bridge_execution_canary(bridge_url: str, bridge_key: str) -> dict[str, Any]:
    started = time.time()
    response = requests.post(
        f"{bridge_url.rstrip('/')}/flush-dll-cache",
        headers=_bridge_headers(bridge_key),
        timeout=BRIDGE_EXECUTION_BUDGET_SEC,
    )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    return {
        "action": "flush_dll_cache",
        "passed": True,
        "duration_sec": round(time.time() - started, 2),
        "response": payload,
    }

def _analyze_only_canary(
    client: ApiClient,
    dll_path: Path,
    heartbeat_path: Path,
    campaign_log: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    job_id = client.analyze(
        dll_path,
        hints="Proving-lane analyze-only canary",
        use_cases="Lane health preflight",
        tags={
            "run_set_id": f"lane-canary-{int(started)}",
            "playbook_step": "analyze-only-canary",
            "analysis_profile": "strict_dll",
            "lane_id": "lane-canary-analyze",
        },
    )
    log_line(f"lane-canary analyze-only start job={job_id}", campaign_log)
    analyzed = wait_job(
        client,
        job_id,
        phase="analyze",
        timeout_sec=ANALYZE_ONLY_BUDGET_SEC,
        poll_sec=5,
        stuck_seconds=30,
        heartbeat_cb=lambda st: write_json(
            heartbeat_path,
            {
                "lane-canary-analyze": {
                    "lane_id": "lane-canary-analyze",
                    "job_id": job_id,
                    "status": "analyze",
                    "updated_at": st.get("updated_at"),
                    "details": {"status": st.get("status"), "progress": st.get("progress")},
                }
            },
        ),
    )
    payload = {
        "job_id": job_id,
        "passed": str(analyzed.get("status") or "").strip().lower() == "done",
        "duration_sec": round(time.time() - started, 2),
        "status": str(analyzed.get("status") or ""),
        "invocable_count": len(list((analyzed.get("result") or {}).get("invocables") or [])),
    }
    return payload


def run_proving_lane_canary(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
    freshness_mode: str = "auto",
) -> dict[str, Any]:
    normalized_freshness_mode = str(freshness_mode or "auto").strip().lower() or "auto"
    if normalized_freshness_mode not in {"auto", "observe_only"}:
        raise ValueError(f"unsupported_freshness_mode:{normalized_freshness_mode}")

    if not CANARY_DLL_PATH.exists():
        try:
            ensure_spectrum_compiled_package_built()
        except Exception as exc:
            raise RuntimeError(f"canary_fixture_bootstrap_failed:{exc}") from exc
    if not CANARY_DLL_PATH.exists():
        raise FileNotFoundError(f"canary_dll_missing_after_bootstrap:{CANARY_DLL_PATH}")

    started = time.time()
    resolved_api_key = str(
        api_key
        or os.getenv("MCP_FACTORY_API_KEY", "")
        or _load_repo_env_value("PIPELINE_API_KEY")
    ).strip()
    resolved_bridge_url = str(
        bridge_url
        or os.getenv("GUI_BRIDGE_URL", "")
        or _load_repo_env_value("GUI_BRIDGE_URL")
        or local_bridge_base_url()
    ).strip()
    resolved_bridge_key = str(
        bridge_key
        or os.getenv("GUI_BRIDGE_SECRET", "")
        or os.getenv("BRIDGE_SECRET", "")
        or _load_repo_env_value("GUI_BRIDGE_SECRET")
        or _load_repo_env_value("BRIDGE_SECRET")
    ).strip()
    resolved_api_url, api_msg, api_resolution_source = resolve_api_url(
        api_url,
        resolved_api_key,
        verify_identity=verify_api_identity,
    )
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(output_root) if output_root is not None else _default_output_root() / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_path = output_dir / "heartbeats.json"
    campaign_log = output_dir / "lane-canary.log"

    freshness = ensure_local_api_freshness(
        REPO_ROOT,
        resolved_api_url,
        resolved_api_key,
        campaign_log=campaign_log,
        allow_relaunch=normalized_freshness_mode != "observe_only",
    )
    if freshness.get("freshness_verdict") == "restart_blocked_unmanaged_owner":
        raise RuntimeError("api_freshness_blocked_unmanaged_owner")
    bridge_freshness = ensure_local_bridge_freshness(
        REPO_ROOT,
        resolved_bridge_url,
        resolved_bridge_key,
        campaign_log=campaign_log,
        allow_relaunch=normalized_freshness_mode != "observe_only",
    )
    if bridge_freshness.get("freshness_verdict") == "restart_blocked_unmanaged_owner":
        raise RuntimeError("bridge_freshness_blocked_unmanaged_owner")
    bridge_ok, bridge_msg = verify_bridge_identity(resolved_bridge_url, resolved_bridge_key)
    if not bridge_ok:
        raise RuntimeError(f"bridge_identity_failed:{bridge_msg}")

    client = ApiClient(resolved_api_url, resolved_api_key)
    runner_identity = collect_runner_identity(
        runner_name="run_proving_lane_canary",
        runner_version=RUNNER_VERSION,
        runner_file=Path(__file__),
        api_url=resolved_api_url,
        bridge_url=resolved_bridge_url,
        started_at=started,
    )
    api_identity_payload = collect_api_identity(resolved_api_url, resolved_api_key, api_msg)
    bridge_identity_payload = collect_bridge_identity(resolved_bridge_url, resolved_bridge_key, bridge_msg)
    lane_identity = build_lane_identity_packet(
        runner_identity=runner_identity,
        api_identity=api_identity_payload,
        bridge_identity=bridge_identity_payload,
    )
    lane_identity["freshness_mode"] = normalized_freshness_mode
    write_json(output_dir / "lane-identity.json", lane_identity)

    post_restart_readiness = {"performed": False, "ready": None, "verdict": "not_required"}
    if bool(freshness.get("restart_performed")):
        post_restart_readiness = run_post_restart_readiness_probe(
            client,
            REPO_ROOT,
            output_dir,
            resolved_api_url,
            resolved_api_key,
            CANARY_DLL_PATH,
            heartbeat_path=heartbeat_path,
            campaign_log=campaign_log,
        )
        if not bool(post_restart_readiness.get("ready")):
            raise RuntimeError(
                "post_restart_readiness_failed:"
                + str(post_restart_readiness.get("verdict") or "unknown")
            )

    lane_readiness = build_lane_readiness_packet(
        api_identity=api_identity_payload,
        bridge_identity=bridge_identity_payload,
        api_readiness=fetch_api_readiness(resolved_api_url, resolved_api_key),
        bridge_readiness=fetch_bridge_readiness(resolved_bridge_url, resolved_bridge_key),
        freshness=freshness,
        bridge_freshness=bridge_freshness,
        post_restart_readiness_probe=post_restart_readiness,
        canary_verdict="not_run",
    )
    lane_readiness["freshness_mode"] = normalized_freshness_mode
    write_json(output_dir / "lane-readiness.json", lane_readiness)

    analyze_only = _analyze_only_canary(client, CANARY_DLL_PATH, heartbeat_path, campaign_log=campaign_log)
    write_json(output_dir / "analyze-only-canary.json", analyze_only)

    bridge_execution = _bridge_execution_canary(resolved_bridge_url, resolved_bridge_key)
    write_json(output_dir / "bridge-execution-canary.json", bridge_execution)

    total_runtime_sec = round(time.time() - started, 2)
    canary_passed = (
        bool(analyze_only.get("passed"))
        and bool(bridge_execution.get("passed"))
        and total_runtime_sec <= CANARY_TOTAL_BUDGET_SEC
    )
    canary_verdict = "passed" if canary_passed else "failed"
    lane_readiness["canary_verdict"] = canary_verdict
    write_json(output_dir / "lane-readiness.json", lane_readiness)

    blocking_reason = ""
    if not canary_passed:
        if total_runtime_sec > CANARY_TOTAL_BUDGET_SEC:
            blocking_reason = "time_budget_exceeded"
        elif not bool(analyze_only.get("passed")):
            blocking_reason = "analyze_only_failed"
        elif not bool(bridge_execution.get("passed")):
            blocking_reason = "bridge_execution_failed"
        else:
            blocking_reason = "lane_canary_failed"

    lane_trust_packet = {
        "contract_version": lane_identity.get("contract_version"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scope": "lane_trust_floor",
        "time_budget_sec": CANARY_TOTAL_BUDGET_SEC,
        "total_runtime_sec": total_runtime_sec,
        "fixture_dll_path": str(CANARY_DLL_PATH),
        "fixture_target": CANARY_TARGET_NAME,
        "freshness_mode": normalized_freshness_mode,
        "lane_identity": lane_identity,
        "lane_readiness": lane_readiness,
        "api_freshness": freshness,
        "bridge_freshness": bridge_freshness,
        "analyze_only_canary": analyze_only,
        "bridge_execution_canary": bridge_execution,
        "canary_verdict": canary_verdict,
        "blocking_reason": "" if canary_passed else blocking_reason,
    }
    write_json(output_dir / "lane-trust-packet.json", lane_trust_packet)

    return {
        "output_dir": str(output_dir),
        "summary": lane_trust_packet,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the proving-lane canary suite.")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--freshness-mode", choices=("auto", "observe_only"), default="auto")
    args = parser.parse_args()

    result = run_proving_lane_canary(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
        freshness_mode=str(args.freshness_mode or "").strip(),
    )
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "canary_verdict": result["summary"]["canary_verdict"],
                "total_runtime_sec": result["summary"]["total_runtime_sec"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
