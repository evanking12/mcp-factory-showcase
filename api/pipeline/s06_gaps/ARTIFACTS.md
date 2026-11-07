# S-06 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| Failed or unresolved findings | S-02 through S-05 | Defines what still needs retry or clarification. |
| Verification results | S-05 | Distinguishes proven successes from unresolved cases. |
| Synthesis and MC context | S-04/S-05 | Supplies richer reasoning context for stubborn functions. |
| Sentinels, vocab, unlock history | S-00/S-01/S-03 | Supports final unlock and failure interpretation. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `mc-decisions/mc6-post-gap-resolution.json` | Optional | Records comprehensive final unlock/gap decisions. |
| `mcp_schema_post_gap_resolution.json` | Optional | Captures schema after gap-resolution attempts. |
| `mcp_schema_post_clarification.json` | Optional | Captures schema after clarification question generation. |
| `explore_questions` in `status.json` | Optional | Surfaces remaining user clarification questions. |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-07 finalize | Gap outcomes and remaining questions for closure. |
| Future reruns | Prior gap outcomes and clarification answers. |
| UI/session snapshot | Open questions and gap-resolution evidence. |
