from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from api.pipeline.core.design_suite_artifacts import (
    NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT,
    NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,
    NORTHSTAR_OBSERVER_SUMMARY_ARTIFACT,
    NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT,
    NORTHSTAR_SHARED_STATE_ARTIFACT,
    NorthstarFamilyBlockerReport,
    NorthstarProducerConsumerReport,
    NorthstarSharedStateReport,
)
from api.pipeline.core.design_suite_observers import (
    build_family_blocker_plausibility_observer,
    build_forked_state_visibility_observer,
    build_late_confirmation_visibility_observer,
    build_shared_state_carrier_plausibility_observer,
)
from api.pipeline.core.design_suite_runtime_bridge import resolve_design_suite_pressure_mode
from api.pipeline.core.design_suite_taxonomy import DEFAULT_NORTHSTAR_CONTRACT


DESIGN_SUITE_EXPECTED_OBSERVED_SCHEMA_VERSION = "1.0.0"


def _normalized_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(value or "").strip() for value in tuple(values or ()) if str(value or "").strip())


def _sorted_unique(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(sorted(set(_normalized_tuple(values))))


def load_design_suite_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class NorthstarExpectedObservedReport:
    slice_id: str
    module_family: tuple[str, ...]
    expected_blockers: tuple[str, ...]
    expected_producers: tuple[str, ...]
    expected_consumers: tuple[str, ...]
    expected_shared_state: tuple[str, ...]
    expected_family_groups: tuple[str, ...]
    expected_confirmation_sites: tuple[str, ...]
    expected_lineage_branches: tuple[str, ...]
    expected_accepted_branches: tuple[str, ...]
    observed_blockers: tuple[str, ...]
    observed_producers: tuple[str, ...]
    observed_consumers: tuple[str, ...]
    observed_shared_state: tuple[str, ...]
    observed_family_groups: tuple[str, ...]
    observed_confirmation_sites: tuple[str, ...]
    observed_lineage_branches: tuple[str, ...]
    observed_accepted_branches: tuple[str, ...]
    mismatches: tuple[str, ...]
    overclaims: tuple[str, ...]
    underclaims: tuple[str, ...]
    misgroups: tuple[str, ...]
    deferred: tuple[str, ...]
    notes: tuple[str, ...]
    artifact_type: str = NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT
    contract_version: str = DESIGN_SUITE_EXPECTED_OBSERVED_SCHEMA_VERSION

    def __post_init__(self) -> None:
        slice_id = str(self.slice_id or "").strip()
        if not slice_id:
            raise ValueError("slice_id must be non-empty")
        object.__setattr__(self, "slice_id", slice_id)
        for field_name in (
            "module_family",
            "expected_blockers",
            "expected_producers",
            "expected_consumers",
            "expected_shared_state",
            "expected_family_groups",
            "expected_confirmation_sites",
            "expected_lineage_branches",
            "expected_accepted_branches",
            "observed_blockers",
            "observed_producers",
            "observed_consumers",
            "observed_shared_state",
            "observed_family_groups",
            "observed_confirmation_sites",
            "observed_lineage_branches",
            "observed_accepted_branches",
            "mismatches",
            "overclaims",
            "underclaims",
            "misgroups",
            "deferred",
            "notes",
        ):
            object.__setattr__(self, field_name, _sorted_unique(getattr(self, field_name)))
        if self.artifact_type != NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT:
            raise ValueError("artifact_type mismatch for Northstar expected-observed report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def initialize_expected_report(
    manifest: dict[str, Any],
    *,
    pressure_mode: str = "base",
) -> NorthstarExpectedObservedReport:
    normalized_mode = resolve_design_suite_pressure_mode(pressure_mode)
    relationships = list(manifest.get("expected_relationships", {}).get("producer_consumers", ()))
    blockers = list(manifest.get("blocker_families", ()))
    shared_state = list(manifest.get("shared_state_carriers", ()))
    module_family = tuple(manifest.get("active_modules") or ())
    if normalized_mode == "overlap":
        overlap = manifest.get("overlap_pressure") or {}
        module = str(overlap.get("module") or "").strip()
        if module:
            module_family = tuple(list(module_family) + [module])
        if overlap.get("producer_consumer"):
            relationships.append(overlap["producer_consumer"])
        if overlap.get("family_group"):
            blockers.append(overlap["family_group"])
        if overlap.get("shared_state_carrier"):
            shared_state.append(overlap["shared_state_carrier"])
    if normalized_mode == "late_confirmation":
        late_confirmation = manifest.get("late_confirmation_pressure") or {}
        module = str(late_confirmation.get("module") or "").strip()
        if module:
            module_family = tuple(list(module_family) + [module])
        relationships.extend(list(late_confirmation.get("producer_consumers", ())))
        if late_confirmation.get("family_group"):
            blockers.append(late_confirmation["family_group"])
    if normalized_mode == "forked_state":
        forked_state = manifest.get("forked_state_pressure") or {}
        module = str(forked_state.get("module") or "").strip()
        if module:
            module_family = tuple(list(module_family) + [module])
        relationships.extend(list(forked_state.get("producer_consumers", ())))
        if forked_state.get("family_group"):
            blockers.append(forked_state["family_group"])
        if forked_state.get("shared_state_carrier"):
            shared_state.append(forked_state["shared_state_carrier"])

    confirmation_sites = tuple(
        item
        for blocker in blockers
        for item in tuple(blocker.get("confirmation_sites") or ())
        if str(item or "").strip()
    )
    lineage_branches = tuple(
        item
        for blocker in blockers
        for item in tuple(blocker.get("lineage_branches") or ())
        if str(item or "").strip()
    )
    accepted_branches = tuple(
        str(blocker.get("accepted_branch") or "").strip()
        for blocker in blockers
        if str(blocker.get("accepted_branch") or "").strip()
    )

    return NorthstarExpectedObservedReport(
        slice_id=(
            "northstar:first_slice_overlap"
            if normalized_mode == "overlap"
            else "northstar:first_slice_late_confirmation"
            if normalized_mode == "late_confirmation"
            else "northstar:first_slice_forked_state"
            if normalized_mode == "forked_state"
            else "northstar:first_slice"
        ),
        module_family=module_family,
        expected_blockers=tuple(item.get("family_id", "") for item in blockers),
        expected_producers=tuple(f"{item.get('producer_module','')}.{item.get('producer_step','')}" for item in relationships),
        expected_consumers=tuple(f"{item.get('consumer_module','')}.{item.get('consumer_step','')}" for item in relationships),
        expected_shared_state=tuple(item.get("carrier_id", "") for item in shared_state),
        expected_family_groups=tuple(item.get("family_id", "") for item in blockers),
        expected_confirmation_sites=confirmation_sites,
        expected_lineage_branches=lineage_branches,
        expected_accepted_branches=accepted_branches,
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
        notes=("expected_authored_from_source_truth",),
    )


def build_northstar_producer_consumer_reports(
    manifest: dict[str, Any],
    *,
    pressure_mode: str = "base",
) -> tuple[NorthstarProducerConsumerReport, ...]:
    normalized_mode = resolve_design_suite_pressure_mode(pressure_mode)
    relationships = list(manifest.get("expected_relationships", {}).get("producer_consumers", ()))
    if normalized_mode == "overlap" and manifest.get("overlap_pressure", {}).get("producer_consumer"):
        relationships.append(manifest["overlap_pressure"]["producer_consumer"])
    if normalized_mode == "late_confirmation":
        relationships.extend(list((manifest.get("late_confirmation_pressure") or {}).get("producer_consumers", ())))
    if normalized_mode == "forked_state":
        relationships.extend(list((manifest.get("forked_state_pressure") or {}).get("producer_consumers", ())))
    reports = []
    for item in relationships:
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
                confidence=float(item.get("confidence", 0.85)),
                contradiction_state=item.get("contradiction_state", "none"),
            )
        )
    return tuple(reports)


def build_northstar_shared_state_reports(
    manifest: dict[str, Any],
    *,
    pressure_mode: str = "base",
) -> tuple[NorthstarSharedStateReport, ...]:
    normalized_mode = resolve_design_suite_pressure_mode(pressure_mode)
    carriers = list(manifest.get("shared_state_carriers", ()))
    if normalized_mode == "overlap" and manifest.get("overlap_pressure", {}).get("shared_state_carrier"):
        carriers.append(manifest["overlap_pressure"]["shared_state_carrier"])
    if normalized_mode == "late_confirmation" and (manifest.get("late_confirmation_pressure") or {}).get("shared_state_carrier"):
        carriers.append(manifest["late_confirmation_pressure"]["shared_state_carrier"])
    if normalized_mode == "forked_state" and (manifest.get("forked_state_pressure") or {}).get("shared_state_carrier"):
        carriers.append(manifest["forked_state_pressure"]["shared_state_carrier"])
    reports = []
    for item in carriers:
        reports.append(
            NorthstarSharedStateReport(
                carrier_id=item["carrier_id"],
                carrier_kind=item.get("carrier_kind", "shared_state_carrier"),
                state_tokens=tuple(item["state_tokens"]),
                downstream_consumers=tuple(item["downstream_consumers"]),
                exporting_seams=tuple(item["exporting_seams"]),
                importing_seams=tuple(item["importing_seams"]),
                staleness_risk=item.get("staleness_risk", "medium"),
                confidence=float(item.get("confidence", 0.8)),
                contradiction_state=item.get("contradiction_state", "none"),
            )
        )
    return tuple(reports)


def build_northstar_family_blocker_reports(
    manifest: dict[str, Any],
    *,
    pressure_mode: str = "base",
) -> tuple[NorthstarFamilyBlockerReport, ...]:
    normalized_mode = resolve_design_suite_pressure_mode(pressure_mode)
    blockers = list(manifest.get("blocker_families", ()))
    if normalized_mode == "overlap" and manifest.get("overlap_pressure", {}).get("family_group"):
        blockers.append(manifest["overlap_pressure"]["family_group"])
    if normalized_mode == "late_confirmation" and (manifest.get("late_confirmation_pressure") or {}).get("family_group"):
        blockers.append(manifest["late_confirmation_pressure"]["family_group"])
    if normalized_mode == "forked_state" and (manifest.get("forked_state_pressure") or {}).get("family_group"):
        blockers.append(manifest["forked_state_pressure"]["family_group"])
    reports = []
    for item in blockers:
        reports.append(
            NorthstarFamilyBlockerReport(
                blocker_family=item["family_id"],
                subjects=tuple(item["subjects"]),
                upstream_requirements=tuple(item["upstream_requirements"]),
                shared_state_carriers=tuple(item["shared_state_carriers"]),
                failure_or_pressure_sites=tuple(item["failure_or_pressure_sites"]),
                contradiction_state=item.get("contradiction_state", "none"),
                explanation=item["explanation"],
                confidence=float(item.get("confidence", 0.84)),
                provisional_subjects=tuple(item.get("provisional_subjects") or ()),
                confirmation_sites=tuple(item.get("confirmation_sites") or ()),
                lineage_branches=tuple(item.get("lineage_branches") or ()),
                accepted_branch=item.get("accepted_branch", ""),
                rejected_branches=tuple(item.get("rejected_branches") or ()),
            )
        )
    return tuple(reports)


def build_northstar_observer_summaries(
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
                expected_behavior="Family blocker should explain more than one local pressure site without collapsing into a slice or dependency class.",
                observed_behavior=f"Observed blocker family {report.blocker_family} covering {len(report.failure_or_pressure_sites)} pressure sites.",
                confidence=report.confidence,
                canonical_sources=(NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,),
            )
        )
        if report.confirmation_sites:
            summaries.append(
                build_late_confirmation_visibility_observer(
                    subject_ids=report.subjects,
                    blocker_family=report.blocker_family,
                    contradiction_state=report.contradiction_state,
                    expected_behavior="Upstream local success should remain provisional until the downstream confirmation seam succeeds.",
                    observed_behavior=(
                        f"Observed late confirmer {', '.join(report.confirmation_sites)} "
                        f"for {len(report.provisional_subjects) or len(report.subjects)} provisional subjects."
                    ),
                    confidence=report.confidence,
                    canonical_sources=(NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,),
                    provisional_subject_count=len(report.provisional_subjects),
                    confirmation_site_count=len(report.confirmation_sites),
                )
            )
        if report.lineage_branches:
            summaries.append(
                build_forked_state_visibility_observer(
                    subject_ids=report.subjects,
                    blocker_family=report.blocker_family,
                    contradiction_state=report.contradiction_state,
                    expected_behavior="Forked-state pressure should preserve explicit lineage branches and identify exactly one accepted branch.",
                    observed_behavior=(
                        f"Observed accepted branch {report.accepted_branch or 'unset'} "
                        f"across {len(report.lineage_branches)} lineage branches."
                    ),
                    confidence=report.confidence,
                    canonical_sources=(NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,),
                    lineage_branch_count=len(report.lineage_branches),
                    accepted_branch_present=bool(report.accepted_branch),
                    rejected_branch_count=len(report.rejected_branches),
                )
            )
    for report in shared_state:
        summaries.append(
            build_shared_state_carrier_plausibility_observer(
                subject_ids=report.downstream_consumers,
                blocker_family=DEFAULT_NORTHSTAR_CONTRACT.supporting_blocker_pressure,
                contradiction_state=report.contradiction_state,
                expected_behavior="Shared-state carrier should remain explicit across multiple downstream consumers.",
                observed_behavior=f"Observed shared-state carrier {report.carrier_id} across {len(report.downstream_consumers)} consumers.",
                confidence=report.confidence,
                canonical_sources=(NORTHSTAR_SHARED_STATE_ARTIFACT,),
                downstream_consumer_count=len(report.downstream_consumers),
            )
        )
    return tuple(summaries)


def compare_expected_observed(
    expected: NorthstarExpectedObservedReport,
    *,
    producer_consumer: tuple[NorthstarProducerConsumerReport, ...],
    shared_state: tuple[NorthstarSharedStateReport, ...],
    blocker_reports: tuple[NorthstarFamilyBlockerReport, ...],
    observer_summaries: tuple[dict[str, Any], ...],
) -> NorthstarExpectedObservedReport:
    observed_producers = tuple(f"{item.producer_module}.{item.producer_step}" for item in producer_consumer)
    observed_consumers = tuple(f"{item.consumer_module}.{item.consumer_step}" for item in producer_consumer)
    observed_shared_state = tuple(item.carrier_id for item in shared_state)
    observed_blockers = tuple(item.blocker_family for item in blocker_reports)
    observed_family_groups = tuple(item.blocker_family for item in blocker_reports)
    observed_confirmation_sites = tuple(
        site
        for report in blocker_reports
        for site in report.confirmation_sites
    )
    observed_lineage_branches = tuple(
        branch
        for report in blocker_reports
        for branch in report.lineage_branches
    )
    observed_accepted_branches = tuple(
        report.accepted_branch
        for report in blocker_reports
        if str(report.accepted_branch or "").strip()
    )

    overclaims = sorted(
        (set(observed_producers) - set(expected.expected_producers))
        | (set(observed_consumers) - set(expected.expected_consumers))
        | (set(observed_shared_state) - set(expected.expected_shared_state))
        | (set(observed_blockers) - set(expected.expected_blockers))
        | (set(observed_confirmation_sites) - set(expected.expected_confirmation_sites))
        | (set(observed_lineage_branches) - set(expected.expected_lineage_branches))
        | (set(observed_accepted_branches) - set(expected.expected_accepted_branches))
    )
    underclaims = sorted(
        (set(expected.expected_producers) - set(observed_producers))
        | (set(expected.expected_consumers) - set(observed_consumers))
        | (set(expected.expected_shared_state) - set(observed_shared_state))
        | (set(expected.expected_blockers) - set(observed_blockers))
        | (set(expected.expected_confirmation_sites) - set(observed_confirmation_sites))
        | (set(expected.expected_lineage_branches) - set(observed_lineage_branches))
        | (set(expected.expected_accepted_branches) - set(observed_accepted_branches))
    )

    misgroups: set[str] = set()
    expected_group_map = {item: item for item in expected.expected_family_groups}
    for report in blocker_reports:
        if report.blocker_family in expected_group_map and len(report.failure_or_pressure_sites) < 1:
            misgroups.add(f"{report.blocker_family}:empty_failure_or_pressure_sites")
    for item in observer_summaries:
        if item["status"] == "warn" and item["observer_name"] == "family_blocker_plausibility":
            misgroups.add(f"{item['blocker_family']}:observer_warn")

    deferred = tuple(
        item["observer_name"]
        for item in observer_summaries
        if item["status"] == "warn"
    )
    mismatches = tuple(sorted(set(overclaims) | set(underclaims) | misgroups))
    notes = ["observed_comparison_assembled_from_emitted_artifacts"]
    if not mismatches:
        notes.append("first_slice_match")
    if expected.expected_confirmation_sites and not mismatches:
        notes.append("late_confirmation_match")
    if expected.expected_lineage_branches and not mismatches:
        notes.append("forked_state_match")

    return NorthstarExpectedObservedReport(
        slice_id=expected.slice_id,
        module_family=expected.module_family,
        expected_blockers=expected.expected_blockers,
        expected_producers=expected.expected_producers,
        expected_consumers=expected.expected_consumers,
        expected_shared_state=expected.expected_shared_state,
        expected_family_groups=expected.expected_family_groups,
        expected_confirmation_sites=expected.expected_confirmation_sites,
        expected_lineage_branches=expected.expected_lineage_branches,
        expected_accepted_branches=expected.expected_accepted_branches,
        observed_blockers=observed_blockers,
        observed_producers=observed_producers,
        observed_consumers=observed_consumers,
        observed_shared_state=observed_shared_state,
        observed_family_groups=observed_family_groups,
        observed_confirmation_sites=observed_confirmation_sites,
        observed_lineage_branches=observed_lineage_branches,
        observed_accepted_branches=observed_accepted_branches,
        mismatches=mismatches,
        overclaims=tuple(overclaims),
        underclaims=tuple(underclaims),
        misgroups=tuple(sorted(misgroups)),
        deferred=deferred,
        notes=tuple(notes),
    )


def write_design_suite_artifact(output_dir: str | Path, artifact_name: str, payload: dict[str, Any] | list[dict[str, Any]]) -> Path:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / artifact_name
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    if destination.exists():
        existing_text = destination.read_text(encoding="utf-8")
        if existing_text != serialized:
            superseded_dir = output_root / "superseded"
            superseded_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, superseded_dir / artifact_name)
    destination.write_text(serialized + "\n", encoding="utf-8")
    return destination


def run_northstar_first_slice(
    manifest_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    mode: str | None = None,
    include_overlap: bool = False,
    include_late_confirmation: bool = False,
    include_forked_state: bool = False,
) -> dict[str, Any]:
    pressure_mode = resolve_design_suite_pressure_mode(
        mode,
        include_overlap=include_overlap,
        include_late_confirmation=include_late_confirmation,
        include_forked_state=include_forked_state,
    )
    manifest = load_design_suite_manifest(manifest_path)
    expected = initialize_expected_report(
        manifest,
        pressure_mode=pressure_mode,
    )
    producer_consumer = build_northstar_producer_consumer_reports(
        manifest,
        pressure_mode=pressure_mode,
    )
    shared_state = build_northstar_shared_state_reports(
        manifest,
        pressure_mode=pressure_mode,
    )
    blocker_reports = build_northstar_family_blocker_reports(
        manifest,
        pressure_mode=pressure_mode,
    )
    observer_summaries = build_northstar_observer_summaries(shared_state, blocker_reports)
    comparison = compare_expected_observed(
        expected,
        producer_consumer=producer_consumer,
        shared_state=shared_state,
        blocker_reports=blocker_reports,
        observer_summaries=observer_summaries,
    )
    producer_consumer_payload = json.loads(json.dumps([item.to_dict() for item in producer_consumer]))
    shared_state_payload = json.loads(json.dumps([item.to_dict() for item in shared_state]))
    blocker_payload = json.loads(json.dumps([item.to_dict() for item in blocker_reports]))
    observer_payload = json.loads(json.dumps(list(observer_summaries)))
    comparison_payload = json.loads(json.dumps(comparison.to_dict()))
    bundle = {
        NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT: producer_consumer_payload,
        NORTHSTAR_SHARED_STATE_ARTIFACT: shared_state_payload,
        NORTHSTAR_FAMILY_BLOCKER_ARTIFACT: blocker_payload,
        NORTHSTAR_OBSERVER_SUMMARY_ARTIFACT: observer_payload,
        NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT: comparison_payload,
    }
    if output_dir is not None:
        for artifact_name, payload in bundle.items():
            write_design_suite_artifact(output_dir, artifact_name, payload)
    return bundle
