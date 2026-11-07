# Stage Split Doctrine

This folder is migration doctrine and target-stage reasoning. It is not live
pipeline implementation truth by itself.

For current live pipeline behavior, use:

- `api/pipeline/README.md`
- `api/pipeline/sNN_*/README.md`
- `api/pipeline/sNN_*/PURPOSE.md`
- `api/pipeline/sNN_*/FLOW.md`
- `api/pipeline/sNN_*/ARTIFACTS.md`
- `api/pipeline/sNN_*/SYSTEMS.md`
- `api/pipeline/sNN_*/LIVE-CONTRACT.md`
- `api/pipeline/sNN_*/TRACE.md`

## Active Doctrine Files

| File | Purpose |
| --- | --- |
| `7_stages_to_11_stages.md` | Broad migration argument from the current stage shape toward a narrower target stage map. |
| `s00_stage_split.md` | Historical S-00 split intent and design baseline. Use current campaign evidence before treating any proposed split shape as implementation-ready. |
| `stage_handoff_packets.md` | Handoff packet, reviewer, coordinator, and admission-organization doctrine. |
| `stage_purpose.md` | Target-stage purpose law and handoff-aware interpretation. |

## Archived Doctrine

Historical or superseded notes live under `_archive/`.

| File | Why Archived |
| --- | --- |
| `_archive/PRE-MIGRATION-PACKET.md` | Superseded by the evidence-led S-00 split campaign and current regression/observability system. |
| `_archive/after_11_stages.md` | Preserved as raw architectural thinking, but no longer an active stage-split doctrine surface. |

## Live Truth Rule

If a fact describes what the code does today, mirror it into the owning stage
folder under `api/pipeline/sNN_*/`. If it describes where the architecture is
going, keep it here and do not present it as live behavior.
