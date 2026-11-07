from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUCCESS_LIKE_STATUSES = {
    "success",
    "verified_success",
    "functional",
    "functional_precondition_unmet",
    "inferred_success",
}

RETURN_RE = re.compile(r"Returned:\s*(-?\d+)")


@dataclass
class WrapperHandle:
    instance: Any | None
    source_path: str
    load_error: str


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_findings(session_dir: Path) -> list[dict[str, Any]]:
    candidates = (
        session_dir / "stage-05-finalization" / "findings.json",
        session_dir / "stage-02-synthesis" / "findings.json",
        session_dir / "evidence" / "stage-02-probe-loop" / "findings.json",
        session_dir / "findings.json",
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = _read_json(path)
        except Exception:
            continue
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


def _load_invocables_map(session_dir: Path) -> dict[str, dict[str, Any]]:
    candidates = (
        session_dir / "stage-05-finalization" / "invocables_map.json",
        session_dir / "evidence" / "stage-00-setup" / "invocables-map.json",
        session_dir / "invocables_map.json",
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = _read_json(path)
        except Exception:
            continue
        if isinstance(data, dict):
            return {
                str(name): inv
                for name, inv in data.items()
                if isinstance(inv, dict)
            }
        if isinstance(data, list):
            out: dict[str, dict[str, Any]] = {}
            for inv in data:
                if not isinstance(inv, dict):
                    continue
                name = str(inv.get("name") or "").strip()
                if name:
                    out[name] = inv
            if out:
                return out
    return {}


def _load_wrapper(session_dir: Path) -> WrapperHandle:
    candidates = (
        session_dir / "stage-05-finalization" / "behavioral_spec.py",
        session_dir / "evidence" / "stage-07-finalize" / "behavioral-spec.py",
        session_dir / "behavioral_spec.py",
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location("harness_validation_wrapper", path)
            if spec is None or spec.loader is None:
                return WrapperHandle(None, str(path), "wrapper_spec_loader_missing")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            wrapper_class = None
            for value in vars(module).values():
                if isinstance(value, type) and value.__module__ == module.__name__:
                    wrapper_class = value
                    break
            if wrapper_class is None:
                return WrapperHandle(None, str(path), "wrapper_class_not_found")
            try:
                wrapper = wrapper_class()
            except Exception as exc:
                return WrapperHandle(None, str(path), f"wrapper_init_error:{exc}")
            return WrapperHandle(wrapper, str(path), "")
        except Exception as exc:
            return WrapperHandle(None, str(path), f"wrapper_import_error:{exc}")
    return WrapperHandle(None, "", "wrapper_file_missing")


def _extract_call_args(finding: dict[str, Any]) -> dict[str, Any] | None:
    working_call = finding.get("working_call")
    if isinstance(working_call, dict):
        if isinstance(working_call.get("args"), dict):
            return dict(working_call.get("args") or {})
        if isinstance(working_call.get("arguments"), dict):
            return dict(working_call.get("arguments") or {})
        return dict(working_call)
    return None


def _method_name_for_function(function_name: str) -> str:
    raw = str(function_name or "").strip()
    if raw.startswith("CS_"):
        raw = raw[3:]
    parts: list[str] = []
    token = ""
    for ch in raw:
        if ch.isupper() and token:
            parts.append(token.lower())
            token = ch
        elif ch in {"-", " ", "."}:
            if token:
                parts.append(token.lower())
                token = ""
        else:
            token += ch
    if token:
        parts.append(token.lower())
    return "_".join(p for p in parts if p)


def _coerce_direct_return(raw_result: Any) -> dict[str, Any]:
    text = str(raw_result or "").strip()
    match = RETURN_RE.search(text)
    if match:
        try:
            return {"return_value": int(match.group(1)), "raw": text}
        except Exception:
            pass
    return {"return_value": None, "raw": text}


def _coerce_wrapper_return(result: Any) -> dict[str, Any]:
    if isinstance(result, bool):
        return {"return_value": int(result), "raw": str(result)}
    if isinstance(result, int):
        return {"return_value": int(result), "raw": str(result)}
    text = str(result).strip()
    if text and text.lstrip("-").isdigit():
        return {"return_value": int(text), "raw": text}
    return {"return_value": None, "raw": text}


def _is_placeholder_wrapper_method(method: Any) -> bool:
    try:
        source = inspect.getsource(method)
    except (OSError, TypeError):
        return False
    try:
        module = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return False

    fn_node = next(
        (
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        None,
    )
    if fn_node is None:
        return False

    body = list(fn_node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        getattr(body[0], "value", None), ast.Constant
    ) and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return True
    if len(body) != 1:
        return False
    node = body[0]
    if isinstance(node, ast.Pass):
        return True
    if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
        return node.value.value is Ellipsis
    return False


def _run_direct(inv: dict[str, Any], args: dict[str, Any]) -> tuple[Any | None, str]:
    try:
        from api.services.executor import _execute_tool
    except Exception as exc:
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        try:
            from api.services.executor import _execute_tool
        except Exception:
            return None, f"direct_executor_import_error:{exc}"
    try:
        return _execute_tool(inv, args), ""
    except Exception as exc:
        return None, f"direct_execute_error:{exc}"


def _call_wrapper_method(
    wrapper_instance: Any,
    function_name: str,
    inv: dict[str, Any],
    args: dict[str, Any],
) -> tuple[Any | None, str, str]:
    def _is_output_param(param: dict[str, Any]) -> bool:
        direction = str(param.get("direction") or "").strip().lower()
        if direction in {"out", "output", "inout"}:
            return True
        name = str(param.get("name") or "").strip().lower()
        return bool(name) and name.startswith(("out", "pout", "output_buffer"))

    canonical_method = _method_name_for_function(function_name)
    fn = str(function_name or "").strip()
    no_prefix = fn[3:] if fn.startswith("CS_") else fn
    candidates = [
        canonical_method,
        fn,
        no_prefix,
        fn.lower(),
        no_prefix.lower(),
    ]
    method = None
    selected = ""
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        candidate = getattr(wrapper_instance, name, None)
        if callable(candidate):
            method = candidate
            selected = name
            break
    if method is None:
        return None, f"wrapper_method_missing:{canonical_method}", canonical_method
    if _is_placeholder_wrapper_method(method):
        return None, f"wrapper_method_placeholder:{selected}", selected

    params = inv.get("parameters")
    ordered_names: list[str] = []
    param_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(params, list):
        for param in params:
            if not isinstance(param, dict):
                continue
            pname = str(param.get("name") or "").strip()
            if pname:
                ordered_names.append(pname)
                param_lookup[pname] = param
    if not ordered_names:
        ordered_names = list(args.keys())

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        parameters = list(signature.parameters.values())
        accepted_names = {param.name for param in parameters}
        projected_args = {
            name: value
            for name, value in args.items()
            if not _is_output_param(param_lookup.get(name, {})) or name in accepted_names
        }
        projected_ordered_names = [
            name
            for name in ordered_names
            if name in projected_args
            and (not _is_output_param(param_lookup.get(name, {})) or name in accepted_names)
        ]
        if projected_args:
            args = projected_args
        if projected_ordered_names:
            ordered_names = projected_ordered_names

        accepts_varargs = any(
            param.kind == inspect.Parameter.VAR_POSITIONAL for param in parameters
        )
        accepts_varkw = any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters
        )
        accepted_positional = [
            param
            for param in parameters
            if param.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        accepted_kwargs = {
            param.name
            for param in parameters
            if param.kind
            in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        }
        positional: list[Any] = []
        consumed_names: set[str] = set()
        for name in ordered_names:
            if name not in args:
                continue
            if accepts_varargs or len(positional) < len(accepted_positional):
                positional.append(args[name])
                consumed_names.add(name)
        if accepts_varkw:
            kwargs = {name: value for name, value in args.items() if name not in consumed_names}
        else:
            kwargs = {
                name: value
                for name, value in args.items()
                if name not in consumed_names and name in accepted_kwargs
            }
        try:
            return method(*positional, **kwargs), "", selected
        except Exception as exc:
            return None, f"wrapper_call_error:{exc}", selected

    try:
        positional = [args[name] for name in ordered_names if name in args]
        return method(*positional), "", selected
    except TypeError:
        try:
            return method(**args), "", selected
        except Exception as exc:
            return None, f"wrapper_call_error:{exc}", selected
    except Exception as exc:
        return None, f"wrapper_call_error:{exc}", selected


def emit_validation_report(session_dir: str | Path) -> dict[str, Any]:
    root = Path(session_dir)
    findings = _load_findings(root)
    inv_map = _load_invocables_map(root)
    wrapper = _load_wrapper(root)

    entries: list[dict[str, Any]] = []
    checked = 0
    matched = 0
    mismatched = 0
    wrapper_unavailable = 0
    direct_errors = 0
    wrapper_errors = 0
    skipped = 0

    if wrapper.instance is not None:
        init_method = getattr(wrapper.instance, "initialize", None)
        if callable(init_method):
            try:
                init_method()
            except Exception:
                # Some wrappers require parameters; this check should not block
                # per-function validation attempts.
                pass

    for finding in findings:
        function_name = str(finding.get("function") or "").strip()
        if not function_name:
            continue
        status = str(
            finding.get("status_canonical") or finding.get("status") or "unknown"
        ).strip().lower()
        if status not in SUCCESS_LIKE_STATUSES:
            skipped += 1
            continue
        call_args = _extract_call_args(finding)
        if call_args is None:
            skipped += 1
            continue
        inv = inv_map.get(function_name)
        if not isinstance(inv, dict):
            skipped += 1
            continue

        checked += 1
        row: dict[str, Any] = {
            "function": function_name,
            "status": "unknown",
            "args": call_args,
            "wrapper_method": _method_name_for_function(function_name),
        }

        direct_raw, direct_error = _run_direct(inv, call_args)
        if direct_error:
            row["status"] = "direct_error"
            row["direct_error"] = direct_error
            direct_errors += 1
            entries.append(row)
            continue
        direct_norm = _coerce_direct_return(direct_raw)
        row["direct"] = direct_norm

        if wrapper.instance is None:
            row["status"] = "wrapper_unavailable"
            row["wrapper_error"] = wrapper.load_error
            wrapper_unavailable += 1
            entries.append(row)
            continue

        wrapper_raw, wrapper_error, used_method = _call_wrapper_method(
            wrapper.instance,
            function_name,
            inv,
            call_args,
        )
        row["wrapper_method"] = used_method or row["wrapper_method"]
        if wrapper_error:
            if wrapper_error.startswith("wrapper_method_placeholder:"):
                row["status"] = "wrapper_unavailable"
                row["wrapper_error"] = wrapper_error
                wrapper_unavailable += 1
            else:
                row["status"] = "wrapper_error"
                row["wrapper_error"] = wrapper_error
                wrapper_errors += 1
            entries.append(row)
            continue
        wrapper_norm = _coerce_wrapper_return(wrapper_raw)
        row["wrapper"] = wrapper_norm

        direct_value = direct_norm.get("return_value")
        wrapper_value = wrapper_norm.get("return_value")
        if direct_value is not None and wrapper_value is not None:
            is_match = direct_value == wrapper_value
        else:
            is_match = str(direct_norm.get("raw") or "") == str(wrapper_norm.get("raw") or "")
        row["status"] = "verified_1to1" if is_match else "mismatch"
        if is_match:
            matched += 1
        else:
            mismatched += 1

        entries.append(row)

    payload = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_dir": str(root),
        "wrapper_source": wrapper.source_path,
        "wrapper_load_error": wrapper.load_error,
        "summary": {
            "total_findings": len(findings),
            "checked": checked,
            "verified_1to1": matched,
            "mismatch": mismatched,
            "wrapper_unavailable": wrapper_unavailable,
            "direct_error": direct_errors,
            "wrapper_error": wrapper_errors,
            "skipped": skipped,
        },
        "entries": entries,
    }

    (root / "validation-report.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    human_dir = root / "human"
    human_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Validation Report",
        "",
        f"- Checked: {checked}",
        f"- Verified 1:1: {matched}",
        f"- Mismatch: {mismatched}",
        f"- Wrapper unavailable: {wrapper_unavailable}",
        f"- Direct errors: {direct_errors}",
        f"- Wrapper errors: {wrapper_errors}",
        f"- Skipped: {skipped}",
    ]
    if wrapper.load_error:
        lines.extend(["", f"- Wrapper load note: {wrapper.load_error}"])
    (human_dir / "validation-report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return payload
