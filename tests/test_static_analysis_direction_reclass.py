from api.pipeline.s00_setup.static_analysis import reclassify_ghidra_directions


def test_reclassify_ghidra_directions_keeps_lpcstr_inputs():
    invocables = [{
        "name": "CP_ProcessPurchase",
        "parameters": [
            {
                "name": "param_1",
                "type": "typedef LPCSTR CHAR *",
                "resolved_type": "LPCSTR",
                "direction": "out",
            },
            {
                "name": "param_5",
                "type": "uint *",
                "resolved_type": "uint *",
                "direction": "out",
            },
        ],
    }]

    changed = reclassify_ghidra_directions(invocables, {})

    assert changed == 1
    assert invocables[0]["parameters"][0]["direction"] == "in"
    assert invocables[0]["parameters"][1]["direction"] == "out"


def test_reclassify_ghidra_directions_keeps_lpstr_output_buffers():
    invocables = [{
        "name": "CP_ReserveStock",
        "parameters": [
            {
                "name": "param_5",
                "type": "typedef LPSTR CHAR *",
                "resolved_type": "LPSTR",
                "direction": "out",
            }
        ],
    }]

    changed = reclassify_ghidra_directions(invocables, {})

    assert changed == 0
    assert invocables[0]["parameters"][0]["direction"] == "out"
