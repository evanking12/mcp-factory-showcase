from api.pipeline.core.interwoven_taxonomy import (
    INTERWOVEN_BOUNDARY_REFERENCE,
    INTERWOVEN_RELATIONSHIP_KINDS,
    INTERWOVEN_TAXONOMY_TERMS,
    normalize_interwoven_term,
    normalize_relationship_kind,
    taxonomy_entry,
)


def test_interwoven_taxonomy_terms_are_distinct_and_normalized() -> None:
    assert set(INTERWOVEN_TAXONOMY_TERMS) == {
        "producer",
        "consumer",
        "shared_state_carrier",
        "staged_interwoven_chain",
    }
    assert normalize_interwoven_term("Producer") == "producer"
    assert normalize_interwoven_term("shared_state_carrier") == "shared_state_carrier"


def test_interwoven_taxonomy_entries_keep_boundaries_explicit() -> None:
    producer = taxonomy_entry("producer")
    shared_state = taxonomy_entry("shared_state_carrier")
    staged = taxonomy_entry("staged_interwoven_chain")

    assert set(producer.not_equivalent_to) == set(INTERWOVEN_BOUNDARY_REFERENCE)
    assert set(shared_state.not_equivalent_to) == set(INTERWOVEN_BOUNDARY_REFERENCE)
    assert set(staged.not_equivalent_to) == set(INTERWOVEN_BOUNDARY_REFERENCE)
    assert producer.canonical_relationship_kinds == ("producer_consumer", "staged_chain")
    assert shared_state.canonical_relationship_kinds == ("shared_state",)
    assert staged.canonical_relationship_kinds == ("staged_chain",)


def test_interwoven_relationship_kinds_validate_supported_shapes() -> None:
    assert set(INTERWOVEN_RELATIONSHIP_KINDS) == {
        "producer_consumer",
        "shared_state",
        "staged_chain",
    }
    assert normalize_relationship_kind("shared_state") == "shared_state"

