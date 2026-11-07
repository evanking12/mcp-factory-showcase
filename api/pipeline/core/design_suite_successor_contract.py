from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.design_suite_taxonomy import DESIGN_SUITE_SCHEMA_VERSION, normalize_blocker_class


SUCCESSOR_SUITE_CONTRACT_ARTIFACT = "successor-suite-contract.json"
SUCCESSOR_SUITE_FIRST_SLICE_ARTIFACT = "successor-suite-first-slice.json"

ATLAS_SUCCESSOR_SUITE_ID = "atlas_reconciliation_suite"
ATLAS_SUCCESSOR_SUITE_NAME = "Atlas Reconciliation Suite"


@dataclass(frozen=True)
class SuccessorSuiteContract:
    suite_name: str = ATLAS_SUCCESSOR_SUITE_NAME
    suite_id: str = ATLAS_SUCCESSOR_SUITE_ID
    suite_purpose: str = (
        "Prove that the reusable design-suite campaign pathway survives a harder "
        "mutual-pressure family where two provisional upstream truths must be "
        "jointly confirmed before either is trustworthy."
    )
    suite_non_purpose: str = (
        "It is not a raw unlock-count suite, not a compare-bearing campaign surface, "
        "and not a replacement for Northstar."
    )
    inherited_surfaces: tuple[str, ...] = (
        "campaign truth projection",
        "campaign cohesion projection",
        "campaign attribution preservation",
        "local runtime and package projection shape",
        "expected-observed comparison shape",
    )
    non_inherited_surfaces: tuple[str, ...] = (
        "Northstar story and module names",
        "Northstar-specific campaign artifact naming",
        "Northstar-specific branch review wording",
        "compare or promotion readiness",
    )
    first_harder_pressure_family: str = "mutual_pressure_blocker"
    first_bounded_slice: tuple[str, ...] = ("batch", "identity", "ledger", "reconcile")
    expected_observed_contract_present: bool = True
    compare_ready: bool = False
    promotion_ready: bool = False
    schema_version: str = DESIGN_SUITE_SCHEMA_VERSION
    artifact_type: str = SUCCESSOR_SUITE_CONTRACT_ARTIFACT

    def __post_init__(self) -> None:
        suite_name = str(self.suite_name or "").strip()
        suite_id = str(self.suite_id or "").strip()
        suite_purpose = str(self.suite_purpose or "").strip()
        suite_non_purpose = str(self.suite_non_purpose or "").strip()
        first_harder_pressure_family = normalize_blocker_class(self.first_harder_pressure_family)
        first_bounded_slice = tuple(
            str(item or "").strip()
            for item in tuple(self.first_bounded_slice or ())
            if str(item or "").strip()
        )
        inherited_surfaces = tuple(
            str(item or "").strip()
            for item in tuple(self.inherited_surfaces or ())
            if str(item or "").strip()
        )
        non_inherited_surfaces = tuple(
            str(item or "").strip()
            for item in tuple(self.non_inherited_surfaces or ())
            if str(item or "").strip()
        )
        if not suite_name or not suite_id or not suite_purpose or not suite_non_purpose:
            raise ValueError("successor suite contract fields must be non-empty")
        if len(first_bounded_slice) not in {3, 4}:
            raise ValueError("successor first bounded slice must stay within 3-4 modules")
        if not inherited_surfaces or not non_inherited_surfaces:
            raise ValueError("successor suite inheritance surfaces must be non-empty")
        if self.compare_ready or self.promotion_ready:
            raise ValueError("successor suite contract must remain non-compare and non-promotion ready")
        object.__setattr__(self, "suite_name", suite_name)
        object.__setattr__(self, "suite_id", suite_id)
        object.__setattr__(self, "suite_purpose", suite_purpose)
        object.__setattr__(self, "suite_non_purpose", suite_non_purpose)
        object.__setattr__(self, "first_harder_pressure_family", first_harder_pressure_family)
        object.__setattr__(self, "first_bounded_slice", first_bounded_slice)
        object.__setattr__(self, "inherited_surfaces", inherited_surfaces)
        object.__setattr__(self, "non_inherited_surfaces", non_inherited_surfaces)
        if self.artifact_type != SUCCESSOR_SUITE_CONTRACT_ARTIFACT:
            raise ValueError("successor suite contract artifact_type mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SuccessorSuiteFirstSlice:
    suite_name: str = ATLAS_SUCCESSOR_SUITE_NAME
    first_harder_pressure_family: str = "mutual_pressure_blocker"
    active_modules: tuple[str, ...] = ("batch", "identity", "ledger", "reconcile")
    deferred_modules: tuple[str, ...] = ("settlement", "notifications")
    execution_inputs_present: bool = True
    expected_observed_contract_present: bool = True
    inherits_reusable_campaign_seam: bool = True
    compare_ready: bool = False
    promotion_ready: bool = False
    schema_version: str = DESIGN_SUITE_SCHEMA_VERSION
    artifact_type: str = SUCCESSOR_SUITE_FIRST_SLICE_ARTIFACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "first_harder_pressure_family", normalize_blocker_class(self.first_harder_pressure_family))
        active_modules = tuple(
            str(item or "").strip()
            for item in tuple(self.active_modules or ())
            if str(item or "").strip()
        )
        deferred_modules = tuple(
            str(item or "").strip()
            for item in tuple(self.deferred_modules or ())
            if str(item or "").strip()
        )
        if len(active_modules) not in {3, 4}:
            raise ValueError("successor active modules must remain within 3-4")
        if len(deferred_modules) > 2:
            raise ValueError("successor deferred modules must remain <= 2")
        if self.compare_ready or self.promotion_ready:
            raise ValueError("successor first slice must remain non-compare and non-promotion ready")
        object.__setattr__(self, "active_modules", active_modules)
        object.__setattr__(self, "deferred_modules", deferred_modules)
        if self.artifact_type != SUCCESSOR_SUITE_FIRST_SLICE_ARTIFACT:
            raise ValueError("successor first slice artifact_type mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_SUCCESSOR_SUITE_CONTRACT = SuccessorSuiteContract()
DEFAULT_SUCCESSOR_SUITE_FIRST_SLICE = SuccessorSuiteFirstSlice()
