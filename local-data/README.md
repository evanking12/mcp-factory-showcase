`local-data/` is machine-oriented runtime storage for the local workflow.

Use it for:
- local artifact container mirrors
- upload/cache state used by the API and worker
- transient runtime data that should survive process restarts

Do not treat it as the first human review surface.

Human review order:
1. `sessions/README.md`
2. `sessions/codex-runs/<run-family>/<run-id>/artifacts/WHERE-TO-LOOK.md`
3. `sessions/codex-runs/<run-family>/<run-id>/summary.json`

If a result matters long term:
- promote the conclusion into `docs/architecture/`
- keep the raw machine output in `sessions/`
