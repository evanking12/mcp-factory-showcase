# Ghidra-First Discovery Cleanup

The active discovery product is the compiled-binary path:

- native PE metadata and exports/imports
- Ghidra-backed static evidence
- `.NET` specialization when the binary is actually `.NET`

`strict_dll` is the required compiled-first contract. It must not pull in
quarantined exploratory analyzers as hidden side paths.

## Active vs Quarantined

Active analyzers:

- PE DLL / PE EXE structural analysis
- `.NET` assembly analysis
- Ghidra-backed bridge/static recovery

Quarantined analyzers:

- COM registry / type-library enumeration
- GUI analysis
- CLI help-scraping
- Windows registry scan
- script and service-descriptor analyzers

Quarantined analyzers stay on disk, but they are not part of the required
merge-path trust story. They belong only to explicit exploratory profiles.

## Profile Contract

- `strict_dll`
  - compiled-first only
  - PE metadata and export parsing may be used as structural/preflight evidence
  - hard-family comparable discovery requires Ghidra-backed route authority when
    `ghidra_required` is set
  - PE-only discovery output is non-comparable for hard-family targets that
    require Ghidra-backed evidence
  - no COM registry scan
  - no GUI / CLI / registry side analyzers
  - no non-binary script/spec analyzers

- `greybox_dll`
  - compiled-first with bounded experimental CLI support
  - still excludes COM / GUI / registry and non-binary analyzers

- `full_surface`
  - exploratory profile
  - owns the quarantined analyzers

## Why

The regression ladder depends on `strict_dll` being an honest floor. If the
required trust path inherits COM, GUI, registry, or other exploratory analyzers,
Tier 1 stops measuring lane trust and starts failing on unrelated discovery
sprawl. This cleanup keeps required CI aligned to the product being built.

## Hard-Family Route Authority

`reservation_stage_ghidra_first_discovery_routing_v1` adds the explicit runtime
contract that was previously implicit:

- hard01 and hard02 mark `strict_dll` target analysis with `ghidra_required`;
- API job status preserves that route requirement;
- discovery-output authority records whether Ghidra was required, whether the
  bridge/Ghidra route was attempted, whether Ghidra-backed output was present,
  and whether legacy PE parsing was entered;
- PE-only output remains useful diagnostic evidence, but it cannot satisfy
  hard-family comparable discovery when Ghidra-backed evidence is required.

If Ghidra is required but not entered, the correct outcome is a durable
non-comparable packet such as `ghidra_required_not_entered`,
`legacy_pe_discovery_blocked_for_hard_family`, `ghidra_bridge_unavailable`, or
`ghidra_output_missing`, not silent fallback to PE-only discovery.

The bounded proof for this route reached progress `60` and bridge authority
under `ghidra_required=true`, then stopped at `bridge_stream_no_heartbeat`.
That keeps PE structural evidence diagnostic-only and moves the active blocker
to bridge/Ghidra runtime authority.
