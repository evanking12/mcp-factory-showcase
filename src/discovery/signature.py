"""
signature.py - Digital signature extraction from PE files.

Extracts Authenticode signature information from Security Directory[4].
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple


def get_signature_info(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Extract digital signature info from PE file.
    
    Uses PowerShell Get-AuthenticodeSignature to verify Authenticode.
    
    Args:
        file_path: Path to PE file
        
    Returns:
        Tuple of (is_signed: bool, publisher: str or None)
    """
    if not file_path.exists():
        return False, None
    
    try:
        # Use PowerShell Get-AuthenticodeSignature cmdlet
        ps_cmd = f'(Get-AuthenticodeSignature "{file_path}").SignerCertificate.Subject'
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_cmd],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            subject = result.stdout.strip()
            
            # Parse subject DN to extract CN (Common Name)
            # Format: "CN=Publisher Name, O=Organization, ..."
            publisher = _extract_publisher_from_subject(subject)
            
            if publisher and publisher.lower() != 'none':
                return True, publisher
        
        return False, None
        
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
        return False, None


def _extract_publisher_from_subject(subject: str) -> Optional[str]:
    """Extract publisher name from certificate subject DN.
    
    Args:
        subject: Certificate subject (e.g., "CN=Microsoft Corporation, O=Microsoft, ...")
        
    Returns:
        Publisher name or None
    """
    if not subject or subject.lower() == 'none':
        return None
    
    # Parse subject components
    parts = [part.strip() for part in subject.split(',')]
    
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            if key.strip().upper() == 'CN':
                return value.strip()
    
    # Fallback: return first component
    if parts:
        return parts[0].split('=', 1)[1].strip() if '=' in parts[0] else parts[0].strip()
    
    return None


def is_microsoft_signed(publisher: Optional[str]) -> bool:
    """Check if publisher is Microsoft.
    
    Args:
        publisher: Publisher name from certificate
        
    Returns:
        True if Microsoft signature
    """
    if not publisher:
        return False
    
    microsoft_names = [
        'microsoft corporation',
        'microsoft',
        'microsoft windows',
        'microsoft code signing pca'
    ]
    
    publisher_lower = publisher.lower()
    return any(name in publisher_lower for name in microsoft_names)
