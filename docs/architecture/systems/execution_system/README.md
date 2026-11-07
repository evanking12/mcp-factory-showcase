# Execution System

## Purpose

The execution system owns the real runtime boundary between a requested target
and the rest of the product.

Its job is to make execution possible and trustworthy enough that reasoning can
begin.

If the execution system is unstable, deeper reasoning conclusions are suspect.

## Owned Surfaces

Primary owned code areas:

- `api/routes/`
- `api/services/`
- `api/infra/`
- `scripts/bridge/`
- startup and lane wiring surfaces:
  - `runtime/`
  - `start.ps1`
  - `setup.ps1`
  - `sessions/restart_local_services.ps1` (legacy wrapper)
  - `sessions/restart_dashboard_lab.ps1` (specialist recovery utility)

Common examples:

- upload and analyze entrypoints
- analyze-path entrypoint
- bridge communication
- worker launch
- subprocess discovery execution
- DLL executor invocation
- storage registration around live jobs

## Primary Inputs

- uploaded binaries and analyze requests
- local file paths for analyze-path workflows
- bridge availability and bridge configuration
- worker/runtime configuration
- lane configuration such as API and bridge port pairing

## Primary Outputs

- job records
- session roots
- discovery artifacts
- executor results
- status snapshots
- API responses that downstream systems consume

## Public Contracts

Critical contracts include:

- route request and response shapes
- worker job lifecycle semantics
- bridge transport expectations
- storage registration and artifact location rules
- health and lab-status surfaces

The execution system must not silently mutate those contracts in a way that
breaks evidence collection, dashboard interpretation, or compare-run logic.

## Invariants

- one live run at a time per bridge + API pair
- health and lab-status should reflect the actual live lane being trusted
- upload and analyze-path semantics must remain explicit and distinguishable
- route and worker surfaces must register artifacts early enough for evidence
  consumers to audit failure paths
- bridge failures must not be misreported as semantic reasoning failures

## Common Failure Modes

- route receives valid input but worker context is unstable
- subprocess discovery exits early or is interrupted
- bridge reachable but unusable for the active lane
- healthy route status but unhealthy real execution path
- stale worker or reload process introduces hidden variables
- upload-lane and analyze-path behavior diverge silently

## Observability Gaps

Current recurring gaps include:

- route-level health can look green while the exact live execution lane is not
  trustworthy
- operator surfaces do not always expose lane identity clearly enough
- API/bridge pair selection is still too easy to blur in local setups

## Typical Tests And Checks

When this system changes, likely checks include:

- `python scripts/verify_sync.py --tier A`
- `python scripts/harness.py test -- tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py`
- route-focused tests
- executor or worker tests
- lab health re-checks after recycling the lane

If routes, services, bridge, or lab-status surfaces change:

- recycle the local lane via `start.ps1` or the runtime wrappers
- re-check `/health`, bridge `/health`, and `/api/lab/status`

## Agent Guidance

Use this doc before editing when the task involves:

- upload failures
- analyze-path vs upload disagreements
- bridge connectivity
- worker lifecycle
- lane instability
- local startup or restart behavior

Do not treat an execution-system failure as a reasoning bug until the lane is
stable enough to trust.

## Do Not Own

The execution system does not own:

- semantic blocker classification
- diagnosis ranking
- compare-run policy
- operator-facing coverage narratives

Those belong to reasoning, evidence, and operator systems.
