# Fixtures (zstd + sqlite3)

We use these libraries as deterministic test fixtures for the DLL discovery pipeline.

Install via vcpkg (x64-windows), then run the discovery scripts against:
- zstd (zstd.dll or libzstd.dll)
- sqlite3 (sqlite3.dll)

We do NOT commit binaries to the repo. Fixtures are installed locally via vcpkg.
