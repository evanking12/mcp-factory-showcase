# S-02 Family Blockers

S-02 owns runtime probe evidence. It should classify blockers around execution,
argument choice, and observed status without pretending to own final synthesis.

## handles

| Blocker family | Stage stance |
| --- | --- |
| callable has no observed probe evidence | Attempt probing within configured budget. |
| candidate argument selection needed | Use vocab, sentinels, and prior context to choose calls. |
| lineage argument selection | Prefer trusted/primary lineage for trusted inputs and rejected/replay lineage for rejected inputs when both are available. |
| probe evidence persistence | Emit probe logs for later stages. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| write function blocked by unlock state | Defer to S-03/S-06 unlock reasoning with evidence. |
| functional precondition unmet | Record observation; later stages classify semantics. |
| ambiguous return code | Preserve evidence for reconciliation. |
| object-bound corrective authority | Preserve selected inputs and observations, but final authority must prove any success token is bound to the exact rejected, stale, unsafe, duplicate, or quarantined object. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| final API description | Not owned; S-04/S-07 handle synthesis/finalization. |
| broad cross-run strategy | Not owned by S-02 stage logic. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| repeated probes add no new evidence | Requires curriculum, budget, or blocker-classification improvement. |
| executor/lane instability masks probe truth | Requires lane/runtime reliability work before semantic claims. |
