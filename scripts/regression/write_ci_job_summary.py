from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _lane_summary(result: dict[str, Any]) -> str:
    reasons = list(result.get("reasons") or [])
    validator_failure = dict(result.get("validator_failure") or {})
    failure_kind = str(validator_failure.get("failure_kind") or "").strip()
    failure_message = str(validator_failure.get("message") or "").strip()
    validator_details = dict(validator_failure.get("details") or {})
    freshness_mode = str(
        validator_details.get("freshness_mode")
        or result.get("freshness_mode")
        or ""
    ).strip()
    restart_suppressed = (
        validator_details["restart_suppressed"]
        if "restart_suppressed" in validator_details
        else result.get("restart_suppressed")
    )
    packet_completeness = str(result.get("packet_completeness") or "").strip()
    missing_packets = list(result.get("missing_packets") or [])
    lines = [
        "## Lane Trust",
        "",
        f"- Verdict: `{result.get('verdict')}`",
    ]
    if failure_kind:
        lines.append(f"- Validator failure class: `{failure_kind}`")
    if failure_message:
        lines.append(f"- First concrete cause: `{failure_message}`")
    if freshness_mode:
        lines.append(f"- Freshness mode: `{freshness_mode}`")
    if restart_suppressed is not None:
        lines.append(f"- Restart suppressed: `{bool(restart_suppressed)}`")
    if packet_completeness:
        lines.append(f"- Packet completeness: `{packet_completeness}`")
    if missing_packets:
        lines.append(f"- Missing packets: `{', '.join(str(item) for item in missing_packets)}`")
    if reasons:
        lines.append(f"- Reasons: `{', '.join(str(item) for item in reasons)}`")
    return "\n".join(lines) + "\n"


def _startup_summary(startup_root: Path) -> str:
    failure_path = startup_root / "lane-startup-failure.json"
    success_path = startup_root / "lane-startup.json"
    packet: dict[str, Any] = {}
    verdict = "unknown"
    lines = [
        "## Managed Lane Startup",
        "",
    ]
    if failure_path.exists():
        packet = _read_json(failure_path)
        verdict = "fail"
        lines.append(f"- Verdict: `{verdict}`")
        lines.append(f"- Failure class: `{packet.get('failure_kind')}`")
        lines.append(f"- Stage: `{packet.get('stage')}`")
        lines.append(f"- Message: `{packet.get('message')}`")
    elif success_path.exists():
        packet = _read_json(success_path)
        verdict = "pass"
        lab_status = dict(packet.get("lab_status") or {})
        lines.append(f"- Verdict: `{verdict}`")
        lines.append(f"- Lab status: `{lab_status.get('status')}`")
        lines.append(f"- Promotion safe: `{packet.get('promotion_safe')}`")
    else:
        lines.append("- Verdict: `missing`")
        lines.append("- Message: `No managed-lane startup artifact was found.`")
    return "\n".join(lines) + "\n"


def _suite_summary(result: dict[str, Any]) -> str:
    reasons = list(result.get("reasons") or [])
    runner_exception = dict(result.get("runner_exception") or {})
    lines = [
        f"## {result.get('surface')}",
        "",
        f"- Verdict: `{result.get('verdict')}`",
    ]
    if runner_exception:
        lines.append(f"- Runner failure class: `{runner_exception.get('type')}`")
        lines.append(f"- First concrete cause: `{runner_exception.get('message')}`")
    if reasons:
        lines.append(f"- Reasons: `{', '.join(str(item) for item in reasons)}`")
    return "\n".join(lines) + "\n"


def _triage_summary(triage: dict[str, Any]) -> str:
    if not triage:
        return ""
    artifact_status = dict(triage.get("artifact_status") or {})
    baseline_access = dict(triage.get("baseline_access") or {})
    lines = [
        "## Regression Triage",
        "",
        f"- First failed tier: `{triage.get('first_failed_tier') or ''}`",
        f"- First failed checkpoint: `{triage.get('first_failed_checkpoint') or 'none'}`",
        f"- Failure class: `{triage.get('failure_kind') or 'none'}`",
        f"- Failure domain: `{triage.get('failure_domain') or ''}`",
        f"- Runner: `{triage.get('runner') or ''}`",
        f"- Ports: `api={triage.get('api_port') or ''}, bridge={triage.get('bridge_port') or ''}`",
        f"- Baseline access: `{baseline_access.get('verdict') or 'missing'}`",
        f"- Downloaded checkpoint artifacts: `{artifact_status.get('downloaded_artifact_count')}`",
        f"- Missing targets: `{', '.join(str(item) for item in list(artifact_status.get('missing_targets') or [])) or 'none'}`",
        f"- Next action: `{triage.get('next_action') or ''}`",
    ]
    return "\n".join(lines) + "\n"


def _medium_summary(result: dict[str, Any], checkpoints: dict[str, Any]) -> str:
    first_failed = str(checkpoints.get("first_failed_checkpoint") or "").strip() or "none"
    passed = int(checkpoints.get("passed_checkpoint_count") or 0)
    total = int(checkpoints.get("total_checkpoint_count") or 0)
    summary = dict(checkpoints.get("checkpoint_verdict_summary") or {})
    failure_kind = ""
    for row in list(checkpoints.get("checkpoints") or []):
        if str(row.get("verdict") or "") == "fail":
            failure_kind = str(row.get("failure_kind") or "").strip()
            break

    lines = [
        "## Medium01 Checkpoints",
        "",
        f"- Overall verdict: `{result.get('verdict')}`",
        f"- First failed checkpoint: `{first_failed}`",
        f"- Passed checkpoints: `{passed}/{total}`",
        f"- Failure class: `{failure_kind or 'none'}`",
        f"- Checkpoint counts: `pass={summary.get('pass', 0)}, fail={summary.get('fail', 0)}, skipped={summary.get('skipped', 0)}`",
        "",
        "| Checkpoint | Verdict | Phase | Failure Kind |",
        "| --- | --- | --- | --- |",
    ]
    for row in list(checkpoints.get("checkpoints") or []):
        lines.append(
            f"| `{row.get('target_name')}` | `{row.get('verdict')}` | `{row.get('phase') or ''}` | `{row.get('failure_kind') or ''}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a compact GitHub job summary for regression jobs.")
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--checkpoints", type=Path, default=None)
    parser.add_argument("--startup-root", type=Path, default=None)
    parser.add_argument("--triage", type=Path, default=None)
    args = parser.parse_args(argv)

    startup_root = args.startup_root if args.startup_root and args.startup_root.exists() else None
    startup_markdown = _startup_summary(startup_root) if startup_root else ""
    result = _read_json(args.result) if args.result.exists() else {}
    checkpoints = _read_json(args.checkpoints) if args.checkpoints and args.checkpoints.exists() else {}
    triage = _read_json(args.triage) if args.triage and args.triage.exists() else {}
    triage_markdown = _triage_summary(triage)
    surface = str(result.get("surface") or "").strip()

    if surface == "lane_trust":
        markdown = _lane_summary(result)
    elif not result and startup_markdown:
        markdown = startup_markdown
    elif surface == "medium-01" and checkpoints:
        markdown = (
            triage_markdown
            + ("\n" if triage_markdown and startup_markdown else "")
            + startup_markdown
            + ("\n" if (triage_markdown or startup_markdown) else "")
            + _medium_summary(result, checkpoints)
        )
    else:
        markdown = (
            triage_markdown
            + ("\n" if triage_markdown and startup_markdown else "")
            + startup_markdown
            + ("\n" if (triage_markdown or startup_markdown) else "")
            + _suite_summary(result)
        )

    summary_path = str(os.getenv("GITHUB_STEP_SUMMARY") or "").strip()
    if summary_path:
        Path(summary_path).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
