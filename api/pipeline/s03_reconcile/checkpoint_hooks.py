"""S-03 checkpoint hooks.

READS:
  - All S-02 per-function checkpoints must be present
  - sentinels for MC-3 classification

WRITES:
  - Reconciled findings (error->success upgrades)
  - sentinel_catalog: promoted sentinel evidence
  - write_unlock_block: updated if MC-3 cracks write-unlock

STAGE GATE:
  is_stage_complete("s03_reconcile") -> skip reconciliation + MC-3
"""
CHECKPOINT_STAGE_NAME = "s03_reconcile"

READS_FROM_CHECKPOINT = [
    "per_function_entries",
    "sentinels",
]

WRITES_TO_CHECKPOINT = [
    "sentinel_catalog",
    "write_unlock_block",
]

STAGE_COMPLETE_METADATA = {}
