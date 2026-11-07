"""
headers_scan.py - Header file scanning and prototype extraction.

Searches header files for function prototypes matching exports,
extracting signatures and documentation comments.
"""

import re
from bisect import bisect_right
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from schema import ExportedFunc, MatchInfo


def iter_header_files(root: Path) -> List[Path]:
    """Find all header files in the given directory tree."""
    exts = {".h", ".hpp", ".hh", ".hxx", ".inl"}
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    return files


def make_proto_regex(func_name: str) -> re.Pattern:
    """Create regex to find function prototype in header files."""
    escaped = re.escape(func_name)
    return re.compile(rf"(^|[^A-Za-z0-9_]){escaped}\s*\(", re.MULTILINE)


def build_comment_spans(text: str) -> Tuple[List[Tuple[int, int]], List[int]]:
    """Build a list of (start, end) character indices for all comments in the text."""
    spans: List[Tuple[int, int]] = []
    i = 0
    n = len(text)

    while i < n:
        # Single-line comment
        if text.startswith("//", i):
            start = i
            i = text.find("\n", i)
            if i == -1:
                spans.append((start, n))
                break
            spans.append((start, i))
            continue

        # Multi-line comment
        if text.startswith("/*", i):
            start = i
            end = text.find("*/", i + 2)
            if end == -1:
                spans.append((start, n))
                break
            spans.append((start, end + 2))
            i = end + 2
            continue

        i += 1

    starts = [s for s, _ in spans]
    return spans, starts


def in_comment_spans(idx: int, spans: List[Tuple[int, int]], starts: List[int]) -> bool:
    """Check if the given index is inside a comment span."""
    if not spans:
        return False
    pos = bisect_right(starts, idx) - 1
    if pos < 0:
        return False
    s, e = spans[pos]
    return s <= idx < e


def extract_doc_comment_above(text: str, start_index: int) -> str:
    """Extract documentation comment appearing immediately before the given index.
    
    Robustly handles blank lines between comment definition and function.
    """
    # Look at text before the function
    before = text[:start_index]
    lines = before.splitlines()
    if not lines:
        return ""
    
    # 1. Look backwards for the first non-empty line
    i = len(lines) - 1
    blank_limit = 5 # Allow up to N blank lines
    blanks_seen = 0
    
    while i >= 0:
        if lines[i].strip():
            break # Found content
        blanks_seen += 1
        i -= 1
        
    if i < 0 or blanks_seen > blank_limit:
        return "" # No comment found within range

    line = lines[i].lstrip()

    # 2. Check for Single-line Doxygen (/// or //!)
    if line.startswith("///") or line.startswith("//!"):
        block = []
        while i >= 0:
            l = lines[i].lstrip()
            if l.startswith("///") or l.startswith("//!"):
                block.append(l[3:].lstrip())
                i -= 1
            else:
                break
        block.reverse()
        return "\n".join(block).strip()

    # 3. Check for Multi-line Doxygen (ends with */)
    if lines[i].strip().endswith("*/"):
        block_lines = []
        
        # Scan backwards to find /* or /**
        while i >= 0:
            block_lines.append(lines[i])
            if "/*" in lines[i]:
                break
            i -= 1
            
        if i < 0: return "" # Never found start
        
        block_lines.reverse()
        
        # Check if it starts with Doxygen marker
        opening = block_lines[0].lstrip()
        if not (opening.startswith("/**") or opening.startswith("/*!")):
            # Standard C comment, but maybe we treat it as doc?
            # For now, stick to Doxygen
            return ""
            
        block_text = "\n".join(block_lines)
        
        # Clean up the Doxygen block
        # Remove opening /**
        block_text = re.sub(r"^\s*/\*\*?\s?", "", block_text.lstrip())
        # Remove closing */
        block_text = re.sub(r"\s?\*/\s*$", "", block_text.rstrip())
        
        # Remove leading * on each line
        cleaned = []
        for l in block_text.splitlines():
            l = re.sub(r"^\s*\*\s?", "", l)
            cleaned.append(l.rstrip())
            
        return "\n".join(cleaned).strip()

    return ""


def extract_inline_comment(line_text: str) -> str:
    """Extract inline comment from a line of code."""
    idx = line_text.find("//")
    if idx != -1:
        return line_text[idx + 2:].strip()
    idx = line_text.find("/*")
    if idx != -1:
        end = line_text.find("*/", idx + 2)
        if end != -1:
            return line_text[idx + 2:end].strip()
    return ""


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def clean_return_type(text: str) -> str:
    """Clean up return type by removing storage class specifiers and calling conventions."""
    if not text:
        return ""
    text = re.sub(r"__declspec\s*\([^)]*\)", "", text)
    text = re.sub(r"__attribute__\s*\(\([^)]*\)\)", "", text)
    text = re.sub(
        r"\b(?:extern|static|inline|constexpr|consteval|constinit|friend)\b", "", text
    )
    text = re.sub(
        r"\b(?:__cdecl|__stdcall|__fastcall|__vectorcall|__thiscall)\b", "", text
    )
    text = re.sub(r"\b[A-Z][A-Z0-9_]*_(?:API|EXPORT|IMPORT|STATIC_API)\b", "", text)
    text = normalize_whitespace(text)
    return text


def find_prototype_in_header(file_path: Path, export_name: str) -> Optional[MatchInfo]:
    """Find function prototype in a header file."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    rx = make_proto_regex(export_name)
    comment_spans, comment_starts = build_comment_spans(text)

    for m in rx.finditer(text):
        name_index = m.start(0)
        if in_comment_spans(name_index, comment_spans, comment_starts):
            continue

        line_start = text.rfind("\n", 0, name_index) + 1
        line_no = text.count("\n", 0, line_start) + 1

        # Skip preprocessor directives
        line_prefix = text[line_start:name_index].lstrip()
        if line_prefix.startswith("#"):
            continue

        # Find end of declaration (semicolon or opening brace)
        end_idx = None
        depth = 0
        i = line_start
        n = len(text)
        while i < n:
            if in_comment_spans(i, comment_spans, comment_starts):
                i += 1
                continue
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch in (";", "{") and depth == 0:
                end_idx = i
                break
            i += 1

        if end_idx is None:
            continue

        proto = text[line_start:end_idx].strip()
        if f"{export_name}(" not in proto and f"{export_name} (" not in proto:
            continue

        # Extract inline comment
        line_end = text.find("\n", end_idx)
        if line_end == -1:
            line_end = len(text)
        inline_comment = extract_inline_comment(text[end_idx:line_end])
        doc = inline_comment or extract_doc_comment_above(text, line_start)

        # Parse prototype
        proto_one = normalize_whitespace(proto)
        idx = proto_one.find(export_name)
        if idx <= 0:
            continue
        before_name = proto_one[:idx].strip()
        after_name = proto_one[idx + len(export_name) :].lstrip()

        # Extract parameters
        if not after_name.startswith("("):
            params = ""
        else:
            depth = 0
            params_chars = []
            for ch in after_name:
                if ch == "(":
                    depth += 1
                    if depth == 1:
                        continue
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                if depth >= 1:
                    params_chars.append(ch)
            params = normalize_whitespace("".join(params_chars))

        return_type = clean_return_type(before_name)

        return MatchInfo(
            function=export_name,
            return_type=return_type,
            parameters=params,
            doc_comment=doc.strip(),
            header_file=str(file_path),
            line=line_no,
            prototype=proto_one,
        )

    return None


def scan_headers(
    headers_root: Path, exports: List[ExportedFunc]
) -> Dict[str, MatchInfo]:
    """Scan header files for function prototypes matching exports.
    
    Args:
        headers_root: Root directory to search for headers
        exports: List of exported functions to find prototypes for
        
    Returns:
        Dict mapping export name to MatchInfo (or empty if no match found)
    """
    matches: Dict[str, MatchInfo] = {}
    header_files = iter_header_files(headers_root)

    for exp in exports:
        if exp.name in matches:
            continue

        for hdr in header_files:
            mi = find_prototype_in_header(hdr, exp.name)
            if mi:
                matches[exp.name] = mi
                break

    return matches


def scan_docs_for_exports(
    docs_root: Path, exports: List[ExportedFunc], max_hits: int = 2
) -> Dict[str, List[str]]:
    """Scan documentation directory for mentions of exported functions.
    
    Searches documentation files for mentions of exported functions
    and links them back to the exports.
    
    Args:
        docs_root: Root directory to search for documentation
        exports: List of exported functions to search for
        max_hits: Maximum number of documentation files to link per export
        
    Returns:
        Dict mapping export name to list of documentation file paths
    """
    results: Dict[str, List[str]] = {}

    doc_extensions = {".md", ".txt", ".rst", ".adoc", ".htm", ".html"}
    doc_files = [
        p
        for p in docs_root.rglob("*")
        if p.is_file() and p.suffix.lower() in doc_extensions
    ]

    for exp in exports:
        hits = []

        for doc_file in doc_files:
            if len(hits) >= max_hits:
                break

            try:
                content = doc_file.read_text(encoding="utf-8", errors="ignore")
                if exp.name in content:
                    hits.append(str(doc_file.relative_to(docs_root)))
            except Exception:
                continue

        if hits:
            results[exp.name] = hits

    return results
