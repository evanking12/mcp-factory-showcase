# MCP Factory

MCP Factory recovers callable interfaces from undocumented Windows binaries and
turns them into tools that AI agents can call through the Model Context Protocol
(MCP). It was built as a Microsoft-sponsored capstone by a four-person University
of South Florida team.

**[Explore the five-run replay](docs/creator-challenge/replay-demo/README.md)** ·
[View a recorded trace](docs/creator-challenge/replay-demo/data/runs/easy01/run-trace.md) ·
[Set up the Windows prototype](SETUP.md)

## Try the replay

Run this from the repository root with Python, then open
[localhost:8088](http://localhost:8088/). The browser displays recorded runs and
diagnostic traces without starting the Windows backend or using an API key.

```sh
python -m http.server 8088 --directory docs/creator-challenge/replay-demo
```

## What I built

Evan King led the team and worked on binary and function discovery, checkpointed
runtime probes, and regression gates. The pipeline uses Python, FastAPI, Ghidra,
and a Windows execution bridge.

| Design decision | Tradeoff |
| --- | --- |
| Start with [PE export discovery](src/discovery/exports.py) and [Ghidra analysis](src/discovery/ghidra_analyzer.py). | Export names help identify entry points. Static analysis can suggest signatures, but behavior and state requirements still need runtime evidence. |
| Use [checkpointed probes](api/pipeline/s02_probe/probe_loop.py) to record arguments, results, and prerequisites. | Stateful APIs need a valid sequence of calls. Capturing and replaying evidence adds bookkeeping and makes failures easier to isolate. |
| Compare end-to-end runs against [pinned baselines](configs/regression/pinned_baselines/) before accepting regressions as resolved. | Missing evidence and incomparable runs can block a result even when a call returns successfully. The replay shows those distinctions alongside the traces. |

The [pipeline map](api/pipeline/README.md) covers how those stages connect to
[MCP server generation](src/generation/section4_generate_server.py).

## One recorded example

In the [Easy01 replay](docs/creator-challenge/replay-demo/data/runs/easy01/run.json),
the Windows fixture exports `SP_OpenOperatorSession`. The run records that
function as the required semantic checkpoint for the session-bootstrap target.
Easy01 verified all four expected checkpoints. Batch B is also included as a
package-level diagnostic, with dependency-only DLLs and runtime targets shown
separately.

You can compare the
[fixture source](tests/fixtures/spectrum_transaction_release_settlement_suite/src/spectrum_session_bootstrap.c)
with the [recorded trace](docs/creator-challenge/replay-demo/data/runs/easy01/run-trace.md).

## Reproduce and inspect

- [Regenerate the replay](docs/creator-challenge/replay-demo/README.md#regenerate-the-data)
  from the tracked inputs or verify the shipped data with
  `python scripts/creator_challenge/build_replay_bundle.py --check`.
- [Set up the Windows prototype](SETUP.md) to run binary analysis and tool
  generation locally.
- [Read the architecture map](docs/architecture/README.md) for the execution
  pipeline, runtime boundary, and validation design.

Built by Evan King, Layalie AbuOleim, Caden Spokas, and Thinh Nguyen.
[MIT License](LICENSE).
