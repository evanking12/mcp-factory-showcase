from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.runs import run_spectrum_compiled_hard03 as hard03
from scripts.regression import replay_hard03_reservation_managed_lane as replay


def test_pre_target_api_recovery_relaunches_auto_detect_openapi_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    relaunches: list[dict[str, object]] = []

    def fake_resolve(api_url: str, api_key: str, *, verify_identity):  # noqa: ANN001
        calls.append(api_url)
        if len(calls) == 1:
            raise RuntimeError(
                "api_identity_failed:auto-detect:http://127.0.0.1:8201:api_openapi_unavailable"
            )
        return "http://127.0.0.1:8201", "api_ok:identity_shape", "auto-detected"

    def fake_relaunch(repo_root, api_url, api_key, *, campaign_log=None, no_reload=False):  # noqa: ANN001
        relaunches.append(
            {
                "repo_root": repo_root,
                "api_url": api_url,
                "api_key": api_key,
                "campaign_log": campaign_log,
                "no_reload": no_reload,
            }
        )
        return {"restart_performed": True, "post_restart_identity": "api_ok:test"}

    monkeypatch.setattr(hard03, "resolve_api_url", fake_resolve)
    monkeypatch.setattr(hard03, "relaunch_local_api_lane", fake_relaunch)

    resolved_url, message, source, packet = hard03._resolve_api_url_with_pre_target_recovery(
        api_url="",
        api_key="",
        output_dir=tmp_path,
        campaign_log=tmp_path / "compiled-ingest.log",
    )

    saved = json.loads((tmp_path / "pre-target-api-identity-authority.json").read_text(encoding="utf-8"))
    assert resolved_url == "http://127.0.0.1:8201"
    assert message == "api_ok:identity_shape"
    assert source == "auto-detected"
    assert packet["verdict"] == "pass_after_managed_relaunch"
    assert saved["recovery_attempted"] is True
    assert saved["target_execution_invoked"] is False
    assert saved["product_green_claimed"] is False
    assert relaunches == [
        {
            "repo_root": hard03.REPO_ROOT,
            "api_url": "http://127.0.0.1:8201",
            "api_key": "",
            "campaign_log": tmp_path / "compiled-ingest.log",
            "no_reload": True,
        }
    ]


def test_pre_target_api_recovery_relaunches_auto_detect_readiness_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    relaunches: list[dict[str, object]] = []

    def fake_resolve(api_url: str, api_key: str, *, verify_identity):  # noqa: ANN001
        calls.append(api_url)
        if len(calls) == 1:
            raise RuntimeError(
                "api_identity_failed:auto-detect:http://127.0.0.1:8201:api_readiness_unavailable"
            )
        return "http://127.0.0.1:8201", "api_ok:identity_shape", "auto-detected"

    def fake_relaunch(repo_root, api_url, api_key, *, campaign_log=None, no_reload=False):  # noqa: ANN001
        relaunches.append(
            {
                "repo_root": repo_root,
                "api_url": api_url,
                "api_key": api_key,
                "campaign_log": campaign_log,
                "no_reload": no_reload,
            }
        )
        return {"restart_performed": True, "post_restart_identity": "api_ok:test"}

    monkeypatch.setattr(hard03, "resolve_api_url", fake_resolve)
    monkeypatch.setattr(hard03, "relaunch_local_api_lane", fake_relaunch)

    resolved_url, message, source, packet = hard03._resolve_api_url_with_pre_target_recovery(
        api_url="",
        api_key="",
        output_dir=tmp_path,
        campaign_log=tmp_path / "compiled-ingest.log",
    )

    saved = json.loads((tmp_path / "pre-target-api-identity-authority.json").read_text(encoding="utf-8"))
    assert resolved_url == "http://127.0.0.1:8201"
    assert message == "api_ok:identity_shape"
    assert source == "auto-detected"
    assert packet["verdict"] == "pass_after_managed_relaunch"
    assert saved["recovery_attempted"] is True
    assert saved["recovery_reason"] == "auto_detect_local_api_readiness_unavailable"
    assert saved["target_execution_invoked"] is False
    assert relaunches == [
        {
            "repo_root": hard03.REPO_ROOT,
            "api_url": "http://127.0.0.1:8201",
            "api_key": "",
            "campaign_log": tmp_path / "compiled-ingest.log",
            "no_reload": True,
        }
    ]


def test_pre_target_api_recovery_does_not_relaunch_explicit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resolve(api_url: str, api_key: str, *, verify_identity):  # noqa: ANN001
        raise RuntimeError("api_identity_failed:explicit:http://localhost:8001:api_openapi_unavailable")

    monkeypatch.setattr(hard03, "resolve_api_url", fake_resolve)
    monkeypatch.setattr(
        hard03,
        "relaunch_local_api_lane",
        lambda *args, **kwargs: pytest.fail("explicit API failures must not relaunch"),
    )

    with pytest.raises(RuntimeError, match="api_identity_failed:explicit"):
        hard03._resolve_api_url_with_pre_target_recovery(
            api_url="http://localhost:8001",
            api_key="",
            output_dir=tmp_path,
            campaign_log=tmp_path / "compiled-ingest.log",
        )

    saved = json.loads((tmp_path / "pre-target-api-identity-authority.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "fail"
    assert saved["recovery_attempted"] is False
    assert saved["recovery_reason"] == "not_recoverable_by_managed_local_api_relaunch"


def test_pre_target_api_recovery_does_not_relaunch_explicit_readiness_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resolve(api_url: str, api_key: str, *, verify_identity):  # noqa: ANN001
        raise RuntimeError("api_identity_failed:explicit:http://localhost:8001:api_readiness_unavailable")

    monkeypatch.setattr(hard03, "resolve_api_url", fake_resolve)
    monkeypatch.setattr(
        hard03,
        "relaunch_local_api_lane",
        lambda *args, **kwargs: pytest.fail("explicit readiness failures must not relaunch"),
    )

    with pytest.raises(RuntimeError, match="api_identity_failed:explicit"):
        hard03._resolve_api_url_with_pre_target_recovery(
            api_url="http://localhost:8001",
            api_key="",
            output_dir=tmp_path,
            campaign_log=tmp_path / "compiled-ingest.log",
        )

    saved = json.loads((tmp_path / "pre-target-api-identity-authority.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "fail"
    assert saved["recovery_attempted"] is False
    assert saved["recovery_reason"] == "not_recoverable_by_managed_local_api_relaunch"


def test_pre_target_api_recovery_writes_packet_when_relaunch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resolve(api_url: str, api_key: str, *, verify_identity):  # noqa: ANN001
        raise RuntimeError(
            "api_identity_failed:auto-detect:http://127.0.0.1:8201:api_openapi_unavailable"
        )

    def fake_relaunch(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("api_relaunch_failed:test")

    monkeypatch.setattr(hard03, "resolve_api_url", fake_resolve)
    monkeypatch.setattr(hard03, "relaunch_local_api_lane", fake_relaunch)

    with pytest.raises(RuntimeError, match="api_relaunch_failed:test"):
        hard03._resolve_api_url_with_pre_target_recovery(
            api_url="",
            api_key="",
            output_dir=tmp_path,
            campaign_log=tmp_path / "compiled-ingest.log",
        )

    saved = json.loads((tmp_path / "pre-target-api-identity-authority.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "fail_managed_relaunch"
    assert saved["blocking_signal"] == "managed_api_process_hang_after_fresh_gate"
    assert saved["recovery_attempted"] is True
    assert saved["target_execution_invoked"] is False


def test_strict_local_preflight_authority_writes_fail_closed_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_preflight(**kwargs):  # noqa: ANN003
        raise RuntimeError(
            "strict_local_lane_preflight_failed:api_local_lane_admission_unavailable"
        )

    monkeypatch.setattr(hard03, "ensure_strict_local_lane_preflight", fake_preflight)

    with pytest.raises(RuntimeError, match="api_local_lane_admission_unavailable"):
        hard03._run_strict_local_preflight_with_authority(
            api_url="http://127.0.0.1:8201",
            api_key="",
            bridge_url="http://127.0.0.1:8090",
            bridge_key="secret",
            output_dir=tmp_path,
        )

    saved = json.loads((tmp_path / "strict-local-preflight-authority.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "fail"
    assert saved["blocking_signal"] == "api_local_lane_admission_unavailable"
    assert saved["blocking_reasons"] == ["api_local_lane_admission_unavailable"]
    assert saved["target_execution_invoked"] is False
    assert saved["safe_to_compare"] is False
    assert saved["product_green_claimed"] is False


def test_strict_local_preflight_authority_writes_pass_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight = {"admitted": True, "api": {"admitted": True}, "bridge": {"admitted": True}}
    monkeypatch.setattr(
        hard03,
        "ensure_strict_local_lane_preflight",
        lambda **kwargs: dict(preflight),
    )

    result = hard03._run_strict_local_preflight_with_authority(
        api_url="http://127.0.0.1:8201",
        api_key="",
        bridge_url="http://127.0.0.1:8090",
        bridge_key="secret",
        output_dir=tmp_path,
    )

    saved = json.loads((tmp_path / "strict-local-preflight-authority.json").read_text(encoding="utf-8"))
    assert result == preflight
    assert saved["verdict"] == "pass"
    assert saved["blocking_signal"] == ""
    assert saved["blocking_reasons"] == []
    assert saved["preflight"] == preflight


def test_post_restart_api_readiness_survival_relaunches_after_probe_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_calls = 0
    relaunches: list[dict[str, object]] = []

    def fake_fetch_readiness(api_url: str, api_key: str):  # noqa: ANN001
        nonlocal readiness_calls
        readiness_calls += 1
        if readiness_calls == 1:
            return None
        return {"ready": True, "blocking_reasons": []}

    def fake_relaunch(repo_root, api_url, api_key, *, campaign_log=None, no_reload=False):  # noqa: ANN001
        relaunches.append(
            {
                "repo_root": repo_root,
                "api_url": api_url,
                "api_key": api_key,
                "campaign_log": campaign_log,
                "no_reload": no_reload,
            }
        )
        return {"restart_performed": True, "freshness_verdict": "fresh_after_relaunch"}

    monkeypatch.setattr(hard03, "fetch_api_readiness", fake_fetch_readiness)
    monkeypatch.setattr(hard03, "relaunch_local_api_lane", fake_relaunch)
    monkeypatch.setattr(hard03, "collect_api_identity", lambda *args, **kwargs: {"component": "api"})
    monkeypatch.setattr(
        hard03,
        "_run_strict_local_preflight_with_authority",
        lambda **kwargs: {"admitted": True, "api": {"admitted": True}, "bridge": {"admitted": True}},
    )

    api_readiness, api_identity, strict_preflight, freshness, packet = (
        hard03._fetch_api_readiness_after_post_restart_probe(
            resolved_api_url="http://127.0.0.1:8201",
            resolved_api_key="",
            resolved_bridge_url="http://127.0.0.1:8090",
            resolved_bridge_key="secret",
            api_msg="api_ok:test",
            freshness={"restart_performed": True},
            post_restart_readiness={"ready": True},
            output_dir=tmp_path,
            campaign_log=tmp_path / "compiled-ingest.log",
        )
    )

    saved = json.loads((tmp_path / "post-restart-api-readiness-survival-authority.json").read_text(encoding="utf-8"))
    assert api_readiness == {"ready": True, "blocking_reasons": []}
    assert api_identity == {"component": "api"}
    assert strict_preflight["admitted"] is True
    assert freshness["freshness_verdict"] == "fresh_after_relaunch"
    assert packet["verdict"] == "pass_after_managed_relaunch"
    assert saved["initial_blocking_signal"] == "api_readiness_unavailable_after_post_restart_probe"
    assert saved["target_execution_invoked"] is False
    assert saved["safe_to_compare"] is False
    assert relaunches == [
        {
            "repo_root": hard03.REPO_ROOT,
            "api_url": "http://127.0.0.1:8201",
            "api_key": "",
            "campaign_log": tmp_path / "compiled-ingest.log",
            "no_reload": True,
        }
    ]


def test_post_restart_api_readiness_survival_fails_closed_without_ready_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hard03, "fetch_api_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        hard03,
        "relaunch_local_api_lane",
        lambda *args, **kwargs: pytest.fail("must not relaunch when readiness probe was not ready"),
    )
    monkeypatch.setattr(hard03, "collect_api_identity", lambda *args, **kwargs: {"component": "api"})

    api_readiness, api_identity, strict_preflight, freshness, packet = (
        hard03._fetch_api_readiness_after_post_restart_probe(
            resolved_api_url="http://127.0.0.1:8201",
            resolved_api_key="",
            resolved_bridge_url="http://127.0.0.1:8090",
            resolved_bridge_key="secret",
            api_msg="api_ok:test",
            freshness={"restart_performed": True},
            post_restart_readiness={"ready": False},
            output_dir=tmp_path,
            campaign_log=tmp_path / "compiled-ingest.log",
        )
    )

    assert api_readiness is None
    assert api_identity == {"component": "api"}
    assert strict_preflight == {}
    assert freshness == {"restart_performed": True}
    assert packet["verdict"] == "fail_no_relaunch"
    assert packet["blocking_signal"] == "api_readiness_unavailable_after_post_restart_probe"
    assert packet["target_execution_invoked"] is False


def test_post_restart_api_readiness_survival_fails_closed_for_non_local_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hard03, "fetch_api_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        hard03,
        "relaunch_local_api_lane",
        lambda *args, **kwargs: pytest.fail("must not relaunch non-local API URLs"),
    )
    monkeypatch.setattr(hard03, "collect_api_identity", lambda *args, **kwargs: {"component": "api"})

    api_readiness, api_identity, strict_preflight, freshness, packet = (
        hard03._fetch_api_readiness_after_post_restart_probe(
            resolved_api_url="http://10.0.0.7:8201",
            resolved_api_key="",
            resolved_bridge_url="http://127.0.0.1:8090",
            resolved_bridge_key="secret",
            api_msg="api_ok:test",
            freshness={"restart_performed": True},
            post_restart_readiness={"ready": True},
            output_dir=tmp_path,
            campaign_log=tmp_path / "compiled-ingest.log",
        )
    )

    saved = json.loads((tmp_path / "post-restart-api-readiness-survival-authority.json").read_text(encoding="utf-8"))
    assert api_readiness is None
    assert api_identity == {"component": "api"}
    assert strict_preflight == {}
    assert freshness == {"restart_performed": True}
    assert packet["verdict"] == "fail_no_relaunch"
    assert saved["relaunch_blocked_reason"] == "not_ready_probe_or_not_managed_local_restart"
    assert saved["managed_relaunch_attempted"] is False
    assert saved["target_execution_invoked"] is False


def test_hard03_runner_integrated_preflight_failure_writes_authority_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hard03, "ensure_spectrum_compiled_package_built", lambda: {"selected_runtime_targets": []})
    monkeypatch.setattr(hard03, "load_spectrum_compiled_truth_manifest", lambda: {"dlls": []})
    monkeypatch.setattr(hard03, "load_spectrum_authored_truth_manifest", lambda: {"suite_id": "compiled"})
    monkeypatch.setattr(hard03, "load_spectrum_authored_hard03_manifest", lambda: {"case_id": "hard-03"})
    monkeypatch.setattr(
        hard03,
        "resolve_api_url",
        lambda api_url, api_key, *, verify_identity: (
            "http://127.0.0.1:8201",
            "api_ok:identity_shape",
            "auto-detected",
        ),
    )
    monkeypatch.setattr(hard03, "ensure_local_bridge_freshness", lambda *args, **kwargs: {"freshness_verdict": "fresh"})
    monkeypatch.setattr(hard03, "ensure_local_api_freshness", lambda *args, **kwargs: {"freshness_verdict": "fresh"})
    monkeypatch.setattr(hard03, "verify_bridge_identity", lambda *args, **kwargs: (True, "bridge_ok:test"))

    def fake_preflight(**kwargs):  # noqa: ANN003
        raise RuntimeError(
            "strict_local_lane_preflight_failed:api_local_lane_admission_unavailable"
        )

    monkeypatch.setattr(hard03, "ensure_strict_local_lane_preflight", fake_preflight)

    with pytest.raises(RuntimeError, match="api_local_lane_admission_unavailable"):
        hard03.run_spectrum_compiled_hard03(output_root=tmp_path)

    packet = json.loads((tmp_path / "strict-local-preflight-authority.json").read_text(encoding="utf-8"))
    assert packet["verdict"] == "fail"
    assert packet["blocking_signal"] == "api_local_lane_admission_unavailable"
    assert packet["target_execution_invoked"] is False
    assert packet["safe_to_compare"] is False
    assert packet["product_green_claimed"] is False
    assert (tmp_path / "pre-target-api-identity-authority.json").exists()


def test_target_local_replay_pre_target_api_recovery_relaunches_auto_detect_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    relaunches: list[dict[str, object]] = []

    def fake_resolve(api_url: str, api_key: str, *, verify_identity):  # noqa: ANN001
        calls.append(api_url)
        if len(calls) == 1:
            raise RuntimeError(
                "api_identity_failed:auto-detect:http://127.0.0.1:8201:api_openapi_unavailable"
            )
        return "http://127.0.0.1:8201", "api_ok:identity_shape", "auto-detected"

    def fake_relaunch(repo_root, api_url, api_key, *, campaign_log=None, no_reload=False):  # noqa: ANN001
        relaunches.append(
            {
                "repo_root": repo_root,
                "api_url": api_url,
                "api_key": api_key,
                "campaign_log": campaign_log,
                "no_reload": no_reload,
            }
        )
        return {"restart_performed": True, "post_restart_identity": "api_ok:test"}

    monkeypatch.setattr(replay, "resolve_api_url", fake_resolve)
    monkeypatch.setattr(replay, "relaunch_local_api_lane", fake_relaunch)

    resolved_url, message, source, packet = replay._resolve_api_url_with_target_local_recovery(
        api_url="",
        api_key="",
        output_root=tmp_path,
        campaign_log=tmp_path / "managed-lane-replay.log",
    )

    saved = json.loads((tmp_path / "pre-target-api-identity-authority.json").read_text(encoding="utf-8"))
    assert resolved_url == "http://127.0.0.1:8201"
    assert message == "api_ok:identity_shape"
    assert source == "auto-detected"
    assert packet["verdict"] == "pass_after_managed_relaunch"
    assert saved["claim"] == "hard03_target_local_pre_target_api_identity_authority"
    assert saved["target_execution_invoked"] is False
    assert saved["safe_to_compare"] is False
    assert saved["recovery_attempted"] is True
    assert relaunches == [
        {
            "repo_root": replay.REPO_ROOT,
            "api_url": "http://127.0.0.1:8201",
            "api_key": "",
            "campaign_log": tmp_path / "managed-lane-replay.log",
            "no_reload": True,
        }
    ]
