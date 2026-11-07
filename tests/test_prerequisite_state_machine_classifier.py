from types import SimpleNamespace

from api.pipeline.core.evidence_candidates import build_prerequisite_dag, _classify_param_kind
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.s02_probe import curriculum
from api.pipeline.s02_probe.curriculum import _run_phase_2_curriculum_order
from api.pipeline.s02_probe.probe_loop import _extract_required_preconditions


def test_build_prerequisite_dag_promotes_explicit_preconditions_into_edges_and_roles() -> None:
    invocables = [
        {"name": "WF_Initialize", "parameters": []},
        {"name": "WF_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}]},
        {
            "name": "WF_CreateReservation",
            "parameters": [
                {"name": "lpszSku", "json_type": "string", "description": "SKU"},
                {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation ID output"},
            ],
            "doc_comment": "Required preconditions: WF_BindCustomer | Canonical args: {\"lpszSku\":\"ACC-USB-C\"}",
        },
    ]

    roles, edges = build_prerequisite_dag(invocables, ["CUST-001"])
    role_map = {role.name: role for role in roles}

    assert role_map["WF_CreateReservation"].prerequisites == ["WF_BindCustomer", "WF_Initialize"]
    assert role_map["WF_CreateReservation"].sequence_role == "lifecycle_transition"
    assert any(
        edge.producer == "WF_BindCustomer"
        and edge.consumer == "WF_CreateReservation"
        and edge.shared_kind == "explicit_precondition"
        for edge in edges
    )


def test_build_prerequisite_dag_infers_bind_gate_from_decompiled_text() -> None:
    invocables = [
        {"name": "CFG_Initialize", "parameters": []},
        {"name": "CFG_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}]},
        {
            "name": "CFG_OpenLicensedWindow",
            "parameters": [
                {"name": "pOutTicket", "json_type": "string", "direction": "out", "description": "Output config ticket"},
                {"name": "dwBufLen", "json_type": "integer", "description": "Ticket buffer size"},
            ],
            "doc_comment": "if (!g_bInitialised || g_szCustomer[0] == '\\0') { _set_last_error(\"customer binding required\"); return CFG_ERR_PRECONDITION; }",
        },
    ]

    roles, edges = build_prerequisite_dag(invocables, ["CUST-001"])
    role_map = {role.name: role for role in roles}

    assert "CFG_BindCustomer" in role_map["CFG_OpenLicensedWindow"].prerequisites
    assert role_map["CFG_OpenLicensedWindow"].sequence_role == "lifecycle_transition"
    assert any(
        edge.producer == "CFG_BindCustomer"
        and edge.consumer == "CFG_OpenLicensedWindow"
        and edge.shared_kind == "heuristic_gate"
        for edge in edges
    )


def test_build_prerequisite_dag_does_not_treat_open_as_initializer() -> None:
    invocables = [
        {"name": "WF_Initialize", "parameters": []},
        {
            "name": "WF_OpenFulfillment",
            "parameters": [
                {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
                {"name": "pOutHandle", "json_type": "integer", "direction": "out", "description": "Workflow handle"},
            ],
            "doc_comment": "Reservation created required before workflow open.",
        },
    ]

    roles, _ = build_prerequisite_dag(invocables, [])
    role_map = {role.name: role for role in roles}

    assert role_map["WF_OpenFulfillment"].role != "init"
    assert role_map["WF_OpenFulfillment"].sequence_role == "lifecycle_transition"


def test_build_prerequisite_dag_infers_reservation_producer_before_open() -> None:
    invocables = [
        {"name": "WF_Initialize", "parameters": []},
        {
            "name": "WF_CreateReservation",
            "parameters": [
                {"name": "lpszSku", "json_type": "string", "description": "SKU"},
                {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation ID output"},
            ],
        },
        {
            "name": "WF_OpenFulfillment",
            "parameters": [
                {"name": "param_1", "json_type": "integer", "description": "Reservation identifier", "resolved_type": "char *"},
                {"name": "param_2", "json_type": "integer", "direction": "out", "description": "Workflow handle"},
                {"name": "param_3", "json_type": "integer", "description": "Buffer size"},
            ],
            "doc_comment": "Requires a valid reservation ID before fulfillment can be opened.",
        },
    ]

    roles, edges = build_prerequisite_dag(invocables, [])
    role_map = {role.name: role for role in roles}

    assert "WF_CreateReservation" in role_map["WF_OpenFulfillment"].prerequisites
    assert any(
        edge.producer == "WF_CreateReservation"
        and edge.consumer == "WF_OpenFulfillment"
        and edge.shared_kind == "heuristic_gate"
        for edge in edges
    )


def test_classify_param_kind_does_not_treat_reservation_producer_inputs_as_reservation_ids() -> None:
    assert _classify_param_kind(
        {
            "name": "lpszSku",
            "json_type": "integer",
            "description": "The SKU of the product being reserved (e.g., 'ACC-USB-C').",
        }
    ) == "sku"
    assert _classify_param_kind(
        {
            "name": "wQty",
            "json_type": "integer",
            "description": "The quantity of the product to reserve (must be greater than 0, e.g., 2).",
        }
    ) == "integer"
    assert _classify_param_kind(
        {
            "name": "dwHoldMinutes",
            "json_type": "string",
            "description": "Duration in minutes for which the reservation is held (e.g., 30).",
        }
    ) == "integer"


def test_build_prerequisite_dag_refuses_weak_sequence_claims() -> None:
    invocables = [
        {"name": "ZZ_DoThing", "parameters": [{"name": "param_1", "json_type": "string", "description": "Arbitrary text"}]},
        {"name": "ZZ_GetThing", "parameters": [{"name": "param_1", "json_type": "string", "description": "Arbitrary text"}], "doc_comment": "No useful sequencing hints are present here."},
    ]

    roles, edges = build_prerequisite_dag(invocables, [])
    role_map = {role.name: role for role in roles}

    assert role_map["ZZ_GetThing"].sequence_role == "unknown"
    assert role_map["ZZ_GetThing"].prerequisites == []
    assert not any(edge.consumer == "ZZ_GetThing" and edge.shared_kind == "heuristic_gate" for edge in edges)


def test_build_prerequisite_dag_filters_self_prerequisites() -> None:
    invocables = [
        {"name": "CFG_Initialize", "parameters": []},
        {
            "name": "CFG_ApproveLicensedCall",
            "parameters": [
                {"name": "lpszTicket", "json_type": "string", "description": "Ticket"},
                {"name": "dwNonce", "json_type": "integer", "description": "Nonce"},
            ],
            "doc_comment": "Required preconditions: CFG_GetLicenseNonce",
        },
        {
            "name": "CFG_GetLicenseNonce",
            "parameters": [
                {"name": "lpszTicket", "json_type": "string", "description": "Ticket"},
                {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Output nonce"},
            ],
            "doc_comment": "license approval required before final approved call",
        },
    ]

    roles, _ = build_prerequisite_dag(invocables, [])
    role_map = {role.name: role for role in roles}

    assert "CFG_ApproveLicensedCall" not in role_map["CFG_ApproveLicensedCall"].prerequisites


def test_pricing_curriculum_keeps_quote_producer_ahead_of_nonce_consumer_on_pass_1() -> None:
    invocables = [
        {"name": "PR_Initialize", "parameters": []},
        {
            "name": "PR_LoadSkuContext",
            "parameters": [
                {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            ],
            "doc_comment": "Required preconditions: PR_Initialize",
        },
        {
            "name": "PR_BeginQuote",
            "parameters": [
                {"name": "pOutQuoteId", "json_type": "string", "direction": "out", "description": "Output quote id"},
                {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
            ],
            "doc_comment": "Required preconditions: PR_LoadSkuContext",
        },
        {
            "name": "PR_GetQuoteNonce",
            "parameters": [
                {"name": "lpszQuoteId", "json_type": "string", "description": "Quote id"},
                {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Output nonce"},
            ],
            "doc_comment": "Required preconditions: PR_BeginQuote",
        },
    ]

    ctx = SimpleNamespace(
        job_id="pricing-pass1",
        invocables=[dict(inv) for inv in invocables],
        vocab={"id_formats": ["PRQ-CUST-001-03"]},
        call_graph={},
        runtime=ExploreRuntime(pass_index=1, pass_scope_profile="foundation"),
    )

    original_upload = curriculum._upload_to_blob
    curriculum._upload_to_blob = lambda *_args, **_kwargs: None
    try:
        curriculum._run_phase_2_curriculum_order(ctx)
    finally:
        curriculum._upload_to_blob = original_upload

    ordered = [inv["name"] for inv in ctx.invocables]
    assert ordered.index("PR_BeginQuote") < ordered.index("PR_GetQuoteNonce")


def test_build_prerequisite_dag_config_flow_refuses_backward_lifecycle_edges() -> None:
    invocables = [
        {"name": "CFG_Initialize", "parameters": [], "doc_comment": "not initialized"},
        {
            "name": "CFG_SetupEnvironment",
            "parameters": [{"name": "dwMode", "json_type": "integer", "description": "Mode"}],
        },
        {
            "name": "CFG_BindCustomer",
            "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
            "doc_comment": "Required preconditions: CFG_Initialize",
        },
        {
            "name": "CFG_OpenLicensedWindow",
            "parameters": [
                {"name": "pOutTicket", "json_type": "string", "direction": "out", "description": "License ticket output"},
                {"name": "dwBufLen", "json_type": "integer", "description": "Ticket buffer size"},
            ],
            "doc_comment": "Required preconditions: CFG_BindCustomer, CFG_SetupEnvironment | licensed mode required",
        },
        {
            "name": "CFG_GetLicenseNonce",
            "parameters": [
                {"name": "lpszTicket", "json_type": "string", "description": "License ticket"},
                {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Output nonce"},
            ],
            "doc_comment": "Required preconditions: CFG_OpenLicensedWindow, CFG_BindCustomer | license approval required before final approved call",
        },
        {
            "name": "CFG_ApproveLicensedCall",
            "parameters": [
                {"name": "lpszTicket", "json_type": "string", "description": "Ticket"},
                {"name": "dwNonce", "json_type": "integer", "description": "Nonce"},
            ],
            "doc_comment": "Required preconditions: CFG_GetLicenseNonce",
        },
        {
            "name": "CFG_RunCustomerSync",
            "parameters": [{"name": "lpszTicket", "json_type": "string", "description": "Ticket"}],
            "doc_comment": "licensed approval required",
        },
    ]

    roles, _ = build_prerequisite_dag(invocables, [])
    role_map = {role.name: role for role in roles}

    assert role_map["CFG_Initialize"].prerequisites == []
    assert "CFG_OpenLicensedWindow" not in role_map["CFG_BindCustomer"].prerequisites
    assert "CFG_ApproveLicensedCall" not in role_map["CFG_GetLicenseNonce"].prerequisites
    assert "CFG_GetLicenseNonce" in role_map["CFG_ApproveLicensedCall"].prerequisites
    assert "CFG_ApproveLicensedCall" in role_map["CFG_RunCustomerSync"].prerequisites


def test_build_prerequisite_dag_excludes_entry_from_prerequisites() -> None:
    invocables = [
        {"name": "entry", "parameters": []},
        {"name": "RP_Initialize", "parameters": []},
        {"name": "RP_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}]},
        {
            "name": "RP_PrepareReservationReport",
            "parameters": [{"name": "lpszSku", "json_type": "string", "description": "SKU"}],
            "doc_comment": "Required preconditions: entry | RP_BindCustomer",
        },
    ]

    roles, _ = build_prerequisite_dag(invocables, ["CUST-001"])
    role_map = {role.name: role for role in roles}

    assert "entry" not in role_map["RP_PrepareReservationReport"].prerequisites
    assert "RP_BindCustomer" in role_map["RP_PrepareReservationReport"].prerequisites


def test_curriculum_patches_invocable_metadata_and_context(monkeypatch) -> None:
    monkeypatch.setattr("api.pipeline.s02_probe.curriculum._upload_to_blob", lambda *args, **kwargs: None)

    invocables = [
        {"name": "WF_Initialize", "parameters": []},
        {"name": "WF_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}]},
        {
            "name": "WF_CreateReservation",
            "parameters": [
                {"name": "lpszSku", "json_type": "string", "description": "SKU"},
                {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation ID output"},
            ],
            "doc_comment": "Required preconditions: WF_BindCustomer",
        },
    ]
    runtime = ExploreRuntime()
    ctx = ExploreContext(
        job_id="job-sequence",
        runtime=runtime,
        client=None,
        model="test-model",
        invocables=invocables,
        inv_map={inv["name"]: inv for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
        sentinels={},
        vocab={"id_formats": ["CUST-001"]},
    )

    _run_phase_2_curriculum_order(ctx)

    create_reservation = next(inv for inv in ctx.invocables if inv["name"] == "WF_CreateReservation")
    assert create_reservation["_required_preconditions"] == ["WF_BindCustomer", "WF_Initialize"]
    assert create_reservation["_sequence_role"] == "lifecycle_transition"
    assert ctx.prerequisite_map["WF_CreateReservation"] == ["WF_BindCustomer", "WF_Initialize"]
    assert ctx.execution_layers


def test_extract_required_preconditions_prefers_classifier_metadata() -> None:
    inv = {
        "name": "WF_OpenFulfillment",
        "_required_preconditions": ["WF_CreateReservation"],
        "doc_comment": "Required preconditions: WF_BindCustomer",
    }

    assert _extract_required_preconditions(inv) == ["WF_CreateReservation"]


def test_curriculum_foundation_pass_deprioritizes_hard_consumers(monkeypatch) -> None:
    monkeypatch.setattr("api.pipeline.s02_probe.curriculum._upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.pipeline.s02_probe.curriculum._uncertainty_score", lambda _inv: 0)

    roles = [
        SimpleNamespace(
            name="WF_Initialize",
            role="init",
            sequence_role="unknown",
            sequence_confidence=0.9,
            sequence_reasons=[],
            prerequisites=[],
            input_kinds=[],
            output_kinds=[],
        ),
        SimpleNamespace(
            name="WF_ApproveReservation",
            role="consumer",
            sequence_role="lifecycle_transition",
            sequence_confidence=0.7,
            sequence_reasons=["stateful consumer"],
            prerequisites=["WF_Initialize", "WF_GetReservationState"],
            input_kinds=[],
            output_kinds=[],
        ),
        SimpleNamespace(
            name="WF_GetReservationState",
            role="consumer",
            sequence_role="state_consumer",
            sequence_confidence=0.8,
            sequence_reasons=["read surface"],
            prerequisites=["WF_Initialize"],
            input_kinds=[],
            output_kinds=[],
        ),
    ]
    monkeypatch.setattr("api.pipeline.s02_probe.curriculum.build_prerequisite_dag", lambda *_args, **_kwargs: (roles, []))
    monkeypatch.setattr(
        "api.pipeline.s02_probe.curriculum.dag_to_execution_layers",
        lambda _roles, _edges: [["WF_Initialize", "WF_ApproveReservation", "WF_GetReservationState"]],
    )

    invocables = [
        {"name": "WF_Initialize", "parameters": []},
        {"name": "WF_ApproveReservation", "parameters": [{"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"}]},
        {"name": "WF_GetReservationState", "parameters": [{"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"}]},
    ]

    foundation_ctx = ExploreContext(
        job_id="job-foundation",
        runtime=ExploreRuntime(pass_index=1, pass_scope_profile="foundation"),
        client=None,
        model="test-model",
        invocables=[dict(inv) for inv in invocables],
        inv_map={inv["name"]: dict(inv) for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
        sentinels={},
        vocab={},
    )
    _run_phase_2_curriculum_order(foundation_ctx)

    later_ctx = ExploreContext(
        job_id="job-later",
        runtime=ExploreRuntime(pass_index=2, pass_scope_profile="later_pass"),
        client=None,
        model="test-model",
        invocables=[dict(inv) for inv in invocables],
        inv_map={inv["name"]: dict(inv) for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
        sentinels={},
        vocab={},
    )
    _run_phase_2_curriculum_order(later_ctx)

    foundation_names = [inv["name"] for inv in foundation_ctx.invocables]
    later_names = [inv["name"] for inv in later_ctx.invocables]

    assert foundation_names == ["WF_Initialize", "WF_GetReservationState", "WF_ApproveReservation"]
    assert later_names == ["WF_Initialize", "WF_ApproveReservation", "WF_GetReservationState"]
    approve = next(inv for inv in foundation_ctx.invocables if inv["name"] == "WF_ApproveReservation")
    assert approve["_pass_scope_reason"] == "deferred_deep_state_consumer"
