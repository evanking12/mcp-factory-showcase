from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime.run_local_product_suite import (
    build_entrypoint_packet,
    build_lane_startup_command_with_mode,
    build_runner_command,
    resolve_suite_runner,
    run_local_product_suite,
)


def test_resolve_suite_runner_maps_product_suites() -> None:
    assert resolve_suite_runner("easy01").name == "run_spectrum_compiled_easy01_product.py"
    assert resolve_suite_runner("medium01").name == "run_spectrum_compiled_medium01_product.py"
    assert resolve_suite_runner("medium02").name == "run_spectrum_compiled_medium02_product.py"
    assert resolve_suite_runner("hard01").name == "run_spectrum_compiled_hard01_product.py"


def test_resolve_suite_runner_rejects_unknown_suite() -> None:
    with pytest.raises(ValueError, match="unknown_local_product_suite:hard02"):
        resolve_suite_runner("hard02")


def test_build_runner_command_uses_canonical_local_urls_and_optional_flags(tmp_path: Path) -> None:
    command = build_runner_command(
        suite="easy01",
        output_root=tmp_path / "runner",
        stop_after_first_failure=True,
        poll_sec=3,
        analyze_timeout_sec=111,
        explore_timeout_sec=222,
        stuck_seconds=33,
        target_names="session_bootstrap",
        prior_job_id="job-1",
        cross_dll_prior_job_ids="job-a,job-b",
    )

    assert command[1].endswith("run_spectrum_compiled_easy01_product.py")
    assert "--api-url" in command
    assert "http://127.0.0.1:8201" in command
    assert "--bridge-url" in command
    assert "http://127.0.0.1:8090" in command
    assert "--stop-after-first-failure" in command
    assert "--target-names" in command
    assert "session_bootstrap" in command
    assert "--prior-job-id" in command
    assert "job-1" in command
    assert "--cross-dll-prior-job-ids" in command
    assert "job-a,job-b" in command


def test_build_runner_command_dispatches_hard01_product(tmp_path: Path) -> None:
    command = build_runner_command(
        suite="hard01",
        output_root=tmp_path / "runner",
        stop_after_first_failure=True,
        poll_sec=3,
        analyze_timeout_sec=111,
        explore_timeout_sec=222,
        stuck_seconds=33,
    )

    assert command[1].endswith("run_spectrum_compiled_hard01_product.py")
    assert "--stop-after-first-failure" in command


def test_build_lane_startup_command_can_force_no_reload(tmp_path: Path) -> None:
    command = build_lane_startup_command_with_mode(
        output_root=tmp_path / "lane",
        no_reload=True,
    )

    assert "start-managed-lane.ps1" in command[4]
    assert "-NoReload" in command


def test_build_entrypoint_packet_does_not_claim_product_green_on_lane_startup_alone() -> None:
    packet = build_entrypoint_packet(
        suite="easy01",
        lane_startup_attempted=True,
        lane_startup_passed=True,
        lane_startup_packet_path="lane-startup.json",
        runner_invoked=False,
        runner_command=[],
        runner_output_root="runner",
        blocking_signal="",
        safe_to_compare=False,
        product_green_eligible=False,
        runner_exit_code=None,
        startup_exit_code=0,
    )

    assert packet["lane_startup_passed"] is True
    assert packet["runner_invoked"] is False
    assert packet["product_green_eligible"] is False
    assert packet["safe_to_compare"] is False
    assert packet["telemetry_diagnostic_only"] is True


def test_run_local_product_suite_stops_after_lane_startup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane_output_root = tmp_path / "entry" / "lane-startup"

    class _Completed:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[list[str]] = []

    def fake_run(command):  # noqa: ANN001
        calls.append(command)
        lane_output_root.mkdir(parents=True, exist_ok=True)
        (lane_output_root / "lane-startup-failure.json").write_text(
            json.dumps({"failure_kind": "promotion_not_safe"}),
            encoding="utf-8",
        )
        return _Completed(1)

    monkeypatch.setattr("runtime.run_local_product_suite._run_command", fake_run)
    monkeypatch.setattr(
        "runtime.run_local_product_suite.find_python_executable",
        lambda: "python",
    )

    exit_code, packet, packet_path = run_local_product_suite(
        suite="easy01",
        output_root=tmp_path / "entry",
        stop_after_first_failure=True,
    )

    saved_packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert len(calls) == 1
    assert "start-managed-lane.ps1" in calls[0][4]
    assert "-NoReload" in calls[0]
    assert packet["lane_startup_passed"] is False
    assert packet["runner_invoked"] is False
    assert packet["blocking_signal"] == "promotion_not_safe"
    assert saved_packet["blocking_signal"] == "promotion_not_safe"


def test_run_local_product_suite_invokes_runner_after_green_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane_output_root = tmp_path / "entry" / "lane-startup"
    runner_output_root = tmp_path / "entry" / "runner"

    class _Completed:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[list[str]] = []

    def fake_run(command):  # noqa: ANN001
        calls.append(command)
        if "start-managed-lane.ps1" in command[4]:
            lane_output_root.mkdir(parents=True, exist_ok=True)
            (lane_output_root / "lane-startup.json").write_text(
                json.dumps({"status": "passed", "promotion_safe": True}),
                encoding="utf-8",
            )
            return _Completed(0)
        assert os.environ.get("MCP_FACTORY_PRODUCT_TRACE_ID")
        assert os.environ.get("MCP_FACTORY_PRODUCT_TRACE_PATH")
        runner_output_root.mkdir(parents=True, exist_ok=True)
        (runner_output_root / "compiled-ingest-summary.json").write_text(
            json.dumps(
                {
                    "blocking_signal": "post_explore_verdict_fetch_connection_reset",
                    "safe_to_compare": False,
                    "product_green_eligible": False,
                }
            ),
            encoding="utf-8",
        )
        return _Completed(0, stdout='{"blocking_signal":"post_explore_verdict_fetch_connection_reset"}')

    monkeypatch.setattr("runtime.run_local_product_suite._run_command", fake_run)
    monkeypatch.setattr(
        "runtime.run_local_product_suite.find_python_executable",
        lambda: "python",
    )

    exit_code, packet, packet_path = run_local_product_suite(
        suite="medium01",
        output_root=tmp_path / "entry",
        stop_after_first_failure=True,
    )

    saved_packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(calls) == 2
    assert "-NoReload" in calls[0]
    assert calls[1][1].endswith("run_spectrum_compiled_medium01_product.py")
    assert "--api-url" in calls[1]
    assert "http://127.0.0.1:8201" in calls[1]
    assert "--bridge-url" in calls[1]
    assert "http://127.0.0.1:8090" in calls[1]
    assert "--stop-after-first-failure" in calls[1]
    assert packet["lane_startup_passed"] is True
    assert packet["runner_invoked"] is True
    assert packet["blocking_signal"] == "post_explore_verdict_fetch_connection_reset"
    assert packet["trace_id"]
    assert Path(packet["trace_path"]).exists()
    trace_events = [json.loads(line) for line in Path(packet["trace_path"]).read_text(encoding="utf-8").splitlines()]
    entrypoint_events = [event for event in trace_events if event["span_name"] == "local_product_suite.entrypoint"]
    assert [event["event_name"] for event in entrypoint_events] == ["start", "end"]
    assert entrypoint_events[0]["span_id"] == entrypoint_events[1]["span_id"]
    assert entrypoint_events[1]["attributes"]["duration_ms"] >= 0
    assert saved_packet["runner_invoked"] is True
