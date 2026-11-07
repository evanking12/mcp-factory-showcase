"""
sample.py - Demo Python script for MCP Factory script_analyzer tests.

This file contains a variety of Python functions with docstrings, type
annotations, and default arguments so the AST-based analyzer can
exercise all extraction paths.
"""

from pathlib import Path
from typing import Optional, List


def compress_file(source: Path, dest: Path, level: int = 3) -> int:
    """Compress *source* into *dest* using the specified compression level.

    Args:
        source: Path to the input file.
        dest:   Path where compressed output is written.
        level:  Compression level 1–9 (default 3).

    Returns:
        Number of bytes written to *dest*.
    """
    data = source.read_bytes()
    # Placeholder – real implementation would call a codec
    dest.write_bytes(data)
    return len(data)


def list_exports(dll_path: Path, filter_prefix: Optional[str] = None) -> List[str]:
    """Return exported symbol names from a PE DLL.

    Args:
        dll_path:      Path to the DLL to inspect.
        filter_prefix: If given, only symbols starting with this prefix are returned.

    Returns:
        List of exported symbol name strings.
    """
    # Stub – real implementation calls dumpbin
    return []


def score_confidence(name: str, has_doc: bool, is_signed: bool) -> str:
    """Assign an invocability confidence label to an export.

    Args:
        name:      Symbol name.
        has_doc:   Whether a header/docstring was found.
        is_signed: Whether the binary is digitally signed.

    Returns:
        One of ``'guaranteed'``, ``'high'``, ``'medium'``, or ``'low'``.
    """
    if has_doc and is_signed:
        return "guaranteed"
    if has_doc or is_signed:
        return "high"
    if name.startswith("_") is False:
        return "medium"
    return "low"


def _internal_helper(value: int) -> int:
    """Internal helper – should still appear as a discovered invocable."""
    return value * 2


class BinaryAnalyzer:
    """Wraps low-level analysis routines for a single binary target."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def run(self) -> dict:
        """Run the full analysis pipeline and return a result dict."""
        return {"path": str(self.path), "invocables": []}

    def to_json(self, indent: int = 2) -> str:
        """Serialise the result to a JSON string.

        Args:
            indent: JSON indentation width.

        Returns:
            Formatted JSON string.
        """
        import json
        return json.dumps(self.run(), indent=indent)
