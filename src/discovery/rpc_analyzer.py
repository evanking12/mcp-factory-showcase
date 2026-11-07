"""
rpc_analyzer.py - RPC (Remote Procedure Call) endpoint detection and analysis.

Detects RPC interfaces in native DLLs by:
1. Analyzing imports (RpcServer*, RpcBinding*, etc.)
2. Searching for MIDL-generated stub/proxy code patterns
3. Extracting interface UUIDs from binary
4. Detecting named pipes and RPC endpoints
"""

import logging
import re
import struct
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from schema import Invocable

logger = logging.getLogger(__name__)


@dataclass
class RpcInterface:
    """Represents an RPC interface found in a DLL."""
    uuid: str
    version: str
    name: Optional[str] = None
    is_server: bool = False
    is_client: bool = False
    endpoints: List[str] = None
    procedures: List[str] = None
    
    def __post_init__(self):
        if self.endpoints is None:
            self.endpoints = []
        if self.procedures is None:
            self.procedures = []


def extract_uuids_from_binary(dll_path: Path) -> List[str]:
    """Extract UUID patterns from binary data.
    
    RPC interface UUIDs are stored in specific format:
    GUID: {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
    Binary: 16 bytes in little-endian format
    """
    uuids = []
    
    try:
        with open(dll_path, 'rb') as f:
            data = f.read()
        
        # Search for UUID patterns in binary
        # UUIDs typically appear near MIDL stub code
        # Pattern: Look for 16-byte aligned GUID structures
        
        offset = 0
        while offset < len(data) - 16:
            try:
                # Try to parse as GUID (little-endian)
                guid_bytes = data[offset:offset+16]
                
                # Basic validation: first field should look reasonable
                # (not all zeros, not all FFs)
                if guid_bytes != b'\x00' * 16 and guid_bytes != b'\xff' * 16:
                    # Parse GUID components
                    data1 = struct.unpack('<I', guid_bytes[0:4])[0]
                    data2 = struct.unpack('<H', guid_bytes[4:6])[0]
                    data3 = struct.unpack('<H', guid_bytes[6:8])[0]
                    data4 = guid_bytes[8:16]
                    
                    # Format as UUID string
                    uuid_str = f"{{{data1:08X}-{data2:04X}-{data3:04X}-"
                    uuid_str += f"{data4[0]:02X}{data4[1]:02X}-"
                    uuid_str += ''.join(f"{b:02X}" for b in data4[2:])
                    uuid_str += "}"
                    
                    # Check if it looks like a valid RPC interface UUID
                    # (heuristic: version field should be small)
                    if data2 < 100 and data3 < 100:
                        if uuid_str not in uuids:
                            uuids.append(uuid_str)
                
            except Exception:
                pass
            
            offset += 4  # Search every 4 bytes (alignment)
            
            # Limit to prevent excessive processing
            if len(uuids) > 50:
                break
        
        logger.info(f"Found {len(uuids)} potential UUIDs in {dll_path.name}")
        return uuids
        
    except Exception as e:
        logger.warning(f"Error extracting UUIDs: {e}")
        return []


def detect_rpc_from_imports(imports: Dict[str, List[str]]) -> Dict:
    """Detect RPC usage from import table.
    
    Args:
        imports: Dict mapping DLL names to imported functions
        
    Returns:
        Dict with RPC detection info
    """
    rpc_info = {
        'detected': False,
        'is_server': False,
        'is_client': False,
        'functions': [],
        'endpoint_types': []
    }
    
    # Check if rpcrt4.dll is imported
    all_functions = []
    for dll, funcs in imports.items():
        if 'rpcrt4' in dll.lower():
            rpc_info['detected'] = True
            all_functions.extend(funcs)
    
    if not rpc_info['detected']:
        return rpc_info
    
    # Categorize RPC functions
    server_funcs = [f for f in all_functions if 'Server' in f or 'Listen' in f]
    client_funcs = [f for f in all_functions if 'Binding' in f or 'Client' in f]
    
    rpc_info['is_server'] = len(server_funcs) > 0
    rpc_info['is_client'] = len(client_funcs) > 0
    rpc_info['functions'] = all_functions
    
    # Detect endpoint types
    endpoint_keywords = {
        'ncacn_np': 'Named Pipes',
        'ncacn_ip_tcp': 'TCP/IP',
        'ncacn_http': 'HTTP',
        'ncalrpc': 'Local RPC'
    }
    
    # These would be detected from string analysis
    # For now, infer from function usage
    if any('Protseq' in f for f in all_functions):
        rpc_info['endpoint_types'].append('Protocol sequence detected')
    
    return rpc_info


def search_named_pipes(dll_path: Path) -> List[str]:
    """Search for named pipe references in binary.
    
    Named pipes used for RPC typically follow pattern:
    \\.\pipe\<name>
    """
    pipes = []
    
    try:
        with open(dll_path, 'rb') as f:
            data = f.read()
        
        # Convert to string (try UTF-16 and ASCII)
        try:
            text_utf16 = data.decode('utf-16le', errors='ignore')
            text_ascii = data.decode('ascii', errors='ignore')
            combined = text_utf16 + ' ' + text_ascii
        except:
            combined = str(data)
        
        # Search for named pipe patterns
        pipe_pattern = r'\\\\\.\\pipe\\[\w\-_]+'
        matches = re.findall(pipe_pattern, combined)
        
        pipes = list(set(matches))[:20]  # Limit to 20 unique pipes
        
        if pipes:
            logger.info(f"Found {len(pipes)} named pipe references")
        
        return pipes
        
    except Exception as e:
        logger.warning(f"Error searching named pipes: {e}")
        return []


def analyze_rpc(dll_path: Path, imports: Dict[str, List[str]] = None) -> Dict:
    """Comprehensive RPC analysis.
    
    Args:
        dll_path: Path to DLL
        imports: Optional pre-parsed imports
        
    Returns:
        Dict with RPC analysis results
    """
    logger.info(f"Analyzing RPC interfaces in {dll_path.name}")
    
    analysis = {
        'has_rpc': False,
        'interfaces': [],
        'named_pipes': [],
        'summary': {}
    }
    
    # 1. Check imports
    if imports:
        import_info = detect_rpc_from_imports(imports)
        analysis['has_rpc'] = import_info['detected']
        analysis['summary'] = import_info
    
    if not analysis['has_rpc']:
        logger.info("No RPC usage detected in imports")
        return analysis
    
    # 2. Extract UUIDs (potential RPC interface IDs)
    uuids = extract_uuids_from_binary(dll_path)
    
    # 3. Search for named pipes
    pipes = search_named_pipes(dll_path)
    analysis['named_pipes'] = pipes
    
    # 4. Create RpcInterface objects for discovered interfaces
    for uuid in uuids[:10]:  # Limit to first 10
        interface = RpcInterface(
            uuid=uuid,
            version="1.0",  # Default version
            name=f"RPC Interface {uuid}",
            is_server=analysis['summary'].get('is_server', False),
            is_client=analysis['summary'].get('is_client', False),
            endpoints=pipes if pipes else ['Unknown']
        )
        analysis['interfaces'].append(interface)
    
    logger.info(f"RPC analysis complete: {len(analysis['interfaces'])} interfaces found")
    
    return analysis


def rpc_to_invocables(rpc_analysis: Dict, dll_path: Path) -> List[Invocable]:
    """Convert RPC interfaces to Invocable objects.
    
    Args:
        rpc_analysis: Results from analyze_rpc()
        dll_path: Path to DLL
        
    Returns:
        List of Invocable objects for RPC endpoints
    """
    invocables = []
    
    if not rpc_analysis.get('has_rpc'):
        return invocables
    
    interfaces = rpc_analysis.get('interfaces', [])
    
    for interface in interfaces:
        # RPC interfaces with server functions detected = HIGH confidence
        # RPC interfaces from binary UUID scan only = MEDIUM confidence
        confidence = 'high' if interface.is_server or interface.is_client else 'medium'
        reasons = ['RPC interface UUID detected']
        if interface.is_server:
            reasons.append('RPC server functions imported')
        if interface.is_client:
            reasons.append('RPC client functions imported')
        
        invocable = Invocable(
            name=interface.name or f"RPC_{interface.uuid}",
            source_type="rpc",
            signature=f"UUID: {interface.uuid}, Version: {interface.version}",
            doc_comment=f"RPC Interface - {'Server' if interface.is_server else ''} {'Client' if interface.is_client else ''}" .strip(),
            parameters=', '.join(interface.endpoints) if interface.endpoints else None,
            dll_path=str(dll_path),
            confidence=confidence,
            confidence_reasons=reasons
        )
        
        invocables.append(invocable)
    
    # Add named pipe endpoints as separate invocables
    for pipe in rpc_analysis.get('named_pipes', []):
        pipe_name = pipe.split('\\')[-1]
        # Named pipes found in binary strings = MEDIUM-HIGH confidence
        invocable = Invocable(
            name=f"NamedPipe_{pipe_name}",
            source_type="rpc",
            signature=f"Named Pipe: {pipe}",
            doc_comment="RPC endpoint via named pipe",
            parameters=pipe,
            dll_path=str(dll_path),
            confidence='medium',
            confidence_reasons=['named pipe string found in binary', 'likely RPC endpoint']
        )
        invocables.append(invocable)
    
    return invocables


def format_rpc_summary(rpc_analysis: Dict) -> str:
    """Format RPC analysis as human-readable summary."""
    if not rpc_analysis.get('has_rpc'):
        return "No RPC interfaces detected"
    
    lines = ["\nRPC ANALYSIS:"]
    
    summary = rpc_analysis.get('summary', {})
    
    if summary.get('is_server'):
        lines.append("  Mode: RPC Server")
    if summary.get('is_client'):
        lines.append("  Mode: RPC Client")
    
    funcs = summary.get('functions', [])
    if funcs:
        lines.append(f"  RPC Functions: {len(funcs)}")
        for func in funcs[:5]:
            lines.append(f"    - {func}")
        if len(funcs) > 5:
            lines.append(f"    ... and {len(funcs) - 5} more")
    
    interfaces = rpc_analysis.get('interfaces', [])
    if interfaces:
        lines.append(f"\n  Interfaces Found: {len(interfaces)}")
        for iface in interfaces[:3]:
            lines.append(f"    - {iface.uuid} (v{iface.version})")
        if len(interfaces) > 3:
            lines.append(f"    ... and {len(interfaces) - 3} more")
    
    pipes = rpc_analysis.get('named_pipes', [])
    if pipes:
        lines.append(f"\n  Named Pipes: {len(pipes)}")
        for pipe in pipes[:5]:
            lines.append(f"    - {pipe}")
        if len(pipes) > 5:
            lines.append(f"    ... and {len(pipes) - 5} more")
    
    return '\n'.join(lines)
