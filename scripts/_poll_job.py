"""Quick job status poller."""
import httpx, json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.runtime_contract import local_api_base_url

job_id = sys.argv[1] if len(sys.argv) > 1 else "2dc39a87"
r = httpx.get(f"{local_api_base_url()}/api/jobs/{job_id}", timeout=10)
d = r.json()
print(f"phase={d.get('explore_phase')} stage={d.get('explore_stage')} progress={d.get('explore_progress')} updated={d.get('updated_at')}")
print(f"msg={d.get('explore_message','')[:100]}")
print(f"unlock_outcome={d.get('write_unlock_outcome')} findings={len(d.get('findings', []))}")
