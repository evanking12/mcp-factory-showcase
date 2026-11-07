# Compliance (FERPA + Data Handling)

## Data rules
- Do not store real student/customer PII in repo, logs, or artifacts.
- Use synthetic/test data only for demos and verification.

## Artifact policy
- Artifacts committed to the repo must be non-sensitive:
  - dumpbin outputs, parsed CSV/JSON, synthetic logs
- Avoid committing proprietary binaries unless licensing allows.
- If needed, store large/proprietary binaries outside git and document retrieval steps.

## Access control
- Repo access restricted to project team.
- Azure resources restricted to project team accounts only.
