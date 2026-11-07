# S-07 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| Gap outcomes and questions | S-06 | Determines whether closure is done or awaiting clarification. |
| Verification and enrichment results | S-05 | Distinguishes proven behavior from inferred behavior. |
| Synthesis | S-04 | Provides narrative context for behavioral spec. |
| Reconciled findings and vocab | S-03/S-00 | Supplies final behavior and terminology. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `behavioral_spec.py` | Optional | Typed Python behavioral summary of the API surface. |
| `harmonization_report.json` | Optional | Records final deterministic finding repairs. |
| `vocab.json` | Yes when finalization updates description/vocab | Captures final vocabulary and one-sentence DLL description. |
| Contract artifacts | Optional | Emits session/stage/transition/cohesion surfaces for review. |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| Operator/UI | Final status, behavioral spec, harmonization, and open questions. |
| Future reruns | Final vocab, findings, and closure state. |
| Session snapshot | Final artifacts and contract surfaces. |
