# Agent Evaluation Artifact Schema

## Purpose

This is the reusable schema for evaluating a specialist role in the MCP Factory
agentic ecosystem.

Use this schema whenever a role is:

- first introduced
- materially refined
- considered for splitting
- considered for merging
- considered for retirement

## Required Fields

- `evaluation_id`
- `evaluated_at`
- `role_name`
- `role_family`
- `prompt_version`
- `task_id`
- `task_type`
- `task_input`
- `repo_surfaces_used`
- `output_produced`
- `what_it_got_right`
- `what_it_missed`
- `what_it_overclaimed`
- `signal_to_noise_assessment`
- `citation_quality_assessment`
- `boundedness_assessment`
- `usefulness_for_next_branch_choice`
- `refinement_needed`
- `decision`

## Field Intent

### Identity

- `evaluation_id`
  - stable identifier for the evaluation record
- `evaluated_at`
  - timestamp for the evaluation
- `role_name`
  - exact role being evaluated
- `role_family`
  - broader family such as `review`, `gate`, `handoff`, `evidence`, `ui`

### Prompt and Task

- `prompt_version`
  - the exact role prompt or contract version used
- `task_id`
  - stable task or diff identifier
- `task_type`
  - what kind of task was used, such as `real_diff`, `artifact_audit`, or
    `synthetic_edge_case`
- `task_input`
  - concise description of the input the agent received
- `repo_surfaces_used`
  - files, artifacts, or diffs inspected during the evaluation

### Output Assessment

- `output_produced`
  - concise summary of what the role returned
- `what_it_got_right`
  - strongest correct elements
- `what_it_missed`
  - strongest omissions
- `what_it_overclaimed`
  - strongest overreach, noise, or unsupported claims

### Quality Assessment

- `signal_to_noise_assessment`
  - whether the output was concise enough and high-value enough
- `citation_quality_assessment`
  - whether the output cited the right files, lines, or artifacts
- `boundedness_assessment`
  - whether the role stayed inside its intended scope
- `usefulness_for_next_branch_choice`
  - whether the output helped the parent thread make a real decision

### Refinement

- `refinement_needed`
  - exact prompt or role changes needed next
- `decision`
  - one of:
    - `keep`
    - `refine`
    - `split`
    - `merge`
    - `retire`

## Example Decision Rules

- choose `keep` when the role is already useful and well-bounded
- choose `refine` when the role is useful but noisy, broad, or weakly shaped
- choose `split` when one role is doing two distinct jobs badly
- choose `merge` when the distinction from another role is not real
- choose `retire` when the role is no longer recurring or is better handled by
  the parent thread
