# MCP Factory replay

The replay shows four recorded end-to-end baselines and one package-level
diagnostic. It serves sanitized data in a browser. It requires no API key or
Windows backend.

## Run the demo

Run the server from the repository root.

```sh
python -m http.server 8088 --directory docs/creator-challenge/replay-demo
```

Open [localhost:8088](http://localhost:8088/). Start with Easy01 and compare its
required semantic checkpoints with the discovered symbols. Batch B shows how
the pipeline separates DLLs it plans to probe from dependency-only DLLs.

## Regenerate the data

```sh
python scripts/creator_challenge/build_replay_bundle.py
```

The builder reads the
[pinned baseline summaries](../../../configs/regression/pinned_baselines/) and a
[Batch B manifest](inputs/contoso-batch-b-manifest.json). It writes the replay
index, run summaries, and trace files in [data/](data/).

This command verifies the checked-in data in a separate temporary directory.

```sh
python scripts/creator_challenge/build_replay_bundle.py --check
```

The replay illustrates recorded behavior on controlled fixtures. Live analysis
and tool generation run separately in the [Windows prototype](../../../SETUP.md).

A static host can serve this directory directly for visitors who open the demo
from a résumé link.
