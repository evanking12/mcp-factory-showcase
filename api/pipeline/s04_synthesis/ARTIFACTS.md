# S-04 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| Reconciled findings | S-03 | Supplies corrected behavior evidence. |
| Vocab and sentinel context | S-00 through S-03 | Gives terms and return-code meanings. |
| Invocable registry | Discovery/context | Defines the API surface to document. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `api_reference.md` | Yes when synthesis runs | Human-readable API reference built from accumulated evidence. |
| `mc-decisions/mc4-post-synthesis.json` | Optional | Records init clues inferred from synthesis context. |
| `evidence/stage-04-synthesis/synthesis-input-snapshot.json` | Optional | Captures synthesis input for auditability. |
| `evidence/stage-04-synthesis/synthesis-coverage-check.json` | Optional | Records function coverage in the synthesis output. |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-05 enrichment | Uses synthesis to backfill parameter descriptions and schema details. |
| S-06 gaps | Uses synthesis context for stubborn failures. |
| S-07 finalize | Uses synthesis as narrative input for behavioral spec and closure. |
| UI/session snapshot | Displays generated API documentation. |
