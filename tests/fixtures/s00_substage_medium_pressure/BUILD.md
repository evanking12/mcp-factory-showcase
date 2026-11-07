# S-00 Substage Medium Pressure Fixture

This fixture builds `s00_substage_medium_pressure.dll`.

Purpose:

- Tier 2 compiled pressure for `S-00A setup_baseline`
- Tier 2 compiled pressure for `S-00B static_evidence`
- Tier 2 compiled pressure for `S-00C admission_handoff`

Pressure shape:

- many average-difficulty exported functions
- noisier init/write/read/distractor names than Tier 1
- richer static IDs, emails, status tokens, and format strings
- deterministic behavior
- no live GhidraMCP, bridge lane, or model dependency

This fixture does not prove runtime unlock correctness, cross-DLL maturity, or
post-S-00 coordinator judgment.

