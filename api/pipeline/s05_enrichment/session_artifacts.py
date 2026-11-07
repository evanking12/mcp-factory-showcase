"""S-05 session artifacts."""

STAGE_ARTIFACTS = {
    "backfill_result.json": {
        "description": "Schema backfill statistics",
        "format": '{"patches_requested": N, "patches_applied": N, "patched_functions": [...]}',
        "produced_by": "_run_phase_7_backfill",
        "consumed_by": ["session-snapshot"],
    },
    "verification-report.json": {
        "description": "Per-function verification outcomes (verified/inferred/error)",
        "format": '{"verified_count": N, "inferred_count": N, "entries": [...]}',
        "produced_by": "_run_phase_7b_verify_enrichment",
        "consumed_by": ["MC-5", "MC-6", "session-snapshot", "UI coverage display"],
    },
    "mc-decisions/mc5-post-verification.json": {
        "description": "MC-5 read-to-write chaining decisions",
        "format": '[{"trigger": "...", "analysis": {...}, "action": "...", "result": "..."}]',
        "produced_by": "_mc5_post_verification",
        "consumed_by": ["MC-6 (prior MC decisions as context)"],
    },
    "mcp_schema_post_discovery.json": {
        "description": "Schema snapshot after backfill (for diffing)",
        "format": "Full MCP schema JSON",
        "produced_by": "_run_phase_7_backfill",
        "consumed_by": ["session-snapshot (diff tool)"],
    },
}

FUTURE_RUNTIME_ALIASES = {
    "evidence/stage-05a-schema-backfill/backfill-report.json": "backfill_result.json",
    "evidence/stage-05a-schema-backfill/schema-post-backfill.json": "mcp_schema_post_discovery.json",
    "evidence/stage-05b-verification-replay/verification-report.json": "verification-report.json",
    "evidence/stage-05c-read-to-write-chaining/mc5-post-verification.json": "mc-decisions/mc5-post-verification.json",
}
