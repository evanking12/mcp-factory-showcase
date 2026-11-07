"""S-00 checkpoint hooks: what checkpoint data this stage reads and writes.

READS (from prior checkpoint):
  - sentinels: dict[int, str]          Prior calibrated sentinel table
  - vocab: dict                        Prior accumulated vocabulary
  - static_analysis_result: dict       Prior binary analysis (skip re-analysis)
  - dll_strings: dict                  Prior embedded string evidence
  - call_graph: dict                   Prior XREF call graph
  - ghidra_data_types: list            Prior Ghidra data types

WRITES (to checkpoint after completion):
  - sentinels                          Calibrated sentinel table (may be refined)
  - vocab                              Seeded vocabulary with user hints + binary seeds + FLOSS
  - static_analysis_result             Binary analysis result (includes FLOSS strings)
  - dll_strings                        Extracted string evidence
  - call_graph                         Function dependency DAG from Ghidra XREF
  - ghidra_data_types                  Structs, enums, typedefs from Ghidra DTM

STAGE GATE:
  is_stage_complete("s00_setup") -> skip entire calibration + vocab + static analysis
"""
CHECKPOINT_STAGE_NAME = "s00_setup"

READS_FROM_CHECKPOINT = [
    "sentinels",
    "vocab",
    "static_analysis_result",
    "dll_strings",
    "call_graph",
    "ghidra_data_types",
]

WRITES_TO_CHECKPOINT = [
    "sentinels",
    "vocab",
    "static_analysis_result",
    "dll_strings",
    "call_graph",
    "ghidra_data_types",
]

STAGE_COMPLETE_METADATA = {
    "sentinel_count": "len(ctx.sentinels)",
    "vocab_keys": "list(ctx.vocab.keys())[:10]",
    "call_graph_edges": "sum(len(v) for v in ctx.call_graph.values())",
    "data_type_count": "len(ctx.ghidra_data_types)",
}
