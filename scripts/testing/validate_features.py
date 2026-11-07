"""
Feature Validation Suite
------------------------
Validates supported features by scanning representative files.
Runs analysis on a small set of targets for each supported feature type.
"""

import sys
import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "discovery"))

from main import main as analyze_main
from utils import Spinner

# Configure targets for each feature
TARGET_GROUPS = {
    "NATIVE_DLL": [
        "C:\\Windows\\System32\\kernel32.dll",
        "C:\\Windows\\System32\\user32.dll",
        "C:\\Windows\\System32\\advapi32.dll",
        "C:\\Windows\\System32\\gdi32.dll",
        # Local targets if available
        str(Path(__file__).parent.parent / "tests/fixtures/vcpkg_installed/x64-windows/bin/zstd.dll")
    ],
    "DOTNET": [
        "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\System.dll",
        "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\mscorlib.dll",
        "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\System.Data.dll",
        "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\System.Core.dll"
    ],
    "COM": [
        "C:\\Windows\\System32\\ole32.dll",    # Core COM
        "C:\\Windows\\System32\\oleaut32.dll", # Automation
        "C:\\Windows\\System32\\wmiutils.dll", # WMI Utils
        "C:\\Windows\\System32\\actxprxy.dll"  # ActiveX Proxy
    ],
    "CLI": [
        "C:\\Windows\\System32\\find.exe",
        "C:\\Windows\\System32\\attrib.exe",
        "C:\\Windows\\System32\\cmd.exe",
        "C:\\Windows\\System32\\ipconfig.exe",
        "C:\\Windows\\System32\\tar.exe" if os.path.exists("C:\\Windows\\System32\\tar.exe") else None,
        "C:\\Windows\\System32\\curl.exe" if os.path.exists("C:\\Windows\\System32\\curl.exe") else None
    ],
    "RPC": [
        "C:\\Windows\\System32\\rpcrt4.dll",
        "C:\\Windows\\System32\\samlib.dll",
        "C:\\Windows\\System32\\lsasrv.dll"
    ]
}

def run_group(label: str, targets: List[str], output_root: Path):
    """Run analysis on a group of targets."""
    print(f"\n--- Testing Feature: {label} ---")
    
    passes = 0
    total = 0
    
    for target in targets:
        if not target:
            continue
            
        path = Path(target)
        if not path.exists():
            print(f"Skipping {path.name} (not found)")
            continue
            
        total += 1
        output_dir = output_root / label / path.name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Analyzing {path.name}...", end="", flush=True)
        
        # Capture args
        sys.argv = [
            "main.py",
            "--dll", str(path),
            "--out", str(output_dir)
        ]
        
        try:
            # Silence logging during run
            logging.disable(logging.CRITICAL)
            result = analyze_main()
            logging.disable(logging.NOTSET)
            
            # Check if JSON generated
            mcp_json = list(output_dir.glob("*_mcp.json"))
            if result == 0 and mcp_json:
                print(" OK")
                passes += 1
            else:
                print(" FAIL (Invocables not generated)")
                
        except Exception as e:
            logging.disable(logging.NOTSET)
            print(f" ERROR: {e}")
            
    print(f"Result: {passes}/{total} Passed")
    return passes == total

def main():
    print("MCP Factory Feature Validation")
    print("==============================")
    
    out_root = Path("validation_output")
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir()
    
    results = {}
    
    for key, targets in TARGET_GROUPS.items():
        results[key] = run_group(key, targets, out_root)
        
    print("\nSummary")
    print("-------")
    for key, passed in results.items():
        status = "PASS" if passed else "FAIL (Partial)"
        print(f"{key:<12} : {status}")

if __name__ == "__main__":
    main()
