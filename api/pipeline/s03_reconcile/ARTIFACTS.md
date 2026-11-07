# S-03 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| Probe log and findings | S-02 | Supplies executable evidence and model-labeled findings. S-03 prefers the S-02C-owned durable probe-log alias when present and falls back to legacy `explore_probe_log.json`. |
| Sentinel catalog context | S-00 and S-02 observations | Supports return-code interpretation. |
| Write-unlock context | S-01/S-02 | Separates global unlock failures from per-function failures. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `mc-decisions/mc3-post-reconcile.json` | Optional | Records MC-3 write-failure analysis and actions. |
| `sentinel_catalog.json` | Optional | Promotes observed sentinel evidence for review and later interpretation. |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-04 synthesis | Reconciled findings and corrected status labels. |
| S-05 verification | Reconciled success claims and working calls. |
| S-06 gaps | MC decisions and unresolved failure classifications. |
| Session snapshot | Reconcile artifacts for auditability. |
