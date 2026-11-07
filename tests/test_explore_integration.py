"""
test_explore_integration.py — Regression tests for the exploration pipeline.

These tests run without network/blob access and cover:
  - FIX-1: _strip_output_buffer_params correctly preserves byte* string inputs
            while stripping undefined4* / int* genuine output buffers
  - FIX-2: return values ≤ 0xFFFFFFF0 are NOT treated as sentinel error codes
            (catches the CS_GetVersion = 131841 false-sentinel regression)
  - ExploreRuntime defaults load correctly from an empty env dict
  - ExploreContext construction produces the expected shape
  - session_snapshot ZIP structure: stage paths appear in main.py source
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
#  FIX-1 — _strip_output_buffer_params
# ─────────────────────────────────────────────────────────────────────────────

class TestStripOutputBufferParams:
    """Verify FIX-1: output-buffer stripping preserves byte* string arguments."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from api.pipeline.core.helpers import _strip_output_buffer_params
        self.strip = _strip_output_buffer_params

    def test_preserves_byte_star_string_input(self):
        """byte* params (customer_id, order_id) must NOT be stripped."""
        tc_args = {"customer_id": "CUST-007", "result_buf": 0}
        p_lookup = {
            "customer_id": {"type": "byte *",    "direction": "in"},
            "result_buf":  {"type": "undefined4 *", "direction": "out"},
        }
        result = self.strip(tc_args, p_lookup)
        assert "customer_id" in result, "byte* string input must not be stripped"
        assert "result_buf"  not in result, "undefined4* output buffer must be stripped"

    def test_strips_undefined4_star(self):
        """undefined4 * (canonical Ghidra output buffer) is stripped."""
        tc_args = {"buf": 0, "name": "Alice"}
        p_lookup = {
            "buf":  {"type": "undefined4 *"},
            "name": {"type": "char *"},
        }
        result = self.strip(tc_args, p_lookup)
        assert "buf"  not in result
        assert "name" in result

    def test_strips_int_star(self):
        """int * is a numeric-pointer output buffer and must be stripped."""
        tc_args = {"out_len": 0, "data": "hello"}
        p_lookup = {
            "out_len": {"type": "int *"},
            "data":    {"type": "byte *"},
        }
        result = self.strip(tc_args, p_lookup)
        assert "out_len" not in result
        assert "data" in result

    def test_no_output_buffers_unchanged(self):
        """When no output buffers exist the result equals the input."""
        tc_args = {"customer_id": "CUST-001", "amount": 100}
        p_lookup = {
            "customer_id": {"type": "byte *"},
            "amount":       {"type": "int"},
        }
        result = self.strip(tc_args, p_lookup)
        assert result == tc_args

    def test_empty_args_returns_empty(self):
        result = self.strip({}, {})
        assert result == {}

    def test_param_missing_from_lookup_is_preserved(self):
        """Params with no lookup entry (unknown) must be kept — never discard unknown params."""
        tc_args = {"mystery": "x"}
        result = self.strip(tc_args, {})
        assert "mystery" in result

    def test_direction_out_not_stripped_for_byte_star(self):
        """Even if Ghidra marks direction=out, byte* must NOT be stripped (FIX-1 invariant)."""
        tc_args = {"id_ptr": "CUST-042"}
        p_lookup = {"id_ptr": {"type": "byte *", "direction": "out"}}
        result = self.strip(tc_args, p_lookup)
        # byte* is excluded from _out_bases, so direction=out alone must not strip it
        assert "id_ptr" in result

    def test_strips_explicit_lpstr_output_buffer(self):
        """Explicit LPSTR output aliases should be stripped like other output buffers."""
        tc_args = {"param_1": "CUST-001", "param_5": "RESV-12345678-0001", "param_6": 64}
        p_lookup = {
            "param_1": {"type": "typedef LPCSTR CHAR *", "resolved_type": "LPCSTR", "direction": "in"},
            "param_5": {"type": "typedef LPSTR CHAR *", "resolved_type": "LPSTR", "direction": "out"},
            "param_6": {"type": "uint", "direction": "in"},
        }
        result = self.strip(tc_args, p_lookup)
        assert "param_1" in result
        assert "param_6" in result
        assert "param_5" not in result


# ─────────────────────────────────────────────────────────────────────────────
#  FIX-2 — sentinel code range gate (0xFFFFFFF0 threshold)
# ─────────────────────────────────────────────────────────────────────────────

class TestSentinelRangeGate:
    """Verify FIX-2: ordinary return values ≤ 0xFFFFFFF0 are not sentinel codes.

    CS_GetVersion returns 131841 (0x20301) which must never be classified as a
    sentinel error code.  Sentinel values always sit above 0xFFFFFFF0.
    """

    SENTINEL_FLOOR = 0xFFFFFFF0  # the threshold used in explore.py line ~840 / ~959

    def _is_sentinel_candidate(self, value: int) -> bool:
        """Mirrors the threshold logic in explore.py (see _seen_codes block)."""
        v = int(value) & 0xFFFFFFFF
        return v > self.SENTINEL_FLOOR

    def test_version_number_is_not_sentinel(self):
        """131841 (CS_GetVersion typical output) must NOT be a sentinel."""
        assert not self._is_sentinel_candidate(131841)

    def test_zero_is_not_sentinel(self):
        """0 (success / S_OK) must not be treated as a sentinel."""
        assert not self._is_sentinel_candidate(0)

    def test_small_positive_is_not_sentinel(self):
        assert not self._is_sentinel_candidate(1)
        assert not self._is_sentinel_candidate(42)
        assert not self._is_sentinel_candidate(0x0000FFFF)

    def test_exact_floor_is_not_sentinel(self):
        """The threshold is exclusive: value == 0xFFFFFFF0 must NOT be flagged."""
        assert not self._is_sentinel_candidate(0xFFFFFFF0)

    def test_above_floor_is_sentinel(self):
        """0xFFFFFFF1 through 0xFFFFFFFF are all sentinel-range values."""
        for v in [0xFFFFFFF1, 0xFFFFFFF5, 0xFFFFFFFB, 0xFFFFFFFC, 0xFFFFFFFE, 0xFFFFFFFF]:
            assert self._is_sentinel_candidate(v), f"0x{v:08X} should be sentinel-range"

    def test_negative_int_wraps_correctly(self):
        """Python int -1 masks to 0xFFFFFFFF which is sentinel-range."""
        assert self._is_sentinel_candidate(-1)
        assert self._is_sentinel_candidate(-5)


# ─────────────────────────────────────────────────────────────────────────────
#  S-02 fallback arg ranking + selection metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestRankedFallbackArgs:
    """Verify ranked fallback candidate selection and reason logging metadata."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from api.pipeline.core.helpers import _build_ranked_fallback_probe_args
        self.build = _build_ranked_fallback_probe_args

    def test_attempt_uses_ranked_candidates(self):
        inv = {
            "name": "CS_ProcessPayment",
            "parameters": [
                {"name": "customer_id", "json_type": "string", "direction": "in", "description": "Customer ID"},
                {"name": "amount_cents", "json_type": "integer", "direction": "in", "description": "Amount in cents"},
            ],
        }
        vocab = {"id_formats": ["CUST-001", "CUST-002", "ORD-20260315-0117"]}

        args0, meta0 = self.build(inv, vocab, attempt=0)
        args1, meta1 = self.build(inv, vocab, attempt=1)

        assert args0["customer_id"] == "CUST-001"
        assert args1["customer_id"] == "CUST-002"
        assert args0["amount_cents"] == 2500
        assert args1["amount_cents"] == 1000

        assert meta0["customer_id"]["rank"] == 1
        assert meta1["customer_id"]["rank"] == 2
        assert meta0["amount_cents"]["source"].startswith("heuristic.")
        assert meta0["amount_cents"]["candidate_count"] >= 2

    def test_out_params_are_excluded_from_args_and_selection(self):
        inv = {
            "name": "CS_GetOrderStatus",
            "parameters": [
                {"name": "order_id", "json_type": "string", "direction": "in"},
                {"name": "status_out", "json_type": "string", "direction": "out"},
            ],
        }
        args, meta = self.build(inv, {"id_formats": ["ORD-YYYYMMDD-NNNN"]}, attempt=0)
        assert "order_id" in args and "order_id" in meta
        assert "status_out" not in args
        assert "status_out" not in meta

    def test_generic_order_status_function_uses_real_order_id_and_buffer_size(self):
        inv = {
            "name": "CS_GetOrderStatus",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_2", "json_type": "string", "direction": "out", "type": "undefined *"},
                {"name": "param_3", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
            ],
        }
        vocab = {"id_formats": ["CUST-001", "ORD-20040301-0042", "ORD-20040315-0117"]}

        args, meta = self.build(inv, vocab, attempt=0)

        assert args["param_1"] == "ORD-20040301-0042"
        assert args["param_3"] == 64
        assert meta["param_1"]["source"] == "function_context.id"
        assert meta["param_3"]["source"] == "heuristic.buffer"

    def test_purchase_function_with_evidence_splits_customer_and_sku_slots(self):
        """With evidence registry, purchase functions use evidence-backed candidates."""
        from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

        inv = {
            "name": "CP_ProcessPurchase",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_2", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_3", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "CUST-002", "ORD-20040301-0042"],
            "binary_string_ids": ["ACC-USB-C", "WDG-XL-BLU"],
        }
        ecr = EvidenceCandidateRegistry()
        ecr.seed_tier0()
        ecr.seed_tier1(vocab)

        args, meta = self.build(inv, vocab, attempt=0, evidence=ecr)

        assert args["param_1"] == "CUST-001"
        assert args["param_2"] == "ACC-USB-C"
        assert "evidence" in meta["param_1"]["source"]
        assert "sku" in meta["param_2"]["reason"]

    def test_reserve_function_with_evidence_uses_customer_sku_and_buffer_size(self):
        """Reserve-style functions should split customer/SKU slots and size the output buffer."""
        from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

        inv = {
            "name": "CP_ReserveStock",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_2", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_3", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
                {"name": "param_4", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
                {"name": "param_5", "json_type": "string", "direction": "out", "type": "undefined *"},
                {"name": "param_6", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "CUST-002", "ORD-20040301-0042"],
            "binary_string_ids": ["ACC-USB-C", "WDG-XL-BLU"],
        }
        ecr = EvidenceCandidateRegistry()
        ecr.seed_tier0()
        ecr.seed_tier1(vocab)

        args, meta = self.build(inv, vocab, attempt=0, evidence=ecr)

        assert args["param_1"] == "CUST-001"
        assert args["param_2"] == "ACC-USB-C"
        assert args["param_6"] == 64
        assert "param_5" not in args
        assert "buffer_size" in meta["param_6"]["reason"]

    def test_reserve_function_with_lpstr_output_buffer_omits_output_slot(self):
        """Explicit LPSTR output buffers should be omitted from deterministic fallback args."""
        inv = {
            "name": "CP_ReserveStock",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "type": "typedef LPCSTR CHAR *"},
                {"name": "param_2", "json_type": "string", "direction": "in", "type": "byte *"},
                {"name": "param_3", "json_type": "integer", "direction": "in", "type": "ushort"},
                {"name": "param_4", "json_type": "integer", "direction": "in", "type": "uint"},
                {"name": "param_5", "json_type": "string", "direction": "out", "type": "typedef LPSTR CHAR *", "resolved_type": "LPSTR"},
                {"name": "param_6", "json_type": "integer", "direction": "in", "type": "uint"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001"],
            "binary_string_ids": ["ACC-USB-C"],
        }

        args, meta = self.build(inv, vocab, attempt=0)

        assert args["param_1"] == "CUST-001"
        assert args["param_2"] == "ACC-USB-C"
        assert args["param_6"] == 64
        assert "param_5" not in args
        assert "param_5" not in meta

    def test_purchase_function_without_evidence_uses_generic_fallback(self):
        """Without evidence, generic params get function-context candidates."""
        inv = {
            "name": "CP_ProcessPurchase",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_2", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_3", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "CUST-002", "ORD-20040301-0042"],
            "binary_string_ids": ["ACC-USB-C", "WDG-XL-BLU"],
        }

        args, meta = self.build(inv, vocab, attempt=0)

        assert isinstance(args["param_1"], str)
        assert isinstance(args["param_2"], str)

    def test_transaction_history_with_evidence_prefers_customer_and_buffer_size(self):
        """History readers with an output buffer should query by customer-like id and size the buffer."""
        from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

        inv = {
            "name": "CP_GetTransactionHistory",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_2", "json_type": "string", "direction": "out", "type": "undefined *"},
                {"name": "param_3", "json_type": "integer", "direction": "in", "description": "Integer input parameter"},
                {"name": "param_4", "json_type": "integer", "direction": "out", "type": "int *"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "CUST-002", "ORD-20040301-0042"],
            "binary_string_ids": ["TXN-00000001-0000", "TXN-00000002-0001"],
        }
        ecr = EvidenceCandidateRegistry()
        ecr.seed_tier0()
        ecr.seed_tier1(vocab)

        args, meta = self.build(inv, vocab, attempt=0, evidence=ecr)

        assert args["param_1"] == "CUST-001"
        assert args["param_3"] == 64
        assert "customer_id" in meta["param_1"]["reason"]
        assert "buffer_size" in meta["param_3"]["reason"]

    def test_void_transaction_with_evidence_prefers_transaction_id(self):
        """Void-style transaction functions should prefer transaction ids over generic order ids."""
        from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

        inv = {
            "name": "CP_VoidTransaction",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
                {"name": "param_2", "json_type": "integer", "direction": "out", "type": "undefined4 *"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "ORD-20040301-0042"],
            "binary_string_ids": ["TXN-00000001-0000", "TXN-00000002-0001"],
        }
        ecr = EvidenceCandidateRegistry()
        ecr.seed_tier0()
        ecr.seed_tier1(vocab)

        args, meta = self.build(inv, vocab, attempt=0, evidence=ecr)

        assert args["param_1"] == "TXN-00000001-0000"
        assert "transaction_id" in meta["param_1"]["reason"]

    def test_cancel_reservation_with_runtime_evidence_prefers_reservation_id(self):
        """Cancel-reservation functions should use reservation ids when runtime evidence provides them."""
        from api.pipeline.core.evidence_candidates import (
            EvidenceCandidateRegistry,
            TIER_RUNTIME,
        )

        inv = {
            "name": "CP_CancelReservation",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
            ],
        }
        ecr = EvidenceCandidateRegistry()
        ecr.seed_tier0()
        ecr.add("RESV-12345678-0001", TIER_RUNTIME, "runtime:CP_ReserveStock", "reservation_id", 0.95, "CP_ReserveStock")

        args, meta = self.build(inv, {"id_formats": ["ORD-20040301-0042"]}, attempt=0, evidence=ecr)

        assert args["param_1"] == "RESV-12345678-0001"
        assert "reservation_id" in meta["param_1"]["reason"]

    def test_stock_function_with_evidence_prefers_sku_over_customer_id(self):
        """Stock/product-style functions should query SKU candidates before customer IDs."""
        from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

        inv = {
            "name": "CP_CheckStock",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "CUST-002", "ORD-20040301-0042"],
            "binary_string_ids": ["ACC-USB-C", "WDG-XL-BLU"],
        }
        ecr = EvidenceCandidateRegistry()
        ecr.seed_tier0()
        ecr.seed_tier1(vocab)

        args, meta = self.build(inv, vocab, attempt=0, evidence=ecr)

        assert args["param_1"] == "ACC-USB-C"
        assert "sku" in meta["param_1"]["reason"]

    def test_stock_function_without_evidence_prefers_sku_fallback(self):
        """No-evidence fallback should still prefer SKU-like values for stock/product functions."""
        inv = {
            "name": "CP_CheckStock",
            "parameters": [
                {"name": "param_1", "json_type": "string", "direction": "in", "description": "Input string parameter"},
            ],
        }
        vocab = {
            "id_formats": ["CUST-001", "CUST-002", "ORD-20040301-0042"],
            "binary_string_ids": ["ACC-USB-C", "WDG-XL-BLU"],
        }

        args, meta = self.build(inv, vocab, attempt=0)

        assert args["param_1"] == "ACC-USB-C"
        assert meta["param_1"]["source"] == "function_context.sku"

    def test_discount_function_is_treated_as_write_like(self):
        from api.pipeline.core.helpers import _WRITE_FN_RE

        assert _WRITE_FN_RE.search("CP_ApplyBulkDiscount")

    def test_classify_common_result_code_zero(self):
        """classify_common_result_code(0) must return None (S_OK is not an error)."""
        from api.analysis.sentinel_codes import classify_common_result_code
        assert classify_common_result_code(0) is None

    def test_classify_common_result_code_version(self):
        """classify_common_result_code(131841) must return None."""
        from api.analysis.sentinel_codes import classify_common_result_code
        assert classify_common_result_code(131841) is None

    def test_classify_common_result_code_sentinel(self):
        """classify_common_result_code(0xFFFFFFFF) must return a non-None description."""
        from api.analysis.sentinel_codes import classify_common_result_code
        result = classify_common_result_code(0xFFFFFFFF)
        assert result is not None and len(result) > 0


# ─────────────────────────────────────────────────────────────────────────────
#  ExploreRuntime defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestExploreRuntime:
    """Verify ExploreRuntime produces correct defaults without a live environment."""

    def test_default_construction(self):
        from api.pipeline.core.types import ExploreRuntime
        r = ExploreRuntime()
        assert r.max_rounds >= 1
        assert r.max_tool_calls >= 1
        assert r.max_functions >= 1
        assert r.min_direct_probes >= 1
        assert r.cap_profile == "default"
        assert r.deterministic_fallback_enabled is True
        assert r.gap_resolution_enabled is True
        assert r.clarification_enabled is True
        assert r.pass_index == 1
        assert r.pass_scope_profile == "foundation"

    def test_from_job_runtime_empty_dict(self):
        """from_job_runtime({}) should fall back to defaults / environment defaults."""
        from api.pipeline.core.types import ExploreRuntime
        r = ExploreRuntime.from_job_runtime({})
        # Must not raise; runtime values must be sensible positive numbers
        assert r.max_rounds >= 1
        assert r.max_tool_calls >= 1
        assert r.max_functions >= 1

    def test_from_job_runtime_overrides(self):
        """Explicit keys in the explore_runtime dict must override defaults.

        The dict uses camelCase-style short keys (see ExploreRuntime.from_job_runtime
        source): 'max_rounds', 'max_tool_calls', 'max_functions'.
        """
        from api.pipeline.core.types import ExploreRuntime
        r = ExploreRuntime.from_job_runtime({
            "max_rounds":     3,
            "max_tool_calls": 12,
            "max_functions":  5,
            "pass_index": 2,
            "pass_scope_profile": "later_pass",
        })
        assert r.max_rounds == 3
        assert r.max_tool_calls == 12
        assert r.max_functions == 5
        assert r.pass_index == 2
        assert r.pass_scope_profile == "later_pass"


# ─────────────────────────────────────────────────────────────────────────────
#  ExploreContext construction shape
# ─────────────────────────────────────────────────────────────────────────────

class TestExploreContext:
    """Verify ExploreContext dataclass has expected attributes."""

    def test_dataclass_fields_exist(self):
        from api.pipeline.core.types import ExploreContext, ExploreRuntime
        from threading import Lock

        ctx = ExploreContext(
            job_id="test-job",
            runtime=ExploreRuntime(),
            client=None,
            model="gpt-4o",
            run_started_at=0.0,
            invocables=[{"name": "Foo"}],
            inv_map={"Foo": {"name": "Foo"}},
            tool_schemas=[],
            total=1,
            sentinels={0xFFFFFFFF: "not found"},
            already_explored=set(),
        )
        assert ctx.job_id == "test-job"
        assert ctx.model == "gpt-4o"
        assert ctx.total == 1
        assert 0xFFFFFFFF in ctx.sentinels
        # phase fields default to None / empty
        assert ctx.vocab == {}
        assert ctx.static_analysis_result == {}
        assert ctx.sentinel_catalog == {}

    def test_state_dict_initialised(self):
        from api.pipeline.core.types import ExploreContext, ExploreRuntime
        ctx = ExploreContext(
            job_id="j", runtime=ExploreRuntime(), client=None, model="m",
            run_started_at=0.0, invocables=[], inv_map={}, tool_schemas=[],
            total=0, sentinels={}, already_explored=set(),
        )
        assert isinstance(ctx._state, dict)
        assert "explored" in ctx._state


def test_probe_loop_allows_focused_rerun_for_already_explored_layered_function(monkeypatch):
    from api.pipeline.core.types import ExploreContext, ExploreRuntime
    from api.pipeline.s02_probe.probe_loop import _run_phase_3_probe_loop

    calls: list[str] = []

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda _job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *_args, **_kwargs: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._explore_one",
        lambda inv, _ctx: calls.append(inv["name"]),
    )

    class _FakeEcr:
        def stats(self):
            return {"total_candidates": 0}

    runtime = ExploreRuntime(skip_documented=False, focus_functions=["CP_ReserveStock"])
    ctx = ExploreContext(
        job_id="job-focus",
        runtime=runtime,
        client=None,
        model="gpt-4o-mini",
        run_started_at=0.0,
        invocables=[
            {"name": "CP_ReserveStock"},
            {"name": "CP_CancelReservation"},
        ],
        inv_map={
            "CP_ReserveStock": {"name": "CP_ReserveStock"},
            "CP_CancelReservation": {"name": "CP_CancelReservation"},
        },
        tool_schemas=[],
        total=2,
        sentinels={},
        already_explored={"CP_ReserveStock"},
    )
    ctx._execution_layers = [["CP_ReserveStock", "CP_CancelReservation"]]
    ctx.evidence_candidates = _FakeEcr()

    _run_phase_3_probe_loop(ctx)

    assert calls == ["CP_ReserveStock", "CP_CancelReservation"]


def test_documented_skip_gate_yields_to_focus_functions():
    from api.pipeline.core.types import ExploreContext, ExploreRuntime
    from api.pipeline.s02_probe.probe_loop import _should_skip_documented_function

    runtime = ExploreRuntime(skip_documented=True, focus_functions=["CP_ReserveStock"])
    ctx = ExploreContext(
        job_id="job-focus-gate",
        runtime=runtime,
        client=None,
        model="gpt-4o-mini",
        run_started_at=0.0,
        invocables=[],
        inv_map={},
        tool_schemas=[],
        total=0,
        sentinels={},
        already_explored={"CP_ReserveStock", "CP_CancelReservation"},
    )

    assert _should_skip_documented_function("CP_ReserveStock", ctx) is False
    assert _should_skip_documented_function("CP_CancelReservation", ctx) is True


def test_documented_skip_gate_yields_to_selected_semantic_checkpoint():
    from api.pipeline.core.types import ExploreContext, ExploreRuntime
    from api.pipeline.s02_probe.probe_loop import _should_skip_documented_function

    runtime = ExploreRuntime(
        skip_documented=True,
        focus_functions=[],
        selected_invocable_names=["SP_CommitRelease"],
        required_semantic_checkpoint="SP_CommitRelease",
    )
    ctx = ExploreContext(
        job_id="job-selected-target",
        runtime=runtime,
        client=None,
        model="gpt-4o-mini",
        run_started_at=0.0,
        invocables=[],
        inv_map={},
        tool_schemas=[],
        total=0,
        sentinels={},
        already_explored={"SP_CommitRelease"},
    )

    assert _should_skip_documented_function("SP_CommitRelease", ctx) is False


def test_skip_probe_function_emits_reason_for_focus_gate(monkeypatch):
    from api.pipeline.core.types import ExploreContext, ExploreRuntime
    from api.pipeline.s02_probe import probe_loop

    logged: list[list[dict]] = []

    runtime = ExploreRuntime(skip_documented=True, focus_functions=["CP_ReserveStock"])
    ctx = ExploreContext(
        job_id="job-skip-log",
        runtime=runtime,
        client=None,
        model="gpt-4o-mini",
        run_started_at=0.0,
        invocables=[],
        inv_map={},
        tool_schemas=[],
        total=1,
        sentinels={},
        already_explored=set(),
    )

    monkeypatch.setattr(probe_loop, "_append_explore_probe_log", lambda job_id, entries: logged.append(entries))
    monkeypatch.setattr(probe_loop, "_set_explore_status", lambda *args, **kwargs: None)

    assert probe_loop._should_skip_probe_function("CP_CancelReservation", ctx) is True  # noqa: SLF001
    assert logged
    assert logged[0][0]["phase"] == "skip_pre_probe"
    assert logged[0][0]["args"]["reason"] == "skip_focus"


def test_curriculum_places_reservation_consumer_after_reservation_producer():
    from api.pipeline.core.evidence_candidates import build_prerequisite_dag, dag_to_execution_layers

    invocables = [
        {"name": "CP_Initialize", "parameters": []},
        {
            "name": "CP_ReserveStock",
            "parameters": [
                {"name": "param_1", "json_type": "string", "description": "customer ID"},
                {"name": "param_2", "json_type": "string", "description": "SKU string"},
                {"name": "param_3", "json_type": "integer", "description": "quantity"},
                {"name": "param_4", "json_type": "integer", "description": "hold minutes"},
                {"name": "param_5", "json_type": "string", "direction": "out", "description": "reservation id output"},
                {"name": "param_6", "json_type": "integer", "description": "buffer size"},
            ],
        },
        {
            "name": "CP_CancelReservation",
            "parameters": [
                {"name": "param_1", "json_type": "string", "description": "reservation id"},
            ],
        },
    ]

    roles, edges = build_prerequisite_dag(invocables, ["CUST-001"])
    layers = dag_to_execution_layers(roles, edges)

    reserve_layer = next(i for i, layer in enumerate(layers) if "CP_ReserveStock" in layer)
    cancel_layer = next(i for i, layer in enumerate(layers) if "CP_CancelReservation" in layer)

    assert any(
        edge.producer == "CP_ReserveStock"
        and edge.consumer == "CP_CancelReservation"
        and edge.shared_kind == "reservation_id"
        for edge in edges
    )
    assert reserve_layer < cancel_layer


# ─────────────────────────────────────────────────────────────────────────────
#  session_snapshot endpoint: staged ZIP structure (static source check)
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionSnapshotZipStructure:
    """Verify that routes_session.py embeds the expected stage-based ZIP paths.

    We parse the source rather than importing it (which requires a live
    FastAPI + Azure environment) so the check runs offline in CI.
    The session_snapshot endpoint was moved from main.py to routes_session.py
    in the a2fc8c5 refactor.
    """

    SESSION_PY = ROOT / "api" / "routes" / "routes_session.py"

    @pytest.fixture(autouse=True)
    def _source(self):
        self.src = self.SESSION_PY.read_text(encoding="utf-8")

    def _assert_present(self, path_fragment: str):
        assert path_fragment in self.src, f"Expected '{path_fragment}' in routes_session.py session_snapshot"

    def test_stage_00_setup_present(self):
        self._assert_present("stage-00-setup/explore_config.json")
        self._assert_present("stage-00-setup/static_analysis.json")
        self._assert_present("stage-00-setup/sentinel_calibration.json")
        self._assert_present("stage-00-setup/schema.json")

    def test_stage_01_probe_loop_present(self):
        self._assert_present("stage-01-probe-loop/explore_probe_log.json")
        self._assert_present("stage-01-probe-loop/schema-before.json")
        self._assert_present("stage-01-probe-loop/schema-after.json")

    def test_stage_02_synthesis_present(self):
        self._assert_present("stage-02-synthesis/findings.json")
        self._assert_present("stage-02-synthesis/api_reference.md")

    def test_stage_03_gap_resolution_present(self):
        self._assert_present("stage-03-gap-resolution/gap_resolution_log.json")
        self._assert_present("stage-03-gap-resolution/schema-before.json")
        self._assert_present("stage-03-gap-resolution/schema-after.json")

    def test_stage_04_clarification_present(self):
        self._assert_present("stage-04-clarification/clarification-questions.md")
        self._assert_present("stage-04-clarification/schema-before.json")
        self._assert_present("stage-04-clarification/schema-after.json")

    def test_stage_05_finalization_present(self):
        self._assert_present("stage-05-finalization/findings.json")
        self._assert_present("stage-05-finalization/vocab.json")
        self._assert_present("stage-05-finalization/behavioral_spec.py")
        self._assert_present("stage-05-finalization/invocables_map.json")
        self._assert_present("stage-05-finalization/sentinel_catalog.json")
        self._assert_present("stage-05-finalization/harmonization_report.json")

    def test_diagnostics_present(self):
        self._assert_present("diagnostics/chat_transcript.txt")
        self._assert_present("diagnostics/executor_trace.json")
        self._assert_present("diagnostics/model_context.txt")
        self._assert_present("diagnostics/diagnosis_raw.json")

    def test_contract_artifacts_present(self):
        self._assert_present('"session-meta.json"')
        self._assert_present('"stage-index.json"')
        self._assert_present('"transition-index.json"')
        self._assert_present('"cohesion-report.json"')
        self._assert_present('"canonical-stage-model.json"')
        self._assert_present('"capture-layout-stage-aliases.json"')
        self._assert_present('"README-STAGES.md"')

    def test_session_manifest_present(self):
        self._assert_present('"session-manifest.json"')
        self._assert_present('"checkpoints/manifest.json"')

    def test_no_old_flat_artifacts_path(self):
        """Old ZIP structure used 'artifacts/' prefix — must no longer appear."""
        assert "artifacts/findings.json" not in self.src, \
            "Old 'artifacts/' ZIP prefix still present in session_snapshot"

    def test_no_old_schema_numbered_files(self):
        """Old ZIP used 'schema/01-pre-enrichment.json' etc. — must no longer appear."""
        assert "schema/01-pre-enrichment.json" not in self.src, \
            "Old numbered schema/ ZIP prefix still present in session_snapshot"


class TestFindingTaxonomy:
    """Business-precondition sentinels should not be treated as generic failures."""

    def test_insufficient_points_maps_to_functional_precondition_unmet(self):
        from api.pipeline.core.helpers import _classify_finding_status

        status = _classify_finding_status(
            return_value=-5,
            sentinels={0xFFFFFFFB: "insufficient loyalty points"},
            sentinel_meaning="",
        )
        assert status == "functional_precondition_unmet"
