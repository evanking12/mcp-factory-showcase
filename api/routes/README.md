# API Routes

`api/routes/` owns HTTP request surfaces and operator-facing route wiring. It
does not own pipeline stage behavior.

## What This Folder Owns

| File | Role |
| --- | --- |
| `main.py` | Main FastAPI route registration and job-facing endpoints such as analyze, generate, and explore entry surfaces. |
| `routes_session.py` | Session and artifact-facing route surfaces. |
| `body_parsers.py` | Request-body parsing helpers for route handlers. |
| `health_probes.py` | Route-level health and readiness probe helpers. |

## How It Feeds The Pipeline

Routes accept operator/API requests, create or read job state, and call worker,
service, or pipeline entrypoints. Once execution enters numbered pipeline
stages, live stage truth belongs under `api/pipeline/sNN_*/`.

## What This Folder Does Not Own

- stage contracts
- stage artifact ownership
- discovery semantics
- runtime probing semantics
- final API behavior claims

Use stage `TRACE.md` files to see how route surfaces feed a specific stage.
