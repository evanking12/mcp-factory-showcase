import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_interwoven_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_interwoven"
    assert (fixture_dir / "contoso_cs_interwoven.c").exists()
    assert (fixture_dir / "build-interwoven.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_cs_interwoven"
    assert "contoso_cs.dll" in manifest["depends_on"]
    assert any(step["function"] == "CI_PrimeSession" for step in manifest["canonical_flow"])
    patterns = {item["pattern_id"]: item for item in manifest.get("interwoven_patterns", [])}
    assert "prime_session_fanout" in patterns
    assert set(patterns["prime_session_fanout"]["consumers"]) == {"CI_EarnThenRedeem", "CI_UnlockAndDebit"}


def test_workflow_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_workflow"
    assert (fixture_dir / "contoso_workflow.c").exists()
    assert (fixture_dir / "build-workflow.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_workflow"
    assert "contoso_cs.dll" in manifest["depends_on"]
    assert "contoso_payments.dll" in manifest["depends_on"]
    assert any(step["function"] == "WF_CommitShipment" for step in manifest["canonical_flow"])


def test_workflow_fixture_manifest_declares_handle_passing_path():
    manifest = _load_json(ROOT / "tests" / "fixtures" / "contoso_workflow" / "truth_manifest.json")
    names = [item["name"] for item in manifest["functions"]]
    assert "WF_OpenFulfillment" in names
    assert "WF_GetWorkflowNonce" in names
    assert "WF_ConfirmWorkflow" in names
    assert "WF_CommitShipment" in names


def test_pricing_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_pricing"
    assert (fixture_dir / "contoso_pricing.c").exists()
    assert (fixture_dir / "build-pricing.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_pricing"
    assert "contoso_cs.dll" in manifest["depends_on"]
    assert "contoso_payments.dll" in manifest["depends_on"]
    assert any(step["function"] == "PR_SealQuote" for step in manifest["canonical_flow"])


def test_reporting_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_reporting"
    assert (fixture_dir / "contoso_reporting.c").exists()
    assert (fixture_dir / "build-reporting.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_reporting"
    assert "contoso_cs.dll" in manifest["depends_on"]
    assert "contoso_payments.dll" in manifest["depends_on"]
    assert "contoso_workflow.dll" in manifest["depends_on"]
    assert any(step["function"] == "RP_ExportLedger" for step in manifest["canonical_flow"])


def test_new_fixture_manifests_declare_rule_and_report_state_paths():
    pricing = _load_json(ROOT / "tests" / "fixtures" / "contoso_pricing" / "truth_manifest.json")
    reporting = _load_json(ROOT / "tests" / "fixtures" / "contoso_reporting" / "truth_manifest.json")
    pricing_names = [item["name"] for item in pricing["functions"]]
    reporting_names = [item["name"] for item in reporting["functions"]]

    assert "PR_GetQuoteNonce" in pricing_names
    assert "PR_ApproveRuleWindow" in pricing_names
    assert "PR_ApplyTierDiscount" in pricing_names
    assert "PR_SealQuote" in pricing_names

    assert "RP_PrepareReservationReport" in reporting_names
    assert "RP_GetReportNonce" in reporting_names
    assert "RP_RenderPreview" in reporting_names
    assert "RP_ExportLedger" in reporting_names


def test_config_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_config"
    assert (fixture_dir / "contoso_config.c").exists()
    assert (fixture_dir / "build-config.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_config"
    assert "contoso_cs.dll" in manifest["depends_on"]
    assert any(step["function"] == "CFG_RunCustomerSync" for step in manifest["canonical_flow"])


def test_transport_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_transport"
    assert (fixture_dir / "contoso_transport.c").exists()
    assert (fixture_dir / "build-transport.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_transport"
    assert "contoso_config.dll" in manifest["depends_on"]
    assert any(step["function"] == "TP_SubmitPacket" for step in manifest["canonical_flow"])


def test_gateway_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_gateway"
    assert (fixture_dir / "contoso_gateway.c").exists()
    assert (fixture_dir / "build-gateway.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_gateway"
    assert "contoso_transport.dll" in manifest["depends_on"]
    assert any(step["function"] == "GW_RenderBridgeW" for step in manifest["canonical_flow"])


def test_events_fixture_has_truth_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_events"
    assert (fixture_dir / "contoso_events.c").exists()
    assert (fixture_dir / "build-events.ps1").exists()
    manifest = _load_json(fixture_dir / "truth_manifest.json")
    assert manifest["fixture_id"] == "contoso_events"
    assert "contoso_transport.dll" in manifest["depends_on"]
    assert any(step["function"] == "EV_ReplayMask" for step in manifest["canonical_flow"])


def test_contoso_business_suite_package_fixture_has_manifest_and_build_script():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_business_suite"
    assert (fixture_dir / "package_manifest.json").exists()
    assert (fixture_dir / "package_manifest_batch_a.json").exists()
    assert (fixture_dir / "package_manifest_batch_b.json").exists()
    assert (fixture_dir / "package_manifest_batch_c.json").exists()
    assert (fixture_dir / "build-package.ps1").exists()
    manifest = _load_json(fixture_dir / "package_manifest.json")
    assert manifest["package_id"] == "contoso-business-suite"
    bundled = {item["staged_name"]: item for item in manifest["bundled_dlls"]}
    targets = manifest["selected_runtime_targets"]

    assert "contoso_transport.dll" in bundled
    assert "contoso_workflow.dll" in bundled
    assert "contoso_reporting.dll" in bundled
    assert {item["staged_name"] for item in targets} == {
        "contoso_config.dll",
        "contoso_transport.dll",
        "contoso_workflow.dll",
        "contoso_reporting.dll",
    }
    for item in manifest["bundled_dlls"]:
        source_path = ROOT / item["source_path"]
        if source_path.exists():
            continue
        build_script = item.get("build_script")
        assert build_script, f"missing source fixture binary: {item['source_path']}"
        assert (ROOT / build_script).exists(), f"missing build script for fixture binary: {build_script}"


def test_contoso_business_suite_batch_manifests_expand_runtime_targets():
    fixture_dir = ROOT / "tests" / "fixtures" / "contoso_business_suite"
    batch_a = _load_json(fixture_dir / "package_manifest_batch_a.json")
    batch_b = _load_json(fixture_dir / "package_manifest_batch_b.json")
    batch_c = _load_json(fixture_dir / "package_manifest_batch_c.json")

    targets_a = {item["staged_name"] for item in batch_a["selected_runtime_targets"]}
    targets_b = {item["staged_name"] for item in batch_b["selected_runtime_targets"]}
    targets_c = {item["staged_name"] for item in batch_c["selected_runtime_targets"]}

    assert {"contoso_pricing.dll", "contoso_gateway.dll"} <= targets_a
    assert {"contoso_events.dll", "contoso_cs_interwoven.dll"} <= targets_b
    assert {"contoso_cs.dll", "contoso_payments.dll"} <= targets_c
    assert len(targets_a) < len(targets_b) < len(targets_c)
