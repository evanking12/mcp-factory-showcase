"""api.pipeline.core -- Shared pipeline infrastructure.

Contains the cross-stage building blocks:
  helpers     -- constants, regex patterns, utility functions
  prompts     -- LLM system message construction
  vocab       -- vocabulary management and hypothesis generation
  types       -- ExploreContext, ExploreRuntime dataclasses
  checkpoint  -- pipeline checkpoint load/save/gate logic
  cluster_checkpoint -- lower-than-stage checkpoint schema for semantically coherent rerun units
"""
