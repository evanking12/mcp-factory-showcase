# Principle Audit Schema

Use this schema for every audited principle in `docs/architecture/principle_audits/family_audits/`.

## Required Fields

- `principle_id`
- `principle_name`
- `score_1_to_10`
- `why`
- `evidence_found`
- `evidence_missing`
- `repo_surfaces_reviewed`
- `main_failure_mode`
- `recommended_tightening`
- `escalate_to_gm`
- `escalation_reason`

## Scoring Rule

- `9-10`
  - strong and consistently embodied
- `7-8`
  - acceptable but with clear tightening room
- `4-6`
  - materially weak; escalate to GM
- `1-3`
  - seriously broken or mostly aspirational; escalate to GM

## Escalation Rule

- if `score_1_to_10 < 7`, set:
  - `escalate_to_gm: yes`
- if `score_1_to_10 >= 7`, set:
  - `escalate_to_gm: no`

If `escalate_to_gm: no`, `escalation_reason` should be `none`.

## Family Audit Header

Each family audit should begin with:

- `audit_family`
- `strongest_principle`
- `weakest_principle`
- `recurring_failure_pattern`
- `count_of_escalations`

## Recommended Markdown Shape

```md
# Principle Family Audit: `<family>`

- strongest_principle: `...`
- weakest_principle: `...`
- recurring_failure_pattern: `...`
- count_of_escalations: `...`

## `<principle_id>`: `<principle_name>`

- score_1_to_10: `...`
- why: `...`
- evidence_found:
  - `...`
- evidence_missing:
  - `...`
- repo_surfaces_reviewed:
  - `...`
- main_failure_mode: `...`
- recommended_tightening: `...`
- escalate_to_gm: `yes | no`
- escalation_reason: `... | none`
```
