from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str) -> dict:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_product_proving_posture_is_minimal_contract_not_baseline_duplicate() -> None:
    posture = _load_json("configs/regression/product_proving_posture.json")

    assert posture["principle"] == "authoritative_contract_compression"
    assert posture["canonical_sources"]["active_defended_baselines"] == (
        "configs/regression/baseline_registry.json"
    )
    assert posture["canonical_sources"]["product_gate_membership"] == "configs/regression/gate_v1.json"
    assert "pinned_root" not in json.dumps(posture)
    assert "required_summary_fields" not in json.dumps(posture)


def test_product_posture_matches_registry_and_gate_truth() -> None:
    posture = _load_json("configs/regression/product_proving_posture.json")
    registry = _load_json("configs/regression/baseline_registry.json")
    gate = _load_json("configs/regression/gate_v1.json")

    surfaces = {surface["surface_id"]: surface for surface in registry["surfaces"]}
    gate_surfaces = {suite["baseline_registry_surface_id"] for suite in gate["suites"]}
    active_product_surfaces = {
        surface_id
        for surface_id, surface in surfaces.items()
        if surface.get("active") and surface.get("baseline_type") == "pinned_output_root"
    }

    assert active_product_surfaces == {"easy01", "medium01", "medium02", "hard01"}
    assert gate_surfaces == active_product_surfaces
    assert posture["local_proving_anchor"]["surface_id"] == "medium02"
    assert surfaces["medium02"]["active"] is True
    pressure_target = posture["active_pressure_target"]["surface_id"]
    assert pressure_target.startswith("hard")
    assert pressure_target not in gate_surfaces
    assert surfaces["hard01"]["active"] is True
    assert surfaces["hard02"]["active"] is False


def test_product_posture_active_blocker_is_canonical_signal() -> None:
    posture = _load_json("configs/regression/product_proving_posture.json")
    signal_map = (
        REPO_ROOT / "docs" / "architecture" / "testing_strategy" / "HARD-FAMILY-FAILURE-SIGNAL-MAP.md"
    ).read_text(encoding="utf-8")

    signal_key = posture["active_blocker"]["signal_key"]
    family = posture["active_blocker"]["family"]

    assert signal_key
    assert family
    assert signal_key in signal_map
    assert posture["active_blocker"]["signal_source"] == (
        "docs/architecture/testing_strategy/HARD-FAMILY-FAILURE-SIGNAL-MAP.md"
    )


def test_enterprise_survivability_tier_lift_matrix_routes_canonical_blockers() -> None:
    matrix = _load_json("configs/regression/enterprise_survivability_tier_lift_impact_matrix.json")
    signal_map = (
        REPO_ROOT / "docs" / "architecture" / "testing_strategy" / "HARD-FAMILY-FAILURE-SIGNAL-MAP.md"
    ).read_text(encoding="utf-8")

    assert matrix["claim_ceiling"]
    assert matrix["evidence_roots"]["hard01"]["artifact_backed"] is True
    assert matrix["evidence_roots"]["hard02"]["artifact_backed"] is True
    assert matrix["evidence_roots"]["hard03"]["first_blocker"] == "runner_observed_nonterminal_timeout"
    assert (
        matrix["evidence_roots"]["hard03"]["sharpened_blocker"]
        == "hard03_confirmation_reopen_gate_after_api_analyze_route_event_queue_repair"
    )
    assert (
        matrix["evidence_roots"]["hard03"]["branch_steering_signal"]
        == "hard03_confirmation_reopen_gate_after_api_analyze_route_event_queue_repair"
    )

    known_suites = {"hard01", "hard02", "hard03", "medium02", "batch_b"}
    assert set(matrix["suite_ids"]) == known_suites
    for row in matrix["artifact_backed_blockers"]:
        assert row["signal_key"] in signal_map
        assert row["classification"] in {"local_bug", "family_blocker", "missing_system"}
        assert row["suite"] in known_suites
        assert row["proof_surface"]
        assert row["evidence_root"]

    selected = [row for row in matrix["tier_lift_candidates"] if row["selected_for_tranche"]]
    assert len(selected) == 1
    candidate = selected[0]
    assert candidate["required_pressure"] == "compiled_or_checkpoint_backed"
    assert set(candidate["predicted_suite_impact"]) == known_suites
    assert candidate["accepted_classifier_result"]["product_green_claimed"] is False


def test_required_ci_check_and_docs_point_to_contract_truth() -> None:
    posture = _load_json("configs/regression/product_proving_posture.json")
    workflow = (REPO_ROOT / ".github" / "workflows" / "required-regression-gates.yml").read_text(
        encoding="utf-8"
    )
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    green_contract = (
        REPO_ROOT / "docs" / "architecture" / "testing_strategy" / "COMPILED-SUITE-GREEN-CONTRACT.md"
    ).read_text(encoding="utf-8")
    proving_map = (
        REPO_ROOT / "docs" / "architecture" / "testing_strategy" / "STAGE-PROVING-MAP.md"
    ).read_text(encoding="utf-8")
    system_map = (
        REPO_ROOT / "docs" / "architecture" / "testing_strategy" / "SYSTEM-MAP.md"
    ).read_text(encoding="utf-8")

    assert posture["required_external_check"]["name"] == "Required Regression Gates / Product Baseline Gate"
    assert "name: Product Baseline Gate" in workflow
    assert "--surfaces lane_trust,easy-01,medium-01,medium-02,hard-01" in workflow
    for text in (agents, green_contract, proving_map, system_map):
        assert "product_proving_posture.json" in text

    assert "Lane Trust` and `Easy01 Gate` are the current required" not in agents
    assert "product-green completion/stability candidate" not in green_contract
    assert "The next Medium01 step is" not in green_contract
