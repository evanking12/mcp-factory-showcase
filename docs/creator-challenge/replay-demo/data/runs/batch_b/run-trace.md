# Batch B Replay Trace

- Claim ceiling: package-scale diagnostic replay
- Source: fixture package manifest
- Telemetry claim: telemetry is diagnostic evidence only

## Spans

- `Floor 0` Package admission: pass (0 sec)
- `Floor 1` Runtime target selection: pass (0 sec)
- `Floor 2` Package-scale blocker harvest: diagnostic (0 sec)

## Metrics

- `bundled_dll_count` = `10` (pass) - Shows package-scale intake breadth before expensive deep analysis.
- `runtime_target_count` = `8` (pass) - Shows selective activation: not every DLL is deeply probed immediately.
- `dependency_confidence_counts` = `{'high': 9, 'medium': 1}` (pass) - Shows that package intake preserves confidence, dependency, and role labels.
- `candidate_comparability_state` = `diagnostic_package_replay` (warn) - Distinguishes diagnostic output from evidence that can support comparison.
- `next_action_confidence` = `medium` (pass) - Tells the operator whether to fix, rerun, inspect, or stop.
