from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 2

    request_path = Path(argv[1])
    response_path = Path(argv[2])

    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        from scripts.bridge.gui_bridge import _execute_dll_bridge

        result = _execute_dll_bridge(
            payload.get("inv") or {},
            payload.get("execution") or {},
            payload.get("args") or {},
        )
        response_path.write_text(
            json.dumps({"status": "ok", "result": result}, ensure_ascii=True),
            encoding="utf-8",
        )
        return 0
    except BaseException as exc:
        try:
            response_path.write_text(
                json.dumps(
                    {
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
