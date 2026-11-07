# S-02 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| Invocable registry | Discovery and prior stages | Defines the functions to probe. |
| Sentinels and vocab | S-00 | Interprets return codes and selects candidate arguments. |
| Write-unlock state | S-01 | Determines whether write calls can be attempted safely. |
| Prior findings | Previous run or current context | Avoids repeating stable work and focuses uncertainty. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `explore_probe_log.json` | Yes | Records concrete DLL calls, arguments, results, and probe context. |
| `explore_config.json` | Yes | Records runtime cap/profile settings for the probe run. |
| `mcp_schema_t0.json` | Yes | Captures the pre-enrichment schema baseline for later diffing. |
| `prerequisite_state_machine.json` | Yes when ordering runs | Records S-02A prerequisite roles, edges, and execution layers. |
| `evidence/stage-02a-probe-ordering/prerequisite-state-machine.json` | Alias | Session alias for S-02A ordering evidence. |
| `evidence/stage-02b-invocation-execution/stage-context.txt` | Alias | Session alias for S-02B invocation context. |
| `evidence/stage-02c-evidence-capture/probe-log.json` | Alias | Session alias for S-02C persisted probe log. |
| `evidence/stage-02c-evidence-capture/findings.json` | Alias | Session alias for S-02C persisted findings. |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-03 reconcile | Probe log and raw findings for deterministic correction. |
| S-04 synthesis | Behavior findings after reconciliation. |
| S-05 verification | Working calls and success claims. |
| S-07 finalize | Probe evidence for harmonization and closure. |
