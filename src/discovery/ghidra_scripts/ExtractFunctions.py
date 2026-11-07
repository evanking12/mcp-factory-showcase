# -*- coding: utf-8 -*-
# ExtractFunctions.py
# Ghidra headless post-analysis script (Jython / GhidraScript API)
#
# Extracts all functions from the analyzed binary and writes a JSON file
# containing names, signatures, parameter types, calling conventions, and
# whether each function is in the PE export table.
#
# Called by ghidra_analyzer.py via:
#   analyzeHeadless.bat <proj> <name> -import <dll>
#       -postScript ExtractFunctions.py <output_json_path>
#       -scriptPath <this_directory>
#       -deleteProject
#
# The single script argument is the absolute path where JSON should be written.

# NOTE: do NOT add any top-level Ghidra imports here (e.g.
# "from ghidra.program.model.symbol import SymbolType").
# Such imports run before run() is defined.  If they fail in the installed
# Ghidra version the entire module dies, run() is never called, and the
# output JSON stays empty — producing the misleading
# "Expecting value: line 1 column 1" error on the Python side.
import json
import os


def _decompile_params(func, decompiler, monitor):
    """Use Ghidra's DecompInterface to recover parameter info and decompiled C for *func*.

    Returns a tuple:
      params              - list of {"name", "type", "ordinal", "resolved_type"} dicts
      decompiled_c        - first 1200 chars of decompiled C body (may be "")
      decompiler_confidence - float 0.0-1.0 indicating decompiler quality
      decompiler_warnings   - string with any warnings/errors from decompiler
    """
    try:
        results = decompiler.decompileFunction(func, 30, monitor)
        if not results or not results.decompileCompleted():
            _err = ""
            if results:
                try:
                    _err = str(results.getErrorMessage() or "")
                except Exception:
                    pass
            return [], "", 0.3, _err or "decompiler did not complete"
        high_func = results.getHighFunction()
        if not high_func:
            return [], "", 0.3, "no HighFunction produced"

        _warnings = ""
        try:
            _err_msg = results.getErrorMessage()
            if _err_msg:
                _warnings = str(_err_msg)
        except Exception:
            pass

        proto = high_func.getFunctionPrototype()
        params = []
        for i in range(proto.getNumParams()):
            p = proto.getParam(i)
            _dt = p.getDataType()
            _resolved = ""
            try:
                _dt_name = str(_dt.getName()) if _dt else ""
                _dt_display = str(_dt.getDisplayName()) if _dt else ""
                if (_dt_name and not _dt_name.startswith("undefined")
                        and _dt_name not in ("int", "uint", "byte", "char", "void")):
                    _resolved = _dt_display or _dt_name
            except Exception:
                pass
            params.append({
                "name":          p.getName(),
                "type":          str(_dt) if _dt else "undefined",
                "ordinal":       i,
                "resolved_type": _resolved,
            })

        decompiled_c = ""
        try:
            decompiled_func = results.getDecompiledFunction()
            if decompiled_func:
                c_text = decompiled_func.getC()
                if c_text:
                    decompiled_c = str(c_text)[:1200]
        except Exception as _dc_exc:
            print("WARNING: decompiled C capture for " + func.getName() + ": " + str(_dc_exc))

        _confidence = 1.0 if not _warnings else 0.7
        return params, decompiled_c, _confidence, _warnings
    except Exception as exc:
        print("WARNING: decompiler params for " + func.getName() + ": " + str(exc))
        return [], "", 0.0, str(exc)


def run():
    args = getScriptArgs()  # noqa: F821  (injected by Ghidra GhidraScript context)
    if not args:
        print("ERROR: ExtractFunctions.py requires one argument: <output_json_path>")
        return

    out_path = args[0]
    result   = {"binary": "", "function_count": 0, "functions": [],
                "call_graph": {}, "data_types": []}

    try:
        prog    = getCurrentProgram()  # noqa: F821
        fm      = prog.getFunctionManager()
        sym_tbl = prog.getSymbolTable()
        result["binary"] = prog.getName()

        decompiler = None
        decompiler_monitor = None
        try:
            from ghidra.app.decompiler import DecompInterface  # noqa: F821
            from ghidra.util.task import ConsoleTaskMonitor    # noqa: F821
            decompiler = DecompInterface()
            decompiler.openProgram(prog)
            decompiler_monitor = ConsoleTaskMonitor()
            print("INFO: DecompInterface initialised")
        except Exception as _dcomp_exc:
            print("WARNING: DecompInterface unavailable: " + str(_dcomp_exc))

        export_addrs = set()
        try:
            ep_iter = sym_tbl.getExternalEntryPointIterator()
            while ep_iter.hasNext():
                export_addrs.add(str(ep_iter.next()))
        except Exception as _ep_exc:
            print("WARNING: getExternalEntryPointIterator failed: " + str(_ep_exc))

        # ── Build address→name map for call graph resolution ─────────────────
        addr_to_name = {}
        _func_iter_map = fm.getFunctions(True)
        while _func_iter_map.hasNext():
            _f = _func_iter_map.next()
            addr_to_name[str(_f.getEntryPoint())] = _f.getName()

        # ── Walk all defined functions ────────────────────────────────────────
        functions = []
        call_graph = {}
        func_iter = fm.getFunctions(True)
        while func_iter.hasNext():
            func = func_iter.next()

            if func.isThunk() or func.isExternal():
                continue

            addr_str    = str(func.getEntryPoint())
            is_exported = addr_str in export_addrs

            params = []
            decompiled_c = ""
            _decomp_confidence = 0.0
            _decomp_warnings = ""
            if is_exported and decompiler is not None:
                params, decompiled_c, _decomp_confidence, _decomp_warnings = \
                    _decompile_params(func, decompiler, decompiler_monitor)
                if params:
                    print("INFO: decompiler recovered " + str(len(params)) +
                          " params for exported " + func.getName())

            if not params:
                _decomp_confidence = 0.3 if _decomp_confidence == 0.0 else _decomp_confidence
                try:
                    for p in func.getParameters():
                        params.append({
                            "name":          p.getName(),
                            "type":          str(p.getDataType()),
                            "ordinal":       p.getOrdinal(),
                            "resolved_type": "",
                        })
                except Exception as _p_exc:
                    print("WARNING: params for " + func.getName() + ": " + str(_p_exc))

            if not params:
                _decomp_confidence = 0.0

            cc_raw = func.getCallingConventionName()
            cc = str(cc_raw) if cc_raw else "unknown"

            try:
                sig = func.getPrototypeString(True, False)
            except Exception:
                sig = func.getName()

            functions.append({
                "name":                   func.getName(),
                "address":                addr_str,
                "signature":              sig,
                "calling_convention":     cc,
                "return_type":            str(func.getReturnType()),
                "parameters":             params,
                "is_exported":            is_exported,
                "decompiled_c":           decompiled_c,
                "decompiler_confidence":  _decomp_confidence,
                "decompiler_warnings":    _decomp_warnings,
            })

            # ── XREF Call Graph: collect outgoing calls from this function ────
            try:
                from ghidra.program.model.symbol import RefType  # noqa: F821
                callees = set()
                body = func.getBody()
                ref_mgr = prog.getReferenceManager()
                addr_iter = body.getAddresses(True)
                while addr_iter.hasNext():
                    addr = addr_iter.next()
                    for ref in ref_mgr.getReferencesFrom(addr):
                        if ref.getReferenceType().isCall():
                            target_addr = str(ref.getToAddress())
                            target_name = addr_to_name.get(target_addr)
                            if target_name and target_name != func.getName():
                                callees.add(target_name)
                if callees:
                    call_graph[func.getName()] = sorted(callees)
            except Exception as _cg_exc:
                print("WARNING: call graph for " + func.getName() + ": " + str(_cg_exc))

        result["functions"]      = functions
        result["function_count"] = len(functions)
        result["call_graph"]     = call_graph

        # ── Data Type Manager: extract user-defined structs, enums, typedefs ─
        try:
            dtm = prog.getDataTypeManager()
            data_types = []
            _seen = set()
            _all_dt = dtm.getAllDataTypes()
            while _all_dt.hasNext():
                dt = _all_dt.next()
                dt_name = str(dt.getName())
                dt_path = str(dt.getCategoryPath())
                if dt_path.startswith("/") and "ghidra" not in dt_path.lower():
                    pass
                else:
                    continue
                if dt_name in _seen or dt_name.startswith("undefined"):
                    continue
                _seen.add(dt_name)
                try:
                    from ghidra.program.model.data import Structure  # noqa: F821
                    from ghidra.program.model.data import Enum       # noqa: F821
                    from ghidra.program.model.data import TypeDef    # noqa: F821
                    if isinstance(dt, Structure):
                        fields = []
                        for i in range(dt.getNumComponents()):
                            comp = dt.getComponent(i)
                            fields.append({
                                "name":   str(comp.getFieldName() or ("field_" + str(i))),
                                "type":   str(comp.getDataType()),
                                "offset": comp.getOffset(),
                                "size":   comp.getLength(),
                            })
                        if fields:
                            data_types.append({
                                "name":   dt_name,
                                "kind":   "struct",
                                "size":   dt.getLength(),
                                "fields": fields,
                            })
                    elif isinstance(dt, Enum):
                        members = {}
                        for name in dt.getNames():
                            members[str(name)] = int(dt.getValue(name))
                        if members:
                            data_types.append({
                                "name":    dt_name,
                                "kind":    "enum",
                                "members": members,
                            })
                    elif isinstance(dt, TypeDef):
                        base = dt.getBaseDataType()
                        if base:
                            data_types.append({
                                "name":      dt_name,
                                "kind":      "typedef",
                                "base_type": str(base),
                            })
                except Exception:
                    pass
            result["data_types"] = data_types
            if data_types:
                print("INFO: extracted " + str(len(data_types)) + " user-defined data types")
        except Exception as _dtm_exc:
            print("WARNING: data type extraction failed: " + str(_dtm_exc))

    except Exception as _outer_exc:
        print("ERROR in ExtractFunctions.py: " + str(_outer_exc))
        result["error"] = str(_outer_exc)

    # ── Write JSON ────────────────────────────────────────────────────────────
    # Always write, even on error, so the Python side gets valid JSON and can
    # surface the error message rather than failing with an empty-file parse error.
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    with open(out_path, "w") as fh:
        json.dump(result, fh, indent=2)

    exported_count = sum(1 for f in result["functions"] if f.get("is_exported"))
    print("ExtractFunctions: wrote {} functions ({} exported) to {}".format(
        len(result["functions"]), exported_count, out_path))


run()
