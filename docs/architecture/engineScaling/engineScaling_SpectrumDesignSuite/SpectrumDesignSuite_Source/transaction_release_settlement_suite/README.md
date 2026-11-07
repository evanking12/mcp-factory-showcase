# Transaction Release Settlement Suite

This family is the first authored source realization of the Spectrum Design
Suite.

It models a legacy transaction release and settlement bundle with:

- session bootstrap
- reservation staging
- fanout consumers
- release commit
- attestation reuse
- late settlement reconciliation
- audit invalidation of untrusted replay branches
- stale-attestation invalidation after apparently valid local reuse

Layout:

- `src/`
  - authored Python modules for the mock enterprise system
- `cases/`
  - case-specific manifests
- `expected_observed/`
  - authored expected-versus-observed payloads
- `observer_payloads/`
  - authored observer outputs and expected decision surfaces
- `truth_manifest.json`
  - suite-wide contract-bearing manifest
