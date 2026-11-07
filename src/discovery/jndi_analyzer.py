"""
jndi_analyzer.py — Invocable extractor for JNDI (Java Naming and Directory
                    Interface) configuration files.

Supported input formats:
  • Java .properties files  — key=value pairs (java.naming.*, binding.*, etc.)
  • Spring XML context files — <jee:jndi-lookup>, <bean> with JNDI factory
  • Generic .jndi files     — treated as a .properties file

Each discoverable binding becomes an Invocable with source_type='jndi_lookup'.
The invocables represent things an application can look up and invoke via JNDI,
including JDBC DataSources, JMS queues/topics, EJBs, RMI services, and
LDAP-bound objects.

No third-party dependencies beyond the standard library (+ lxml if present
for XML context file support).
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from lxml import etree as ET
    _LXML_OK = True
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore
    _LXML_OK = False

from schema import Invocable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Known JNDI binding type classifiers
# ---------------------------------------------------------------------------

_BINDING_CLASSIFIERS: List[Tuple[re.Pattern, str, str]] = [
    # (pattern on JNDI name or class, source_type hint, return_type label)
    (re.compile(r'\bjdbc/', re.I),       "jndi_datasource",  "javax.sql.DataSource"),
    (re.compile(r'\bjms/',  re.I),       "jndi_jms",         "javax.jms.Destination"),
    (re.compile(r'\bjava:comp/env/', re.I), "jndi_env_entry", "java.lang.Object"),
    (re.compile(r'^rmi://',  re.I),      "jndi_rmi",         "java.rmi.Remote"),
    (re.compile(r'^ldap://', re.I),      "jndi_ldap",        "javax.naming.directory.DirContext"),
    (re.compile(r'^iiop://', re.I),      "jndi_corba",       "org.omg.CORBA.Object"),
    (re.compile(r'\bmail/', re.I),       "jndi_mail",        "javax.mail.Session"),
    (re.compile(r'\bejb/', re.I),        "jndi_ejb",         "javax.ejb.EJBObject"),
    (re.compile(r'\benv/', re.I),        "jndi_env_entry",   "java.lang.String"),
]

_DEFAULT_SOURCE_TYPE = "jndi_lookup"
_DEFAULT_RETURN_TYPE = "java.lang.Object"


def _classify_binding(jndi_name: str, class_name: str = "") -> Tuple[str, str]:
    """Return (source_type, return_type) for a JNDI binding."""
    for pattern, stype, rtype in _BINDING_CLASSIFIERS:
        if pattern.search(jndi_name) or (class_name and pattern.search(class_name)):
            return stype, rtype
    return _DEFAULT_SOURCE_TYPE, _DEFAULT_RETURN_TYPE


def _confidence(has_doc: bool, has_class: bool, has_url: bool) -> str:
    if has_class and has_url:
        return "high"
    if has_class or has_url:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# .properties / .jndi parser
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'^\s*[#!]')
_KV_RE      = re.compile(r'^(?P<key>[^=:\s][^=:]*?)\s*[=:]\s*(?P<value>.*)$')

# java.naming.* keys we care about
_NAMING_KEYS = {
    "java.naming.factory.initial":    "InitialContextFactory",
    "java.naming.provider.url":       "ProviderURL",
    "java.naming.security.principal": "SecurityPrincipal",
    "java.naming.security.credentials": "SecurityCredentials",
}


def _parse_properties(text: str) -> Dict[str, str]:
    """Parse a Java .properties file into a {key: value} dict.
    Handles line continuations (trailing backslash).
    """
    props: Dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Continuation
        while line.endswith('\\') and i + 1 < len(lines):
            line = line[:-1] + lines[i + 1].lstrip()
            i += 1
        i += 1
        if _COMMENT_RE.match(line) or not line.strip():
            continue
        m = _KV_RE.match(line.strip())
        if m:
            props[m.group("key").strip()] = m.group("value").strip()
    return props


def _invocables_from_properties(props: Dict[str, str], path: Path) -> List[Invocable]:
    """Convert a parsed properties dict into JNDI invocables."""
    invocables: List[Invocable] = []

    # Collect provider URL for context
    provider_url = props.get("java.naming.provider.url", "")

    # Find explicit binding.* or jndi.bind.* style entries
    seen: set = set()
    for key, value in props.items():
        # Binding entries: binding.Name=jndi/path OR jndi.Name=jndi/path
        if re.match(r'^(binding|jndi\.bind)\.',  key, re.I):
            logical_name = re.sub(r'^(binding|jndi\.bind)\.', '', key, flags=re.I)
            jndi_name = value
        elif key.startswith("java.naming.") or key in ("InitialContextFactory",):
            continue
        elif "/" in value and not key.startswith("java."):
            # Heuristic: value looks like a JNDI path
            logical_name = key.split(".")[-1]
            jndi_name = value
        else:
            continue

        if jndi_name in seen:
            continue
        seen.add(jndi_name)

        source_type, ret_type = _classify_binding(jndi_name)
        description = f"JNDI lookup: {jndi_name}"
        if provider_url:
            description += f" (via {provider_url})"

        params_str = f"name: string (jndi_name={jndi_name!r})"
        sig = f"lookup({jndi_name!r}): {ret_type}"

        invocables.append(Invocable(
            name=logical_name,
            source_type=source_type,
            signature=sig,
            parameters=params_str,
            return_type=ret_type,
            doc_comment=description,
            confidence=_confidence(True, source_type != _DEFAULT_SOURCE_TYPE, bool(provider_url)),
            dll_path=str(path),
        ))

    # If no bindings found but we have a provider URL, emit a discovery invocable
    if not invocables and provider_url:
        source_type, ret_type = _classify_binding(provider_url)
        invocables.append(Invocable(
            name="InitialContext",
            source_type=source_type,
            signature=f"new InitialContext(provider_url={provider_url!r})",
            parameters=f"provider_url: string",
            return_type="javax.naming.Context",
            doc_comment=f"Create JNDI InitialContext connecting to {provider_url}",
            confidence="medium",
            dll_path=str(path),
        ))

    return invocables


# ---------------------------------------------------------------------------
# Spring XML context parser
# ---------------------------------------------------------------------------

_SPRING_NS   = "http://www.springframework.org/schema/beans"
_JEE_NS      = "http://www.springframework.org/schema/jee"

def _parse_spring_xml(text: str, path: Path) -> List[Invocable]:
    """Extract JNDI lookups from a Spring XML application context."""
    try:
        if _LXML_OK:
            root = ET.fromstring(text.encode("utf-8"))
        else:
            root = ET.fromstring(text)
    except Exception as exc:
        logger.debug("XML parse error in %s: %s", path.name, exc)
        return []

    invocables: List[Invocable] = []

    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    for elem in root.iter():
        ltag = _local(elem.tag)

        # <jee:jndi-lookup id="..." jndi-name="..." expected-type="..."/>
        if ltag == "jndi-lookup":
            bean_id    = elem.get("id") or elem.get("name") or "jndi_lookup"
            jndi_name  = elem.get("jndi-name") or elem.get("jndiName") or ""
            class_name = elem.get("expected-type") or elem.get("expectedType") or ""
            desc       = f"JNDI lookup for bean '{bean_id}': {jndi_name}"
            if not jndi_name:
                continue
            source_type, ret_type = _classify_binding(jndi_name, class_name)
            invocables.append(Invocable(
                name=bean_id,
                source_type=source_type,
                signature=f"lookup({jndi_name!r}): {class_name or ret_type}",
                parameters=f"jndi_name: string",
                return_type=class_name or ret_type,
                doc_comment=desc,
                confidence="high" if class_name else "medium",
                dll_path=str(path),
            ))

        # <bean class="org.springframework.jndi.JndiObjectFactoryBean">
        elif ltag == "bean":
            class_name = elem.get("class") or ""
            if "JndiObjectFactoryBean" not in class_name and "JndiTemplate" not in class_name:
                continue
            bean_id = elem.get("id") or elem.get("name") or "jndi_bean"
            jndi_name = ""
            for prop in elem:
                if _local(prop.tag) == "property":
                    prop_name = prop.get("name", "")
                    if prop_name in ("jndiName", "jndi-name"):
                        jndi_name = prop.get("value") or (
                            prop[0].text if len(prop) else ""
                        ) or ""
            if not jndi_name:
                continue
            source_type, ret_type = _classify_binding(jndi_name, class_name)
            invocables.append(Invocable(
                name=bean_id,
                source_type=source_type,
                signature=f"lookup({jndi_name!r}): {ret_type}",
                parameters="jndi_name: string",
                return_type=ret_type,
                doc_comment=f"Spring JNDI factory bean: {jndi_name}",
                confidence="high",
                dll_path=str(path),
            ))

    return invocables


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_jndi(path: Path) -> List[Invocable]:
    """Extract JNDI service bindings from a .jndi / .properties / Spring XML file.

    Args:
        path: Path to the JNDI config file.

    Returns:
        List[Invocable] — one entry per discovered JNDI binding / lookup target.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return []

    ext = path.suffix.lower()

    # Try XML first (Spring context files, even if named .properties)
    if ext in (".xml",) or text.lstrip().startswith("<"):
        result = _parse_spring_xml(text, path)
        if result:
            logger.info("JNDI (XML): extracted %d bindings from %s", len(result), path.name)
            return result

    # Fall back to .properties / .jndi format
    props = _parse_properties(text)
    result = _invocables_from_properties(props, path)
    logger.info("JNDI (properties): extracted %d bindings from %s", len(result), path.name)
    return result
