"""S-07 session artifacts."""

STAGE_ARTIFACTS = {
    "behavioral_spec.py": {
        "description": "Typed Python behavioral specification",
        "format": "Python source with dataclasses and function stubs",
        "produced_by": "_run_phase_9_behavioral_spec",
        "consumed_by": ["MVP Component 2 (client.py generation)", "session-snapshot"],
    },
    "harmonization_report.json": {
        "description": "Final deterministic fixes applied",
        "format": '{"patched_error_to_success": [...], "counts": {"success": N, "error": N}}',
        "produced_by": "_run_phase_10_harmonize",
        "consumed_by": ["session-snapshot", "UI final report"],
    },
    "vocab.json": {
        "description": "Final vocabulary with synthesized description",
        "format": "Same as S-00 but with description field added",
        "produced_by": "_run_finalize",
        "consumed_by": ["run N+1 (circular enrichment)", "session-snapshot"],
    },
}
