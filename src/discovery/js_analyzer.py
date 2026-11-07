"""
js_analyzer.py - Invocable extractor for JavaScript and TypeScript files.

Detects and extracts the following patterns without a full AST parser:

  JavaScript
  ----------
  • function declarations          function foo(a, b) { … }
  • const/let arrow functions      const foo = (a, b) => { … }
  • const/let regular functions    const foo = function(a, b) { … }
  • Object method shorthand        foo(a, b) { … }  inside a class or object
  • module.exports.foo = …         CommonJS named exports
  • exports.foo = …                CommonJS named exports

  TypeScript extras
  -----------------
  • export function foo(…): RetType { … }
  • export async function foo(…): Promise<T> { … }
  • public / private / protected methods
  • TypeScript type annotations on parameters and return type

  CLI detection heuristics
  ------------------------
  • Shebang: #!/usr/bin/env node
  • process.argv usage
  • commander / yargs / minimist / meow / oclif imports

Confidence assignment
---------------------
  guaranteed  exported TypeScript function with return type AND JSDoc
  high        exported function with return type OR JSDoc comment
  medium      plain named function
  low         inferred from object property / export assignment
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

# JSDoc block  /** … */  immediately before a declaration
_JSDOC_RE = re.compile(r'/\*\*(?P<content>.*?)\*/', re.DOTALL)
# First @description or plain text from JSDoc
_JSDOC_DESC_RE = re.compile(r'^\s*\*?\s*(?!@)(.+)', re.MULTILINE)
# @param {type} name - description
_JSDOC_PARAM_RE = re.compile(
    r'@param\s+'
    r'(?:\{(?P<type>(?:[^{}]|\{[^}]*\})*)\}\s*)?'  # optional {type} — handles one level of nesting
    r'\[?(?P<name>\w+)'                               # optional [ for JSDoc optional params like [name=default]
    r'(?:[^\s]*)?'                                     # consume rest of [name=default] or bare name
    r'(?:\s*-\s*(?P<desc>.+))?',                      # optional " - description"
)
# @returns / @return
_JSDOC_RETURNS_RE = re.compile(
    r'@returns?\s+(?:\{(?P<type>[^}]*)\})?(?:\s*-?\s*(?P<desc>.+))?',
)

# export keyword prefix (TS/ESM)
_EXPORT_PREFIX = r'export\s+(?:default\s+)?(?:async\s+)?'

# Named function declaration (JS + TS)
#   [export] [async] function name<T>(params): RetType
_FUNC_DECL_RE = re.compile(
    r'(?:' + _EXPORT_PREFIX + r')?(?:async\s+)?function\s*\*?\s*'
    r'(?P<name>\w+)\s*(?:<[^>]*>)?\s*\((?P<params>[^)]*)\)'
    r'(?:\s*:\s*(?P<rettype>[^\{;\n]+))?',
    re.MULTILINE,
)

# Arrow / function-expression assigned to const/let/var
#   [export] const name = [async] (params) => …
#   [export] const name = [async] function(params)
_ARROW_RE = re.compile(
    r'(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*'
    r'(?:async\s+)?(?:'
    r'\((?P<params>[^)]*)\)\s*(?::\s*(?P<rettype>[^\{=>\n]+))?\s*=>'
    r'|function\s*\((?P<fparams>[^)]*)\)'
    r')',
    re.MULTILINE,
)

# TypeScript class method:  [modifier] name(params): RetType {
_TS_METHOD_RE = re.compile(
    r'^\s*(?:public|private|protected|static|async|override|\s)+'
    r'(?P<name>\w+)\s*(?:<[^>]*>)?\s*\((?P<params>[^)]*)\)'
    r'(?:\s*:\s*(?P<rettype>[^\{;\n]+))?\s*\{',
    re.MULTILINE,
)

# CommonJS  module.exports.foo = …  or  exports.foo = …
_CJS_EXPORT_RE = re.compile(
    r'(?:module\.exports|exports)\.(?P<name>\w+)\s*=',
    re.MULTILINE,
)

# CLI detection patterns
_CLI_INDICATORS = [
    re.compile(r'process\.argv', re.IGNORECASE),
    re.compile(r"require\(['\"](?:commander|yargs|minimist|meow|oclif|caporal)['\"]"),
    re.compile(r"import\s+.*from\s+['\"](?:commander|yargs|minimist|meow|oclif)['\"]"),
]

# Shebang
_SHEBANG_RE = re.compile(r'^#!/usr/bin/env\s+node', re.MULTILINE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_js(path: Path) -> List[Invocable]:
    """Extract invocable functions / exports from a .js/.mjs/.cjs/.ts/.tsx file.

    Args:
        path: Path to the JavaScript or TypeScript file.

    Returns:
        List[Invocable] – one entry per discovered callable.
    """
    try:
        source = path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return []

    is_ts = path.suffix.lower() in ('.ts', '.tsx', '.mts')
    is_cli = _is_cli_script(source)

    invocables: List[Invocable] = []
    seen: set = set()

    # Build a list of (match_pos, invocable) from all patterns, then deduplicate
    candidates: List[tuple] = []

    # 1. Named function declarations
    for m in _FUNC_DECL_RE.finditer(source):
        name = m.group('name')
        raw_params = m.group('params') or ''
        rettype = (m.group('rettype') or '').strip()
        jsdoc = _find_jsdoc_before(source, m.start())
        inv = _make_invocable(
            name=name,
            raw_params=raw_params,
            rettype=rettype,
            jsdoc=jsdoc,
            source_type='js_function',
            path=path,
            is_exported='export' in source[max(0, m.start()-10):m.end()],
        )
        candidates.append((m.start(), inv))

    # 2. Arrow / function-expression const/let
    for m in _ARROW_RE.finditer(source):
        name = m.group('name')
        raw_params = m.group('params') or m.group('fparams') or ''
        rettype = (m.group('rettype') or '').strip()
        jsdoc = _find_jsdoc_before(source, m.start())
        inv = _make_invocable(
            name=name,
            raw_params=raw_params,
            rettype=rettype,
            jsdoc=jsdoc,
            source_type='js_arrow',
            path=path,
            is_exported='export' in source[max(0, m.start()-10):m.end()],
        )
        candidates.append((m.start(), inv))

    # 3. TypeScript class methods
    if is_ts:
        for m in _TS_METHOD_RE.finditer(source):
            name = m.group('name')
            if name in ('if', 'for', 'while', 'switch', 'catch'):
                continue
            raw_params = m.group('params') or ''
            rettype = (m.group('rettype') or '').strip()
            jsdoc = _find_jsdoc_before(source, m.start())
            inv = _make_invocable(
                name=name,
                raw_params=raw_params,
                rettype=rettype,
                jsdoc=jsdoc,
                source_type='ts_method',
                path=path,
                is_exported=False,
            )
            candidates.append((m.start(), inv))

    # 4. CommonJS module.exports
    for m in _CJS_EXPORT_RE.finditer(source):
        name = m.group('name')
        inv = Invocable(
            name=name,
            source_type='cjs_export',
            signature=f'{name}(…)',
            confidence='low',
            dll_path=str(path),
        )
        candidates.append((m.start(), inv))

    # Deduplicate by name (keep first appearance per name)
    for _, inv in sorted(candidates, key=lambda x: x[0]):
        if inv.name in seen:
            continue
        # Skip private / internal names
        if inv.name.startswith('_') or inv.name[0].islower() and len(inv.name) <= 1:
            continue
        seen.add(inv.name)
        invocables.append(inv)

    # If this is a CLI script, add a file-level invocable with CLI context
    if is_cli and invocables:
        invocables.insert(0, Invocable(
            name=path.stem,
            source_type='js_cli',
            signature=f'node {path.name} [options]',
            doc_comment='CLI entrypoint (uses process.argv or CLI framework)',
            confidence='high',
            dll_path=str(path),
        ))
    elif not invocables:
        # Fallback
        invocables.append(Invocable(
            name=path.stem,
            source_type='js_module',
            signature=f'{path.name}',
            doc_comment='JavaScript module (no exported functions detected)',
            confidence='low',
            dll_path=str(path),
        ))

    logger.info(
        "%s: %d invocables found in %s",
        'TypeScript' if is_ts else 'JavaScript',
        len(invocables),
        path.name,
    )
    return invocables


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_cli_script(source: str) -> bool:
    """Return True if the file shows CLI entry-point indicators."""
    if _SHEBANG_RE.match(source):
        return True
    return any(pat.search(source) for pat in _CLI_INDICATORS)


def _find_jsdoc_before(source: str, pos: int) -> Optional[str]:
    """Return the body of the JSDoc block (/** … */) immediately before pos."""
    window = source[max(0, pos - 600):pos]
    # Find the last /** … */ block in the window
    matches = list(_JSDOC_RE.finditer(window))
    if not matches:
        return None
    last = matches[-1]
    # Must end close to the declaration (within ~5 lines)
    tail = window[last.end():]
    if '\n' in tail and tail.count('\n') > 3:
        return None  # Too far away
    return last.group('content')


def _parse_jsdoc(jsdoc_body: Optional[str]) -> tuple:
    """Return (description: str, params: dict[name, desc], returns: str)."""
    if not jsdoc_body:
        return '', {}, ''

    desc_lines = []
    params: dict = {}
    returns = ''

    for line in jsdoc_body.splitlines():
        stripped = re.sub(r'^\s*\*\s?', '', line).strip()
        if not stripped:
            continue
        pm = _JSDOC_PARAM_RE.search(stripped)
        if pm:
            params[pm.group('name')] = {
                'type': (pm.group('type') or '').strip(),
                'desc': (pm.group('desc') or '').strip(),
            }
            continue
        rm = _JSDOC_RETURNS_RE.search(stripped)
        if rm:
            ret_type = rm.group('type') or ''
            ret_desc = rm.group('desc') or ''
            returns = f"{ret_type} {ret_desc}".strip()
            continue
        if not stripped.startswith('@'):
            desc_lines.append(stripped)

    return ' '.join(desc_lines[:2]).strip(), params, returns


def _make_invocable(
    name: str,
    raw_params: str,
    rettype: str,
    jsdoc: Optional[str],
    source_type: str,
    path: Path,
    is_exported: bool,
) -> Invocable:
    """Build an Invocable from extracted JS/TS data."""
    desc, param_docs, jsdoc_returns = _parse_jsdoc(jsdoc)

    # Build param list: preserve TS "name: type" annotations as-is;
    # for plain JS names use JSDoc type (or "any") so _parse_single_parameter
    # sees the colon format and keeps the real name instead of emitting arg0/1.
    param_parts: List[str] = []
    for raw_p in raw_params.split(','):
        p = raw_p.strip()
        if not p:
            continue
        if ':' in p:
            # TypeScript already annotated (e.g. "name: string = 'x'") — keep verbatim
            param_parts.append(p)
        else:
            # JS plain param — strip any default value to isolate the name
            bare_name = p.split('=')[0].strip()
            if bare_name in param_docs:
                jsdoc_type = param_docs[bare_name].get('type', '') if isinstance(param_docs[bare_name], dict) else ''
                param_parts.append(f"{bare_name}: {jsdoc_type or 'any'}")
            else:
                # No JSDoc for this param — emit "name: any" to preserve name in schema
                param_parts.append(f"{bare_name}: any")
    params = ', '.join(param_parts)

    # Return type: prefer explicit TS annotation, fall back to JSDoc
    effective_return = rettype or jsdoc_returns or None

    sig = f"{name}({raw_params.strip()})"
    if effective_return:
        sig += f': {effective_return}'

    # Confidence
    has_doc = bool(desc)
    has_ret = bool(effective_return)
    has_params = bool(params)

    if is_exported and has_doc and has_ret:
        confidence = 'guaranteed'
    elif (is_exported and (has_doc or has_ret)) or (has_doc and has_ret):
        confidence = 'high'
    elif has_doc or has_params:
        confidence = 'medium'
    else:
        confidence = 'low'

    return Invocable(
        name=name,
        source_type=source_type,
        signature=sig,
        parameters=params or None,
        return_type=effective_return,
        doc_comment=desc or None,
        confidence=confidence,
        dll_path=str(path),
    )
