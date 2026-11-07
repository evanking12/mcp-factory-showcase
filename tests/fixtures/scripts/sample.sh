#!/usr/bin/env bash
# sample.sh — Demo shell script for MCP Factory script_analyzer tests.
#
# Contains POSIX-compatible functions using the `function_name() { … }`
# declaration style as well as the `function function_name { … }` style.

set -euo pipefail

# ---------------------------------------------------------------------------
# compress_file  –  Compress a file with gzip.
#
# Arguments:
#   $1  source_path   Path to the input file.
#   $2  dest_path     Path for the compressed output (.gz).
#   $3  level         Compression level 1–9 (default: 6).
#
# Returns: 0 on success, 1 on error.
# ---------------------------------------------------------------------------
compress_file() {
    local source_path="$1"
    local dest_path="$2"
    local level="${3:-6}"

    if [[ ! -f "$source_path" ]]; then
        echo "ERROR: source file not found: $source_path" >&2
        return 1
    fi

    gzip -c -"$level" "$source_path" > "$dest_path"
    echo "Compressed: $source_path → $dest_path"
}

# ---------------------------------------------------------------------------
# list_exports  –  Print exported symbol names from a PE DLL.
#
# Arguments:
#   $1  dll_path       Path to the DLL file.
#   $2  filter_prefix  Optional prefix filter (empty = all symbols).
# ---------------------------------------------------------------------------
list_exports() {
    local dll_path="$1"
    local filter_prefix="${2:-}"

    dumpbin /exports "$dll_path" 2>&1 \
        | grep -P '^\s+\d+\s+\w+\s+\w+\s+\S+' \
        | awk '{print $4}' \
        | { [[ -n "$filter_prefix" ]] && grep "^$filter_prefix" || cat; }
}

# ---------------------------------------------------------------------------
# score_confidence  –  Echo a confidence label for an export.
#
# Arguments:
#   $1  name       Symbol name.
#   $2  has_doc    1 if a doc/header was found, 0 otherwise.
#   $3  is_signed  1 if the binary is signed, 0 otherwise.
#
# Outputs: one of: guaranteed high medium low
# ---------------------------------------------------------------------------
score_confidence() {
    local name="$1"
    local has_doc="$2"
    local is_signed="$3"

    if [[ "$has_doc" == "1" && "$is_signed" == "1" ]]; then
        echo "guaranteed"
    elif [[ "$has_doc" == "1" || "$is_signed" == "1" ]]; then
        echo "high"
    elif [[ "$name" != _* ]]; then
        echo "medium"
    else
        echo "low"
    fi
}

# ---------------------------------------------------------------------------
# write_mcp_json  –  Emit a minimal MCP JSON stub to stdout.
#
# Arguments:
#   $1  source_file  The analysed file path.
#   $2  count        Number of invocables discovered.
# ---------------------------------------------------------------------------
function write_mcp_json {
    local source_file="$1"
    local count="$2"

    printf '{\n  "source_file": "%s",\n  "invocable_count": %d,\n  "invocables": []\n}\n' \
           "$source_file" "$count"
}

# ---------------------------------------------------------------------------
# Main  – demo usage when script is executed directly
# ---------------------------------------------------------------------------
main() {
    if [[ $# -lt 1 ]]; then
        echo "Usage: $0 <dll-path> [prefix]" >&2
        exit 1
    fi
    list_exports "$1" "${2:-}"
}

main "$@"
