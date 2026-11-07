# Security & Safety

## Threat model (demo)
- Untrusted binaries may execute arbitrary behavior.
- Invocation could touch filesystem/network/registry.
- Output may contain sensitive data.

## Guardrails (planned)
- Run analysis/invocation in a sandboxed environment (container/VM)
- Timeouts for invocations
- Allowlist of binaries or safe directories for demo
- Capture stdout/stderr; redact obvious secrets if needed

## Demo posture
- Prefer known safe sample binaries (open-source / permissive licensing)
- Avoid running unknown third-party executables during demo
