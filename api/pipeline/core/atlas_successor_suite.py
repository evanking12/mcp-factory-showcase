from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from api.pipeline.core.design_suite_artifacts import (
    NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,
    NORTHSTAR_OBSERVER_SUMMARY_ARTIFACT,
    NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT,
    NORTHSTAR_SHARED_STATE_ARTIFACT,
    NorthstarFamilyBlockerReport,
    NorthstarProducerConsumerReport,
    NorthstarSharedStateReport,
)
from api.pipeline.core.design_suite_expected_observed import (
    NorthstarExpectedObservedReport,
    compare_expected_observed,
    load_design_suite_manifest,
    write_design_suite_artifact,
)
from api.pipeline.core.design_suite_observers import (
    build_family_blocker_plausibility_observer,
    build_late_confirmation_visibility_observer,
    build_shared_state_carrier_plausibility_observer,
)
from api.pipeline.core.design_suite_runtime_bridge import resolve_design_suite_pressure_mode


REPO_ROOT = Path(__file__).resolve().parents[3]

ATLAS_PRODUCER_CONSUMER_ARTIFACT = "atlas-producer-consumer-report.json"
ATLAS_SHARED_STATE_ARTIFACT = "atlas-shared-state-report.json"
ATLAS_FAMILY_BLOCKER_ARTIFACT = "atlas-family-blocker-report.json"
ATLAS_OBSERVER_SUMMARY_ARTIFACT = "atlas-interwoven-observer-summary.json"
ATLAS_EXPECTED_OBSERVED_ARTIFACT = "atlas-expected-observed-report.json"
ATLAS_CAMPAIGN_READINESS_ARTIFACT = "atlas-campaign-readiness.json"


def atlas_suite_root() -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "design_suite" / "atlas_reconciliation_suite"


def atlas_manifest_path() -> Path:
    return atlas_suite_root() / "truth_manifest.json"


def atlas_contract_path() -> Path:
    return atlas_suite_root() / "successor-suite-contract.json"


def atlas_first_slice_path() -> Path:
    return atlas_suite_root() / "successor-suite-first-slice.json"


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load successor-suite module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_suite_modules(manifest: Mapping[str, Any]) -> dict[str, ModuleType]:
    modules: dict[str, ModuleType] = {}
    for module_name, relative_path in dict(manifest.get("module_sources") or {}).items():
        modules[str(module_name).strip()] = _load_module(str(module_name).strip(), REPO_ROOT / str(relative_path or "").strip())
    return modules


def initialize_atlas_expected_report(manifest: Mapping[str, Any]) -> dict[str, Any]:
    blockers = list(manifest.get("blocker_families") or [])
    relationships = list(dict(manifest.get("expected_relationships") or {}).get("producer_consumers") or [])
    shared_state = list(manifest.get("shared_state_carriers") or [])
    expected = NorthstarExpectedObservedReport(
        slice_id="atlas:first_slice_mutual_pressure",
        module_family=tuple(manifest.get("active_modules") or ()),
        expected_blockers=tuple(item.get("family_id", "") for item in blockers),
        expected_producers=tuple(f"{item.get('producer_module','')}.{item.get('producer_step','')}" for item in relationships),
        expected_consumers=tuple(f"{item.get('consumer_module','')}.{item.get('consumer_step','')}" for item in relationships),
        expected_shared_state=tuple(item.get("carrier_id", "") for item in shared_state),
        expected_family_groups=tuple(item.get("family_id", "") for item in blockers),
        expected_confirmation_sites=tuple(
            site
            for blocker in blockers
            for site in tuple(blocker.get("confirmation_sites") or ())
            if str(site or "").strip()
        ),
        expected_lineage_branches=(),
        expected_accepted_branches=(),
        observed_blockers=(),
        observed_producers=(),
        observed_consumers=(),
        observed_shared_state=(),
        observed_family_groups=(),
        observed_confirmation_sites=(),
        observed_lineage_branches=(),
        observed_accepted_branches=(),
        mismatches=(),
        overclaims=(),
        underclaims=(),
        misgroups=(),
        deferred=(),
        notes=("expected_authored_from_source_truth", "mutual_pressure_expected"),
    )
    payload = expected.to_dict()
    payload["artifact_type"] = ATLAS_EXPECTED_OBSERVED_ARTIFACT
    return payload


def _build_atlas_producer_consumer_reports(manifest: Mapping[str, Any]) -> tuple[NorthstarProducerConsumerReport, ...]:
    reports = []
    for item in list(dict(manifest.get("expected_relationships") or {}).get("producer_consumers") or []):
        reports.append(
            NorthstarProducerConsumerReport(
                family=item["family"],
                blocker_family=item["blocker_family"],
                producer_module=item["producer_module"],
                producer_step=item["producer_step"],
                consumer_module=item["consumer_module"],
                consumer_step=item["consumer_step"],
                state_tokens=tuple(item["state_tokens"]),
                evidence_edges=tuple(item["evidence_edges"]),
                dependency_mode=item["dependency_mode"],
                confidence=float(item.get("confidence", 0.84)),
                contradiction_state=item.get("contradiction_state", "none"),
            )
        )
    return tuple(reports)


def _build_atlas_shared_state_reports(manifest: Mapping[str, Any]) -> tuple[NorthstarSharedStateReport, ...]:
    reports = []
    for item in list(manifest.get("shared_state_carriers") or []):
        reports.append(
            NorthstarSharedStateReport(
                carrier_id=item["carrier_id"],
                carrier_kind=item.get("carrier_kind", "shared_state_carrier"),
                state_tokens=tuple(item["state_tokens"]),
                downstream_consumers=tuple(item["downstream_consumers"]),
                exporting_seams=tuple(item["exporting_seams"]),
                importing_seams=tuple(item["importing_seams"]),
                staleness_risk=item.get("staleness_risk", "medium"),
                confidence=float(item.get("confidence", 0.82)),
                contradiction_state=item.get("contradiction_state", "none"),
            )
        )
    return tuple(reports)


def _build_atlas_family_blocker_reports(manifest: Mapping[str, Any]) -> tuple[NorthstarFamilyBlockerReport, ...]:
    reports = []
    for item in list(manifest.get("blocker_families") or []):
        reports.append(
            NorthstarFamilyBlockerReport(
                blocker_family=item["family_id"],
                subjects=tuple(item["subjects"]),
                upstream_requirements=tuple(item["upstream_requirements"]),
                shared_state_carriers=tuple(item["shared_state_carriers"]),
                failure_or_pressure_sites=tuple(item["failure_or_pressure_sites"]),
                contradiction_state=item.get("contradiction_state", "none"),
                explanation=item["explanation"],
                confidence=float(item.get("confidence", 0.85)),
                provisional_subjects=tuple(item.get("provisional_subjects") or ()),
                confirmation_sites=tuple(item.get("confirmation_sites") or ()),
                lineage_branches=tuple(item.get("lineage_branches") or ()),
                accepted_branch=item.get("accepted_branch", ""),
                rejected_branches=tuple(item.get("rejected_branches") or ()),
            )
        )
    return tuple(reports)


def _build_atlas_observer_summaries(
    shared_state: tuple[NorthstarSharedStateReport, ...],
    blocker_reports: tuple[NorthstarFamilyBlockerReport, ...],
) -> tuple[dict[str, Any], ...]:
    summaries: list[dict[str, Any]] = []
    for report in blocker_reports:
        summaries.append(
            build_family_blocker_plausibility_observer(
                subject_ids=report.subjects,
                blocker_family=report.blocker_family,
                contradiction_state=report.contradiction_state,
                expected_behavior="The mutual-pressure family should stay bounded and explain why two provisional upstream truths require one confirmer.",
                observed_behavior=f"Observed blocker family {report.blocker_family} with {len(report.provisional_subjects) or len(report.subjects)} provisional subjects.",
                confidence=report.confidence,
                canonical_sources=(ATLAS_FAMILY_BLOCKER_ARTIFACT,),
            )
        )
        if report.confirmation_sites:
            summaries.append(
                build_late_confirmation_visibility_observer(
                    subject_ids=report.subjects,
                    blocker_family=report.blocker_family,
                    contradiction_state=report.contradiction_state,
                    expected_behavior="Mutual-pressure work should remain provisional until reconcile confirms both upstream halves together.",
                    observed_behavior=(
                        f"Observed confirmer {', '.join(report.confirmation_sites)} "
                        f"for {len(report.provisional_subjects)} provisional upstream subjects."
                    ),
                    confidence=report.confidence,
                    canonical_sources=(ATLAS_FAMILY_BLOCKER_ARTIFACT,),
                    provisional_subject_count=len(report.provisional_subjects),
                    confirmation_site_count=len(report.confirmation_sites),
                )
            )
    for report in shared_state:
        summaries.append(
            build_shared_state_carrier_plausibility_observer(
                subject_ids=report.downstream_consumers,
                blocker_family="shared_state_carrier_blocker",
                contradiction_state=report.contradiction_state,
                expected_behavior="The batch window should remain visible across more than one provisional consumer.",
                observed_behavior=f"Observed shared carrier {report.carrier_id} across {len(report.downstream_consumers)} downstream consumers.",
                confidence=report.confidence,
                canonical_sources=(ATLAS_SHARED_STATE_ARTIFACT,),
                downstream_consumer_count=len(report.downstream_consumers),
            )
        )
    return tuple(summaries)


def _atlas_payload(bundle_rows: tuple[Any, ...], artifact_name: str) -> list[dict[str, Any]]:
    payload = json.loads(json.dumps([row.to_dict() for row in bundle_rows]))
    for row in payload:
        row["artifact_type"] = artifact_name
    return payload


def build_atlas_semantic_bundle(artifact_bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT: list(artifact_bundle.get(ATLAS_PRODUCER_CONSUMER_ARTIFACT) or []),
        NORTHSTAR_SHARED_STATE_ARTIFACT: list(artifact_bundle.get(ATLAS_SHARED_STATE_ARTIFACT) or []),
        NORTHSTAR_FAMILY_BLOCKER_ARTIFACT: list(artifact_bundle.get(ATLAS_FAMILY_BLOCKER_ARTIFACT) or []),
        NORTHSTAR_OBSERVER_SUMMARY_ARTIFACT: list(artifact_bundle.get(ATLAS_OBSERVER_SUMMARY_ARTIFACT) or []),
    }


def run_atlas_first_slice(
    manifest_path: str | Path | None = None,
    *,
    output_dir: str | Path | None = None,
    mode: str = "mutual_pressure",
) -> dict[str, Any]:
    pressure_mode = resolve_design_suite_pressure_mode(mode)
    if pressure_mode != "mutual_pressure":
        raise ValueError("Atlas first slice currently supports only mutual_pressure")
    manifest = load_design_suite_manifest(manifest_path or atlas_manifest_path())
    expected_payload = initialize_atlas_expected_report(manifest)
    expected = NorthstarExpectedObservedReport(
        **{
            key: value
            for key, value in expected_payload.items()
            if key not in {"artifact_type", "contract_version"}
        }
    )
    producer_consumer = _build_atlas_producer_consumer_reports(manifest)
    shared_state = _build_atlas_shared_state_reports(manifest)
    blocker_reports = _build_atlas_family_blocker_reports(manifest)
    observer_summaries = _build_atlas_observer_summaries(shared_state, blocker_reports)
    comparison = compare_expected_observed(
        expected,
        producer_consumer=producer_consumer,
        shared_state=shared_state,
        blocker_reports=blocker_reports,
        observer_summaries=observer_summaries,
    ).to_dict()
    comparison = json.loads(json.dumps(comparison))
    comparison["artifact_type"] = ATLAS_EXPECTED_OBSERVED_ARTIFACT

    artifact_bundle = {
        ATLAS_PRODUCER_CONSUMER_ARTIFACT: _atlas_payload(producer_consumer, ATLAS_PRODUCER_CONSUMER_ARTIFACT),
        ATLAS_SHARED_STATE_ARTIFACT: _atlas_payload(shared_state, ATLAS_SHARED_STATE_ARTIFACT),
        ATLAS_FAMILY_BLOCKER_ARTIFACT: _atlas_payload(blocker_reports, ATLAS_FAMILY_BLOCKER_ARTIFACT),
        ATLAS_OBSERVER_SUMMARY_ARTIFACT: json.loads(json.dumps(list(observer_summaries))),
        ATLAS_EXPECTED_OBSERVED_ARTIFACT: comparison,
    }
    if output_dir is not None:
        for artifact_name, payload in artifact_bundle.items():
            write_design_suite_artifact(output_dir, artifact_name, payload)
    return artifact_bundle


def execute_atlas_first_slice(manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    manifest_payload = dict(manifest or load_design_suite_manifest(atlas_manifest_path()))
    modules = _load_suite_modules(manifest_payload)
    inputs = dict(manifest_payload.get("execution_inputs") or {})
    tenant_id = str(inputs.get("tenant_id") or "").strip()
    party_id = str(inputs.get("party_id") or "").strip()
    amount_cents = int(inputs.get("amount_cents") or 0)

    steps: list[dict[str, Any]] = []

    batch_output = modules["batch"].open_batch(tenant_id)
    steps.append(
        {
            "step_id": "batch.open_batch",
            "module": "batch",
            "function": "open_batch",
            "status": "success",
            "input_keys": ["tenant_id"],
            "output_keys": sorted(batch_output.keys()),
            "error": "",
        }
    )
    identity_output = modules["identity"].bind_party(batch_output["batch_token"], party_id)
    steps.append(
        {
            "step_id": "identity.bind_party",
            "module": "identity",
            "function": "bind_party",
            "status": "success",
            "input_keys": ["batch_token", "party_id"],
            "output_keys": sorted(identity_output.keys()),
            "error": "",
        }
    )
    ledger_output = modules["ledger"].stage_transfer(
        batch_output["batch_token"],
        batch_output["sequence_window"],
        amount_cents,
    )
    steps.append(
        {
            "step_id": "ledger.stage_transfer",
            "module": "ledger",
            "function": "stage_transfer",
            "status": "success",
            "input_keys": ["amount_cents", "batch_token", "sequence_window"],
            "output_keys": sorted(ledger_output.keys()),
            "error": "",
        }
    )
    reconcile_output = modules["reconcile"].confirm_alignment(
        batch_output["batch_token"],
        identity_output["binding_receipt"],
        ledger_output["staged_transfer_id"],
    )
    steps.append(
        {
            "step_id": "reconcile.confirm_alignment",
            "module": "reconcile",
            "function": "confirm_alignment",
            "status": "success",
            "input_keys": ["batch_token", "binding_receipt", "staged_transfer_id"],
            "output_keys": sorted(reconcile_output.keys()),
            "error": "",
        }
    )
    return {
        "schema_version": "1.0.0",
        "suite_id": str(manifest_payload.get("suite_id") or "").strip(),
        "pressure_mode": "mutual_pressure",
        "active_modules": list(manifest_payload.get("active_modules") or []),
        "steps": steps,
        "reconcile_output": reconcile_output,
    }
