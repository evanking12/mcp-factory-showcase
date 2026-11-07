# 5-Chart Architecture Thesis Overview

Use this set when the goal is to explain not just how the code works, but why
the architecture claim is defensible.

This set should inherit the core chart vocabulary and stage naming from:

- `../CHART-CONVENTIONS.md`
- `../01-engineering-overview-4/`

Recommended charts:

1. System overview and dataflow
2. Stage model
3. Status and classification
4. Context and memory model
5. Truth, replay, checkpoints, and compounding

The fifth chart should explain how the system avoids fake progress and how
replay-backed gains become trustworthy architecture evidence.
