"""
In-memory embedding selection for tool retrieval.

This repo is local-first only. Embeddings are cached in memory and persisted to
 local artifact storage so later requests can warm the cache without any remote
 search service.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from typing import Any

logger = logging.getLogger("mcp_factory.search")

EMBEDDING_MODEL = "text-embedding-3-small"

# {job_id: {"functions": [...], "embeddings": [[float...]], "invocables": [...]}}
_EMBED_CACHE: dict[str, dict] = {}
_EMBED_LOCK = threading.Lock()


def _norm(v: list[float]) -> list[float]:
    mag = math.sqrt(sum(x * x for x in v))
    return [x / mag for x in v] if mag else v


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def embed_and_index(
    job_id: str,
    invocables: list[dict],
    openai_client: Any,
    functions: list[dict] | None = None,
) -> None:
    """Embed all invocables and store them in memory plus local artifacts."""
    if not invocables:
        return

    if functions is None:
        functions = _build_functions(invocables)

    texts = [
        f"{fn['function']['name']}: {fn['function']['description']}"
        for fn in functions
    ]

    try:
        resp = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        embeddings = [
            _norm(item.embedding)
            for item in sorted(resp.data, key=lambda x: x.index)
        ]
    except Exception as exc:
        logger.warning("[search] Embedding failed: %s", exc)
        return

    with _EMBED_LOCK:
        _EMBED_CACHE[job_id] = {
            "functions": functions,
            "embeddings": embeddings,
            "invocables": invocables,
        }

    try:
        from api.infra.config import ARTIFACT_CONTAINER
        from api.infra.storage import _upload_to_blob

        _cache_blob = json.dumps({"functions": functions, "embeddings": embeddings})
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/embeddings_cache.json",
            _cache_blob.encode(),
        )
        logger.info("[search] Embeddings persisted to local artifact storage for job %s", job_id)
    except Exception as exc:
        logger.warning("[search] Embedding cache persist failed (non-fatal): %s", exc)


def retrieve_tools(
    job_id: str,
    query: str,
    openai_client: Any,
    top_k: int = 15,
) -> list[dict]:
    """Return top-k OpenAI tool schemas most relevant to the query."""
    with _EMBED_LOCK:
        cached = _EMBED_CACHE.get(job_id)

    if cached and len(cached.get("functions", [])) <= top_k:
        return cached["functions"]

    try:
        q_resp = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[query],
        )
        q_vec = _norm(q_resp.data[0].embedding)
    except Exception as exc:
        logger.warning("[search] Query embedding failed: %s", exc)
        if cached:
            return cached["functions"][:min(top_k, 128)]
        return []

    if not cached:
        try:
            from api.infra.config import ARTIFACT_CONTAINER
            from api.infra.storage import _download_blob

            raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/embeddings_cache.json")
            data = json.loads(raw)
            with _EMBED_LOCK:
                _EMBED_CACHE[job_id] = {
                    "functions": data["functions"],
                    "embeddings": data["embeddings"],
                    "invocables": [],
                }
                cached = _EMBED_CACHE[job_id]
            logger.info("[search] Warmed embedding cache from local artifact storage for job %s", job_id)
        except Exception as exc:
            logger.debug("[search] Embedding cache warm-up failed for job %s: %s", job_id, exc)

    if cached:
        embs = cached["embeddings"]
        fns = cached["functions"]
        scores = [(_dot(q_vec, e), i) for i, e in enumerate(embs)]
        scores.sort(reverse=True)
        return [fns[i] for _, i in scores[:top_k]]

    return []


def _build_functions(invocables: list[dict]) -> list[dict]:
    """Convert invocable dicts to OpenAI function-calling schemas."""
    c_to_json: dict[str, str] = {
        "int": "integer",
        "unsigned": "integer",
        "unsigned int": "integer",
        "long": "integer",
        "unsigned long": "integer",
        "size_t": "integer",
        "float": "number",
        "double": "number",
        "bool": "boolean",
    }

    def _json_type(c: str) -> str:
        t = c.lower().strip().rstrip("*").strip()
        if t in c_to_json:
            return c_to_json[t]
        if "char" in t or "string" in t or t == "str":
            return "string"
        if "int" in t or "long" in t:
            return "integer"
        return "string"

    functions = []
    for inv in invocables:
        props: dict = {}
        required: list = []
        for p in inv.get("parameters", []):
            pname = p.get("name", "arg")
            props[pname] = {
                "type": _json_type(p.get("type", "string")),
                "description": p.get("description", p.get("type", "")),
            }
        desc = (
            inv.get("doc")
            or inv.get("description")
            or inv.get("signature")
            or inv["name"]
        )
        import re as _re

        safe_name = _re.sub(r"[^a-zA-Z0-9_.\\-]", "_", inv["name"])[:64]
        functions.append({
            "type": "function",
            "function": {
                "name": safe_name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    return functions


def _invocable_to_function(inv: dict) -> dict:
    return _build_functions([inv])[0]
