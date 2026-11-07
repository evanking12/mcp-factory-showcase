"""
classify.py - File type, architecture, and signature detection.

Detects file types (PE DLL/EXE, .NET assembly, script, COM object, etc)
to route to appropriate analyzers, and extracts digital signature info.
"""

import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

# Suppress GUI windows when calling wmic or other tools (Windows only).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FileType(Enum):
    """Supported file types for analysis."""
    # Native Windows binaries
    PE_DLL = "PE_DLL"
    PE_EXE = "PE_EXE"
    DOTNET_ASSEMBLY = "DOTNET_ASSEMBLY"
    COM_OBJECT = "COM_OBJECT"
    # JIT / scripting languages
    PYTHON_SCRIPT = "PYTHON_SCRIPT"
    POWERSHELL_SCRIPT = "POWERSHELL_SCRIPT"
    BATCH_SCRIPT = "BATCH_SCRIPT"
    VBSCRIPT = "VBSCRIPT"
    SHELL_SCRIPT = "SHELL_SCRIPT"
    JAVASCRIPT = "JAVASCRIPT"
    TYPESCRIPT = "TYPESCRIPT"
    RUBY_SCRIPT = "RUBY_SCRIPT"
    PHP_SCRIPT = "PHP_SCRIPT"
    # Data / query
    SQL_FILE = "SQL_FILE"
    # Protocol / service descriptors
    OPENAPI_SPEC  = "OPENAPI_SPEC"   # OpenAPI 3.x / Swagger 2.x YAML or JSON
    JSONRPC_SPEC  = "JSONRPC_SPEC"   # JSON-RPC 2.0 service descriptor JSON
    WSDL_FILE     = "WSDL_FILE"      # SOAP/WSDL 1.1 or 2.0
    CORBA_IDL     = "CORBA_IDL"      # CORBA Interface Definition Language
    JNDI_CONFIG   = "JNDI_CONFIG"    # JNDI .properties / Spring XML
    PDB_FILE      = "PDB_FILE"       # Windows Program Database (debug symbols)
    # Generic fallback kept for backwards-compat
    SCRIPT = "SCRIPT"
    UNKNOWN = "UNKNOWN"


def classify_file(file_path: Path) -> FileType:
    """Classify a file based on its signature and extension.
    
    Args:
        file_path: Path to file to classify
        
    Returns:
        FileType enum indicating detected type
    """
    if not file_path.exists():
        return FileType.UNKNOWN

    ext = file_path.suffix.lower()

    # Explicit override for .tlb files - they are always COM/TypeLibraries
    if ext in ['.tlb', '.olb']:
        return FileType.COM_OBJECT

    # --- JIT / scripting / query files (extension-based detection) ---
    if ext == '.py':
        return FileType.PYTHON_SCRIPT
    if ext == '.ps1':
        return FileType.POWERSHELL_SCRIPT
    if ext in ('.bat', '.cmd'):
        return FileType.BATCH_SCRIPT
    if ext == '.vbs':
        return FileType.VBSCRIPT
    if ext in ('.sh', '.bash', '.zsh'):
        return FileType.SHELL_SCRIPT
    if ext in ('.js', '.mjs', '.cjs'):
        return FileType.JAVASCRIPT
    if ext in ('.ts', '.tsx', '.mts'):
        return FileType.TYPESCRIPT
    if ext == '.rb':
        return FileType.RUBY_SCRIPT
    if ext == '.php':
        return FileType.PHP_SCRIPT
    if ext == '.sql':
        return FileType.SQL_FILE

    # ── Service / protocol descriptor files ─────────────────────────────────
    if ext in ('.yaml', '.yml'):
        # Could be a plain YAML config or an OpenAPI spec; peek inside
        try:
            snippet = file_path.read_text(encoding='utf-8', errors='replace')[:2000]
            if any(k in snippet for k in ('openapi:', 'swagger:')):
                return FileType.OPENAPI_SPEC
        except OSError:
            pass
        return FileType.OPENAPI_SPEC  # treat all YAML as potential OpenAPI specs

    if ext == '.wsdl':
        return FileType.WSDL_FILE

    if ext == '.idl':
        return FileType.CORBA_IDL

    if ext in ('.jndi', '.properties'):
        return FileType.JNDI_CONFIG

    if ext == '.pdb':
        return FileType.PDB_FILE

    # XML: could be Spring JNDI context
    if ext == '.xml':
        try:
            snippet = file_path.read_text(encoding='utf-8', errors='replace')[:2000]
            if any(k in snippet for k in ('jndi-lookup', 'JndiObjectFactoryBean',
                                          'java.naming', 'jndiName')):
                return FileType.JNDI_CONFIG
            if '<definitions' in snippet and 'schemas.xmlsoap.org/wsdl' in snippet:
                return FileType.WSDL_FILE
        except OSError:
            pass

    # JSON: could be OpenAPI or JSON-RPC
    if ext == '.json':
        try:
            import json as _json
            snippet = file_path.read_text(encoding='utf-8', errors='replace')[:4000]
            data = _json.loads(snippet + ('}' if not snippet.rstrip().endswith('}') else ''))
        except Exception:
            data = {}
        if isinstance(data, dict):
            if 'openapi' in data or 'swagger' in data:
                return FileType.OPENAPI_SPEC
            if 'methods' in data and 'jsonrpc' not in data:
                return FileType.JSONRPC_SPEC
            if 'jsonrpc' in data or 'method' in data:
                return FileType.JSONRPC_SPEC
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(4)

        # PE signature: "MZ" followed by PE signature at offset
        if magic[:2] == b'MZ':
            # Read PE header offset
            with open(file_path, 'rb') as f:
                f.seek(0x3c)
                pe_offset_bytes = f.read(4)
                if len(pe_offset_bytes) == 4:
                    pe_offset = int.from_bytes(pe_offset_bytes, 'little')

                    # Read PE signature
                    with open(file_path, 'rb') as f2:
                        f2.seek(pe_offset)
                        pe_sig = f2.read(4)

                        if pe_sig == b'PE\x00\x00':
                            # Read machine type (offset +4 in COFF header)
                            f2.seek(pe_offset + 4)
                            machine = f2.read(2)

                            # Check for .NET metadata
                            if _has_dotnet_metadata(file_path):
                                return FileType.DOTNET_ASSEMBLY

                            # Distinguish DLL vs EXE by characteristics
                            f2.seek(pe_offset + 22)  # Characteristics field
                            chars = f2.read(2)
                            if len(chars) == 2:
                                characteristics = int.from_bytes(chars, 'little')
                                # 0x2000 = DLL characteristic
                                if characteristics & 0x2000:
                                    # Check if it's a COM object
                                    if _is_com_object(file_path):
                                        return FileType.COM_OBJECT
                                    return FileType.PE_DLL
                                else:
                                    return FileType.PE_EXE

                            return FileType.PE_DLL  # Default for PE

        # .NET signature
        if magic == b'ILFM':
            return FileType.DOTNET_ASSEMBLY

    except (OSError, struct.error):
        pass

    # Extension-based fallback
    if ext in ['.dll']:
        # If we failed to detect COM/NET via PE, check name
        if _is_com_object(file_path):
             return FileType.COM_OBJECT
        return FileType.PE_DLL
    elif ext in ['.exe', '.com']:
        return FileType.PE_EXE
    elif ext in ['.tlb', '.olb']:
        return FileType.COM_OBJECT
    
    # Pre-check: TLB files often have "MSFT" magic or others, but extension is reliable enough
    if ext in ['.tlb', '.olb']:
        return FileType.COM_OBJECT

    return FileType.UNKNOWN


def _has_dotnet_metadata(file_path: Path) -> bool:
    """Check if PE file contains .NET metadata (CLR header).
    
    Reads PE data directory 14 (CLR Runtime Header).
    If RVA > 0 and Size > 0, the binary contains .NET code.
    """
    try:
        with open(file_path, 'rb') as f:
            # Read DOS header -> PE offset
            f.seek(0x3c)
            pe_offset_bytes = f.read(4)
            if len(pe_offset_bytes) != 4:
                return False
            pe_offset = int.from_bytes(pe_offset_bytes, 'little')
            
            # Validate PE signature
            f.seek(pe_offset)
            pe_sig = f.read(4)
            if pe_sig != b'PE\x00\x00':
                return False
            
            # Read magic (determines bitness)
            # Magic is 2 bytes after PE signature + COFF header (20 bytes)
            f.seek(pe_offset + 24)
            magic_bytes = f.read(2)
            if len(magic_bytes) != 2:
                return False
            magic = int.from_bytes(magic_bytes, 'little')
            
            is_64bit = (magic == 0x20B)  # 0x20B = PE32+, 0x10B = PE32
            
            # Data directories start AFTER NumberOfRvaAndSizes field:
            # PE+24 (Optional Header start) + 108 (x64) or + 92 (x86) = NumberOfRvaAndSizes offset
            # Then +4 to skip NumberOfRvaAndSizes itself = First data directory
            num_dirs_offset = pe_offset + 24 + (108 if is_64bit else 92)
            
            # CLR Runtime Header is directory 14
            # Each directory = 8 bytes (RVA + Size)
            clr_dir_offset = num_dirs_offset + 4 + (14 * 8)
            
            f.seek(clr_dir_offset)
            clr_rva_bytes = f.read(4)
            clr_size_bytes = f.read(4)
            
            if len(clr_rva_bytes) != 4 or len(clr_size_bytes) != 4:
                return False
            
            clr_rva = int.from_bytes(clr_rva_bytes, 'little')
            clr_size = int.from_bytes(clr_size_bytes, 'little')
            
            return clr_rva > 0 and clr_size > 0
    
    except (OSError, ValueError):
        return False


def _is_com_object(file_path: Path, dumpbin_exe: str = "dumpbin") -> bool:
    """Detect if PE DLL is a COM object by checking imports.
    
    COM objects typically import ole32.dll or oleaut32.dll.
    Also checks if file itself is a core COM DLL.
    """
    try:
        # Check if file itself is a core COM DLL (they don't import themselves)
        com_core_dlls = {'ole32.dll', 'oleaut32.dll'}
        if file_path.name.lower() in com_core_dlls:
            return True
        
        from pe_parse import get_pe_imports
        imports, success = get_pe_imports(file_path, dumpbin_exe)
        
        if not success or not imports:
            return False
        
        # Check for COM indicator DLLs in imports
        return any(imp in com_core_dlls for imp in imports)
    
    except Exception:
        return False


def get_architecture(file_path: Path) -> Optional[str]:
    """Detect architecture (x86, x64, ARM64, etc) from PE header.
    
    Returns:
        Architecture string or None if cannot determine
    """
    try:
        with open(file_path, 'rb') as f:
            f.seek(0x3c)
            pe_offset = int.from_bytes(f.read(4), 'little')

            f.seek(pe_offset + 4)
            machine = int.from_bytes(f.read(2), 'little')

            # Machine type constants
            MACHINE_I386 = 0x014C
            MACHINE_AMD64 = 0x8664
            MACHINE_ARM = 0x01C0
            MACHINE_ARM64 = 0xAA64

            if machine == MACHINE_I386:
                return "x86"
            elif machine == MACHINE_AMD64:
                return "x64"
            elif machine == MACHINE_ARM:
                return "ARM"
            elif machine == MACHINE_ARM64:
                return "ARM64"

    except (OSError, ValueError):
        pass

    return None


def extract_signature(pe_path: Path) -> Tuple[bool, Optional[str]]:
    """Extract digital signature and publisher info from PE file.
    
    Parses Security Directory[4] via PowerShell Get-AuthenticodeSignature.
    
    Args:
        pe_path: Path to PE file
        
    Returns:
        (is_signed, publisher_name)
    """
    try:
        from signature import get_signature_info
        return get_signature_info(pe_path)
    except ImportError:
        # Fallback to old method if signature module not available
        try:
            # Use wmic to extract file description/publisher
            result = subprocess.run(
                ['wmic', 'datafile', 'where',
                 f'name="{str(pe_path).replace(chr(92), chr(92)+chr(92))}"',
                 'get', 'Description,Version', '/format:list'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=_NO_WINDOW,
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if 'Description=' in output:
                    publisher = output.split('Description=')[1].split('\n')[0].strip()
                    return True, publisher if publisher else "Unknown"
            
            return False, None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False, None

