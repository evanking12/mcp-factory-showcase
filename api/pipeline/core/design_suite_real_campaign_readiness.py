from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def write_real_campaign_readiness(output_dir: str | Path, artifact_name: str, payload: Mapping[str, Any]) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / artifact_name
    destination.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    return destination
