"""S-04 session artifacts."""

STAGE_ARTIFACTS = {
    "api_reference.md": {
        "description": "LLM-generated API reference documentation",
        "format": "Markdown document with per-function sections",
        "produced_by": "_run_phase_6_synthesize",
        "consumed_by": ["S-05 backfill", "S-07 behavioral spec", "session-snapshot", "UI display"],
    },
    "mc-decisions/mc4-post-synthesis.json": {
        "description": "MC-4 init sequence clues from synthesis",
        "format": '[{"trigger": "...", "analysis": {...}, "action": "...", "result": "..."}]',
        "produced_by": "_mc4_post_synthesis",
        "consumed_by": ["MC-6 (prior MC decisions as context)"],
    },
    "evidence/stage-04-synthesis/synthesis-input-snapshot.json": {
        "description": "Snapshot of what the LLM received for synthesis",
        "format": '{"function_count": N, "findings_count": N, "findings": [...], "vocab": {...}}',
        "produced_by": "_run_phase_6_synthesize",
        "consumed_by": ["debugging / audit trail"],
    },
    "evidence/stage-04-synthesis/synthesis-coverage-check.json": {
        "description": "Which functions appear in the synthesis vs total",
        "format": '{"total_functions": N, "covered_in_report": N, "coverage_pct": F}',
        "produced_by": "_run_phase_6_synthesize",
        "consumed_by": ["debugging / audit trail"],
    },
}
