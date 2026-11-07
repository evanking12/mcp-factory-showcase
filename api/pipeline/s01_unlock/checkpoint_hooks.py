"""S-01 checkpoint hooks.

READS:
  - unlock_result: dict               Prior unlock outcome (replays winning sequence)
  - write_unlock_block: str            Prior unlock status text for LLM prompts

WRITES:
  - unlock_result                      {unlocked: bool, sequence: [...], notes: str}
  - write_unlock_block                 Text injected into every write-function prompt

STAGE GATE:
  is_stage_complete("s01_unlock") -> skip write-unlock probing entirely
"""
CHECKPOINT_STAGE_NAME = "s01_unlock"

READS_FROM_CHECKPOINT = [
    "unlock_result",
    "write_unlock_block",
]

WRITES_TO_CHECKPOINT = [
    "unlock_result",
    "write_unlock_block",
]

STAGE_COMPLETE_METADATA = {
    "unlocked": "ctx.unlock_result.get('unlocked', False)",
}
