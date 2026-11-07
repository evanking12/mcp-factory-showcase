"""
sql_analyzer.py - Invocable extractor for SQL source files.

Extracts the following database objects as invocables:
  • Stored procedures      (CREATE [OR REPLACE] PROCEDURE …)
  • Scalar/table functions (CREATE [OR REPLACE] FUNCTION …)
  • Views                  (CREATE [OR REPLACE] VIEW …)
  • Tables                 (CREATE TABLE …)  — low confidence
  • Triggers               (CREATE TRIGGER …) — metadata only

Handles T-SQL (SQL Server), PL/pgSQL (Postgres), and generic ANSI SQL
syntax well enough for broad invocable discovery without a full parser.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from schema import Invocable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# CREATE [OR REPLACE] [DEFINER=…] PROCEDURE|FUNCTION|VIEW|TABLE|TRIGGER name
_DDL_RE = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:DEFINER\s*=\s*\S+\s+)?'
    r'(?P<kind>PROCEDURE|FUNCTION|VIEW|TABLE|TRIGGER)\s+(?:`?(?P<name>\w+)`?)',
    re.IGNORECASE,
)

# Locate the FIRST opening paren — content is extracted with a depth counter in Python
_OPEN_PAREN_RE = re.compile(r'\(')

# T-SQL style: @param_name TYPE [= default] lines before AS/BEGIN (no parens)
_TSQL_PARAM_LINE_RE = re.compile(
    r'@(?P<name>\w+)\s+(?P<type>[\w\(\)]+(?:\([^)]*\))?)'  # @name type(size)
    r'(?:\s*=\s*(?P<default>[^,\n@]+))?',
    re.MULTILINE,
)

# Type in a parameter: word that appears after the name (handles DECIMAL(10,2), VARCHAR(50), etc.)
_PARAM_ENTRY_RE = re.compile(
    r'(?:(?:IN|OUT|INOUT)\s+)?'
    r'@?(?P<name>\w+)\s+(?P<type>\w+(?:\([^)]*\))?)',  # type optionally followed by (args)
    re.IGNORECASE,
)

# Comment patterns
_LINE_COMMENT_RE = re.compile(r'--\s*(.+)')          # -- comment
_BLOCK_COMMENT_RE = re.compile(r'/\*(.+?)\*/', re.DOTALL)

# RETURNS clause for functions
_RETURNS_RE = re.compile(r'\bRETURNS\s+(TABLE|[\w\(\)]+)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_sql(path: Path) -> List[Invocable]:
    """Extract database objects from a .sql file.

    Args:
        path: Path to the .sql source file.

    Returns:
        List[Invocable] – one entry per discovered object.
    """
    try:
        source = path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return []

    invocables: List[Invocable] = []
    # Normalise line endings
    source = source.replace('\r\n', '\n').replace('\r', '\n')

    for m in _DDL_RE.finditer(source):
        kind = m.group('kind').upper()           # PROCEDURE | FUNCTION | VIEW | TABLE | TRIGGER
        name = m.group('name')
        obj_start = m.start()

        # --- documentation: look for block or line comments before the DDL ---
        preamble = source[max(0, obj_start - 400):obj_start]
        doc = _extract_doc_comment(preamble)

        # --- parameters (PROCEDURE / FUNCTION only) ---
        params_str = ''
        return_type: Optional[str] = None
        if kind in ('PROCEDURE', 'FUNCTION'):
            # Constrain lookahead to the current DDL body only (stop before next CREATE)
            next_ddl = source.find('CREATE', m.end())
            window_end = next_ddl if next_ddl != -1 else m.end() + 3000
            after_name = source[m.end():window_end]

            # Locate AS/BEGIN boundary (marks end of param declaration area)
            as_pos = re.search(r'\bAS\b|\bBEGIN\b|\bLANGUAGE\b', after_name, re.IGNORECASE)
            # Find the first '(' in the text
            first_paren = _OPEN_PAREN_RE.search(after_name)
            # Find first '@param' — its presence before '(' signals T-SQL bare style
            first_at_match = re.search(r'@\w', after_name)
            first_at_pos = first_at_match.start() if first_at_match else float('inf')

            # Only treat a paren block as the parameter list when the '(' appears
            # BEFORE any AS/BEGIN keyword AND before any '@param' token.
            # If '@' comes first, the paren belongs to a type like VARCHAR(255), not the param list.
            paren_is_param_block = (
                first_paren is not None
                and first_paren.start() < first_at_pos          # '(' before any '@param'
                and (as_pos is None or first_paren.start() < as_pos.start())
            )

            if paren_is_param_block:
                # ANSI SQL / PL/pgSQL / T-SQL function style: (param TYPE, ...)
                pb_content = _extract_balanced_parens(after_name)
                if pb_content is not None:
                    params_str = _parse_sql_params(pb_content)
            else:
                # T-SQL stored procedure style: @param TYPE before AS/BEGIN
                tsql_window = after_name[:as_pos.start()] if as_pos else after_name[:500]
                tsql_params = _TSQL_PARAM_LINE_RE.findall(tsql_window)
                if tsql_params:
                    parts = []
                    for name_p, type_p, default_p in tsql_params:
                        entry = f'@{name_p} {type_p}'
                        if default_p.strip():
                            entry += f' = {default_p.strip()}'
                        parts.append(entry)
                    params_str = ', '.join(parts)

            # RETURNS clause
            ret_m = _RETURNS_RE.search(after_name[:500])
            if ret_m:
                return_type = ret_m.group(1).strip()

        # --- confidence ---
        if kind in ('PROCEDURE', 'FUNCTION'):
            confidence = 'guaranteed' if (params_str or return_type) and doc else \
                         'high' if doc or params_str or return_type else 'medium'
        elif kind == 'VIEW':
            confidence = 'high' if doc else 'medium'
        else:
            confidence = 'medium' if doc else 'low'

        # --- signature ---
        if kind == 'PROCEDURE':
            sig = f"EXEC {name}({params_str})"
        elif kind == 'FUNCTION':
            retpart = f' RETURNS {return_type}' if return_type else ''
            sig = f"SELECT {name}({params_str}){retpart}"
        elif kind == 'VIEW':
            sig = f"SELECT * FROM {name}"
        elif kind == 'TABLE':
            sig = f"SELECT * FROM {name} / INSERT INTO {name} …"
        else:  # TRIGGER
            sig = f"-- TRIGGER: {name}"

        invocables.append(Invocable(
            name=name,
            source_type='sql_' + kind.lower(),
            signature=sig,
            parameters=params_str or None,
            return_type=return_type,
            doc_comment=doc,
            confidence=confidence,
            dll_path=str(path),
        ))

    logger.info("SQL: %d objects found in %s", len(invocables), path.name)
    return invocables


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_balanced_parens(text: str) -> Optional[str]:
    """Return the content of the FIRST balanced paren pair in text, or None."""
    start = _OPEN_PAREN_RE.search(text)
    if start is None:
        return None
    depth = 0
    result: list = []
    for i, ch in enumerate(text[start.start():]):
        if ch == '(':
            depth += 1
            if depth > 1:
                result.append(ch)
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return ''.join(result)
            else:
                result.append(ch)
        else:
            if depth > 0:
                result.append(ch)
    return None


def _parse_sql_params(raw: str) -> str:
    """Parse a raw parameter list string into a clean 'name TYPE' representation."""
    if not raw.strip():
        return ''
    parts = []
    # Split on commas that are not inside parentheses
    depth = 0
    current: List[str] = []
    for ch in raw:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())

    cleaned = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        em = _PARAM_ENTRY_RE.match(part)
        if em:
            # Always emit @name TYPE — the '@' sentinel lets _parse_single_parameter
            # in schema.py correctly identify the first token as the name rather than
            # treating it as a C-style 'type name' pair.
            cleaned.append(f"@{em.group('name')} {em.group('type')}")
        else:
            # Just keep whatever text is there, stripped of extra whitespace
            cleaned.append(re.sub(r'\s+', ' ', part))
    return ', '.join(cleaned)


def _extract_doc_comment(preamble: str) -> Optional[str]:
    """Extract the most recent comment block or line comment from preamble text."""
    # Block comment: /* … */
    blocks = _BLOCK_COMMENT_RE.findall(preamble)
    if blocks:
        # Take the last block comment, strip leading * per line (Javadoc style)
        block = blocks[-1]
        lines = [re.sub(r'^\s*\*\s?', '', l).strip() for l in block.splitlines()]
        text = ' '.join(l for l in lines if l)
        if text and not _is_separator_comment(text):
            return text[:300]

    # Line comments: -- …
    line_comments = _LINE_COMMENT_RE.findall(preamble)
    if line_comments:
        # Filter out visual separator lines (box-drawing chars, dashes-only, etc.)
        meaningful = [c.strip() for c in line_comments if not _is_separator_comment(c)]
        if meaningful:
            # Take last 3 consecutive meaningful line comments
            text = ' '.join(meaningful[-3:])
            if text:
                return text[:300]

    return None


def _is_separator_comment(text: str) -> bool:
    """Return True if the comment text is a visual separator (box-drawing chars, dashes, etc.)."""
    # Detect Unicode box-drawing characters (U+2500–U+257F)
    box_chars = sum(1 for c in text if '\u2500' <= c <= '\u257F')
    if box_chars > 3:
        return True
    # Detect ASCII separator lines: 4+ consecutive hyphens or equals
    if re.search(r'[-=]{4,}', text):
        stripped = re.sub(r'[-=\s]', '', text)
        if len(stripped) == 0 or len(stripped) / max(len(text), 1) < 0.35:
            return True
    return False
