# Local Runtime Lane

Canonical managed local runtime:

- API: `http://127.0.0.1:8201`
- Bridge: `http://127.0.0.1:8090`
- Canonical startup: `powershell -ExecutionPolicy Bypass -File .\start.ps1 -LaneOnly -ForceRestartApi -ForceRestartBridge`

Managed local runtime meaning:

- `127.0.0.1:8001` is not the canonical managed local API lane.
- If an unmanaged process is still listening on `8001`, ignore it for normal managed local work.
- Do not infer lane ownership from ad hoc ports or stale local processes.

Endpoint contract:

- `/alive`
  - shallow process-up check only
- `/health`
  - authoritative managed-lane usability check
- `/identity`
  - ownership and contract truth
- `/readiness`
  - dependency-by-dependency readiness and blocking detail
- `/local-lane-admission`
  - strict local proving-lane admission contract

Operator rule:

- A green `/health` means the managed local lane is actually safe to use.
- A green `/alive` only means the process is responding.

Canonical product-suite entrypoint:

- `powershell -ExecutionPolicy Bypass -File .\runtime\run-local-product-suite.ps1 -Suite easy01`
- `powershell -ExecutionPolicy Bypass -File .\runtime\run-local-product-suite.ps1 -Suite medium01`

Entry-point policy:

- lane missing or stopped:
  - materialize the canonical managed lane first via `runtime/start-managed-lane.ps1`
- managed lane stale or red:
  - restart the managed lane through the same startup wrapper
- unknown owner on canonical port:
  - fail closed rather than killing an unmanaged process

This wrapper is the normal human/operator path for local product-route runs.
The underlying Python suite runners remain lower-level proving surfaces for
debugging and tests; they are not the primary operator startup interface.

Product-proving stability policy:

- the product-suite entrypoint starts the managed lane in stable no-reload mode
  for proving runs
- this is scoped to the product-suite entrypoint path and does not change the
  general developer startup default
- the purpose is to reduce proving noise from API reload behavior, not to
  weaken lane safety or route requirements

Owned runtime homes:

- [runtime/api/README.md](api/README.md)
- [runtime/bridge/README.md](bridge/README.md)
- [docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md](../docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md)
