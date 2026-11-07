"""
exports.py - Export normalization, demangling, and forwarder resolution.

Enhances raw export list with demangling, forwarding resolution, and deduplication.
"""

import subprocess
from pathlib import Path
from typing import List

# Suppress GUI windows when calling undname or other tools (Windows only).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

from schema import ExportedFunc


def demangle_with_undname(
    exports: List[ExportedFunc],
    undname_path: str
) -> bool:
    """Demangle C++ export names using undname.exe.
    
    Args:
        exports: List of exports to demangle (modified in-place)
        undname_path: Path to undname.exe
        
    Returns:
        True if demangling succeeded for at least some exports
    """
    demangled_count = 0

    for exp in exports:
        if not exp.name.startswith('?'):
            continue

        try:
            result = subprocess.run(
                [undname_path, exp.name],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=5,
                creationflags=_NO_WINDOW,
            )

            if result.returncode == 0:
                # undname outputs format: "name is: demangled_name"
                output = result.stdout.strip()
                if ' is: ' in output:
                    demangled = output.split(' is: ', 1)[1]
                    exp.demangled = demangled
                    demangled_count += 1

        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return demangled_count > 0


def resolve_forwarders(exports: List[ExportedFunc]) -> dict:
    """Resolve forwarded exports to their real targets.
    
    Maps forwarded exports (e.g., 'kernel32.DeleteFileA') to resolved targets.
    
    Args:
        exports: List of exports (modified in-place for is_forwarded flag)
        
    Returns:
        Dict mapping forwarded_name -> resolved_target
    """
    forwarding_chain = {}
    
    for exp in exports:
        if not exp.forwarded_to:
            continue
        
        # Mark as forwarded
        exp.is_forwarded = True
        
        # Parse format: dll.function or dll.ordinal
        parts = exp.forwarded_to.split('.')
        if len(parts) == 2:
            dll, target = parts
            resolved = f"{dll}.{target}"
            forwarding_chain[exp.name] = resolved
    
    return forwarding_chain


def deduplicate_exports(exports: List[ExportedFunc]) -> List[ExportedFunc]:
    """Remove duplicate exports, keeping last occurrence.
    
    Args:
        exports: List of exports
        
    Returns:
        Deduplicated list
    """
    seen = {}
    for exp in exports:
        seen[exp.name] = exp

    # Return in ordinal order
    return sorted(seen.values(), key=lambda e: e.ordinal or 0)


def classify_export_safety(exp: ExportedFunc) -> str:
    """Heuristically classify export safety (stub for future).
    
    Returns:
        Safety level: "safe", "risky", "unknown"
    """
    # Future: analyze name patterns, check for filesystem/network/process operations
    return "unknown"
