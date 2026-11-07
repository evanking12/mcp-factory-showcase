# `S-00 -> S-01` Handoff Regression Checklist

This is the bounded regression surface for the first live `S-00 -> S-01`
handoff seam.

## Fast Regression Gate

Run this on every meaningful seam change:

```powershell
python -m pytest tests/test_s00_s01_handoff_packet.py tests/test_vocab_seed_artifacts.py tests/test_handoff_contract_audit.py tests/test_stage_split_migration_compare.py tests/test_contract_artifacts.py tests/test_routes_session_snapshot_handoff_packet.py -q
```

This gate pressures:

- packet production
- admitted-slice consumption
- missing and malformed packet fallback
- partial-merge behavior
- legacy `S-00` artifact continuity
- migration-additive posture
- session packaging compatibility

## Manual Real-Run Checklist

After the fast regression gate is green, run one or two real jobs and inspect:

- blob exists at `{job_id}/s01_handoff_packet.json`
- packet contains:
  - `baseline_truth`
  - `surface_inventory`
  - `prior_hints`
  - `s01_targets`
  - `coordination_decision`
- session snapshot includes:
  - `stage-00-setup/s01-handoff-packet.json`
  - `evidence/stage-00-setup/s01-handoff-packet.json`
- `S-01` still produces `write_unlock_probe.json`
- legacy artifacts still exist:
  - `vocab.json`
  - `static_analysis.json`
  - `sentinel_calibration.json`
- no obvious `S-01` archaeology remains for:
  - `dll_strings`
  - `vocab`
  - `sentinels`

## Current Claim Ceiling

- The packet is additive, not yet canonical
- `handoff_contract.py` does not require it yet
- `s01_targets` is advisory until a later consumer-narrowing tranche
- contract-first seam regression is sufficient here; broad fixture-led or full
  runtime proving is not yet required
