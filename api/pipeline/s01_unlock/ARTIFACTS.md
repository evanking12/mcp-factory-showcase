# S-01 Artifacts

## Owned Inputs

| Input | Source | Why it matters |
| --- | --- | --- |
| Admitted S-00 handoff slice | `s01_handoff_packet.json` | Provides narrowed setup/static context for unlock work. |
| Legacy vocab, strings, and sentinels | `ExploreContext` fallback | Keeps S-01 compatible if the packet is missing, thin, or malformed. |
| `ctx.invocables` | Discovery/S-00 context | Supplies candidate init and write functions. |
| Prior unlock state | Checkpoint or previous run context | Allows known unlock sequences to be replayed instead of rediscovered. |

## Owned Outputs

| Artifact | Required | Why it exists |
| --- | --- | --- |
| `write_unlock_probe.json` | Yes | Records unlock probe outcome, sequence, tested write function, and blocking sentinel. |
| `winning_init_sequence.json` | Optional | Captures the concrete sequence that activated write mode when discovered. |
| `code_reasoning_analysis.json` | Optional | Captures LLM reasoning over decompiled C for unlock patterns. |

## Downstream Consumers

| Consumer | What it reads |
| --- | --- |
| S-02 probe | `ctx.write_unlock_block`, live findings for unlock sequence calls, and any active write-mode state. |
| S-03 reconcile | Probe outcome and write failure context. |
| S-06 gaps | Prior unlock attempts and MC context for final unlock reasoning. |
| Session snapshot/UI | `write_unlock_probe.json` and any winning sequence artifacts. |

## Compatibility Notes

S-01 consumes the admitted S-00 packet first, but it must fall back cleanly to
legacy context if the packet is absent or malformed.
