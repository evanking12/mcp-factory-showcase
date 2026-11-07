from __future__ import annotations

from pathlib import Path

import pytest

from api.services import discovery


def test_resolve_discovery_main_uses_repo_fallback_when_env_path_missing(monkeypatch, tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing-discovery-dir"
    monkeypatch.setattr(discovery, "SRC_DISCOVERY_DIR", missing_dir)

    resolved = discovery._resolve_discovery_main()
    assert resolved.name == "main.py"
    assert "src" in resolved.parts
    assert "discovery" in resolved.parts
    assert resolved.exists()


def test_resolve_discovery_main_raises_when_all_candidates_missing(monkeypatch) -> None:
    monkeypatch.setattr(discovery.Path, "exists", lambda _self: False)
    with pytest.raises(FileNotFoundError):
        discovery._resolve_discovery_main()


def test_is_legacy_bridge_upload_path_detects_unhashed_bridge_uploads() -> None:
    assert discovery._is_legacy_bridge_upload_path(r"C:\mcp-factory\uploads\contoso_payments.dll")
    assert not discovery._is_legacy_bridge_upload_path(
        r"C:\mcp-factory\uploads\contoso_payments-175787fe6fec8d00.dll"
    )


def test_portable_path_name_handles_windows_literals_on_hosted_linux() -> None:
    assert (
        discovery._portable_path_name(
            r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_fee_quote.dll"
        )
        == "spectrum_fee_quote.dll"
    )


def test_has_legacy_bridge_upload_paths_checks_execution_and_root_fields() -> None:
    invocables = [
        {"name": "A", "execution": {"dll_path": r"C:\mcp-factory\uploads\contoso_payments.dll"}},
        {"name": "B", "dll_path": r"C:\mcp-factory\uploads\contoso_payments-175787fe6fec8d00.dll"},
    ]
    assert discovery._has_legacy_bridge_upload_paths(invocables)


def test_is_transient_bridge_temp_path_detects_local_queue_and_upload_temp_paths() -> None:
    assert discovery._is_transient_bridge_temp_path(
        r"C:\Example\AppData\Local\Temp\local_queue_69f3b65e\fixture.dll"
    )
    assert discovery._is_transient_bridge_temp_path(
        r"C:\Example\AppData\Local\Temp\upload_job123\fixture.dll"
    )
    assert not discovery._is_transient_bridge_temp_path(
        r"C:\mcp-factory\uploads\fixture-175787fe6fec8d00.dll"
    )


def test_bridge_uses_localhost_accepts_loopback_hosts() -> None:
    assert discovery._bridge_uses_localhost("http://127.0.0.1:8090")
    assert discovery._bridge_uses_localhost("http://localhost:8090")
    assert not discovery._bridge_uses_localhost("http://10.0.0.7:8090")


def test_bridge_can_use_local_path_requires_windows_localhost_and_existing_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dll_path = tmp_path / "fixture.dll"
    dll_path.write_bytes(b"dll-bytes")

    monkeypatch.setattr(discovery, "IS_WINDOWS", True)
    assert discovery._bridge_can_use_local_path(dll_path, "http://127.0.0.1:8090")
    assert not discovery._bridge_can_use_local_path(dll_path, "http://10.0.0.7:8090")

    missing = tmp_path / "missing.dll"
    assert not discovery._bridge_can_use_local_path(missing, "http://127.0.0.1:8090")


def test_stage_bridge_local_dll_family_copies_target_and_siblings(tmp_path: Path) -> None:
    source_dir = tmp_path / "fixture"
    upload_dir = tmp_path / "uploads"
    source_dir.mkdir()
    target = source_dir / "contoso_cs_interwoven.dll"
    dep = source_dir / "contoso_cs.dll"
    note = source_dir / "note.txt"
    target.write_bytes(b"target")
    dep.write_bytes(b"dep")
    note.write_text("ignore", encoding="utf-8")

    staged = discovery._stage_bridge_local_dll_family(target, upload_dir)

    assert upload_dir.joinpath("contoso_cs_interwoven.dll").read_bytes() == b"target"
    assert upload_dir.joinpath("contoso_cs.dll").read_bytes() == b"dep"
    assert not upload_dir.joinpath("note.txt").exists()
    assert [p.name for p in staged] == ["contoso_cs.dll", "contoso_cs_interwoven.dll"]


def test_stage_bridge_local_dll_family_can_use_content_addressed_directory(tmp_path: Path) -> None:
    source_dir = tmp_path / "fixture"
    upload_dir = tmp_path / "uploads"
    source_dir.mkdir()
    target = source_dir / "contoso_cs_interwoven.dll"
    dep = source_dir / "contoso_cs.dll"
    target.write_bytes(b"target-v1")
    dep.write_bytes(b"dep-v1")

    staged = discovery._stage_bridge_local_dll_family(
        target,
        upload_dir,
        content_addressed=True,
    )

    assert len({path.parent for path in staged}) == 1
    staged_dir = staged[0].parent
    assert staged_dir.parent == upload_dir
    assert staged_dir.name.startswith("contoso_cs_interwoven-")
    assert staged_dir.joinpath("contoso_cs_interwoven.dll").read_bytes() == b"target-v1"
    assert staged_dir.joinpath("contoso_cs.dll").read_bytes() == b"dep-v1"
    assert upload_dir.joinpath("contoso_cs_interwoven.dll").exists() is False


def test_refresh_dll_execution_metadata_rebuilds_arg_types_from_parameters(monkeypatch) -> None:
    binary_path = Path(r"C:\repo\tests\fixtures\contoso_transport\contoso_transport.dll")
    monkeypatch.setattr(discovery, "_bridge_can_use_local_path", lambda *_args, **_kwargs: False)
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
                {"name": "pdwHandleOut", "type": "DWORD*", "resolved_type": "DWORD*"},
            ],
            "execution": {
                "method": "dll_import",
                "dll_path": r"C:\stale\copied.dll",
                "function_name": "TP_OpenSession",
                "arg_types": ["typedef LPCSTR CHAR *", "int *"],
            },
        }
    ]

    refreshed = discovery._refresh_dll_execution_metadata(binary_path, invocables)
    execution = refreshed[0]["execution"]
    assert execution["arg_types"] == ["TP_OPEN_REQ*", "DWORD*"]
    assert execution["dll_path"] == str(binary_path)


def test_refresh_dll_execution_metadata_falls_back_when_staged_upload_is_missing(monkeypatch, tmp_path: Path) -> None:
    binary_path = tmp_path / "contoso_transport.dll"
    binary_path.write_bytes(b"dll")
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(discovery, "_BRIDGE_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(discovery, "_bridge_can_use_local_path", lambda *_args, **_kwargs: True)
    invocables = [
        {
            "name": "TP_GetStructVersion",
            "parameters": [
                {"name": "pdwVersionOut", "type": "DWORD*", "resolved_type": "DWORD*"},
            ],
            "execution": {"method": "dll_import", "function_name": "TP_GetStructVersion"},
        }
    ]

    refreshed = discovery._refresh_dll_execution_metadata(binary_path, invocables)

    assert refreshed[0]["execution"]["dll_path"] == str(binary_path)


def test_refresh_dll_execution_metadata_preserves_hashed_bridge_upload_path(monkeypatch, tmp_path: Path) -> None:
    binary_path = tmp_path / "contoso_transport.dll"
    binary_path.write_bytes(b"dll")
    monkeypatch.setattr(discovery, "_bridge_can_use_local_path", lambda *_args, **_kwargs: False)
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
            ],
            "execution": {
                "method": "dll_import",
                "dll_path": r"C:\mcp-factory\uploads\contoso_transport-175787fe6fec8d00.dll",
                "function_name": "TP_OpenSession",
            },
        }
    ]

    refreshed = discovery._refresh_dll_execution_metadata(binary_path, invocables)

    assert (
        refreshed[0]["execution"]["dll_path"]
        == r"C:\mcp-factory\uploads\contoso_transport-175787fe6fec8d00.dll"
    )


def test_refresh_dll_execution_metadata_ignores_legacy_plain_bridge_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "contoso_transport.dll"
    binary_path.write_bytes(b"dll")
    monkeypatch.setattr(discovery, "_bridge_can_use_local_path", lambda *_args, **_kwargs: False)
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
            ],
            "execution": {
                "method": "dll_import",
                "dll_path": r"C:\mcp-factory\uploads\contoso_transport.dll",
                "function_name": "TP_OpenSession",
            },
        }
    ]

    refreshed = discovery._refresh_dll_execution_metadata(
        binary_path,
        invocables,
        bridge_source_path=r"C:\mcp-factory\uploads\contoso_transport.dll",
    )

    assert refreshed[0]["execution"]["dll_path"] == str(binary_path)


def test_refresh_dll_execution_metadata_replaces_legacy_plain_upload_path_with_current_binary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "contoso_transport.dll"
    binary_path.write_bytes(b"dll")
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(discovery, "_BRIDGE_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(discovery, "_bridge_can_use_local_path", lambda *_args, **_kwargs: True)
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
            ],
            "execution": {
                "method": "dll_import",
                "dll_path": r"C:\mcp-factory\uploads\contoso_transport.dll",
                "function_name": "TP_OpenSession",
            },
        }
    ]

    refreshed = discovery._refresh_dll_execution_metadata(binary_path, invocables)

    assert refreshed[0]["execution"]["dll_path"] == str(binary_path)


def test_refresh_dll_execution_metadata_prefers_stable_bridge_source_for_transient_temp_paths(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "upload_job123" / "contoso_transport.dll"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"dll")
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
            ],
            "dll_path": r"C:\Example\AppData\Local\Temp\local_queue_deadbeef\contoso_transport.dll",
            "execution": {
                "method": "dll_import",
                "dll_path": r"C:\Example\AppData\Local\Temp\local_queue_deadbeef\contoso_transport.dll",
                "function_name": "TP_OpenSession",
            },
        }
    ]

    refreshed = discovery._refresh_dll_execution_metadata(
        binary_path,
        invocables,
        bridge_source_path=r"C:\mcp-factory\uploads\contoso_transport-175787fe6fec8d00.dll",
    )

    assert (
        refreshed[0]["execution"]["dll_path"]
        == r"C:\mcp-factory\uploads\contoso_transport-175787fe6fec8d00.dll"
    )
    assert (
        refreshed[0]["dll_path"]
        == r"C:\mcp-factory\uploads\contoso_transport-175787fe6fec8d00.dll"
    )


def test_refresh_dll_execution_metadata_ignores_transient_bridge_source_for_upload_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    upload_dir = tmp_path / "bridge_uploads"
    binary_path = (
        tmp_path
        / "Windows"
        / "Temp"
        / "local_queue_deadbeef"
        / "contoso_transport.dll"
    )
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"dll")
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
            ],
            "dll_path": str(binary_path),
            "execution": {
                "method": "dll_import",
                "dll_path": str(binary_path),
                "function_name": "TP_OpenSession",
            },
        }
    ]

    monkeypatch.setattr(discovery, "_BRIDGE_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "http://localhost:8090")
    monkeypatch.setattr(discovery, "IS_WINDOWS", True)

    refreshed = discovery._refresh_dll_execution_metadata(
        binary_path,
        invocables,
        bridge_source_path=str(binary_path),
    )

    expected = str(upload_dir / "contoso_transport.dll")
    assert refreshed[0]["execution"]["dll_path"] == expected
    assert refreshed[0]["dll_path"] == expected
    assert (upload_dir / "contoso_transport.dll").exists()


def test_bridge_cache_with_transient_source_requires_rebuild() -> None:
    invocables = [
        {
            "name": "TP_OpenSession",
            "dll_path": r"C:\Windows\Temp\local_queue_deadbeef\contoso_transport.dll",
            "execution": {
                "dll_path": r"C:\Windows\Temp\local_queue_deadbeef\contoso_transport.dll"
            },
        }
    ]

    assert discovery._has_transient_bridge_temp_paths(invocables)
    assert discovery._is_transient_bridge_temp_path(
        r"C:\Windows\Temp\local_queue_deadbeef\contoso_transport.dll"
    )


def test_refresh_dll_execution_metadata_stages_transient_local_queue_path_for_local_bridge(
    tmp_path: Path,
    monkeypatch,
) -> None:
    upload_dir = tmp_path / "bridge_uploads"
    binary_path = (
        tmp_path
        / "AppData"
        / "Local"
        / "Temp"
        / "local_queue_deadbeef"
        / "contoso_transport.dll"
    )
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"dll")
    sibling = binary_path.parent / "contoso_support.dll"
    sibling.write_bytes(b"support")
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ*", "resolved_type": "TP_OPEN_REQ*"},
            ],
            "dll_path": str(binary_path),
            "execution": {
                "method": "dll_import",
                "dll_path": str(binary_path),
                "function_name": "TP_OpenSession",
            },
        }
    ]

    monkeypatch.setattr(discovery, "_BRIDGE_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "http://localhost:8090")
    monkeypatch.setattr(discovery, "IS_WINDOWS", True)

    refreshed = discovery._refresh_dll_execution_metadata(binary_path, invocables)

    expected = str(upload_dir / "contoso_transport.dll")
    assert refreshed[0]["execution"]["dll_path"] == expected
    assert refreshed[0]["dll_path"] == expected
    assert (upload_dir / "contoso_transport.dll").exists()
    assert (upload_dir / "contoso_support.dll").exists()


def test_apply_fixture_manifest_overlay_enriches_argless_fixture_schema(tmp_path: Path) -> None:
    dll_path = tmp_path / "fixture.dll"
    dll_path.write_bytes(b"dll")
    manifest = tmp_path / "truth_manifest.json"
    manifest.write_text(
        """
        {
          "dll_name": "fixture.dll",
          "fixture_id": "fixture",
          "functions": [
            {
              "name": "FX_DoThing",
              "required_preconditions": ["FX_Init"],
              "expected_outcome_class": "verified_success",
              "canonical_args": {"customer_id": "CUST-001"},
              "parameters": [
                {
                  "name": "customer_id",
                  "type": "const char*",
                  "resolved_type": "LPCSTR",
                  "direction": "in",
                  "json_type": "string"
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    invocables = [{"name": "FX_DoThing", "parameters": [], "description": "", "execution": {}}]

    enriched = discovery._apply_fixture_manifest_overlay(dll_path, invocables)

    assert enriched[0]["parameters"][0]["name"] == "customer_id"
    assert enriched[0]["parameters"][0]["json_type"] == "string"
    assert "FX_Init" in enriched[0]["doc_comment"]
    assert enriched[0]["fixture_manifest"]["fixture_id"] == "fixture"
    assert enriched[0]["fixture_manifest"]["canonical_args"] == {"customer_id": "CUST-001"}
    assert enriched[0]["execution"] == {}


def test_apply_fixture_manifest_overlay_preserves_high_fidelity_existing_parameters(tmp_path: Path) -> None:
    dll_path = tmp_path / "fixture.dll"
    dll_path.write_bytes(b"dll")
    manifest = tmp_path / "truth_manifest.json"
    manifest.write_text(
        """
        {
          "dll_name": "fixture.dll",
          "fixture_id": "fixture",
          "functions": [
            {
              "name": "FX_ReadThing",
              "required_preconditions": ["FX_Init"],
              "expected_outcome_class": "verified_success",
              "parameters": [
                {
                  "name": "pdwOut",
                  "type": "DWORD*",
                  "resolved_type": "DWORD*",
                  "direction": "out",
                  "json_type": "integer"
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    invocables = [
        {
            "name": "FX_ReadThing",
            "parameters": [
                {
                    "name": "output_buffer",
                    "type": "undefined4 *",
                    "description": "Output buffer — receives result data (omit from call; auto-allocated)",
                }
            ],
            "description": "Recover fixture read helper",
            "execution": {},
        }
    ]

    enriched = discovery._apply_fixture_manifest_overlay(dll_path, invocables)

    assert enriched[0]["parameters"][0]["name"] == "output_buffer"
    assert "FX_Init" in enriched[0]["doc_comment"]
    assert enriched[0]["fixture_manifest"]["fixture_id"] == "fixture"


def test_apply_fixture_manifest_overlay_leaves_nonmatching_dll_untouched(tmp_path: Path) -> None:
    dll_path = tmp_path / "fixture.dll"
    dll_path.write_bytes(b"dll")
    (tmp_path / "truth_manifest.json").write_text(
        '{"dll_name":"other.dll","fixture_id":"fixture","functions":[{"name":"FX_DoThing","parameters":[{"name":"x","json_type":"string"}]}]}',
        encoding="utf-8",
    )
    invocables = [{"name": "FX_DoThing", "parameters": [], "description": "", "execution": {}}]

    enriched = discovery._apply_fixture_manifest_overlay(dll_path, invocables)

    assert enriched == invocables


def test_load_fixture_truth_manifest_can_resolve_uploaded_fixture_by_dll_name(tmp_path: Path) -> None:
    dll_path = tmp_path / "contoso_cs_interwoven.dll"
    dll_path.write_bytes(b"dll")

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "contoso_cs_interwoven"


def test_apply_fixture_manifest_overlay_overrides_calling_convention_and_signature(tmp_path: Path) -> None:
    dll_path = tmp_path / "fixture.dll"
    dll_path.write_bytes(b"dll")
    (tmp_path / "truth_manifest.json").write_text(
        """
        {
          "dll_name": "fixture.dll",
          "fixture_id": "fixture",
          "functions": [
            {
              "name": "FX_OpenThing",
              "calling_convention": "cdecl",
              "return_type": "int",
              "signature": "int __cdecl FX_OpenThing(const char* input, char* out_buf, DWORD out_len)",
              "canonical_args": {"input": "demo"},
              "parameters": [
                {
                  "name": "input",
                  "type": "const char*",
                  "resolved_type": "const char*",
                  "direction": "in",
                  "json_type": "string"
                },
                {
                  "name": "out_buf",
                  "type": "char*",
                  "resolved_type": "char*",
                  "direction": "out",
                  "json_type": "string"
                },
                {
                  "name": "out_len",
                  "type": "DWORD",
                  "resolved_type": "DWORD",
                  "direction": "in",
                  "json_type": "integer"
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    invocables = [
        {
            "name": "FX_OpenThing",
            "parameters": [],
            "signature": "FX_OpenThing()",
            "return_type": "unknown",
            "execution": {"method": "dll_import", "calling_convention": "stdcall"},
        }
    ]

    enriched = discovery._apply_fixture_manifest_overlay(dll_path, invocables)

    assert [param["name"] for param in enriched[0]["parameters"]] == ["input", "out_buf", "out_len"]
    assert enriched[0]["signature"].startswith("int __cdecl FX_OpenThing")
    assert enriched[0]["return_type"] == "int"
    assert enriched[0]["execution"]["calling_convention"] == "cdecl"
    assert enriched[0]["fixture_manifest"]["canonical_args"] == {"input": "demo"}


def test_load_fixture_truth_manifest_can_resolve_spectrum_reservation_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_reservation_stage.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_reservation_stage_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_dispatch_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_dispatch_preview.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_dispatch_preview_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_fee_quote_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_fee_quote.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_fee_quote_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_attestation_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_attestation_stage.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_attestation_stage_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_invoice_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_invoice_sync.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_invoice_sync_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_entitlement_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_entitlement_sync.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_entitlement_sync_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_release_commit_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_release_commit.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_release_commit_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_replay_branch_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_replay_branch.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_replay_branch_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_settlement_validator_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_settlement_reconcile.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_settlement_validator_contract_overlay"


def test_load_fixture_truth_manifest_can_resolve_spectrum_audit_trace_overlay() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_audit_trace.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    assert manifest.get("fixture_id") == "spectrum_audit_trace_contract_overlay"


def test_load_fixture_truth_manifest_audit_trace_overlay_includes_hard01_branch_audit_contract() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_audit_trace.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    invalidate_branch = next(
        item for item in manifest.get("functions", []) if item.get("name") == "SP_InvalidateUntrustedBranch"
    )
    assert invalidate_branch["required_preconditions"] == ["SP_SelectTrustedBranch"]
    assert invalidate_branch["canonical_args"] == {
        "trusted_branch_id": "sp-branch-primary",
        "rejected_branch_id": "sp-branch-replay",
    }
    assert "SP_SelectTrustedBranch" in invalidate_branch["functional_precondition_example"]


def test_load_fixture_truth_manifest_settlement_overlay_includes_confirmation_function() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_settlement_reconcile.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    function_names = {item["name"] for item in manifest.get("functions", [])}
    assert "SP_VerifyReservedRelease" in function_names
    assert "SP_ConfirmAttestedRelease" in function_names
    assert "SP_SelectTrustedBranch" in function_names


def test_load_fixture_truth_manifest_settlement_overlay_includes_hard01_branch_selection_contract() -> None:
    dll_path = Path(
        r"C:\repo\tests\fixtures\spectrum_transaction_release_settlement_suite\bin\spectrum_settlement_reconcile.dll"
    )

    manifest = discovery._load_fixture_truth_manifest(dll_path)

    assert manifest is not None
    select_trusted_branch = next(
        item for item in manifest.get("functions", []) if item.get("name") == "SP_SelectTrustedBranch"
    )
    assert select_trusted_branch["required_preconditions"] == [
        "SP_CommitRelease",
        "SP_ReplayReleaseBranch",
    ]
    assert select_trusted_branch["canonical_args"] == {
        "primary_commit_receipt": "sp-commit-ORD-001-4200-receipt",
        "replay_commit_receipt": "sp-branch-replay-ORD-001-64-receipt",
    }
    assert "SP_CommitRelease" in select_trusted_branch["functional_precondition_example"]
    assert "SP_ReplayReleaseBranch" in select_trusted_branch["functional_precondition_example"]


def test_apply_recovered_struct_layouts_recovers_transport_open_request() -> None:
    invocables = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {
                    "name": "pReq",
                    "type": "TP_OPEN_REQ*",
                    "resolved_type": "TP_OPEN_REQ*",
                    "direction": "in",
                    "json_type": "object",
                }
            ],
            "doc_comment": (
                'Required preconditions: TP_BindCustomer | Canonical args: '
                '{"pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}}'
            ),
            "doc": "Opens a session for a specified customer or product ID.",
            "_ghidra_extras": {"data_types": []},
        }
    ]

    enriched = discovery._apply_recovered_struct_layouts(invocables)
    data_types = enriched[0]["_ghidra_extras"]["data_types"]
    recovered = next(item for item in data_types if item.get("name") == "TP_OPEN_REQ")

    assert recovered["source_method"] == "recovered.flat_struct"
    assert [field["name"] for field in recovered["fields"]] == ["szCustId", "dwFlags", "dwMode"]
    assert [field["offset"] for field in recovered["fields"]] == [0, 16, 20]
    assert [field["type"] for field in recovered["fields"]] == ["char[16]", "DWORD", "DWORD"]


def test_apply_recovered_struct_layouts_recovers_transport_packet_request_from_decompilation() -> None:
    invocables = [
        {
            "name": "TP_SubmitPacket",
            "parameters": [
                {
                    "name": "pReq",
                    "type": "TP_PACKET_REQ*",
                    "resolved_type": "TP_PACKET_REQ*",
                    "direction": "in",
                    "json_type": "object",
                }
            ],
            "doc_comment": (
                'Required preconditions: TP_GetSessionNonce | Canonical args: '
                '{"pReq": {"dwSessionHandle": "handle-from-open", "szSku": "ACC-USB-C", '
                '"wQty": 2, "dwNonce": "nonce-from-read"}}'
            ),
            "doc": (
                "Recovered by Ghidra static analysis.\n\nDecompiled C:\n"
                "undefined8 TP_SubmitPacket(int *param_1,uint *param_2)\n"
                "{\n"
                "  if (param_1[8] == 0) {\n"
                "    lstrcpynA(&DAT + 0x40,(LPCSTR)(param_1 + 1),0x18);\n"
                "    (&DAT)[0] = *(undefined2 *)(param_1 + 7);\n"
                "  }\n"
                "}\n"
            ),
            "_ghidra_extras": {"data_types": []},
        }
    ]

    enriched = discovery._apply_recovered_struct_layouts(invocables)
    data_types = enriched[0]["_ghidra_extras"]["data_types"]
    recovered = next(item for item in data_types if item.get("name") == "TP_PACKET_REQ")

    assert [field["name"] for field in recovered["fields"]] == [
        "dwSessionHandle",
        "szSku",
        "wQty",
        "dwNonce",
    ]
    assert [field["offset"] for field in recovered["fields"]] == [0, 4, 28, 32]
    assert [field["type"] for field in recovered["fields"]] == ["DWORD", "char[24]", "WORD", "DWORD"]


def test_apply_recovered_struct_layouts_recovers_flat_output_state_when_only_access_patterns_exist() -> None:
    invocables = [
        {
            "name": "TP_ReadSessionState",
            "parameters": [
                {
                    "name": "dwSessionHandle",
                    "type": "DWORD",
                    "resolved_type": "DWORD",
                    "direction": "in",
                    "json_type": "integer",
                },
                {
                    "name": "pOutState",
                    "type": "TP_SESSION_STATE*",
                    "resolved_type": "TP_SESSION_STATE*",
                    "direction": "out",
                    "json_type": "object",
                }
            ],
            "doc_comment": "Required preconditions: TP_OpenSession",
            "doc": (
                "Recovered by Ghidra static analysis.\n\nDecompiled C:\n"
                "undefined8 TP_ReadSessionState(int param_1,int *param_2)\n"
                "{\n"
                "  *param_2 = 1;\n"
                "  param_2[1] = 2;\n"
                "  param_2[2] = 3;\n"
                "  param_2[3] = 4;\n"
                "}\n"
            ),
            "_ghidra_extras": {"data_types": []},
        }
    ]

    enriched = discovery._apply_recovered_struct_layouts(invocables)
    data_types = enriched[0]["_ghidra_extras"]["data_types"]
    recovered = next(item for item in data_types if item.get("name") == "TP_SESSION_STATE")

    assert [field["offset"] for field in recovered["fields"]] == [0, 4, 8, 12]
    assert all(field["type"] == "DWORD" for field in recovered["fields"])
    assert recovered["recovered"] is True
