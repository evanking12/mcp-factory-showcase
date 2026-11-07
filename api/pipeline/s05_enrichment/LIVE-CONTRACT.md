# S-05 Live Contract

## Guarantees Today

- Attempts schema backfill from synthesis when available.
- Attempts verification of successful working calls.
- Keeps verified and inferred outcomes distinct.
- May emit MC-5 read-to-write chaining decisions.
- Exposes runtime-visible S-05A/B/C identities while keeping `s05_enrichment`
  as the compatibility parent.

## Semantic Obligation

S-05 must enrich schemas and verify claims without promoting weak positives into
proof. It separates verified behavior from inferred or unverified behavior.

Runtime-visible split:

- `S-05A schema_backfill` / `s05_schema_backfill`: backfill schema descriptions
  from synthesis without claiming verification truth.
- `S-05B verification_replay` / `s05_verification_replay`: re-execute and
  classify working-call/state-effect evidence without promoting weak positives.
- `S-05C read_to_write_chaining` / `s05_read_to_write_chaining`: use verified
  read outputs for bounded MC-5 write retry decisions.

## Handoff Rule

S-05 hands off enriched schema and verification status. Later stages should not
treat every success claim as equally proven.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Enrichment/verification has run or cleanly produced no applicable work. |
| Stay | Synthesis or working-call inputs are too weak to enrich responsibly. |
| Fail | Verification or schema patching corrupts the schema or cannot persist evidence. |

## Compatibility Notes

Verification coverage may be partial. Partial verification is useful evidence
but not full DLL proof.

`s05_enrichment` remains the legacy compatibility parent. Legacy artifact paths
remain canonical until a later cleanup campaign explicitly changes that.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-05 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
