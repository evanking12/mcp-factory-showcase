"""
Utility functions for discovery pipeline: logging, spinner, formatting.
"""

import sys
import time
from typing import Optional


class Spinner:
    """Simple console spinner for long-running operations."""
    
    enabled = False  # Class variable, set by caller
    
    def __init__(self, message: str = ""):
        self.message = message
        self.frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.frame_idx = 0
    
    def start(self):
        """Print initial message."""
        if not Spinner.enabled:
            return
        print(f"[*] {self.message}...", end='', flush=True)
    
    def tick(self):
        """Update spinner frame."""
        if not Spinner.enabled:
            return
        sys.stdout.write(f"\r[*] {self.message}... {self.frames[self.frame_idx % len(self.frames)]}")
        sys.stdout.flush()
        self.frame_idx += 1
        time.sleep(0.05)  # Update every 50ms
    
    def done(self, result: str = "✓"):
        """Complete spinner with final message."""
        if not Spinner.enabled:
            return
        print(f"\r[*] {self.message}... {result}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.done("✗")
        else:
            self.done("✓")


def format_verbose_header(stage: str, details: str = ""):
    """Format a verbose pipeline stage header."""
    header = f"[*] {stage}"
    if details:
        header += f": {details}"
    return header


def format_verbose_result(message: str, success: bool = True):
    """Format a verbose result line with checkmark or X."""
    marker = "✓" if success else "✗"
    return f"    {marker} {message}"


def print_confidence_factors(factors: dict, total_exports: int):
    """Pretty-print confidence factor breakdown."""
    print("\nCONFIDENCE FACTORS (by frequency)")
    print("-" * 60)
    for factor, count in sorted(factors.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_exports * 100) if total_exports > 0 else 0
        print(f"  • {factor:40s} {count:4d} ({percentage:5.1f}%)")
