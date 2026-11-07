from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


def test_cached_bridge_enriched_discovery_marks_bridge_reachable(monkeypatch, tmp_path: Path) -> None:
    from api.services import discovery

    dll_path = tmp_path / "fixture.dll"
    dll_path.write_bytes(b"stub")
    emitted: dict[str, object] = {}

    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "http://127.0.0.1:8090")
    monkeypatch.setattr(discovery, "GUI_BRIDGE_SECRET", "secret")
    monkeypatch.setattr(discovery, "_dll_sha256", lambda _binary: "sha-1")
    monkeypatch.setattr(
        discovery,
        "_read_cache_blob",
        lambda _sha, name: (
            {
                "invocables": [{"name": "FnA", "parameters": [{"name": "value", "description": "typed"}]}],
                "bridge_enriched": True,
            }
            if "discovery_result" in name
            else None
        ),
    )
    monkeypatch.setattr(discovery, "_is_low_fidelity_param_cache", lambda _invocables: False)
    monkeypatch.setattr(discovery, "_apply_fixture_manifest_overlay", lambda _binary, invocables: invocables)
    monkeypatch.setattr(discovery, "_apply_recovered_struct_layouts", lambda invocables: invocables)
    monkeypatch.setattr(discovery, "_refresh_dll_execution_metadata", lambda _binary, invocables: invocables)
    monkeypatch.setattr(discovery, "_schema_param_stats", lambda _invocables: {"param_coverage": 1.0})

    def fake_emit(job_id, binary_sha, cache_state, analysis_profile, param_stats, *, bridge_reachable=None):
        emitted.update(
            {
                "job_id": job_id,
                "binary_sha": binary_sha,
                "cache_state": cache_state,
                "analysis_profile": analysis_profile,
                "param_stats": param_stats,
                "bridge_reachable": bridge_reachable,
            }
        )

    monkeypatch.setattr(discovery, "_emit_discovery_meta", fake_emit)

    payload, sha, cache_state = discovery._try_cached_discovery_result(
        binary_path=dll_path,
        job_id="job-cache-1",
        skip_cache=False,
        analysis_profile="strict_dll",
    )

    assert payload is not None
    assert sha == "sha-1"
    assert cache_state == "warm"
    assert emitted["bridge_reachable"] is True


def test_default_session_meta_includes_campaign_trust_fields() -> None:
    from scripts.harness_lib import capture

    status = {
        "job_id": "job-campaign-1",
        "component_name": "contoso_transport",
        "target_path": r"C:\fixtures\contoso_transport.dll",
        "dll_sha256": "abc123",
        "analysis_entrypoint": "upload",
        "binary_origin": "temp_upload",
        "package_id": "pkg-1",
        "package_label": "Contoso Package",
        "lane_id": "lane-1",
        "lane_trust_status": "trusted",
        "selection_reason": "core_canary",
        "doc_visibility": "internal_fixture",
        "dependency_context": "package_bundle",
        "blocker_family_primary": "opaque handle routing",
        "blocker_family_secondary": ["sequencing/state machine"],
        "blocker_confidence": "high",
        "architecture_relevance": "high",
        "runtime_path_trust": "matched",
        "explore_runtime": {
            "analysis_profile": "strict_dll",
            "parallel_runs": 1,
            "variant_configs": [],
            "campaign_id": "camp-1",
            "lane_id": "lane-1",
            "graph_epoch": "camp-1",
        },
    }

    payload = json.loads(
        capture._default_blob_bytes(  # noqa: SLF001
            "session-meta.json",
            status=status,
            fetched={},
        ).decode("utf-8")
    )

    assert payload["campaign_id"] == "camp-1"
    assert payload["package_id"] == "pkg-1"
    assert payload["package_label"] == "Contoso Package"
    assert payload["lane_id"] == "lane-1"
    assert payload["lane_trust_status"] == "trusted"
    assert payload["blocker_family_primary"] == "opaque handle routing"
    assert payload["runtime_path_trust"] == "matched"


def test_existing_session_meta_is_overlaid_with_latest_campaign_fields() -> None:
    from scripts.harness_lib import capture

    status = {
        "job_id": "job-campaign-2",
        "package_id": "pkg-2",
        "package_label": "Contoso Package",
        "lane_id": "lane-1",
        "lane_trust_status": "trusted",
        "selection_reason": "state_sequence_canary",
        "doc_visibility": "known_fixture",
        "dependency_context": "sibling_install_folder",
        "blocker_family_primary": "sequencing/state machine",
        "blocker_family_secondary": ["opaque handle routing"],
        "blocker_confidence": "medium",
        "architecture_relevance": "high",
        "runtime_path_trust": "echoed",
        "explore_runtime": {
            "analysis_profile": "strict_dll",
            "parallel_runs": 1,
            "variant_configs": [],
            "campaign_id": "camp-2",
            "graph_epoch": "camp-2",
        },
    }
    existing = {
        "job_id": "job-campaign-2",
        "component": "contoso_workflow",
        "package_id": None,
        "lane_trust_status": None,
        "blocker_family_primary": None,
    }

    payload = json.loads(
        capture._patched_session_meta_bytes(  # noqa: SLF001
            json.dumps(existing).encode("utf-8"),
            status=status,
        ).decode("utf-8")
    )

    assert payload["package_id"] == "pkg-2"
    assert payload["package_label"] == "Contoso Package"
    assert payload["lane_trust_status"] == "trusted"
    assert payload["selection_reason"] == "state_sequence_canary"
    assert payload["blocker_family_primary"] == "sequencing/state machine"
    assert payload["blocker_family_secondary"] == ["opaque handle routing"]
    assert payload["runtime_path_trust"] == "echoed"


def test_capture_campaign_child_job_uses_canonical_capture_path(monkeypatch, tmp_path: Path) -> None:
    from api.pipeline import runner
    import harness_lib.capture as capture_module

    captured: dict[str, object] = {}

    def fake_run_capture(**kwargs):
        captured.update(kwargs)
        out_dir = Path(str(kwargs["out_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(session_dir=out_dir, collect_exit=0, summary={"contract": {"valid": True}})

    monkeypatch.setattr(capture_module, "run_capture", fake_run_capture)
    monkeypatch.chdir(tmp_path)

    result = runner._capture_campaign_child_job("camp-ctrl-1", "job-ctrl-1", fresh=True)  # noqa: SLF001

    assert result["collect_exit"] == 0
    assert captured["job_id"] == "job-ctrl-1"
    assert captured["api_url"] == "http://127.0.0.1:1"
    assert str(captured["out_dir"]).endswith(str(Path("sessions") / "campaign-captures" / "camp-ctrl-1" / "job-ctrl-1"))
