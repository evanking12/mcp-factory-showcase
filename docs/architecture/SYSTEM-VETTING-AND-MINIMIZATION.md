# System Vetting And Minimization

## Purpose

This document records the rule that new systems should be added only when they
are decision-distinct, reusable, and cheaper than keeping the same logic in
prompt memory.

## Vetting Questions

- does the system have a distinct trigger?
- does it emit a distinct output or decision?
- does it have a clear non-purpose boundary?
- can it be verified locally before expensive runtime use?
- does it reduce operator burden rather than shifting it around?
