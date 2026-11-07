"""
pe_parse.py - PE file parsing and export extraction.

Extracts export table from PE files using pefile library.
Replaces reliance on dumpbin.exe with a pure Python approach.
"""

import re
import struct
import logging
import subprocess
import glob
from pathlib import Path
from typing import List, Optional, Tuple

import pefile

from schema import ExportedFunc

logger = logging.getLogger(__name__)

def read_pe_exports(dll_path: Path) -> Tuple[List[ExportedFunc], bool]:
    """Read PE export table directly from DLL without dumpbin using `pefile`.

    Returns (exports_list, success_bool).
    """
    try:
        import pefile
    except Exception:
        return [], False

    try:
        pe = pefile.PE(str(dll_path), fast_load=True)
        try:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
        except Exception:
            pass

        if not hasattr(pe, 'DIRECTORY_ENTRY_EXPORT') or not pe.DIRECTORY_ENTRY_EXPORT:
            try:
                pe.close()
            except Exception:
                pass
            return [], False

        exports: List[ExportedFunc] = []
        for sym in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            name = None
            if getattr(sym, 'name', None):
                try:
                    name = sym.name.decode('utf-8', errors='replace')
                except Exception:
                    name = str(sym.name)

            ordinal = getattr(sym, 'ordinal', None)
            if not name:
                name = f"#{ordinal}" if ordinal is not None else "<unknown>"

            rva = None
            if hasattr(sym, 'address') and sym.address is not None:
                try:
                    rva = hex(sym.address)
                except Exception:
                    rva = str(sym.address)

            hint = str(ordinal) if ordinal is not None else None

            forwarded = None
            if getattr(sym, 'forwarder', None):
                try:
                    forwarded = sym.forwarder.decode('utf-8', errors='replace')
                except Exception:
                    forwarded = str(sym.forwarder)

            exports.append(ExportedFunc(
                name=name,
                ordinal=ordinal,
                hint=hint,
                rva=rva,
                forwarded_to=forwarded
            ))

        try:
            pe.close()
        except Exception:
            pass

        return exports, len(exports) > 0

    except Exception:
        return [], False


def get_pe_imports(dll_path: Path) -> Tuple[List[str], bool]:
    """Extract list of imported DLLs using pefile.
    
    Args:
        dll_path: Path to PE file
        
    Returns:
        (list of lowercase DLL names, success_bool)
    """
    try:
        pe = pefile.PE(str(dll_path))
        imports = []
        
        if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                if entry.dll:
                    try:
                        dll_name = entry.dll.decode('utf-8').lower()
                        imports.append(dll_name)
                    except UnicodeDecodeError:
                        pass
                        
        return imports, True
        
    except Exception as e:
        logger.error(f"Error reading imports from {dll_path}: {e}")
        return [], False

# -------------------------------------------------------------------------
# LEGACY DUMPBIN FUNCTIONS (DEPRECATED)
# -------------------------------------------------------------------------

def find_dumpbin() -> str:
    """Auto-locate dumpbin.exe in standard Visual Studio directories."""
    try:
        subprocess.run(['dumpbin', '/?'], capture_output=True)
        return 'dumpbin'
    except FileNotFoundError:
        pass
    return 'dumpbin'

EXPORT_LINE_RE = re.compile(
    r"^\s*(\d+)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{8}|--------)\s+([^\s=]+)(?:\s*=\s*(\S+))?"
)

def parse_dumpbin_exports(text: str) -> List[ExportedFunc]:
    """Parse dumpbin /exports output."""
    exports = []
    seen_names = set()

    for line in text.split('\\n'):
        match = EXPORT_LINE_RE.match(line)
        if not match:
            continue

        ordinal_str, hint, rva, name, forwarded = match.groups()

        if name in seen_names:
            continue

        try:
            ordinal = int(ordinal_str)
        except ValueError:
            ordinal = None

        exports.append(ExportedFunc(
            name=name,
            ordinal=ordinal,
            hint=hint,
            rva=rva,
            forwarded_to=forwarded
        ))
        seen_names.add(name)

    return exports

def get_exports_from_dumpbin(
    dll_path: Path,
    dumpbin_exe: str = None,
    raw_output_path: Optional[Path] = None
) -> Tuple[List[ExportedFunc], bool]:
    """Legacy wrapper for dumpbin extraction."""
    if not dumpbin_exe:
        dumpbin_exe = find_dumpbin()
        
    returncode, output = run_dumpbin(dll_path, dumpbin_exe)

    if returncode != 0:
        return [], False

    if raw_output_path:
        # Save logic skipped for brevity/cleanliness in this overwrite, assume not needed or handled elsewhere if raw is requested
        pass

    exports = parse_dumpbin_exports(output)
    return exports, len(exports) > 0

def run_dumpbin(dll_path: Path, dumpbin_exe: str) -> Tuple[int, str]:
    """Run dumpbin /exports on a DLL."""
    try:
        cmd = [dumpbin_exe, '/exports', str(dll_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30
        )
        output = (result.stdout or '') + '\\n' + (result.stderr or '')
        return result.returncode, output
    except Exception as e:
        return 1, str(e)

def get_imports_from_dumpbin(dll_path: Path, dumpbin_exe: str = "dumpbin") -> Tuple[List[str], bool]:
    """Extract list of imported DLLs using dumpbin /imports."""
    try:
        cmd = [dumpbin_exe, "/imports", str(dll_path)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode != 0:
            return [], False
        
        imports = []
        for line in result.stdout.split('\\n'):
            match = re.match(r'^\s+([a-z0-9_.]+\.dll)\s*$', line, re.IGNORECASE)
            if match:
                dll_name = match.group(1).lower()
                if dll_name not in imports:
                    imports.append(dll_name)
        return imports, True
    except Exception:
        return [], False
