# S-01 Live Contract

## Guarantees Today

- Attempts to determine whether write functions require an init/unlock sequence.
- Reads the S-00 admitted handoff slice when available.
- Falls back to legacy `ctx.vocab`, `ctx.dll_strings`, and `ctx.sentinels` when the packet is unavailable, malformed, or too thin to provide usable admitted string evidence.
- Emits `write_unlock_probe.json` for the unlock attempt surface.

## Semantic Obligation

S-01 must establish whether write-mode preconditions are resolved, blocked, not
attempted, or explicitly deferred. It must not treat static prior hints as proof
of unlock behavior.

## Handoff Rule

S-01 should pass downstream a clear write-mode condition: resolved, blocked,
not attempted, or deferred. It should not pass raw S-00 richness downstream as
if it had organized it itself.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Unlock is resolved or explicitly deferred with a recorded probe artifact. |
| Stay | Packet/context is too weak to attempt unlock and fallback cannot supply enough input. |
| Fail | Unlock execution errors escape the stage or no probe artifact can be emitted. |

## Compatibility Notes

S-01 currently improves input structure more than behavior narrowing. `s01_targets`
is admitted and used for probe ordering, but broad unlock redesign is outside
this seam.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-01 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
