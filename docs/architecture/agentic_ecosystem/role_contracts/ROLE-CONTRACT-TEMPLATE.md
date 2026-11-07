# Role Contract Template

## Purpose

Use this template to define any specialist role in the MCP Factory agentic
ecosystem before trusting that role in recurring workflow use.

## Template

- `name`
  - exact role name
- `family`
  - broader role family such as `review`, `gate`, `handoff`, `evidence`, or
    `observability`
- `purpose`
  - what this role exists to accomplish
- `trigger`
  - the recurring condition that should cause this role to be used
- `do_use_when`
  - explicit positive conditions
- `do_not_use_when`
  - explicit negative conditions
- `required_inputs`
  - exact repo surfaces, artifacts, or context required
- `required_output_shape`
  - exact expected output contract
- `disallowed_behaviors`
  - what this role must not do
- `evaluation_criteria`
  - how the main thread will judge quality
- `close_conditions`
  - when the role has completed its job for the current task

## Evaluation Expectations

Every role defined with this template should later be judged against:

- evidence quality
- boundedness
- signal-to-noise
- citation quality
- usefulness for next-branch choice

## Notes

- use one role contract per specialist role
- refine the contract when evaluations show noise, drift, or missing value
- split or merge roles only after repeated evidence justifies it
