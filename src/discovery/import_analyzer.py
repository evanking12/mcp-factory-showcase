"""
import_analyzer.py - Import Address Table (IAT) analysis for PE/COFF binaries.

Analyzes what DLLs and functions a binary imports to determine capabilities:
- Network operations (WinHTTP, WinINet, Winsock)
- COM/RPC usage
- Cryptography
- File system operations
- Registry access
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Optional
import pefile

logger = logging.getLogger(__name__)


# Capability detection based on imported DLLs
CAPABILITY_DLLS = {
    'networking': {
        'ws2_32.dll', 'wsock32.dll',  # Winsock
        'winhttp.dll',                 # WinHTTP
        'wininet.dll',                 # WinINet
        'iphlpapi.dll',                # IP Helper
        'netapi32.dll',                # Network API
    },
    'com': {
        'ole32.dll',                   # COM core
        'oleaut32.dll',                # COM automation
        'combase.dll',                 # Modern COM
    },
    'rpc': {
        'rpcrt4.dll',                  # RPC runtime
        'rpcns4.dll',                  # RPC name service
    },
    'crypto': {
        'bcrypt.dll',                  # BCrypt
        'crypt32.dll',                 # Crypto API
        'ncrypt.dll',                  # CNG
        'cryptsp.dll',                 # Crypto service provider
    },
    'registry': {
        'advapi32.dll',                # Advanced API (includes registry)
    },
    'filesystem': {
        'kernel32.dll',                # File I/O
        'kernelbase.dll',              # Base kernel
    },
    'security': {
        'secur32.dll',                 # Security support
        'sspicli.dll',                 # SSPI client
    },
    'database': {
        'odbc32.dll',                  # ODBC
        'oledb32.dll',                 # OLE DB
    }
}

# Key network functions to detect
NETWORK_FUNCTIONS = {
    # WinHTTP
    'WinHttpOpen', 'WinHttpConnect', 'WinHttpOpenRequest',
    'WinHttpSendRequest', 'WinHttpReceiveResponse', 'WinHttpReadData',
    'WinHttpSetOption', 'WinHttpQueryOption',
    
    # WinINet
    'InternetOpenA', 'InternetOpenW', 'InternetConnectA', 'InternetConnectW',
    'HttpOpenRequestA', 'HttpOpenRequestW', 'HttpSendRequestA', 'HttpSendRequestW',
    'InternetReadFile', 'InternetCloseHandle',
    
    # Winsock
    'WSAStartup', 'WSACleanup', 'socket', 'connect', 'bind', 'listen',
    'send', 'recv', 'sendto', 'recvfrom', 'closesocket',
    'getaddrinfo', 'gethostbyname', 'inet_addr',
}

# RPC functions
RPC_FUNCTIONS = {
    'RpcServerRegisterIf', 'RpcServerRegisterIfEx', 'RpcServerListen',
    'RpcServerUseProtseq', 'RpcServerUseProtseqEp',
    'RpcBindingFromStringBinding', 'RpcStringBindingCompose',
    'RpcEpRegister', 'RpcEpResolveBinding',
    'NdrClientCall2', 'NdrServerCall2',
}

# COM functions
COM_FUNCTIONS = {
    'CoInitialize', 'CoInitializeEx', 'CoCreateInstance',
    'CoCreateInstanceEx', 'CoGetClassObject', 'CoRegisterClassObject',
    'IDispatch', 'IUnknown',
}


def get_imports_pe(dll_path: Path) -> Dict[str, List[str]]:
    """Parse imports using pefile.
    
    Args:
        dll_path: Path to PE file
        
    Returns:
        Dict mapping DLL names to list of imported functions
    """
    imports = {}
    try:
        pe = pefile.PE(str(dll_path))
        
        if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                if entry.dll:
                    try:
                        dll_name = entry.dll.decode('utf-8').lower()
                    except UnicodeDecodeError:
                        dll_name = str(entry.dll)
                        
                    func_list = []
                    for imp in entry.imports:
                        if imp.name:
                            try:
                                func_list.append(imp.name.decode('utf-8'))
                            except UnicodeDecodeError:
                                func_list.append(str(imp.name))
                        else:
                            # Ordinal import
                            func_list.append(f"#{imp.ordinal}")
                    imports[dll_name] = func_list
                    
    except Exception as e:
        logger.error(f"Error parsing imports with pefile: {e}")
        
    return imports


def detect_capabilities(imports: Dict[str, List[str]]) -> Dict:
    """Detect capabilities based on imported functions and DLLs.
    
    Args:
        imports: Dict mapping DLL names to imported functions
        
    Returns:
        Dict with capability categories and detected features
    """
    capabilities = {}
    imported_dlls = set(dll.lower() for dll in imports.keys())
    all_functions = set()
    for funcs in imports.values():
        all_functions.update(funcs)
    
    # Check each capability category
    for category, dlls in CAPABILITY_DLLS.items():
        detected_dlls = imported_dlls & {d.lower() for d in dlls}
        
        if detected_dlls:
            capabilities[category] = {
                'detected': True,
                'dlls': list(detected_dlls),
                'functions': []
            }
    
    # Detect specific network functions
    if 'networking' in capabilities:
        network_funcs = all_functions & NETWORK_FUNCTIONS
        capabilities['networking']['functions'] = list(network_funcs)
        capabilities['networking']['protocols'] = _detect_network_protocols(network_funcs)
    
    # Detect RPC functions
    if 'rpc' in capabilities or 'rpcrt4.dll' in imported_dlls:
        rpc_funcs = all_functions & RPC_FUNCTIONS
        if rpc_funcs:
            if 'rpc' not in capabilities:
                capabilities['rpc'] = {'detected': True, 'dlls': ['rpcrt4.dll']}
            capabilities['rpc']['functions'] = list(rpc_funcs)
            capabilities['rpc']['is_server'] = any('Server' in f for f in rpc_funcs)
            capabilities['rpc']['is_client'] = any('Binding' in f or 'Client' in f for f in rpc_funcs)
    
    # Detect COM functions
    if 'com' in capabilities:
        com_funcs = all_functions & COM_FUNCTIONS
        capabilities['com']['functions'] = list(com_funcs)
    
    return capabilities


def _detect_network_protocols(network_funcs: Set[str]) -> List[str]:
    """Detect which network protocols are used."""
    protocols = []
    
    if any('WinHttp' in f for f in network_funcs):
        protocols.append('HTTP/HTTPS (WinHTTP)')
    
    if any('Internet' in f or 'Http' in f for f in network_funcs):
        protocols.append('HTTP/HTTPS (WinINet)')
    
    if any(f in network_funcs for f in ['socket', 'WSAStartup', 'connect', 'bind']):
        protocols.append('TCP/UDP (Winsock)')
    
    return protocols


def analyze_imports(dll_path: Path, dumpbin_path: str = "dumpbin") -> Dict:
    """Full import analysis with capability detection.
    
    Args:
        dll_path: Path to PE file
        dumpbin_path: Deprecated, ignored.
        
    Returns:
        Dict with import summary and capabilities
    """
    # Use pure python pefile implementation
    imports = get_imports_pe(dll_path)
    
    capabilities = detect_capabilities(imports)
    
    return {
        'imports': imports,
        'summary': {
            'total_dlls': len(imports),
            'total_functions': sum(len(f) for f in imports.values()),
            'has_networking': 'networking' in capabilities,
            'has_rpc': 'rpc' in capabilities,
            'has_com': 'com' in capabilities
        },
        'capabilities': capabilities
    }

def format_capabilities_summary(analysis: Dict) -> str:
    """Format capabilities analysis into a human-readable string."""
    summary = analysis.get('summary', {})
    lines = []
    lines.append("Capabilities Summary:")
    lines.append(f"  Total Imported DLLs: {summary.get('total_dlls', 0)}")
    lines.append(f"  Total Imported Functions: {summary.get('total_functions', 0)}")
    
    if summary.get('has_networking'):
        lines.append("\\n  [+] Networking Detected:")
        net_cap = analysis.get('capabilities', {}).get('networking', {})
        for proto in net_cap.get('protocols', []):
            lines.append(f"      - {proto}")
            
    if summary.get('has_rpc'):
        lines.append("\\n  [+] RPC Detected")
        
    if summary.get('has_com'):
        lines.append("\\n  [+] COM Detected")
        
    return "\\n".join(lines)
