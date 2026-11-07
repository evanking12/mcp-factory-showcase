"""
ui/main.py – MCP Factory Web UI
Serves a single-page HTML frontend and proxies /api/* calls to the
pipeline container (PIPELINE_URL env var).
"""

from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_factory.ui")

# ── Optional API-key guard ─────────────────────────────────────────────────
# Set UI_API_KEY env var on the container to require a shared key on every
# request.  Leave unset (or empty) for open access during local development.
UI_API_KEY   = os.getenv("UI_API_KEY", "")
PIPELINE_KEY = os.getenv("PIPELINE_KEY", "")  # forwarded as X-Pipeline-Key

PIPELINE_URL = os.getenv(
    "PIPELINE_URL",
    "http://localhost:8201",
).rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
FEATURED_BATCH_B_SESSION = "20260405-182853"
FEATURED_BATCH_B_CAMPAIGN = "12da5cad"
FEATURED_BATCH_B_JOB_ID = "a582e3f8"
FEATURED_BATCH_B_WAVE_SUMMARY = (
    ROOT
    / "sessions"
    / "campaigns"
    / "blocker_harvest"
    / FEATURED_BATCH_B_SESSION
    / "wave-2-batch-b"
    / "wave-summary.json"
)
FEATURED_BATCH_B_VERDICT = (
    ROOT
    / "sessions"
    / "campaigns"
    / "blocker_harvest"
    / FEATURED_BATCH_B_SESSION
    / "wave-2-batch-b"
    / "next-step-verdict.json"
)
BEST_TRUSTED_BATCH_B_WAVE_SUMMARY = (
    ROOT
    / "sessions"
    / "campaigns"
    / "blocker_harvest"
    / "20260405-072319"
    / "wave-2-batch-b"
    / "wave-summary.json"
)
SHOWCASE_DEFAULT_JOB_ID = os.getenv("SHOWCASE_DEFAULT_JOB_ID", "").strip() or FEATURED_BATCH_B_JOB_ID
SHOWCASE_AUTO_GENERATE_SCHEMA = os.getenv("SHOWCASE_AUTO_GENERATE_SCHEMA", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _read_local_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_featured_showcase_payload() -> dict[str, Any]:
    summary = _read_local_json(FEATURED_BATCH_B_WAVE_SUMMARY) or {}
    verdict = _read_local_json(FEATURED_BATCH_B_VERDICT) or {}
    previous = _read_local_json(BEST_TRUSTED_BATCH_B_WAVE_SUMMARY) or {}
    regressions = summary.get("overlap_regression_summary") or []
    dominant = summary.get("dominant_blocker_families") or []
    per_dll = (summary.get("cohesion_summary") or {}).get("per_dll") or []
    top_regressions = [
        f"{item.get('function', 'unknown')} ({str(item.get('dll', '')).replace('.dll', '')})"
        for item in regressions[:6]
    ]
    return {
        "session_id": FEATURED_BATCH_B_SESSION,
        "campaign_id": summary.get("campaign_id") or FEATURED_BATCH_B_CAMPAIGN,
        "representative_job_id": FEATURED_BATCH_B_JOB_ID,
        "package_label": summary.get("package_label") or "Contoso Business Suite",
        "verified_count": summary.get("total_verified"),
        "total_functions": summary.get("total_functions"),
        "verified_rate": summary.get("verified_rate"),
        "overlap_delta": summary.get("overlap_verified_delta"),
        "remaining_regressions": top_regressions,
        "remaining_regression_count": len(regressions),
        "dominant_blockers": dominant,
        "per_dll": per_dll,
        "package_internal_truth_ready": summary.get("package_internal_truth_ready"),
        "overlap_baseline_comparable": summary.get("overlap_baseline_comparable"),
        "architecture_signal": verdict.get("architecture_signal"),
        "verdict": verdict.get("verdict"),
        "previous_verified_count": previous.get("total_verified"),
        "previous_total_functions": previous.get("total_functions"),
        "previous_overlap_delta": previous.get("overlap_verified_delta"),
    }

app = FastAPI(title="MCP Factory UI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_UI_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=_UI_DIR / "static"), name="static")
templates = Jinja2Templates(directory=_UI_DIR / "templates")


@app.middleware("http")
async def _api_key_guard(request: Request, call_next):
    """If UI_API_KEY is set, every non-health request must present it."""
    if not UI_API_KEY:
        return await call_next(request)
    # always allow health + static assets + Copilot Extension endpoint
    if request.url.path in ("/health", "/favicon.ico", "/copilot"):
        return await call_next(request)
    # check header or query param
    provided = (
        request.headers.get("X-UI-Key", "")
        or request.query_params.get("apikey", "")
    )
    # For browser page load we embed the key via a cookie set by the login form
    if not provided:
        provided = request.cookies.get("ui_api_key", "")
    if provided != UI_API_KEY:
        from fastapi.responses import HTMLResponse as _HR
        login_html = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>MCP Factory – Sign In</title>
<style>body{background:#0f1117;color:#e2e6f3;font-family:'Segoe UI',system-ui,sans-serif;
  display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
  .box{background:#1a1d27;border:1px solid #2e3254;border-radius:10px;padding:36px 40px;width:340px}
  h2{margin:0 0 24px;color:#5b8ef0;font-size:1.2rem}input{width:100%;background:#22263a;
  border:1px solid #2e3254;border-radius:7px;color:#e2e6f3;font-size:.9rem;padding:10px 13px;
  outline:none;box-sizing:border-box;margin-bottom:16px}input:focus{border-color:#5b8ef0}
  button{background:#5b8ef0;color:#fff;border:none;border-radius:7px;padding:10px 24px;
  font-size:.9rem;font-weight:600;cursor:pointer;width:100%}.err{color:#f09090;font-size:.82rem;margin-top:8px}
</style></head><body><div class="box">
<h2>⚙ MCP Factory — Access Required</h2>
<form id="f" onsubmit="return submit()">
  <input type="password" id="k" placeholder="Enter API key" autofocus />
  <button type="submit">Continue</button>
  <div class="err" id="err"></div>
</form></div>
<script>
function submit(){
  const k=document.getElementById('k').value;
  document.cookie='ui_api_key='+encodeURIComponent(k)+';path=/;SameSite=Strict';
  fetch('/',{headers:{'X-UI-Key':k}}).then(r=>{
    if(r.ok){location.reload();}else{document.getElementById('err').textContent='Invalid key.';}
  });
  return false;
}
</script></body></html>"""
        return _HR(content=login_html, status_code=401)
    return await call_next(request)



# ── Single-page frontend ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html", {})
# ── Proxy helpers ──────────────────────────────────────────────────────────

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        headers = {"X-Pipeline-Key": PIPELINE_KEY} if PIPELINE_KEY else {}
        _http = httpx.AsyncClient(base_url=PIPELINE_URL, timeout=180.0, headers=headers)
    return _http


async def _proxy_json(path: str, body: Any) -> JSONResponse:
    try:
        r = await _client().post(path, json=body)
        try:
            content = r.json()
        except Exception:
            content = {"detail": r.text or f"Pipeline returned empty response (HTTP {r.status_code})"}
        return JSONResponse(content=content, status_code=r.status_code if r.text else 502)
    except Exception as e:
        logger.error(f"Proxy error → {path}: {e}")
        return JSONResponse({"detail": str(e)}, status_code=502)


# ── Proxied endpoints ──────────────────────────────────────────────────────

@app.post("/api/check-cache")
async def proxy_check_cache(body: dict[str, Any]) -> JSONResponse:
    """Proxy cache check to the pipeline /api/check-cache."""
    return await _proxy_json("/api/check-cache", body)


@app.post("/api/analyze")
async def proxy_analyze(file: UploadFile = File(...), hints: str = Form(default=""),
                        use_cases: str = Form(default=""), skip_cache: str = Form(default="")):
    """Proxy file upload to the pipeline /api/analyze."""
    content = await file.read()
    try:
        form_data = {"hints": hints, "use_cases": use_cases}
        if skip_cache:
            form_data["skip_cache"] = skip_cache
        r = await _client().post(
            "/api/analyze",
            data=form_data,
            files={"file": (file.filename, content, file.content_type or "application/octet-stream")},
        )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        logger.error(f"Proxy analyze error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.post("/api/analyze-path")
async def proxy_analyze_path(body: dict[str, Any]) -> JSONResponse:
    """Proxy installed-path analysis to the pipeline /api/analyze-path."""
    return await _proxy_json("/api/analyze-path", body)


@app.post("/api/generate")
async def proxy_generate(body: dict[str, Any]) -> JSONResponse:
    """Proxy generate request to the pipeline /api/generate."""
    return await _proxy_json("/api/generate", body)


@app.post("/api/chat")
async def proxy_chat(body: dict[str, Any]) -> JSONResponse:
    """Proxy chat request to the pipeline /api/chat."""
    return await _proxy_json("/api/chat", body)


@app.post("/api/chat/stream")
async def proxy_chat_stream(request: Request):
    """Proxy the streaming SSE chat endpoint — pipes bytes through as they arrive."""
    body = await request.json()
    headers = {"X-Pipeline-Key": PIPELINE_KEY} if PIPELINE_KEY else {}

    async def _stream():
        async with httpx.AsyncClient(base_url=PIPELINE_URL, timeout=300.0, headers=headers) as c:
            async with c.stream("POST", "/api/chat", json=body) as r:
                if r.status_code != 200:
                    err = await r.aread()
                    yield f'data: {{"type":"error","message":"Pipeline {r.status_code}: {err.decode()[:200]}"}}\n\n'.encode()
                    return
                async for chunk in r.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/recent")
async def proxy_jobs_recent() -> JSONResponse:
    """Proxy recent job list for Step 1 shortcuts and resume picker."""
    try:
        r = await _client().get("/api/jobs/recent")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        logger.error(f"Proxy jobs/recent error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/lab/status")
async def proxy_lab_status() -> JSONResponse:
    """Proxy aggregate lab status to the pipeline /api/lab/status."""
    try:
        r = await _client().get("/api/lab/status")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        logger.error(f"Proxy lab/status error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/showcase/bootstrap")
async def showcase_bootstrap(request: Request) -> JSONResponse:
    """Expose local showcase startup hints to the web shell."""
    query_job_id = request.query_params.get("job_id", "").strip()
    return JSONResponse({
        "default_job_id": query_job_id or SHOWCASE_DEFAULT_JOB_ID,
        "auto_generate_schema": SHOWCASE_AUTO_GENERATE_SCHEMA,
        "featured": _build_featured_showcase_payload(),
    })


@app.get("/api/jobs/{job_id}/invocables")
async def proxy_job_invocables(job_id: str) -> JSONResponse:
    """Proxy invocable list reload for previously scanned jobs."""
    try:
        r = await _client().get(f"/api/jobs/{job_id}/invocables")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        logger.error(f"Proxy job invocables error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/jobs/{job_id}")
async def proxy_job_status(job_id: str) -> JSONResponse:
    """Proxy job-status polling to the pipeline /api/jobs/{job_id}."""
    try:
        r = await _client().get(f"/api/jobs/{job_id}")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        logger.error(f"Proxy job status error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/jobs/{job_id}/mc-decisions")
async def proxy_mc_decisions(job_id: str) -> JSONResponse:
    """Proxy micro coordinator decisions for a completed job."""
    try:
        r = await _client().get(f"/api/jobs/{job_id}/mc-decisions")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/jobs/{job_id}/verdict")
async def proxy_verdict(job_id: str) -> JSONResponse:
    """Proxy macro verdict for a completed job."""
    try:
        r = await _client().get(f"/api/jobs/{job_id}/verdict")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.post("/api/jobs/{job_id}/explore")
async def proxy_explore(job_id: str, body: dict[str, Any]) -> JSONResponse:
    """Proxy exploration trigger to the pipeline /api/jobs/{job_id}/explore."""
    return await _proxy_json(f"/api/jobs/{job_id}/explore", body)


@app.post("/api/jobs/{job_id}/refine")
async def proxy_refine(job_id: str, body: dict[str, Any]) -> JSONResponse:
    """Proxy refinement trigger to the pipeline /api/jobs/{job_id}/refine."""
    return await _proxy_json(f"/api/jobs/{job_id}/refine", body)


@app.post("/api/jobs/{job_id}/answer-gaps")
async def proxy_answer_gaps(job_id: str, body: dict[str, Any]) -> JSONResponse:
    """Proxy gap answers to the pipeline POST /api/jobs/{job_id}/answer-gaps."""
    return await _proxy_json(f"/api/jobs/{job_id}/answer-gaps", body)


@app.post("/api/jobs/{job_id}/explore-cancel")
async def proxy_explore_cancel(job_id: str) -> JSONResponse:
    """Proxy cooperative cancellation for explore/refine to the pipeline."""
    return await _proxy_json(f"/api/jobs/{job_id}/explore-cancel", {})


@app.get("/api/jobs/{job_id}/session-snapshot")
async def proxy_session_snapshot(job_id: str) -> Response:
    """Proxy session snapshot ZIP download from the pipeline."""
    try:
        r = await _client().get(f"/api/jobs/{job_id}/session-snapshot")
        return Response(
            content=r.content,
            status_code=r.status_code,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="session-{job_id}.zip"'},
        )
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/campaigns/{campaign_id}")
async def proxy_campaign_status(campaign_id: str) -> JSONResponse:
    """Proxy campaign status for end-of-run review."""
    try:
        r = await _client().get(f"/api/campaigns/{campaign_id}")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/campaigns/{campaign_id}/session-snapshot")
async def proxy_campaign_snapshot(campaign_id: str) -> Response:
    """Proxy campaign session snapshot ZIP download from the pipeline."""
    try:
        r = await _client().get(f"/api/campaigns/{campaign_id}/session-snapshot")
        return Response(
            content=r.content,
            status_code=r.status_code,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id}.zip"'},
        )
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/download/{job_id}/{filename}")
async def proxy_download(job_id: str, filename: str) -> Response:
    """Stream artifact download from the pipeline."""
    try:
        r = await _client().get(f"/api/download/{job_id}/{filename}")
        return Response(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "application/json"),
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/findings/{job_id}")
async def proxy_findings(job_id: str) -> JSONResponse:
    """Proxy findings endpoint to the pipeline /api/findings/{job_id}."""
    try:
        r = await _client().get(f"/api/findings/{job_id}")
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/api/jobs/{job_id}/report")
async def proxy_report(job_id: str) -> Response:
    """Stream the markdown report from the pipeline /api/jobs/{job_id}/report."""
    try:
        r = await _client().get(f"/api/jobs/{job_id}/report")
        return Response(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "text/markdown"),
            headers={"Content-Disposition": f'attachment; filename="report-{job_id}.md"'},
        )
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=502)


@app.get("/health")
def health():
    return {"status": "ok", "pipeline_url": PIPELINE_URL}


# ── P6: GitHub Copilot Extension agent endpoint ──────────────────────────
# GitHub routes @mcp-factory invocations here when the app is registered
# as a Copilot Extension.  Token verification + SSE streaming.
@app.post("/copilot")
async def copilot(request: Request):
    """GitHub Copilot Extensions agent endpoint (P6)."""
    from copilot_handler import copilot_endpoint  # type: ignore
    return await copilot_endpoint(request)
