# S-05 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| `api_reference.md` | S-04 | Source for schema backfill and parameter descriptions. |
| Reconciled findings and working calls | S-03/S-02 | Inputs for verification. |
| Current schema/invocables | Discovery and prior stages | Surface to patch and validate. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `backfill_result.json` | Optional | Records schema backfill statistics and patched functions. |
| `verification-report.json` | Optional | Records verified, inferred, and failed verification outcomes. |
| `mc-decisions/mc5-post-verification.json` | Optional | Records read-to-write chaining decisions. |
| `mcp_schema_post_discovery.json` | Optional | Captures schema after enrichment/backfill for diffing. |

## Runtime Alias Outputs

These aliases are additive and do not replace legacy paths.

| Alias | Source |
| --- | --- |
| `evidence/stage-05a-schema-backfill/backfill-report.json` | `backfill_result.json` |
| `evidence/stage-05a-schema-backfill/schema-post-backfill.json` | `mcp_schema_post_discovery.json` |
| `evidence/stage-05b-verification-replay/verification-report.json` | `verification-report.json` |
| `evidence/stage-05c-read-to-write-chaining/mc5-post-verification.json` | `mc-decisions/mc5-post-verification.json` |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-06 gaps | Verification results and enriched schema for retries. |
| S-07 finalize | Verified/inferred distinction and enriched schema. |
| UI/session snapshot | Verification and backfill reports for operator review. |
