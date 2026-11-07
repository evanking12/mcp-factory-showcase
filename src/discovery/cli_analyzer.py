"""
cli_analyzer.py - CLI tool capability analyzer.

Analyzes executable files for CLI capabilities by:
1. Running with help flags (/? --help -h)
2. Parsing output for usage syntax and arguments
3. Generating Invocable records for CLI usage
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

# Suppress any GUI window when launching EXEs for --help scraping (Windows only).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

from schema import Invocable

logger = logging.getLogger(__name__)

# Common help flags to try
HELP_FLAGS = ['/?', '--help', '-h', 'help']

def analyze_cli(exe_path: Path, timeout: int = 5) -> List[Invocable]:
    """Analyze an executable for CLI capabilities.
    
    Args:
        exe_path: Path to executable
        timeout: Execution timeout in seconds (to prevent hanging on GUI apps)
        
    Returns:
        List of Invocable records representing CLI capabilities
    """
    invocables = []
    
    # Try to get help output
    help_text = _get_help_output(exe_path, timeout)
    
    if not help_text:
        # If no help text (maybe GUI app or no output), still record existence
        inv = Invocable(
            name=exe_path.stem,
            source_type='cli',
            signature=f"{exe_path.name} [arguments]",
            confidence="low",
            dll_path=str(exe_path),
            doc_comment="Executable file (no help output detected)"
        )
        invocables.append(inv)
        return invocables

    # Parse help text
    usage_syntax = _extract_usage(help_text, exe_path.name)
    arguments = _extract_arguments(help_text)
    
    # Create main invocable for the tool
    main_inv = Invocable(
        name=exe_path.stem,
        source_type='cli',
        signature=usage_syntax or f"{exe_path.name} [options]",
        parameters=arguments, # Storing structured args here or as separate invocables? 
                             # Schema puts parameters as string.
                             # Let's put the full help text in docs.
        doc_comment=_summarize_help(help_text),
        confidence="high",
        dll_path=str(exe_path)
    )
    invocables.append(main_inv)
    
    return invocables

def _get_help_output(exe_path: Path, timeout: int) -> Optional[str]:
    """Run executable with help flags and return output."""
    
    for flag in HELP_FLAGS:
        try:
            # Run command
            # Note: We capture both stdout and stderr
            # We use a timeout to avoid hanging on GUI apps (like notepad)
            result = subprocess.run(
                [str(exe_path), flag],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=_NO_WINDOW,
            )
            
            output = result.stdout + "\n" + result.stderr
            if output.strip():
                return output.strip()
                
        except subprocess.TimeoutExpired:
            logger.debug(f"Timeout running {exe_path.name} {flag}")
            continue
        except Exception as e:
            logger.debug(f"Error running {exe_path.name} {flag}: {e}")
            continue
            
    return None

def _extract_usage(text: str, exe_name: str) -> Optional[str]:
    """Extract usage line from help text."""
    # Look for "Usage:" or "syntax:"
    lines = text.splitlines()
    for line in lines:
        if re.search(r'^\s*(usage|syntax):', line, re.IGNORECASE):
            return line.strip()
            
    # Look for line starting with exe name
    for line in lines:
        if line.strip().startswith(exe_name):
            return line.strip()
            
    return None

def _extract_arguments(text: str) -> str:
    """Extract argument list from help text as a string."""
    args = []
    lines = text.splitlines()
    
    # Regex for flags like -f, --file, /?
    arg_pattern = re.compile(r'^\s{1,8}(-{1,2}[\w-]+|/[\w?]+)\s+(.*)')
    
    for line in lines:
        match = arg_pattern.match(line)
        if match:
            flag = match.group(1)
            desc = match.group(2).strip()
            args.append(f"{flag}: {desc}")
            
    return "; ".join(args)

def _summarize_help(text: str) -> str:
    """Get first few lines or description from help text."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return ""
        
    # Skip "Usage:" lines to find description
    for line in lines:
        if not re.match(r'^(usage|syntax):', line, re.IGNORECASE) and not line.startswith('-'):
            return line
            
    return lines[0]
