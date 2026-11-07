"""api.pipeline.core.ghidra_provenance — Provenance and confidence tagging for Ghidra-derived facts.

Every Ghidra output is evidence, not ground truth.  This module provides
structured provenance so downstream consumers (ECR, DAG builder, probe
planner) can weight facts by source quality rather than treating them
uniformly.

Trust hierarchy:
  High   (0.9-1.0): exported function existence, committed calling conventions,
                     concrete data types from headers/known libraries.
  Medium (0.6-0.8): decompiler-recovered param count, recovered structures,
                     call graph edges, constant strings, sentinel constants.
  Low    (0.3-0.5): pointer direction inference, in/out semantics, unnamed param
                     roles (param_1), guessed structure field meaning.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
#  Source methods — how the fact was produced
# ═══════════════════════════════════════════════════════════════════════════════

SOURCE_DECOMPILER = "decompiler"
SOURCE_GET_PARAMETERS = "getParameters"
SOURCE_SIGNATURE_PARSE = "signature_parse"
SOURCE_PE_EXPORT = "pe_export"
SOURCE_DTM_LOOKUP = "dtm_lookup"
SOURCE_HEURISTIC = "heuristic"
SOURCE_RECLASSIFIED = "reclassified"

TRUST_HIGH = "high"
TRUST_MEDIUM = "medium"
TRUST_LOW = "low"


# ═══════════════════════════════════════════════════════════════════════════════
#  Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GhidraFieldProvenance:
    """Provenance for a single Ghidra-derived field (type, direction, name, etc.)."""
    value: Any
    source_method: str
    trust_level: str
    confidence: float
    decompiler_warnings: list[str] = field(default_factory=list)
    reclassified: bool = False
    reclassified_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> GhidraFieldProvenance:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class GhidraParamProvenance:
    """Per-parameter provenance bundle — each field tracked independently."""
    name: GhidraFieldProvenance
    param_type: GhidraFieldProvenance
    direction: GhidraFieldProvenance
    json_type: GhidraFieldProvenance

    def to_dict(self) -> dict:
        return {
            "name": self.name.to_dict(),
            "param_type": self.param_type.to_dict(),
            "direction": self.direction.to_dict(),
            "json_type": self.json_type.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> GhidraParamProvenance:
        return cls(
            name=GhidraFieldProvenance.from_dict(d.get("name", {})),
            param_type=GhidraFieldProvenance.from_dict(d.get("param_type", {})),
            direction=GhidraFieldProvenance.from_dict(d.get("direction", {})),
            json_type=GhidraFieldProvenance.from_dict(d.get("json_type", {})),
        )

    @property
    def min_confidence(self) -> float:
        return min(self.name.confidence, self.param_type.confidence,
                   self.direction.confidence, self.json_type.confidence)

    @property
    def direction_confidence(self) -> float:
        return self.direction.confidence

    @property
    def type_confidence(self) -> float:
        return self.param_type.confidence


@dataclass
class GhidraFunctionProvenance:
    """Function-level provenance — aggregates per-param provenance."""
    exists: GhidraFieldProvenance
    calling_convention: GhidraFieldProvenance
    param_count: GhidraFieldProvenance
    return_type: GhidraFieldProvenance
    params: dict[str, GhidraParamProvenance] = field(default_factory=dict)
    call_graph_edges: list[GhidraFieldProvenance] = field(default_factory=list)
    decompiler_confidence: float = 0.5
    decompiler_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "exists": self.exists.to_dict(),
            "calling_convention": self.calling_convention.to_dict(),
            "param_count": self.param_count.to_dict(),
            "return_type": self.return_type.to_dict(),
            "params": {k: v.to_dict() for k, v in self.params.items()},
            "call_graph_edges": [e.to_dict() for e in self.call_graph_edges],
            "decompiler_confidence": self.decompiler_confidence,
            "decompiler_warnings": self.decompiler_warnings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GhidraFunctionProvenance:
        return cls(
            exists=GhidraFieldProvenance.from_dict(d.get("exists", {})),
            calling_convention=GhidraFieldProvenance.from_dict(d.get("calling_convention", {})),
            param_count=GhidraFieldProvenance.from_dict(d.get("param_count", {})),
            return_type=GhidraFieldProvenance.from_dict(d.get("return_type", {})),
            params={
                k: GhidraParamProvenance.from_dict(v)
                for k, v in (d.get("params") or {}).items()
            },
            call_graph_edges=[
                GhidraFieldProvenance.from_dict(e) for e in (d.get("call_graph_edges") or [])
            ],
            decompiler_confidence=d.get("decompiler_confidence", 0.5),
            decompiler_warnings=d.get("decompiler_warnings", []),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Trust assignment
# ═══════════════════════════════════════════════════════════════════════════════

_TRUST_TABLE: dict[str, tuple[str, float]] = {
    SOURCE_DECOMPILER:      (TRUST_MEDIUM, 0.75),
    SOURCE_GET_PARAMETERS:  (TRUST_MEDIUM, 0.65),
    SOURCE_SIGNATURE_PARSE: (TRUST_LOW,    0.45),
    SOURCE_PE_EXPORT:       (TRUST_HIGH,   0.95),
    SOURCE_DTM_LOOKUP:      (TRUST_MEDIUM, 0.70),
    SOURCE_HEURISTIC:       (TRUST_LOW,    0.40),
    SOURCE_RECLASSIFIED:    (TRUST_MEDIUM, 0.70),
}

_WARNING_PENALTY = 0.15


def assign_trust_level(source_method: str, has_warnings: bool = False) -> tuple[str, float]:
    """Map a Ghidra source method to (trust_level, confidence).

    If decompiler warnings are present, confidence is reduced.
    """
    trust, conf = _TRUST_TABLE.get(source_method, (TRUST_LOW, 0.40))
    if has_warnings:
        conf = max(0.1, conf - _WARNING_PENALTY)
        if trust == TRUST_HIGH:
            trust = TRUST_MEDIUM
    return trust, round(conf, 2)


def assign_direction_trust(
    direction: str,
    ghidra_type: str,
    resolved_type: str = "",
    reclassified: bool = False,
) -> tuple[str, float]:
    """Assign trust specifically for parameter direction inference.

    Direction is one of the lowest-trust Ghidra outputs because the decompiler
    marks all pointer params as out by default.
    """
    raw = f"{ghidra_type} {resolved_type}".lower()

    if reclassified:
        return TRUST_MEDIUM, 0.70

    if "lpcstr" in raw or "pcstr" in raw or "lpcwstr" in raw or "pcwstr" in raw:
        return TRUST_HIGH, 0.90

    if "lpstr" in raw or "lpwstr" in raw:
        return TRUST_HIGH, 0.85

    if "*" not in raw:
        return TRUST_MEDIUM, 0.75

    if "const " in raw:
        return TRUST_MEDIUM, 0.70

    return TRUST_LOW, 0.35


def assign_type_trust(
    ghidra_type: str,
    resolved_type: str = "",
    source_method: str = SOURCE_DECOMPILER,
    has_warnings: bool = False,
) -> tuple[str, float]:
    """Assign trust for parameter type recovery.

    Known typedefs (LPCSTR, DWORD, etc.) are higher trust than generic
    undefined* types.
    """
    raw = f"{ghidra_type} {resolved_type}".lower()

    _known_typedefs = {"lpcstr", "lpstr", "lpcwstr", "lpwstr", "dword", "word",
                       "byte", "bool", "handle", "hresult", "hwnd", "lpvoid"}
    if any(td in raw for td in _known_typedefs):
        trust, conf = TRUST_HIGH, 0.85
    elif "undefined" in raw:
        trust, conf = TRUST_LOW, 0.35
    else:
        trust, conf = assign_trust_level(source_method, has_warnings)

    if has_warnings:
        conf = max(0.1, conf - _WARNING_PENALTY)
    return trust, round(conf, 2)


def assign_param_name_trust(
    param_name: str,
    source_method: str = SOURCE_DECOMPILER,
) -> tuple[str, float]:
    """Assign trust for a recovered parameter name.

    Named params from decompiler are medium trust; generic param_N names are low.
    """
    import re
    if re.match(r"^param_\d+$", param_name, re.I):
        return TRUST_LOW, 0.30
    return assign_trust_level(source_method, has_warnings=False)


# ═══════════════════════════════════════════════════════════════════════════════
#  Factory: build provenance for a parsed invocable
# ═══════════════════════════════════════════════════════════════════════════════

def build_function_provenance(
    fn_data: dict,
    param_source: str,
    is_exported: bool = False,
) -> GhidraFunctionProvenance:
    """Construct a full GhidraFunctionProvenance from a parsed function dict.

    Args:
        fn_data: The raw function dict from ExtractFunctions.py JSON.
        param_source: How params were obtained ("decompiler", "getParameters",
                      "signature_parse").
        is_exported: Whether the function appears in the PE export table.
    """
    has_warnings = bool(fn_data.get("decompiler_warnings"))
    decomp_conf = fn_data.get("decompiler_confidence", 0.5)

    exists_trust, exists_conf = (
        (TRUST_HIGH, 1.0) if is_exported else (TRUST_MEDIUM, 0.6)
    )

    cc_raw = fn_data.get("calling_convention", "unknown")
    cc_trust, cc_conf = (
        (TRUST_HIGH, 0.90) if cc_raw not in ("unknown", "default")
        else (TRUST_LOW, 0.40)
    )

    param_count_trust, param_count_conf = assign_trust_level(param_source, has_warnings)

    ret_type = fn_data.get("return_type", "int")
    rt_trust, rt_conf = assign_type_trust(ret_type, source_method=param_source,
                                          has_warnings=has_warnings)

    params_prov: dict[str, GhidraParamProvenance] = {}
    for p in fn_data.get("parameters") or []:
        pname = p.get("name", f"param_{p.get('ordinal', 0)}")
        ptype = p.get("type", "int")
        resolved = p.get("resolved_type", "")
        direction = p.get("direction", "in")

        name_trust, name_conf = assign_param_name_trust(pname, param_source)
        type_trust, type_conf = assign_type_trust(ptype, resolved, param_source, has_warnings)
        dir_trust, dir_conf = assign_direction_trust(direction, ptype, resolved)
        jtype_trust, jtype_conf = assign_trust_level(param_source, has_warnings)

        warnings_list = [fn_data.get("decompiler_warnings", "")] if has_warnings else []

        params_prov[pname] = GhidraParamProvenance(
            name=GhidraFieldProvenance(
                value=pname, source_method=param_source,
                trust_level=name_trust, confidence=name_conf,
            ),
            param_type=GhidraFieldProvenance(
                value=ptype, source_method=param_source,
                trust_level=type_trust, confidence=type_conf,
                decompiler_warnings=warnings_list,
            ),
            direction=GhidraFieldProvenance(
                value=direction, source_method=SOURCE_HEURISTIC,
                trust_level=dir_trust, confidence=dir_conf,
            ),
            json_type=GhidraFieldProvenance(
                value=p.get("json_type", "string"), source_method=param_source,
                trust_level=jtype_trust, confidence=jtype_conf,
            ),
        )

    call_graph_edges = []
    for callee in fn_data.get("call_graph_callees") or []:
        edge_trust, edge_conf = (TRUST_MEDIUM, 0.70)
        call_graph_edges.append(GhidraFieldProvenance(
            value=callee, source_method="call_graph_xref",
            trust_level=edge_trust, confidence=edge_conf,
        ))

    return GhidraFunctionProvenance(
        exists=GhidraFieldProvenance(
            value=fn_data.get("name", ""), source_method=SOURCE_PE_EXPORT if is_exported else SOURCE_DECOMPILER,
            trust_level=exists_trust, confidence=exists_conf,
        ),
        calling_convention=GhidraFieldProvenance(
            value=cc_raw, source_method=SOURCE_DECOMPILER,
            trust_level=cc_trust, confidence=cc_conf,
        ),
        param_count=GhidraFieldProvenance(
            value=len(fn_data.get("parameters") or []),
            source_method=param_source,
            trust_level=param_count_trust, confidence=param_count_conf,
        ),
        return_type=GhidraFieldProvenance(
            value=ret_type, source_method=param_source,
            trust_level=rt_trust, confidence=rt_conf,
        ),
        params=params_prov,
        call_graph_edges=call_graph_edges,
        decompiler_confidence=decomp_conf,
        decompiler_warnings=[fn_data.get("decompiler_warnings", "")] if has_warnings else [],
    )


def get_param_provenance(param: dict) -> GhidraParamProvenance | None:
    """Extract GhidraParamProvenance from a parameter dict, if tagged."""
    prov = param.get("_ghidra_provenance")
    if prov is None:
        return None
    if isinstance(prov, GhidraParamProvenance):
        return prov
    if isinstance(prov, dict):
        try:
            return GhidraParamProvenance.from_dict(prov)
        except Exception:
            return None
    return None


def get_function_provenance(inv: dict) -> GhidraFunctionProvenance | None:
    """Extract GhidraFunctionProvenance from an invocable dict, if tagged."""
    prov = inv.get("_ghidra_provenance")
    if prov is None:
        return None
    if isinstance(prov, GhidraFunctionProvenance):
        return prov
    if isinstance(prov, dict):
        try:
            return GhidraFunctionProvenance.from_dict(prov)
        except Exception:
            return None
    return None
