"""
Test import and RPC analysis capabilities
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "discovery"))

from import_analyzer import analyze_imports
from rpc_analyzer import analyze_rpc

def test_rpcrt4():
    """Test analyzing rpcrt4.dll itself"""
    dll_path = Path(r"C:\Windows\System32\rpcrt4.dll")
    
    print("="*70)
    print(f"ANALYZING: {dll_path.name}")
    print("="*70)
    
    # Import analysis
    import_analysis = analyze_imports(dll_path)
    
    print(f"\n📦 IMPORT ANALYSIS:")
    print(f"   Total DLLs: {import_analysis['summary']['total_dlls']}")
    print(f"   Total Functions: {import_analysis['summary']['total_functions']}")
    
    caps = import_analysis['capabilities']
    if caps:
        print(f"\n🔍 CAPABILITIES DETECTED:")
        for cap_name, cap_info in sorted(caps.items()):
            print(f"   [{cap_name.upper()}]")
            print(f"      DLLs: {', '.join(cap_info['dlls'])}")
            if 'functions' in cap_info and cap_info['functions']:
                print(f"      Functions: {len(cap_info['functions'])}")
    
    # RPC analysis
    rpc_analysis = analyze_rpc(dll_path, import_analysis['imports'])
    
    print(f"\n🔌 RPC ANALYSIS:")
    print(f"   Has RPC: {rpc_analysis.get('has_rpc', False)}")
    if rpc_analysis.get('has_rpc'):
        summary = rpc_analysis.get('summary', {})
        print(f"   Is Server: {summary.get('is_server', False)}")
        print(f"   Is Client: {summary.get('is_client', False)}")
        print(f"   RPC Functions: {len(summary.get('functions', []))}")
        
        interfaces = rpc_analysis.get('interfaces', [])
        print(f"   Interfaces Found: {len(interfaces)}")
        
        pipes = rpc_analysis.get('named_pipes', [])
        print(f"   Named Pipes: {len(pipes)}")
        
        if pipes:
            print(f"\n   📍 Named Pipes:")
            for pipe in pipes[:5]:
                print(f"      - {pipe}")


def test_lsass():
    """Test analyzing lsass.exe which uses RPC"""
    dll_path = Path(r"C:\Windows\System32\lsass.exe")
    
    if not dll_path.exists():
        print(f"⚠️  {dll_path} not found, skipping")
        return
    
    print("\n" + "="*70)
    print(f"ANALYZING: {dll_path.name}")
    print("="*70)
    
    import_analysis = analyze_imports(dll_path)
    
    print(f"\n📦 IMPORT ANALYSIS:")
    print(f"   Total DLLs: {import_analysis['summary']['total_dlls']}")
    
    if import_analysis['summary'].get('has_rpc'):
        print(f"   ✅ RPC DETECTED!")
        
        rpc_analysis = analyze_rpc(dll_path, import_analysis['imports'])
        summary = rpc_analysis.get('summary', {})
        
        print(f"   Is Server: {summary.get('is_server', False)}")
        print(f"   RPC Functions:")
        for func in summary.get('functions', [])[:10]:
            print(f"      - {func}")


def test_winhttp():
    """Test analyzing winhttp.dll for network capabilities"""
    dll_path = Path(r"C:\Windows\System32\winhttp.dll")
    
    print("\n" + "="*70)
    print(f"ANALYZING: {dll_path.name}")
    print("="*70)
    
    import_analysis = analyze_imports(dll_path)
    
    print(f"\n📦 IMPORT ANALYSIS:")
    print(f"   Total DLLs: {import_analysis['summary']['total_dlls']}")
    print(f"   Has Networking: {import_analysis['summary'].get('has_networking', False)}")
    
    if import_analysis['summary'].get('has_networking'):
        print(f"\n   ✅ NETWORK CAPABILITIES DETECTED!")
        net_info = import_analysis['capabilities'].get('networking', {})
        
        print(f"   DLLs: {', '.join(net_info.get('dlls', []))}")
        
        protocols = net_info.get('protocols', [])
        if protocols:
            print(f"   Protocols: {', '.join(protocols)}")
        
        funcs = net_info.get('functions', [])
        if funcs:
            print(f"   Network Functions ({len(funcs)}):")
            for func in funcs[:15]:
                print(f"      - {func}")


if __name__ == '__main__':
    test_rpcrt4()
    test_lsass()
    test_winhttp()
    
    print("\n" + "="*70)
    print("✅ ALL TESTS COMPLETE")
    print("="*70)
