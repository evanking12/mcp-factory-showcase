"""S-00 session artifacts: what this stage persists to blob storage.

Every artifact listed here is uploaded to {job_id}/ in the artifact container
and captured by the session-snapshot endpoint for archival.
"""

STAGE_ARTIFACTS = {
    "sentinel_calibration.json": {
        "description": "Calibrated sentinel error code table",
        "format": '{"0xHHHHHHHH": "human meaning", ...}',
        "produced_by": "run_baseline_truth",
        "consumed_by": ["S-02 probe loop", "S-03 MC-3", "S-06 MC-6"],
    },
    "vocab.json": {
        "description": "Accumulated vocabulary (ID formats, value semantics, error codes, FLOSS strings)",
        "format": '{"id_formats": [...], "value_semantics": {...}, "error_codes": {...}}',
        "produced_by": "_run_phase_0_vocab_seed",
        "consumed_by": ["S-02 probe loop", "S-04 synthesis", "S-07 finalize"],
    },
    "static_analysis.json": {
        "description": "Full binary static analysis result (PE, IAT, strings, Capstone, FLOSS)",
        "format": '{"binary_strings": {...}, "iat_capabilities": {...}, "sentinel_constants": {...}, "floss_strings": {...}}',
        "produced_by": "_run_phase_0_static",
        "consumed_by": ["S-02 probe loop (via static_hints_block)"],
    },
    "s01_handoff_packet.json": {
        "description": "Additive S-00 -> S-01 handoff packet for the first migration seam",
        "format": '{"baseline_truth": {...}, "surface_inventory": {...}, "prior_hints": {...}, "coordination_decision": {...}}',
        "produced_by": "build_s00_s01_handoff_packet",
        "consumed_by": ["S-01 write-unlock probe"],
    },
    "call_graph.json": {
        "description": "Function dependency DAG from Ghidra XREF analysis",
        "format": '{"fn_name": ["callee1", "callee2"], ...}',
        "produced_by": "_build_call_graph",
        "consumed_by": ["S-02 curriculum ordering (topological sort)"],
    },
    "ghidra_data_types.json": {
        "description": "User-defined structs, enums, typedefs from Ghidra Data Type Manager",
        "format": '[{"name": "...", "kind": "struct|enum|typedef", ...}]',
        "produced_by": "_extract_ghidra_data_types",
        "consumed_by": ["S-02 probe loop (LLM system message)", "S-05 schema backfill"],
    },
}
