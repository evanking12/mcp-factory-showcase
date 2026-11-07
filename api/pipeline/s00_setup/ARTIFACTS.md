# S-00 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| DLL bytes or local DLL path | Intake/discovery job | Static setup needs the binary, not only the invocable skeleton. |
| `ctx.invocables` | Discovery/Ghidra bridge | Supplies callable names, parameters, decompiled hints, call graph extras, and execution paths. |
| Job hints and use cases | `status.json` | Seeds vocabulary, user context, and optional hint-provided error codes. |
| Prior vocab or sentinels | Previous run / blob reload | Allows circular enrichment instead of cold restart. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `sentinel_calibration.json` | Yes | Captures calibrated or hinted sentinel/error-code meanings for downstream interpretation. |
| `vocab.json` | Yes | Captures IDs, error codes, value semantics, and user context used by later stages. |
| `static_analysis.json` | Yes when binary bytes are available | Captures binary strings, IAT hints, harvested sentinels, and static prompt context. |
| `static_enrichment.json` | Yes after static surface extraction runs | Normalizes callable inventory, prerequisite hints, deferred snippets, and ambiguity without requiring Ghidra availability. |
| `s01_handoff_packet.json` | Yes for the current S-00 to S-01 seam | Organizes S-00 output into an admitted packet for S-01 instead of raw scattered context. |
| `call_graph.json` | Optional | Captures exported-function call relationships when Ghidra XREF data is available. |
| `ghidra_data_types.json` | Optional | Captures recovered structs, enums, and typedefs when Ghidra data types are available. |

## Aliases And Snapshot Paths

| Live blob | Snapshot alias |
| --- | --- |
| `{job_id}/s01_handoff_packet.json` | `stage-00-setup/s01-handoff-packet.json` |
| `{job_id}/s01_handoff_packet.json` | `evidence/stage-00-setup/s01-handoff-packet.json` |
| `{job_id}/sentinel_calibration.json` | `stage-00-setup/sentinel_calibration.json` |
| `{job_id}/static_analysis.json` | `stage-00-setup/static_analysis.json` |
| `{job_id}/static_enrichment.json` | `stage-00-setup/static-enrichment.json` |
| `{job_id}/static_enrichment.json` | `evidence/stage-00-setup/static-enrichment.json` |
| `{job_id}/sentinel_calibration.json` | `evidence/stage-00a-setup-baseline/sentinel-calibration.json` |
| `{job_id}/vocab.json` | `evidence/stage-00a-setup-baseline/vocab.json` |
| `{job_id}/static_analysis.json` | `evidence/stage-00b-static-evidence/static-analysis.json` |
| `{job_id}/static_enrichment.json` | `evidence/stage-00b-static-evidence/static-enrichment.json` |
| `{job_id}/call_graph.json` | `evidence/stage-00b-static-evidence/call-graph.json` |
| `{job_id}/ghidra_data_types.json` | `evidence/stage-00b-static-evidence/ghidra-data-types.json` |
| `{job_id}/s01_handoff_packet.json` | `evidence/stage-00c-admission-handoff/s01-handoff-packet.json` |
| `{job_id}/vocab.json` | `stage-05-finalization/vocab.json` and `evidence/stage-07-finalize/final-vocab.json` |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-01 unlock | Admitted `baseline_truth`, `surface_inventory`, `prior_hints`, and `s01_targets` from `s01_handoff_packet.json`; it does not read `static_enrichment.json` directly. |
| S-02 probe | Sentinels, vocab, static hints, call graph, and unlock context inherited through `ExploreContext`. |
| S-03 through S-07 | Sentinel meanings, vocab, probe context, and optional static structure through context and snapshot artifacts. |
| Session snapshot | Legacy and canonical aliases for review, save-session, and operator inspection. |

## Producer Ownership

`sentinel_calibration.json` and `vocab.json` are produced through the S-00-owned
setup baseline boundary at `api/pipeline/s00_setup/setup_baseline.py`.
`baseline_truth.py` and `vocab_prior_hints.py` remain the internal seams inside
that boundary. The current sentinel calibration implementation remains in
`api/pipeline/s00_setup/calibration.py`, and the current vocab implementation
remains in `api/pipeline/s00_setup/vocab_seed.py`, so probing, hint fallback,
prior baseline, use-case, and sentinel merge behavior remain unchanged.

Static artifacts are produced through the S-00-owned static evidence boundary
at `api/pipeline/s00_setup/static_evidence.py`.
`api/pipeline/s00_setup/static_surface_extraction.py` remains as a
compatibility wrapper for the older seam name. The current implementation
remains in `api/pipeline/s00_setup/static_analysis.py` during this migration
wave so Ghidra/static behavior remains unchanged.

`static_enrichment.json` is produced through
`api/pipeline/s00_setup/static_enrichment.py` after static analysis completes.
It is additive static guidance only: callable inventory, prerequisite hints,
deferred snippets, data type previews, and ambiguity flags. The handoff packet
builder consumes selected bounded fields from this artifact; raw decompile/xref
material stays deferred and S-01 does not read the artifact directly.

`s01_handoff_packet.json` is produced through the S-00-owned
admission/handoff boundary at `api/pipeline/s00_setup/admission_handoff.py`.
`api/pipeline/s00_setup/s01_handoff_packet.py` remains as a compatibility
wrapper for existing imports and tests. The normalized packet builder still
lives in shared core during this migration wave so packet shape and
compatibility remain unchanged.
