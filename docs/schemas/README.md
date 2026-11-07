# MCP Factory Output Schemas

This directory contains JSON schemas for discovery pipeline outputs. These schemas define stable contracts between Section 2-3 (discovery), Section 4 (MCP generation), and Section 5 (verification UI).

## Active Schemas

### discovery-output.schema.json ✅ CURRENT

**Status:** Production-ready, forward-compatible  
**Used by:** All tier outputs (CSV + JSON)  
**Consumers:** Section 4 (MCP generation), Section 5 (verification UI)

**Design Principles:**
- **Backward compatibility:** New fields can be added without breaking existing consumers
- **Extensible metadata:** Each invocable has a `metadata` object for future enhancements
- **Explicit confidence:** 6-factor breakdown explains why each confidence level was assigned
- **Evidence-first:** Every claim cites source (file, line, discovery method)

**Key Guarantees (will never change):**
- `schema_version` field always present
- `metadata.target_path`, `metadata.target_name`, `metadata.tier` always present
- `invocables[]` is an array of objects
- Each invocable has: `name`, `kind`, `confidence`, `evidence.discovered_by`

**Safe to add later (non-breaking):**
- New fields in `metadata` object
- New fields in `invocables[].metadata` object
- New confidence factors in `confidence_factors`
- New module names in `pipeline_results.modules_*`

**File Format:**
```json
{
  "schema_version": "2.0.0",
  "metadata": {
    "target_path": "C:\\path\\to\\library.dll",
    "target_name": "library.dll",
    "target_type": "dll",
    "tier": 2,
    "analysis_timestamp": "2026-01-23T12:00:00"
  },
  "invocables": [
    {
      "name": "FunctionName",
      "kind": "dll_export",
      "confidence": "high",
      "signature": {
        "return_type": "int",
        "parameters": "void* ptr, size_t len",
        "full_prototype": "int FunctionName(void* ptr, size_t len)"
      },
      "evidence": {
        "discovered_by": "exports.py",
        "header_file": "library.h"
      }
    }
  ],
  "statistics": {
    "total_invocables": 187,
    "high_confidence_count": 8,
    "signature_match_rate": 0.984
  }
}
```

## Output Files

The discovery pipeline generates JSON files alongside CSV and Markdown:

| Tier | CSV | JSON | Markdown | Description |
|------|-----|------|----------|-------------|
| 1 | ✅ | ✅ | ✅ | exports + headers + documentation |
| 2 | ✅ | ✅ | ✅ | exports + headers (current best) |
| 3 | ✅ | ✅ | ✅ | exports + demangling |
| 4 | ✅ | ✅ | ✅ | exports only (fallback) |
| 5 | — | — | ✅ | metadata only |

**Example files:**
```
artifacts/
  zstd_tier2_api_zstd_fixture.csv       # Legacy format (columns)
  zstd_tier2_api_zstd_fixture.json      # NEW: Structured data
  zstd_tier2_api_zstd_fixture.md        # Human-readable report
```

## Legacy Schemas (Deprecated)

### v1.0.json
**Status:** Deprecated (replaced by discovery-output v2.0.0)  
**Issues:** No extensibility, missing confidence breakdown  
**Migration:** Consumers should use `discovery-output.schema.json` v2.0.0+

### inventory.schema.json
**Status:** Experimental (not used in production)  
**Purpose:** Research spike for multi-surface inventory

## Schema Versioning

We use semantic versioning for schemas:
- **Major version** (2.x.x): Breaking changes (field removed, type changed, required field added)
- **Minor version** (x.1.x): New optional fields (backward-compatible)
- **Patch version** (x.x.1): Documentation or example updates (no schema changes)

**Current version:** 2.0.0

**Upgrade path:**
- v2.0.0 → v2.1.0: Consumers don't need changes (optional fields added)
- v2.x.x → v3.0.0: Consumers need updates (breaking changes, full migration guide provided)

## Testing Schema Compliance

To validate JSON output against schema:

```bash
# Install jsonschema validator
pip install jsonschema

# Validate output file
python -m jsonschema -i artifacts/zstd_tier2_api.json docs/schemas/discovery-output.schema.json
```

**Expected result:** No output = valid

