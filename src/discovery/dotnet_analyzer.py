"""
dotnet_analyzer.py - .NET assembly metadata extraction.

Extracts type and method information from .NET assemblies using
System.Reflection via PowerShell.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

from schema import Invocable

logger = logging.getLogger(__name__)


def get_dotnet_methods(dll_path: Path, timeout: int = 60) -> List[Invocable]:
    """Extract .NET types and methods using PowerShell reflection.
    
    Args:
        dll_path: Path to .NET assembly DLL
        timeout: Timeout in seconds for PowerShell execution
        
    Returns:
        List of Invocable records representing .NET methods
    """
    
    # PowerShell script to enumerate all public types/methods
    ps_script = f"""
    try {{
        # Load assembly
        $asm = [System.Reflection.Assembly]::LoadFile('{dll_path}')
        
        # Get all public types
        $types = $asm.GetTypes() | Where-Object {{ $_.IsPublic }}
        
        # For each type, get public methods
        $output = @()
        foreach ($type in $types) {{
            $methods = $type.GetMethods([System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::Static)
            
            foreach ($method in $methods) {{
                # Skip property getters/setters and other compiler-generated methods
                if ($method.IsSpecialName) {{ continue }}
                
                # Extract method info
                $returnType = $method.ReturnType.Name
                
                # Get parameters
                $params = @()
                foreach ($param in $method.GetParameters()) {{
                    $params += "$($param.ParameterType.Name) $($param.Name)"
                }}
                $paramStr = $params -join ', '
                
                # Create record
                $output += @{{
                    Type = $type.FullName
                    Namespace = $type.Namespace
                    Method = $method.Name
                    ReturnType = $returnType
                    Parameters = $paramStr
                    IsStatic = $method.IsStatic
                    IsAbstract = $method.IsAbstract
                }}
            }}
        }}
        
        # Output as JSON
        if ($output.Count -gt 0) {{
            $output | ConvertTo-Json -Depth 10
        }} else {{
            '[]'
        }}
    }}
    catch {{
        Write-Error $_.Exception.Message
        '[]'
    }}
    """
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            logger.warning(f"PowerShell returned error code {result.returncode}: {result.stderr}")
            return []
        
        if not result.stdout or result.stdout.strip() == '[]':
            logger.info(f"No public methods found in {dll_path.name}")
            return []
        
        # Parse JSON output
        data = json.loads(result.stdout)
        
        # Handle single object vs array
        if isinstance(data, dict):
            data = [data]
        
        # Convert to Invocable records
        invocables = []
        for m in data:
            signature = f"{m['ReturnType']} {m['Method']}({m['Parameters']})"
            
            invocable = Invocable(
                name=f"{m['Type']}.{m['Method']}",
                source_type="dotnet",
                return_type=m['ReturnType'],
                parameters=m['Parameters'],
                signature=signature,
                doc_comment=f"{'Static' if m['IsStatic'] else 'Instance'} method from {m['Namespace']}" if m.get('Namespace') else None,
                confidence="guaranteed",  # .NET reflection provides complete invocable signature
                confidence_reasons=["full reflection metadata", "return type known", "parameters known", "invocation method known"]
            )
            invocables.append(invocable)
        
        logger.info(f"Extracted {len(invocables)} .NET methods from {dll_path.name}")
        return invocables
    
    except subprocess.TimeoutExpired:
        logger.error(f"PowerShell timeout after {timeout}s for {dll_path.name}")
        return []
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse .NET assembly: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error analyzing .NET assembly: {e}")
        return []


def get_dotnet_metadata(dll_path: Path) -> Dict[str, str]:
    """Extract basic .NET assembly metadata (version, culture, key).
    
    Args:
        dll_path: Path to .NET assembly
        
    Returns:
        Dictionary with metadata fields
    """
    ps_script = f"""
    try {{
        $asm = [System.Reflection.Assembly]::LoadFile('{dll_path}')
        $name = $asm.GetName()
        
        @{{
            AssemblyName = $name.Name
            Version = $name.Version.ToString()
            Culture = if ($name.CultureName) {{ $name.CultureName }} else {{ 'neutral' }}
            PublicKeyToken = if ($name.GetPublicKeyToken()) {{ 
                ($name.GetPublicKeyToken() | ForEach-Object {{ $_.ToString('x2') }}) -join ''
            }} else {{ 'null' }}
        }} | ConvertTo-Json
    }}
    catch {{
        '{{}}'
    }}
    """
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        
        return {}
    
    except Exception:
        return {}
