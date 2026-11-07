"""S-05 checkpoint hooks.

READS:
  - Findings for verification
  - inv_map for function lookup

WRITES:
  - Verification results per function
  - write_unlock_block: updated if MC-5 cracks write-unlock

STAGE GATE:
  is_stage_complete("s05_enrichment") -> compatibility parent for full S-05
  is_stage_complete("s05_schema_backfill") -> skip S-05A schema backfill
  is_stage_complete("s05_verification_replay") -> skip S-05B verification replay
  is_stage_complete("s05_read_to_write_chaining") -> skip S-05C read-to-write chaining
"""
CHECKPOINT_STAGE_NAME = "s05_enrichment"
CHECKPOINT_SUBSTAGE_NAMES = [
    "s05_schema_backfill",
    "s05_verification_replay",
    "s05_read_to_write_chaining",
]

READS_FROM_CHECKPOINT = [
    "findings",
    "inv_map",
]

WRITES_TO_CHECKPOINT = [
    "verification_results",
    "write_unlock_block",
]

STAGE_COMPLETE_METADATA = {}
