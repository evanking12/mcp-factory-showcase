from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DESIGN_SUITE_SCHEMA_VERSION = "1.0.0"

NORTHSTAR_SUITE_ID = "northstar_transaction_suite"
NORTHSTAR_SUITE_NAME = "Northstar Transaction Suite"

DESIGN_SUITE_ACTIVE_MODULES = (
    "session",
    "inventory",
    "billing",
)

DESIGN_SUITE_DEFERRED_MODULE_ORDER = (
    "audit",
    "fulfillment",
    "notifications",
)

DESIGN_SUITE_BOUNDARY_REFERENCE = (
    "initialization_group",
    "dependency_class",
    "frontier_slice",
)

DESIGN_SUITE_BLOCKER_CLASSES = (
    "bootstrap_family_blocker",
    "shared_state_carrier_blocker",
    "two_family_overlap_blocker",
    "forked_state_blocker",
    "late_confirmation_blocker",
    "mutual_pressure_blocker",
)

PRIMARY_BLOCKER_FAMILY = "bootstrap_family_blocker"
SUPPORTING_BLOCKER_PRESSURE = "shared_state_carrier_blocker"


def normalize_blocker_class(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in DESIGN_SUITE_BLOCKER_CLASSES:
        return candidate
    raise ValueError(f"unknown design-suite blocker class: {value!r}")


@dataclass(frozen=True)
class DesignSuiteBlockerEntry:
    blocker_class: str
    purpose: str
    not_equivalent_to: tuple[str, ...]
    schema_version: str = DESIGN_SUITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_class", normalize_blocker_class(self.blocker_class))
        purpose = str(self.purpose or "").strip()
        if not purpose:
            raise ValueError("design-suite blocker purpose must be non-empty")
        boundaries = tuple(
            str(item or "").strip()
            for item in tuple(self.not_equivalent_to or ())
            if str(item or "").strip()
        )
        if not boundaries:
            raise ValueError("design-suite blocker not_equivalent_to must be non-empty")
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "not_equivalent_to", boundaries)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DESIGN_SUITE_BLOCKER_TAXONOMY = {
    "bootstrap_family_blocker": DesignSuiteBlockerEntry(
        blocker_class="bootstrap_family_blocker",
        purpose="One root state package blocks an entire downstream family until it is satisfied.",
        not_equivalent_to=DESIGN_SUITE_BOUNDARY_REFERENCE,
    ),
    "shared_state_carrier_blocker": DesignSuiteBlockerEntry(
        blocker_class="shared_state_carrier_blocker",
        purpose="Several consumers reuse one carrier but require different validity properties from it.",
        not_equivalent_to=DESIGN_SUITE_BOUNDARY_REFERENCE,
    ),
    "two_family_overlap_blocker": DesignSuiteBlockerEntry(
        blocker_class="two_family_overlap_blocker",
        purpose="One seam plausibly belongs to more than one family and risks being grouped too coarsely.",
        not_equivalent_to=DESIGN_SUITE_BOUNDARY_REFERENCE,
    ),
    "forked_state_blocker": DesignSuiteBlockerEntry(
        blocker_class="forked_state_blocker",
        purpose="More than one plausible state branch exists, but only one is lineage-correct.",
        not_equivalent_to=DESIGN_SUITE_BOUNDARY_REFERENCE,
    ),
    "late_confirmation_blocker": DesignSuiteBlockerEntry(
        blocker_class="late_confirmation_blocker",
        purpose="Local success is insufficient because correctness is only revealed downstream.",
        not_equivalent_to=DESIGN_SUITE_BOUNDARY_REFERENCE,
    ),
    "mutual_pressure_blocker": DesignSuiteBlockerEntry(
        blocker_class="mutual_pressure_blocker",
        purpose="Two families must both advance before either can fully confirm.",
        not_equivalent_to=DESIGN_SUITE_BOUNDARY_REFERENCE,
    ),
}


@dataclass(frozen=True)
class NorthstarSuiteContract:
    suite_id: str = NORTHSTAR_SUITE_ID
    suite_name: str = NORTHSTAR_SUITE_NAME
    active_modules: tuple[str, ...] = DESIGN_SUITE_ACTIVE_MODULES
    deferred_modules: tuple[str, ...] = DESIGN_SUITE_DEFERRED_MODULE_ORDER
    primary_blocker_family: str = PRIMARY_BLOCKER_FAMILY
    supporting_blocker_pressure: str = SUPPORTING_BLOCKER_PRESSURE
    artifact_scope: str = "session_only"
    compare_boundary: str = "architecture_proof_only"
    max_active_modules: int = 3
    max_canonical_artifacts: int = 5
    max_primary_blocker_families: int = 1
    max_supporting_pressures: int = 1
    acceptable_deferred_major_explanations: int = 1
    schema_version: str = DESIGN_SUITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "suite_id", str(self.suite_id or "").strip())
        object.__setattr__(self, "suite_name", str(self.suite_name or "").strip())
        object.__setattr__(
            self,
            "active_modules",
            tuple(str(item or "").strip() for item in tuple(self.active_modules or ()) if str(item or "").strip()),
        )
        object.__setattr__(
            self,
            "deferred_modules",
            tuple(str(item or "").strip() for item in tuple(self.deferred_modules or ()) if str(item or "").strip()),
        )
        object.__setattr__(self, "primary_blocker_family", normalize_blocker_class(self.primary_blocker_family))
        object.__setattr__(
            self,
            "supporting_blocker_pressure",
            normalize_blocker_class(self.supporting_blocker_pressure),
        )
        if not self.suite_id or not self.suite_name:
            raise ValueError("suite_id and suite_name must be non-empty")
        if self.active_modules != DESIGN_SUITE_ACTIVE_MODULES:
            raise ValueError("Northstar first slice must remain session/inventory/billing")
        if self.deferred_modules != DESIGN_SUITE_DEFERRED_MODULE_ORDER:
            raise ValueError("Northstar deferred-module order must remain audit/fulfillment/notifications")
        if self.artifact_scope != "session_only":
            raise ValueError("Northstar tranche one artifacts must remain session_only")
        if self.compare_boundary != "architecture_proof_only":
            raise ValueError("Northstar tranche one compare boundary must remain architecture_proof_only")
        if self.max_active_modules != 3:
            raise ValueError("Northstar tranche one max_active_modules must remain 3")
        if self.max_canonical_artifacts != 5:
            raise ValueError("Northstar tranche one max_canonical_artifacts must remain 5")
        if self.max_primary_blocker_families != 1:
            raise ValueError("Northstar tranche one max_primary_blocker_families must remain 1")
        if self.max_supporting_pressures != 1:
            raise ValueError("Northstar tranche one max_supporting_pressures must remain 1")
        if self.acceptable_deferred_major_explanations != 1:
            raise ValueError("Northstar tranche one acceptable_deferred_major_explanations must remain 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_NORTHSTAR_CONTRACT = NorthstarSuiteContract()
