from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


INTERWOVEN_SCHEMA_VERSION = "1.0.0"

INTERWOVEN_TAXONOMY_TERMS = (
    "producer",
    "consumer",
    "shared_state_carrier",
    "staged_interwoven_chain",
)

INTERWOVEN_RELATIONSHIP_KINDS = (
    "producer_consumer",
    "shared_state",
    "staged_chain",
)

INTERWOVEN_BOUNDARY_REFERENCE = (
    "initialization_group",
    "dependency_class",
    "frontier_slice",
)


def normalize_interwoven_term(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in INTERWOVEN_TAXONOMY_TERMS:
        return candidate
    raise ValueError(f"unknown interwoven taxonomy term: {value!r}")


def normalize_relationship_kind(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in INTERWOVEN_RELATIONSHIP_KINDS:
        return candidate
    raise ValueError(f"unknown interwoven relationship kind: {value!r}")


@dataclass(frozen=True)
class InterwovenTaxonomyEntry:
    term: str
    purpose: str
    not_equivalent_to: tuple[str, ...]
    canonical_relationship_kinds: tuple[str, ...]
    schema_version: str = INTERWOVEN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "term", normalize_interwoven_term(self.term))
        purpose = str(self.purpose or "").strip()
        if not purpose:
            raise ValueError("interwoven taxonomy entry purpose must be non-empty")
        object.__setattr__(self, "purpose", purpose)
        boundaries = tuple(
            str(item or "").strip()
            for item in tuple(self.not_equivalent_to or ())
            if str(item or "").strip()
        )
        if not boundaries:
            raise ValueError("interwoven taxonomy entry not_equivalent_to must be non-empty")
        object.__setattr__(self, "not_equivalent_to", boundaries)
        relationship_kinds = tuple(
            normalize_relationship_kind(item)
            for item in tuple(self.canonical_relationship_kinds or ())
        )
        if not relationship_kinds:
            raise ValueError("interwoven taxonomy entry canonical_relationship_kinds must be non-empty")
        object.__setattr__(self, "canonical_relationship_kinds", relationship_kinds)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


INTERWOVEN_TAXONOMY = {
    "producer": InterwovenTaxonomyEntry(
        term="producer",
        purpose="Emits state another seam needs later.",
        not_equivalent_to=INTERWOVEN_BOUNDARY_REFERENCE,
        canonical_relationship_kinds=("producer_consumer", "staged_chain"),
    ),
    "consumer": InterwovenTaxonomyEntry(
        term="consumer",
        purpose="Depends on upstream state emitted by another seam.",
        not_equivalent_to=INTERWOVEN_BOUNDARY_REFERENCE,
        canonical_relationship_kinds=("producer_consumer", "staged_chain"),
    ),
    "shared_state_carrier": InterwovenTaxonomyEntry(
        term="shared_state_carrier",
        purpose="Carries reusable state consumed by several seams or functions.",
        not_equivalent_to=INTERWOVEN_BOUNDARY_REFERENCE,
        canonical_relationship_kinds=("shared_state",),
    ),
    "staged_interwoven_chain": InterwovenTaxonomyEntry(
        term="staged_interwoven_chain",
        purpose="Represents an ordered state dependency that cannot be reduced to one edge.",
        not_equivalent_to=INTERWOVEN_BOUNDARY_REFERENCE,
        canonical_relationship_kinds=("staged_chain",),
    ),
}


def taxonomy_entry(term: str) -> InterwovenTaxonomyEntry:
    return INTERWOVEN_TAXONOMY[normalize_interwoven_term(term)]

