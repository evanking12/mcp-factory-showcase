# Bridge Runtime

Canonical start path:

```powershell
.\runtime\bridge\start.ps1 -ForceRestart
```

Config surface:
- Root `.env`
- Canonical local contract: [runtime/local-runtime-contract.json](../local-runtime-contract.json)
- Canonical lane note: [runtime/README.md](../README.md)

Identity and readiness contract:
- Base URL: `http://127.0.0.1:8090`
- Alive: `/alive`
- Health: `/health`
- Identity: `/identity`
- Readiness: `/readiness`
- Strict local admission: `/local-lane-admission`
- Expected identity: `component=bridge`, `role=execution_bridge`, `contract_version=trust_contract_v1`
- Required capabilities: `execute`, `flush_dll_cache`

Expected env:
- `GUI_BRIDGE_URL`
- `GUI_BRIDGE_SECRET`

Failure boundary:
- If identity is wrong, the process on `8090` is not the managed local execution bridge.
- If `/health` is red, the managed local bridge lane is not safe to use yet.
- If readiness is red, DLL and GUI execution trust is red for local runs.

Smallest honest trust claim:
- The local bridge lane is an explicit managed runtime for bounded execution and cache-reset validation.

Ownership map:
- [docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md](../../docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md)
