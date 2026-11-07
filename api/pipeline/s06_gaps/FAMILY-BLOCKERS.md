# S-06 Family Blockers

S-06 owns late gap resolution and clarification surfacing. It should classify
blockers that remain after probing, reconciliation, synthesis, and enrichment.

## handles

| Blocker family | Stage stance |
| --- | --- |
| unresolved functions need bounded retry | Attempt gap resolution when enabled. |
| final unlock reasoning needed | Run MC-6 when applicable. |
| user clarification is required | Surface explicit `explore_questions`. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| gap resolution disabled by config | Record configuration outcome and pass to finalization. |
| retry remains inconclusive | Preserve unresolved status for S-07 closure. |
| synthesis/verification disagreement remains | Pass explicit uncertainty forward. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| rebuilding earlier evidence | Not owned; prior stages or rerun must supply it. |
| deciding product-level acceptance | Not owned; operator/finalization handles closure. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| repeated gap loops with no new evidence | Requires roadblock classification or new retry strategy. |
| clarification questions are too vague to act on | Requires better question-generation contract. |
