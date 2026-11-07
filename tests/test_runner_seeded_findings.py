from __future__ import annotations

from api.pipeline.core import helpers
from api.pipeline import runner


def test_persist_explore_bootstrap_artifacts_synthesizes_missing_schema_snapshot(monkeypatch) -> None:
    uploads: dict[str, bytes] = {}

    class _Runtime:
        prior_job_id = ""
        overlap_baseline_job_id = ""
        cap_profile = "deploy"
        max_rounds = 4
        max_tool_calls = 8
        max_functions = 50
        min_direct_probes = 1
        skip_documented = True
        deterministic_fallback_enabled = True
        gap_resolution_enabled = True
        clarification_enabled = True
        analysis_profile = "strict_dll"
        variant_configs: list[dict] = []
        parallel_runs = 1
        lane_id = "lane-a"
        variant_id = ""
        cross_dll_prior_job_ids: list[str] = []
        checkpoint_id = "source-job"
        checkpoint_stage = "s02_probe"
        cluster_checkpoint_id = "pricing_quote_lifecycle"
        adjacent_cluster_id = ""
        cluster_confidence_floor = 0.5
        focus_functions = ["PR_BeginQuote", "PR_GetQuoteNonce"]
        skip_to_stage = ""
        skip_to_stage_reason = ""
        seed_strategy = "default_cluster_seed"
        seed_default_applied = True
        seed_default_reason = "prior_job_focus_cluster_inference"

    class _Ctx:
        runtime = _Runtime()
        invocables = [{"name": "WF_CreateReservation", "description": "Create reservation", "parameters": []}]

    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {"component_name": "contoso_workflow", "explore_runtime": {"mode": "normal"}},
    )
    monkeypatch.setattr(runner, "_download_blob", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(runner, "_build_tool_schemas", lambda invocables: [{"type": "function", "function": {"name": invocables[0]["name"]}}])
    monkeypatch.setattr(runner, "_upload_to_blob", lambda _c, name, data: uploads.setdefault(name, data) or name)

    prior_seeded = runner._persist_explore_bootstrap_artifacts("job-bootstrap", _Ctx())  # noqa: SLF001

    assert prior_seeded == 0
    assert "job-bootstrap/mcp_schema.json" in uploads
    assert "job-bootstrap/mcp_schema_t0.json" in uploads
    config = __import__("json").loads(uploads["job-bootstrap/explore_config.json"])
    assert config["cluster_checkpoint_id"] == "pricing_quote_lifecycle"
    assert config["checkpoint_stage"] == "s02_probe"
    assert config["focus_functions"] == ["PR_BeginQuote", "PR_GetQuoteNonce"]
    assert config["seed_strategy"] == "default_cluster_seed"
    assert config["seed_default_applied"] is True
    schema = uploads["job-bootstrap/mcp_schema_t0.json"].decode("utf-8")
    assert "contoso_workflow" in schema
    assert "WF_CreateReservation" in schema


def test_persist_explore_bootstrap_artifacts_keeps_runtime_normalized_t0_when_raw_schema_exists(monkeypatch) -> None:
    uploads: dict[str, bytes] = {}
    raw_schema = b'{"component":"raw","tools":[{"function":{"name":"SP_CommitRelease","parameters":{"properties":{"param_1":{"type":"integer"}}}}}]}'

    class _Runtime:
        prior_job_id = ""
        overlap_baseline_job_id = ""
        cap_profile = "deploy"
        max_rounds = 4
        max_tool_calls = 8
        max_functions = 50
        min_direct_probes = 1
        skip_documented = True
        deterministic_fallback_enabled = True
        gap_resolution_enabled = True
        clarification_enabled = True
        analysis_profile = "strict_dll"
        variant_configs: list[dict] = []
        parallel_runs = 1
        lane_id = "lane-a"
        variant_id = ""
        cross_dll_prior_job_ids: list[str] = []
        checkpoint_id = ""
        checkpoint_stage = ""
        cluster_checkpoint_id = ""
        adjacent_cluster_id = ""
        cluster_confidence_floor = 0.0
        focus_functions: list[str] = []
        skip_to_stage = ""
        skip_to_stage_reason = ""
        seed_strategy = ""
        seed_default_applied = False
        seed_default_reason = ""

    class _Ctx:
        runtime = _Runtime()
        invocables = [
            {
                "name": "SP_CommitRelease",
                "description": "Commit release",
                "parameters": [
                    {"name": "param_1", "type": "char *", "json_type": "string", "description": "must start with \"sp-resv-\""},
                    {"name": "param_2", "type": "char *", "json_type": "string", "description": "must start with \"sp-hold-\""},
                ],
            }
        ]

    def _download(_container: str, name: str) -> bytes:
        if name.endswith("/mcp_schema.json"):
            return raw_schema
        raise FileNotFoundError(name)

    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {"component_name": "release_commit", "explore_runtime": {"mode": "normal"}},
    )
    monkeypatch.setattr(runner, "_download_blob", _download)
    monkeypatch.setattr(runner, "_upload_to_blob", lambda _c, name, data: uploads.setdefault(name, data) or name)

    runner._persist_explore_bootstrap_artifacts("job-bootstrap", _Ctx())  # noqa: SLF001

    assert "job-bootstrap/mcp_schema.json" not in uploads
    t0_schema = uploads["job-bootstrap/mcp_schema_t0.json"].decode("utf-8")
    assert '"component": "release_commit"' in t0_schema
    assert '"type": "string"' in t0_schema
    assert 'sp-resv-' in t0_schema


def test_seed_prior_verified_findings_saves_when_current_job_has_no_row(monkeypatch) -> None:
    saved: list[tuple[str, list[dict]]] = []
    patched: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(runner, "_seed_findings", lambda job_id, entries: saved.append((job_id, entries)))
    monkeypatch.setattr(runner, "_patch_finding", lambda job_id, fn, patch: patched.append((job_id, fn, patch)))

    seeded = runner._seed_prior_verified_findings(  # noqa: SLF001
        job_id="job-1",
        prior_job_id="prior-1",
        current_findings=[],
        prior_findings=[
            {
                "function": "CS_ProcessPayment",
                "status_canonical": "verified_success",
                "finding": "seeded",
                "working_call": {"param_1": "CUST-001", "param_2": 1},
            }
        ],
        invocables_by_name={
            "CS_ProcessPayment": {
                "name": "CS_ProcessPayment",
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": "Customer identifier"},
                    {"name": "param_2", "json_type": "integer", "description": "Payment count"},
                ],
            }
        },
    )

    assert seeded == {"CS_ProcessPayment"}
    assert len(saved) == 1
    assert not patched
    assert saved[0][1][0]["source"] == "prior_session"
    assert saved[0][1][0]["status"] == "success"


def test_seed_prior_verified_findings_patches_when_row_already_exists(monkeypatch) -> None:
    saved: list[tuple[str, list[dict]]] = []
    patched: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(runner, "_seed_findings", lambda job_id, entries: saved.append((job_id, entries)))
    monkeypatch.setattr(runner, "_patch_finding", lambda job_id, fn, patch: patched.append((job_id, fn, patch)))

    seeded = runner._seed_prior_verified_findings(  # noqa: SLF001
        job_id="job-1",
        prior_job_id="prior-1",
        current_findings=[{"function": "CS_ProcessPayment"}],
        prior_findings=[
            {
                "function": "CS_ProcessPayment",
                "status_canonical": "verified_success",
                "finding": "seeded",
                "working_call": {"param_1": "CUST-001", "param_2": 1},
            }
        ],
        invocables_by_name={
            "CS_ProcessPayment": {
                "name": "CS_ProcessPayment",
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": "Customer identifier"},
                    {"name": "param_2", "json_type": "integer", "description": "Payment count"},
                ],
            }
        },
    )

    assert seeded == {"CS_ProcessPayment"}
    assert not saved
    assert len(patched) == 1
    assert patched[0][2]["source"] == "prior_session"


def test_seed_prior_verified_findings_skips_seed_ineligible_success(monkeypatch) -> None:
    saved: list[tuple[str, list[dict]]] = []
    patched: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(runner, "_seed_findings", lambda job_id, entries: saved.append((job_id, entries)))
    monkeypatch.setattr(runner, "_patch_finding", lambda job_id, fn, patch: patched.append((job_id, fn, patch)))

    seeded = runner._seed_prior_verified_findings(  # noqa: SLF001
        job_id="job-1",
        prior_job_id="prior-1",
        current_findings=[],
        prior_findings=[
            {
                "function": "CS_ProcessPayment",
                "status_canonical": "verified_success",
                "finding": "returned 0",
                "working_call": {"param_1": "ACC-USB-C", "param_2": 1},
            }
        ],
        invocables_by_name={
            "CS_ProcessPayment": {
                "name": "CS_ProcessPayment",
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": "Customer identifier"},
                    {"name": "param_2", "json_type": "integer", "description": "Payment count"},
                ],
            }
        },
    )

    assert seeded == set()
    assert not saved
    assert not patched


def test_build_explore_context_without_prior_findings_does_not_touch_seeded_functions(monkeypatch) -> None:
    monkeypatch.setattr(runner, "_get_job_status", lambda job_id: {"explore_runtime": {}})
    monkeypatch.setattr(runner, "_merge_invocables", lambda job_id, invocables: None)
    monkeypatch.setattr(runner, "_build_tool_schemas", lambda invocables: [])
    monkeypatch.setattr(runner, "_openai_client", lambda: object())
    monkeypatch.setattr(runner, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(runner, "_load_prior_session_artifacts", lambda prior_job_id: {})
    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "OPENAI_EXPLORE_MODEL", "test-model")

    ctx = runner._build_explore_context("job-1", [{"name": "CP_Initialize"}])  # noqa: SLF001

    assert ctx.runtime.prior_job_id == ""
    assert ctx.live_findings == []
    assert ctx.already_explored == set()


def test_build_explore_context_preserves_focused_and_init_functions_under_session_cap(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {"explore_runtime": {"max_functions": 1, "focus_functions": ["CP_ReserveStock"]}},
    )
    monkeypatch.setattr(runner, "_merge_invocables", lambda job_id, invocables: None)
    monkeypatch.setattr(runner, "_build_tool_schemas", lambda invocables: [])
    monkeypatch.setattr(runner, "_openai_client", lambda: object())
    monkeypatch.setattr(runner, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(runner, "_load_prior_session_artifacts", lambda prior_job_id: {})
    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "OPENAI_EXPLORE_MODEL", "test-model")

    ctx = runner._build_explore_context(  # noqa: SLF001
        "job-1",
        [
            {"name": "CP_Initialize"},
            {"name": "CP_ProcessPurchase"},
            {"name": "CP_ReserveStock"},
        ],
    )

    assert [inv["name"] for inv in ctx.invocables] == ["CP_Initialize", "CP_ReserveStock"]
    assert ctx.total == 2


def test_build_explore_context_merges_prior_invocable_metadata_before_curriculum(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {"explore_runtime": {"prior_job_id": "prior-1"}},
    )
    monkeypatch.setattr(runner, "_merge_invocables", lambda job_id, invocables: None)
    monkeypatch.setattr(runner, "_build_tool_schemas", lambda invocables: [])
    monkeypatch.setattr(runner, "_openai_client", lambda: object())
    monkeypatch.setattr(runner, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(runner, "_load_prior_session_artifacts", lambda prior_job_id: {})
    monkeypatch.setattr(
        runner,
        "_load_prior_invocables",
        lambda prior_job_id: [
            {
                "name": "WF_OpenFulfillment",
                "description": "Prior enriched description",
                "parameters": [
                    {"name": "lpszResvId", "json_type": "string", "description": "Reservation ID"}
                ],
            }
        ],
    )
    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "OPENAI_EXPLORE_MODEL", "test-model")

    ctx = runner._build_explore_context(  # noqa: SLF001
        "job-1",
        [
            {
                "name": "WF_OpenFulfillment",
                "execution": {"dll_path": "current.dll"},
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": ""}
                ],
            }
        ],
    )

    inv = ctx.inv_map["WF_OpenFulfillment"]
    assert inv["description"] == "Prior enriched description"
    assert inv["execution"]["dll_path"] == "current.dll"
    assert inv["parameters"][0]["name"] == "lpszResvId"


def test_build_explore_context_uses_overlap_baseline_without_seeding_prior_findings(monkeypatch) -> None:
    uploads: dict[str, bytes] = {}

    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {"explore_runtime": {"overlap_baseline_job_id": "baseline-1", "campaign_id": "camp-1"}},
    )
    monkeypatch.setattr(runner, "_merge_invocables", lambda job_id, invocables: None)
    monkeypatch.setattr(runner, "_build_tool_schemas", lambda invocables: [])
    monkeypatch.setattr(runner, "_openai_client", lambda: object())
    monkeypatch.setattr(runner, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(
        runner,
        "_load_prior_session_artifacts",
        lambda prior_job_id: {
            "findings": [
                {"function": "PR_BeginQuote", "status_canonical": "verified_success"},
            ],
            "vocab": {"id_formats": ["QTE-####", "CUST-###"]},
            "sentinels": {0xDEADBEEF: "baseline"},
        } if prior_job_id == "baseline-1" else {},
    )
    monkeypatch.setattr(
        runner,
        "_load_prior_invocables",
        lambda prior_job_id: [
            {
                "name": "PR_BeginQuote",
                "description": "Begin quote using customer and sku context",
                "parameters": [
                    {"name": "lpszCustomerId", "json_type": "string", "description": "Customer identifier"},
                    {"name": "lpszSku", "json_type": "string", "description": "SKU"},
                    {"name": "pOutQuoteId", "json_type": "string", "description": "Output quote id"},
                ],
            }
        ] if prior_job_id == "baseline-1" else [],
    )
    monkeypatch.setattr(
        runner,
        "_download_blob",
        lambda _container, blob_name: (
            b'{"candidates":{"customer_id":[{"value":"CUST-001","tier":2,"source":"working_call:PR_BeginQuote","param_kind":"customer_id","confidence":1.0,"discovered_at":"PR_BeginQuote"}]}}'
            if blob_name == "baseline-1/evidence_candidates.json"
            else (_ for _ in ()).throw(FileNotFoundError())
        ),
    )
    monkeypatch.setattr(runner, "_upload_to_blob", lambda _c, name, data: uploads.setdefault(name, data) or name)
    monkeypatch.setattr(runner, "_seed_prior_verified_findings", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not seed prior findings from overlap baseline")))
    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "OPENAI_EXPLORE_MODEL", "test-model")

    ctx = runner._build_explore_context(  # noqa: SLF001
        "job-1",
        [
            {
                "name": "PR_BeginQuote",
                "execution": {"dll_path": "current.dll"},
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": ""},
                    {"name": "param_2", "json_type": "string", "description": ""},
                    {"name": "param_3", "json_type": "string", "description": ""},
                ],
            }
        ],
    )

    assert ctx.runtime.prior_job_id == ""
    assert ctx.runtime.overlap_baseline_job_id == "baseline-1"
    assert ctx.already_explored == set()
    assert ctx.inv_map["PR_BeginQuote"]["parameters"][0]["name"] == "lpszCustomerId"
    assert ctx.vocab["id_formats"] == ["QTE-####", "CUST-###"]
    assert "job-1/overlap_baseline_context.json" in uploads
    customer_candidates = ctx.evidence_candidates.query("customer_id", "string", max_results=1)
    assert customer_candidates[0].value == "CUST-001"
    assert customer_candidates[0].source.startswith("overlap_baseline:")


def test_explore_worker_marks_error_when_llm_config_missing(monkeypatch) -> None:
    persisted: list[tuple[str, dict]] = []

    monkeypatch.setattr(runner, "OPENAI_API_KEY", "")
    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {"status": "done", "explore_phase": "queued"},
    )
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda job_id, payload: persisted.append((job_id, payload)),
    )

    runner._explore_worker("job-missing-llm", [{"name": "CP_Initialize"}])  # noqa: SLF001

    assert len(persisted) == 1
    job_id, payload = persisted[0]
    assert job_id == "job-missing-llm"
    assert payload["explore_phase"] == "error"
    assert "OPENAI_API_KEY" in payload["error"]


def test_set_explore_status_uses_terminal_stage_as_phase(monkeypatch) -> None:
    persisted: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        helpers,
        "_get_job_status",
        lambda job_id: {"status": "done", "explore_phase": "exploring"},
    )
    monkeypatch.setattr(
        helpers,
        "_persist_job_status",
        lambda job_id, payload: persisted.append((job_id, payload)),
    )

    helpers._set_explore_status(  # noqa: SLF001
        "job-terminal-phase",
        13,
        13,
        "Complete - done",
        stage="done",
    )

    assert len(persisted) == 1
    job_id, payload = persisted[0]
    assert job_id == "job-terminal-phase"
    assert payload["explore_phase"] == "done"
    assert payload["explore_progress"] == "13/13"


def test_explore_worker_populates_focus_from_evidence_graph_before_stage_ladder(monkeypatch) -> None:
    class _Runtime:
        cap_profile = "deploy"
        max_rounds = 4
        max_tool_calls = 8
        max_functions = 50
        min_direct_probes = 1
        skip_documented = True
        deterministic_fallback_enabled = True
        gap_resolution_enabled = True
        clarification_enabled = True
        analysis_profile = "strict_dll"
        variant_configs: list[dict] = []
        parallel_runs = 1
        lane_id = "lane-a"
        variant_id = ""
        prior_job_id = ""
        overlap_baseline_job_id = ""
        cross_dll_prior_job_ids: list[str] = []
        checkpoint_id = ""
        checkpoint_stage = ""
        skip_to_stage = ""
        skip_to_stage_reason = "new_cross_dll_evidence"
        focus_functions: list[str] = []

    class _Ctx:
        job_id = "job-focus"
        runtime = _Runtime()
        total = 1
        vocab: dict = {}
        variant_id = "variant-a"
        lane_id = "lane-a"
        invocables = [{"name": "CP_Initialize"}]
        static_analysis_result: dict = {}
        ghidra_data_types: list = []
        sentinels: dict = {}
        unlock_result = {"unlocked": False}
        evidence_candidates = None

        @staticmethod
        def cost_summary() -> dict:
            return {}

    class _StubGraph:
        entities: dict = {}
        functions: dict = {}

        @staticmethod
        def context_slice(_dll_fp: str) -> dict:
            return {}

        @staticmethod
        def re_probe_recommendations(_dll_fp: str) -> list[dict]:
            return [{"function": "CP_ProcessPayment"}]

    persisted: list[tuple[str, dict, bool]] = []
    ctx = _Ctx()

    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "_build_explore_context", lambda _job_id, _inv: ctx)
    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda _job_id: {"explore_runtime": {"mode": "normal"}, "dll_fingerprint": "dll-fp-1"},
    )
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append((job_id, payload, bool(sync))) or True,
    )
    monkeypatch.setattr(runner, "_upload_to_blob", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(runner, "_download_blob", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(runner, "_cancel_requested", lambda _job_id: False)

    from api.pipeline.core import evidence_graph as _evidence_graph_module
    monkeypatch.setattr(
        _evidence_graph_module.EvidenceGraph,
        "load_blob",
        classmethod(lambda cls, _container: _StubGraph()),
    )

    from api.pipeline import s00_setup as _s00_setup
    monkeypatch.setattr(_s00_setup, "run_s00", lambda _ctx: (_ for _ in ()).throw(RuntimeError("stop-after-focus")))

    runner._explore_worker("job-focus", [{"name": "CP_Initialize"}])  # noqa: SLF001

    assert ctx.runtime.focus_functions == ["CP_ProcessPayment"]
    assert persisted, "worker should persist an error status after sentinel stop exception"


def test_build_explore_context_augments_focus_from_cluster_seed(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {
            "explore_runtime": {
                "checkpoint_id": "source-job",
                "checkpoint_stage": "s03_reconcile",
                "cluster_checkpoint_id": "workflow_reservation_open_state",
            }
        },
    )
    monkeypatch.setattr(runner, "load_checkpoint", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        runner,
        "resolve_cluster_seed_plan",
        lambda *_args, **_kwargs: type(
            "_Plan",
            (),
            {"focus_functions": ("WF_CreateReservation", "WF_GetWorkflowState")},
        )(),
    )
    monkeypatch.setattr(runner, "_merge_invocables", lambda job_id, invocables: None)
    monkeypatch.setattr(runner, "_build_tool_schemas", lambda invocables: [])
    monkeypatch.setattr(runner, "_openai_client", lambda: object())
    monkeypatch.setattr(runner, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(runner, "_load_prior_session_artifacts", lambda prior_job_id: {})
    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "OPENAI_EXPLORE_MODEL", "test-model")

    ctx = runner._build_explore_context(  # noqa: SLF001
        "job-1",
        [
            {"name": "WF_Initialize"},
            {"name": "WF_CreateReservation"},
            {"name": "WF_GetWorkflowState"},
            {"name": "WF_CancelWorkflow"},
        ],
    )

    assert [inv["name"] for inv in ctx.invocables] == [
        "WF_Initialize",
        "WF_CreateReservation",
        "WF_GetWorkflowState",
        "WF_CancelWorkflow",
    ]
    assert ctx.runtime.focus_functions == ["WF_CreateReservation", "WF_GetWorkflowState"]


def test_build_explore_context_normalizes_tool_schema_char_pointer_inputs_before_schema_build(monkeypatch) -> None:
    monkeypatch.setattr(runner, "_get_job_status", lambda job_id: {"explore_runtime": {}})
    monkeypatch.setattr(runner, "_merge_invocables", lambda job_id, invocables: None)
    monkeypatch.setattr(runner, "_openai_client", lambda: object())
    monkeypatch.setattr(runner, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(runner, "_load_prior_session_artifacts", lambda prior_job_id: {})
    monkeypatch.setattr(runner, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "OPENAI_EXPLORE_MODEL", "test-model")

    ctx = runner._build_explore_context(  # noqa: SLF001
        "job-1",
        [
            {
                "name": "SP_CommitRelease",
                "parameters": [
                    {
                        "name": "param_1",
                        "type": "char *",
                        "resolved_type": "char *",
                        "direction": "in",
                        "json_type": "integer",
                        "description": "Parameter recovered by Ghidra decompiler",
                    },
                    {
                        "name": "param_2",
                        "type": "char *",
                        "resolved_type": "char *",
                        "direction": "in",
                        "json_type": "integer",
                        "description": "Parameter recovered by Ghidra decompiler",
                    },
                    {
                        "name": "param_3",
                        "type": "undefined *",
                        "resolved_type": "undefined *",
                        "direction": "out",
                        "json_type": "string",
                        "description": "Output buffer",
                    },
                    {
                        "name": "param_4",
                        "type": "uint",
                        "resolved_type": "uint",
                        "direction": "in",
                        "json_type": "integer",
                        "description": "Integer input parameter",
                    },
                ],
                "doc_comment": (
                    'strncmp(param_1,"sp-resv-",8) != 0 || '
                    'strncmp(param_2,"sp-hold-",8) != 0'
                ),
            }
        ],
    )

    props = ctx.tool_schemas[0]["function"]["parameters"]["properties"]
    assert props["param_1"]["type"] == "string"
    assert 'must start with "sp-resv-"' in props["param_1"]["description"]
    assert props["param_2"]["type"] == "string"
    assert 'must start with "sp-hold-"' in props["param_2"]["description"]


def test_persist_convergence_summary_records_narrower_repeat_surface(monkeypatch) -> None:
    uploads: dict[str, dict] = {}

    class _Runtime:
        cluster_checkpoint_id = "pricing_quote_lifecycle"
        checkpoint_id = "26ddca42"
        prior_job_id = "26ddca42"
        pass_index = 1
        pass_scope_profile = "foundation"
        focus_functions = [
            "PR_BeginQuote",
            "PR_GetQuoteNonce",
            "PR_ApproveRuleWindow",
            "PR_ApplyBundleOverride",
            "PR_GetQuoteState",
            "PR_SealQuote",
        ]
        seed_strategy = "default_cluster_seed"
        seed_default_applied = True
        seed_default_reason = "prior_job_focus_cluster_inference"

    class _Ctx:
        runtime = _Runtime()

    current_findings = [
        {"function": "PR_BeginQuote", "status": "success", "status_canonical": "verified_success", "working_call": {"pOutQuoteId": "PRQ-CUST-001-03"}, "source": "checkpoint_resume"},
        {"function": "PR_GetQuoteNonce", "status": "success", "status_canonical": "verified_success", "working_call": {"pdwNonceOut": 1500757424}, "source": "checkpoint_resume"},
        {"function": "PR_ApproveRuleWindow", "status": "success", "status_canonical": "verified_success", "working_call": {"dwNonce": 1500757424}, "source": "checkpoint_resume"},
        {"function": "PR_ApplyBundleOverride", "status": "error", "status_canonical": "error", "working_call": None},
        {"function": "PR_GetQuoteState", "status": "success", "status_canonical": "verified_success", "working_call": {"lpszQuoteId": "PRQ-CUST-001-03"}},
        {"function": "PR_SealQuote", "status": "error", "status_canonical": "error", "working_call": None},
    ]

    def _fake_download(_container: str, blob_name: str) -> bytes:
        if blob_name == "job-current/explore_config.json":
            return __import__("json").dumps({"focus_functions": _Runtime.focus_functions, "pass_index": 1, "pass_scope_profile": "foundation"}).encode("utf-8")
        if blob_name == "job-current/stage_kpis.json":
            return __import__("json").dumps({"cost_summary": {"wall_time_s": 120.0}}).encode("utf-8")
        if blob_name == "26ddca42/findings.json":
            return __import__("json").dumps(
                [{"function": f"FN_{idx}", "status": "success", "status_canonical": "verified_success", "working_call": {"param": idx}} for idx in range(10)]
                + [
                    {"function": "PR_BeginQuote", "status": "success", "status_canonical": "verified_success", "working_call": {"pOutQuoteId": ""}},
                    {"function": "PR_GetQuoteState", "status": "error", "status_canonical": "error"},
                ]
            ).encode("utf-8")
        if blob_name == "26ddca42/explore_config.json":
            return __import__("json").dumps({"focus_functions": [], "pass_index": 1, "pass_scope_profile": "foundation"}).encode("utf-8")
        if blob_name == "26ddca42/stage_kpis.json":
            return __import__("json").dumps({"cost_summary": {"wall_time_s": 560.16}}).encode("utf-8")
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(runner, "_load_findings", lambda job_id: current_findings if job_id == "job-current" else [])
    monkeypatch.setattr(runner, "_download_blob", _fake_download)
    monkeypatch.setattr(
        runner,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))) or blob_name,
    )

    runner._persist_convergence_summary("job-current", _Ctx())  # noqa: SLF001

    summary = uploads["job-current/convergence_summary.json"]
    assert summary["seed_strategy"] == "default_cluster_seed"
    assert summary["current"]["surface_function_count"] == 6
    assert summary["baseline"]["surface_function_count"] == 12
    assert summary["current"]["consumer_coverage"]["coverage_ratio"] == 1.0
    assert "narrower" in summary["movement"]["compression_reasons"]
