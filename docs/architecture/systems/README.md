# Systems Architecture Map

## Purpose

This folder is the contract-first ownership map for the major MCP Factory
systems.

Use it to answer:

- which system owns a module or behavior
- what contracts the system exposes
- what the system depends on
- what must be tested when it changes
- what an AI agent should read before editing that part of the repo

## Rule Of Use

This folder is for documentation and ownership, not code placement.

Do not use `docs/architecture/systems/` as:

- a duplicate implementation tree
- a scratch area for ad hoc ideas
- a substitute for prompt-chain notes

## Canonical Systems

- [execution_system](execution_system/README.md)
- [reasoning_system](reasoning_system/README.md)
- [evidence_system](evidence_system/README.md)
- [operator_system](operator_system/README.md)
- [governance_system](governance_system/README.md)
- [verification_system](verification_system/README.md)

## Shared Expectations

Each system document should define:

- purpose
- owned modules and surfaces
- primary inputs
- primary outputs
- public contracts
- invariants
- common failure modes
- observability gaps
- required or typical tests
- agent guidance

## For AI Agents

If a task touches a major repo surface and ownership is unclear:

1. read this folder first
2. identify the owning system
3. read that system document before editing
4. update the system doc if the system boundary or contract materially changed
