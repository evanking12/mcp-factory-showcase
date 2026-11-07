# Change-Admission Packet Template

Use this packet in implementation closeouts for meaningful runtime, regression, workflow, architecture, or governance changes.

```yaml
system_changed:
  - ""
durable_contracts:
  - ""
allowed_churn:
  - ""
meta_checks:
  - command: ""
    result: ""
regression_posture: ""
change_admission_result: "pass | fail | partially_proven"
unexpected_blast_radius:
  - ""
classification_updates_required: "yes | no"
next_blocker: ""
```

## Field Intent

- `system_changed`: The owned subsystem, not just a file list.
- `durable_contracts`: What should still be true after this change.
- `allowed_churn`: What implementation details or tests may legitimately move.
- `meta_checks`: Cheap boundary checks run before or alongside expensive proving.
- `regression_posture`: Which ladder tier applies and what remains unproven.
- `change_admission_result`: Whether the change is sufficiently classified and checked for its blast radius.
- `unexpected_blast_radius`: Any surface that broke outside the declared owned subsystem.
- `classification_updates_required`: Whether `configs/regression/check_registry.json` or this system map needs to change.
- `next_blocker`: The next specific blocker, not a vague request for more testing.
