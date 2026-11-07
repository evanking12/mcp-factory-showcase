# MCP Factory architecture

MCP Factory converts callable surfaces recovered from Windows binaries into
MCP tools. It uses static discovery to identify candidate entry points and a
Windows bridge to collect evidence about how to call them.

- [Discovery](../../src/discovery/main.py) classifies inputs and builds a catalog
  of candidates from PE exports, Ghidra, and other input-specific analyzers.
- [Runtime probing](../../api/pipeline/README.md) uses observed arguments,
  results, and call prerequisites to refine that catalog.
- [Server generation](../../src/generation/section4_generate_server.py) uses
  selected interfaces and their schemas to produce MCP server code.
- [Local runtime](../../runtime/README.md) documents how the API and bridge
  start and communicate.
- [Validation design](testing_strategy/README.md) covers fixture families,
  checkpoint evidence, and regression policy. The
  [browser replay](../creator-challenge/replay-demo/README.md) presents five
  recorded examples.
