# API Runtime

Canonical start path:

```powershell
.\runtime\api\start.ps1 -ForceRestart
```

Config surface:
- Root `.env`
- Canonical local contract: [runtime/local-runtime-contract.json](../local-runtime-contract.json)
- Canonical lane note: [runtime/README.md](../README.md)

Identity and readiness contract:
- Base URL: `http://127.0.0.1:8201`
- Alive: `/alive`
- Health: `/health`
- Identity: `/identity`
- Readiness: `/readiness`
- Strict local admission: `/local-lane-admission`
- Expected identity: `component=api`, `role=pipeline_control_plane`, `contract_version=trust_contract_v1`

Expected env:
- `OPENAI_API_KEY`
- `MCP_STORAGE_BACKEND`
- `GUI_BRIDGE_URL`
- `GUI_BRIDGE_SECRET`

Failure boundary:
- If identity is wrong, the process on `8201` is not the managed local API lane.
- If `/health` is red, the managed local API lane is not safe to use yet.
- If readiness is red, local proving runs should not start.

Smallest honest trust claim:
- The local API lane is an explicit managed runtime with machine-readable identity/readiness for bounded proving-lane use.

Ownership map:
- [docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md](../../docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md)
