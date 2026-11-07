# Architect Operating Guide

## Purpose

This guide captures the repo's preferred architect-to-architect feedback style
and the rules for turning direction into contract-bearing systems.

## Guidance

- weigh strengths, weaknesses, tradeoffs, and failure modes directly
- preserve what is directionally right before tightening what is risky
- start with the smallest verifiable system slice
- encode recurring rules into repo governance instead of prompt memory
- whenever a major new system or layer is introduced, state plainly:
  - why it exists
  - what it does not replace
  - why it should happen now instead of later
- whenever a new system overlaps an older one, resolve the overlap explicitly:
  - keep
  - narrow
  - supersede
  - or retire after a stated gate
- do not let multiple surfaces carry the same operator meaning indefinitely
  just because each one is locally coherent
- when prompt chains are active, close each prompt with an explicit evaluation
  of:
  - what was proved
  - what remains unproven
  - what changed in the architecture
  - whether the planned next prompt is still correct
  - or whether a new bounded prompt should be written immediately
- before presenting a new prompt or prompt chain, run a self-review:
  - what are the weaknesses of this prompt?
  - what oversights could still exist?
  - what seam is still under-specified?
  - what default should be tightened before implementation starts?
