from api.pipeline.s01_unlock.write_unlock import (
    _analyze_decompiled_unlock_patterns,
    _build_unlock_probe_arg_sets,
)


def test_analyze_unlock_patterns_detects_auth_gated_non_unlock_name() -> None:
    invocables = [
        {
            "name": "CP_ApplyBulkDiscount",
            "parameters": [{"name": "param_1"}, {"name": "param_2"}, {"name": "param_3"}],
            "doc_comment": """
/*
 * CP_ApplyBulkDiscount
 * lpszSku         : SKU to discount
 * dwNewPriceCents : new unit price in cents
 * lpszAuthToken   : 8-char auth token (XOR validation, same as contoso_cs)
 */
if (bCheck != 0xA5) return CP_ERR_BADPARAM;
""",
        }
    ]

    analysis = _analyze_decompiled_unlock_patterns(invocables)

    assert analysis["unlock_functions"]
    assert analysis["unlock_functions"][0]["name"] == "CP_ApplyBulkDiscount"
    assert analysis["unlock_functions"][0]["xor_target_hex"] == "0xA5"


def test_build_unlock_probe_arg_sets_uses_doc_param_roles() -> None:
    inv = {
        "name": "CP_ApplyBulkDiscount",
        "parameters": [
            {"name": "param_1", "json_type": "string", "description": "Input string parameter"},
            {"name": "param_2", "json_type": "integer", "description": "Integer input parameter"},
            {"name": "param_3", "json_type": "string", "description": "Input string parameter"},
        ],
        "doc_comment": """
/*
 * CP_ApplyBulkDiscount
 * lpszSku         : SKU to discount
 * dwNewPriceCents : new unit price in cents
 * lpszAuthToken   : 8-char auth token (XOR validation, same as contoso_cs)
 */
""",
    }

    arg_sets = _build_unlock_probe_arg_sets(
        inv,
        xor_code="ABCxyz12",
        id_samples=["CUST-001"],
        sku_samples=["WDG-XL-BLU"],
        amount_samples=[5000],
    )

    assert arg_sets
    first = arg_sets[0]
    assert first["param_1"] == "WDG-XL-BLU"
    assert first["param_2"] == 5000
    assert first["param_3"] == "ABCxyz12"
