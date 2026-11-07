# API Infrastructure

`api/infra/` owns shared runtime infrastructure for the local API lane. It does
not own pipeline stage semantics.

## What This Folder Owns

| File | Role |
| --- | --- |
| `config.py` | Runtime configuration and environment-derived settings. |
| `local_lane_admission.py` | Local lane admission and guard behavior. |
| `service_identity.py` | Managed service identity and ownership signals. |
| `storage.py` | Low-level artifact and blob storage mechanics. |
| `storage_api.py` | Public storage wrapper surface for callers outside infra. |
| `telemetry.py` | Shared telemetry helpers. |
| `worker.py` | Background worker orchestration for discovery, explore, and job progression. |

## How It Feeds The Pipeline

Infra keeps jobs, storage, worker execution, and managed-lane identity coherent.
Stages consume infra through public wrappers or runner context; they should not
silently own infra behavior.

## What This Folder Does Not Own

- numbered stage implementation
- stage artifact contracts
- stage split doctrine
- migration target architecture

Use `api/pipeline/README.md` and stage `TRACE.md` files for live stage truth.
