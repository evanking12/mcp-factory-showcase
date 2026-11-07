# Test Fixtures

This directory contains both:

- controlled Contoso-family benchmark fixtures
- vcpkg-backed real-world DLL fixtures

## Dependencies

- **zstd** - Compression library (libzstd.dll or zstd.dll)
- **sqlite3** - Database engine (sqlite3.dll)

## Usage

These fixtures are automatically installed when running `scripts/run_fixtures.ps1`.

Manual installation:
```powershell
vcpkg install --triplet x64-windows --manifest-root tests/fixtures
```

## Purpose

### Controlled Contoso fixtures

These fixtures are intentionally authored to benchmark:

- generic-to-specific learning
- cross-DLL interweave
- blocker-family diversity
- realistic legacy-business unlock paths

Current controlled families:

- `contoso_legacy/`
- `contoso_interwoven/`
- `contoso_workflow/`

### Real-world fixtures

Provides real-world DLLs with:

- comprehensive exports
- documented or semi-documented C APIs
- broader ecosystem coverage
- active maintenance

These DLLs serve as additional test cases for the export analysis pipeline.
