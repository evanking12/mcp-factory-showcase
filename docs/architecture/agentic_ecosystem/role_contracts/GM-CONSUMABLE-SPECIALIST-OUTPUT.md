# GM-Consumable Specialist Output Contract

## Purpose

Specialist roles exist to reduce GM search cost and sharpen branch decisions.
Their first output must therefore be a compact, structured packet the GM can
consume without reading a full audit memo.

This contract applies to every specialist role unless a role contract defines a
strictly narrower compatible schema.

## Required Top Block

Every specialist response must begin with this YAML block:

```yaml
gm_consumable:
  role: ""
  task: ""
  verdict: pass | fail | partial | unsupported | not_applicable
  claim_ceiling: ""
  can_steer_next: yes | no | conditional
  blocker: ""
  next_action: ""
  blocking_needed_now: yes | no
  confidence: high | medium | low
  key_risks:
    - ""
  evidence_refs:
    - ""
```

## Field Meanings

- `role`: specialist role name.
- `task`: the bounded question the GM asked.
- `verdict`: the role's answer at its own claim ceiling.
- `claim_ceiling`: strongest legal claim the output supports.
- `can_steer_next`: whether the GM may use this output to steer branch choice.
- `blocker`: smallest blocker or `none`.
- `next_action`: one recommended next action, not a plan tree.
- `blocking_needed_now`: whether the parent thread should stop and wait.
- `confidence`: evidence confidence for the verdict.
- `key_risks`: only branch-relevant risks.
- `evidence_refs`: files, artifact paths, commands, or checked facts.

## Detail Section

After the YAML block, the role may include a short role-specific detail section.

Rules:

- findings must be ordered by branch impact
- avoid repeating the YAML fields in prose
- cite evidence precisely when making a claim
- keep details bounded to the assigned role
- do not choose the final branch
- do not edit canonical campaign artifacts

## Integration Rule

The GM should be able to update campaign closeout, dispatch accountability, or
next-branch packets from the YAML block alone. If not, the role output is too
verbose, too vague, or not structured enough.

