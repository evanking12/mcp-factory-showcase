# API Services

`api/services/` owns shared service-level capabilities used by routes, workers,
and pipeline entrypoints. It does not own numbered pipeline stage contracts.

## What This Folder Owns

| File | Role |
| --- | --- |
| `discovery.py` | DLL discovery and callable skeleton production before explore enters S-00. |
| `executor.py` | Execution service internals. |
| `executor_api.py` | Public executor wrapper surface for callers outside services. |
| `generate.py` | MCP/server generation service behavior. |
| `chat.py` | Chat/service interaction helpers. |
| `search.py` | Search helper surfaces. |

## How It Feeds The Pipeline

Services prepare or support the work that stages consume. For the current DLL
path, `discovery.py` is the important upstream producer before S-00 because it
creates the callable skeleton and discovery metadata.

## What This Folder Does Not Own

- S-00 setup/static contracts
- S-01 unlock behavior
- stage handoff packet semantics
- final stage outputs

Use stage `TRACE.md` files to see which services feed a specific stage.
