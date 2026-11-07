"""S-06 session artifacts."""

STAGE_ARTIFACTS = {
    "mc-decisions/mc6-post-gap-resolution.json": {
        "description": "MC-6 comprehensive unlock attempt decisions",
        "format": '[{"trigger": "...", "analysis": {...}, "action": "...", "result": "..."}]',
        "produced_by": "_mc6_post_gap_resolution",
        "consumed_by": ["session-snapshot", "audit trail"],
    },
    "mcp_schema_post_gap_resolution.json": {
        "description": "Schema after gap resolution attempts",
        "format": "Full MCP schema JSON",
        "produced_by": "run_s06",
        "consumed_by": ["session-snapshot (diff tool)"],
    },
    "mcp_schema_post_clarification.json": {
        "description": "Schema after clarification question generation",
        "format": "Full MCP schema JSON",
        "produced_by": "run_s06",
        "consumed_by": ["session-snapshot (diff tool)"],
    },
}
