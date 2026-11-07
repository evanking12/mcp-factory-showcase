from __future__ import annotations

from api.infra import storage


def test_merge_invocable_union_preserves_existing_params_when_incoming_empty() -> None:
    existing = {
        "name": "CS_ProcessPayment",
        "description": "Processes payment for a customer account.",
        "parameters": [
            {
                "name": "customer_id",
                "type": "string",
                "description": "Customer ID (e.g. CUST-001).",
            },
            {
                "name": "amount",
                "type": "int",
                "description": "Payment amount in cents.",
            },
        ],
    }
    incoming = {
        "name": "CS_ProcessPayment",
        "description": "",
        "parameters": [],
    }

    merged = storage._merge_invocable_union(existing, incoming)  # noqa: SLF001
    assert len(merged.get("parameters") or []) == 2
    assert merged["parameters"][0]["name"] == "customer_id"
    assert merged["description"] == existing["description"]


def test_merge_invocable_union_keeps_richer_param_descriptions() -> None:
    existing = {
        "name": "CS_UnlockAccount",
        "parameters": [
            {
                "name": "customer_id",
                "type": "string",
                "description": "Customer ID to unlock (e.g. CUST-001).",
            }
        ],
    }
    incoming = {
        "name": "CS_UnlockAccount",
        "parameters": [
            {
                "name": "customer_id",
                "type": "string",
                "description": "input parameter",
            }
        ],
    }

    merged = storage._merge_invocable_union(existing, incoming)  # noqa: SLF001
    assert (merged.get("parameters") or [])[0]["description"] == (
        "Customer ID to unlock (e.g. CUST-001)."
    )


def test_merge_invocable_union_prefers_richer_positional_param_layout_over_generic_names() -> None:
    existing = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "param_1", "type": "char *", "description": "Parameter of type char *"},
            {"name": "param_2", "type": "short", "description": "Parameter of type short"},
            {"name": "param_3", "type": "undefined4", "description": "Parameter of type undefined4"},
        ],
    }
    incoming = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "type": "char *", "description": "SKU of the product to reserve."},
            {"name": "wQty", "type": "short", "description": "Quantity to reserve."},
            {"name": "dwHoldMinutes", "type": "undefined4", "description": "Duration in minutes to hold the reservation."},
        ],
    }

    merged = storage._merge_invocable_union(existing, incoming)  # noqa: SLF001
    params = merged.get("parameters") or []

    assert [p["name"] for p in params] == ["lpszSku", "wQty", "dwHoldMinutes"]
    assert params[0]["description"] == "SKU of the product to reserve."

