import json
import os
from datetime import datetime, timezone

DISCOVERY_PATH = os.path.join("artifacts", "discovery-output.json")
OUTPUT_PATH = os.path.join("artifacts", "selected-invocables.json")

def load_discovery(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key in ["metadata", "invocables"]:
        if key not in data:
            raise ValueError(f"Discovery JSON missing required key: {key}")

    if not isinstance(data["invocables"], list) or len(data["invocables"]) == 0:
        raise ValueError("Discovery JSON has no invocables to select.")

    return data

def suggest_component_name(metadata: dict) -> str:
    target_name = metadata.get("target_name", "target").lower()
    target_base = target_name.replace(".exe", "").replace(".dll", "").replace(" ", "-")
    return f"mcp-{target_base}"

def print_invocables(invocables: list) -> None:
    print("\nInvocable features found\n")
    for i, inv in enumerate(invocables, start=1):
        name = inv.get("name", "unknown")
        kind = inv.get("kind", "unknown")
        conf = inv.get("confidence", "unknown")
        summary = inv.get("description", "")
        line = f"{i}. {name}  kind={kind}  confidence={conf}"
        if summary:
            line += f"  summary={summary}"
        print(line)

def parse_deselection(user_text: str, max_n: int) -> set[int]:
    user_text = user_text.strip()
    if user_text == "":
        return set()

    removed = set()
    parts = [p.strip() for p in user_text.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            a, b = p.split("-", 1)
            a_i = int(a.strip())
            b_i = int(b.strip())
            if a_i < 1 or b_i > max_n or a_i > b_i:
                raise ValueError(f"Bad range: {p}")
            for x in range(a_i, b_i + 1):
                removed.add(x)
        else:
            x = int(p)
            if x < 1 or x > max_n:
                raise ValueError(f"Bad number: {p}")
            removed.add(x)

    return removed

def main() -> None:
    discovery = load_discovery(DISCOVERY_PATH)
    metadata = discovery["metadata"]
    invocables = discovery["invocables"]

    print("\nSection 4 tool selection\n")
    print(f"Target: {metadata.get('target_name', 'unknown')} at {metadata.get('target_path', 'unknown')}")
    print_invocables(invocables)

    print("\nAll items are selected by default.")
    print("If you want to remove some, type numbers like: 2,4 or ranges like: 2-5")
    print("Press Enter to keep all.\n")

    user_text = input("Remove which items: ")
    removed = parse_deselection(user_text, len(invocables))

    selected = []
    for i, inv in enumerate(invocables, start=1):
        if i not in removed:
            selected.append(inv)

    suggested = suggest_component_name(metadata)
    print("\nComponent name is the name of the generated MCP server folder and service.")
    component_name = input(f"Component name [{suggested}]: ").strip()
    if component_name == "":
        component_name = suggested

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "component_name": component_name,
        "metadata": metadata,
        "selected_invocables": selected
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("\nSaved selection file")
    print(OUTPUT_PATH)
    print(f"Selected {len(selected)} of {len(invocables)} invocables.\n")

if __name__ == "__main__":
    main()
