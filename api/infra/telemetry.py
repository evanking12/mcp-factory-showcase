"""Local timing helpers and direct OpenAI client factory."""

from __future__ import annotations

import contextlib
import logging
import threading
import time

from api.infra.config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger("mcp_factory.api")


@contextlib.contextmanager
def _ai_span(name: str, **props):
    """Emit a best-effort local telemetry event with duration and properties."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        dims = {
            "event": name,
            "duration_ms": elapsed_ms,
            **{key: str(value) for key, value in props.items()},
        }

        def _emit_telemetry(d=dims, event_name=name, duration_ms=elapsed_ms):
            logger.info(
                "[telemetry] %s completed in %dms",
                event_name,
                duration_ms,
                extra={"custom_dimensions": d},
            )

        threading.Thread(target=_emit_telemetry, daemon=True, name="local-telemetry-log").start()


_CLIENT_LOCK = threading.Lock()
_cached_client = None


def _openai_client():
    """Return the cached direct OpenAI client for the local workflow."""
    global _cached_client

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for the local workflow.")

    if _cached_client is None:
        with _CLIENT_LOCK:
            if _cached_client is None:
                from openai import OpenAI

                _cached_client = OpenAI(api_key=OPENAI_API_KEY, timeout=120.0)
                logger.info("[telemetry] Using direct OpenAI client (model: %s)", OPENAI_MODEL)
    return _cached_client


def _warmup_openai() -> None:
    """Send a minimal completion request to warm the direct OpenAI client path."""
    try:
        client = _openai_client()
        client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        logger.debug("[telemetry] OpenAI endpoint warm-up complete")
    except Exception as exc:
        logger.debug("[telemetry] OpenAI warm-up skipped (non-critical): %s", exc)


def _proactive_token_refresh() -> None:
    """Daemon thread: periodically warm the direct OpenAI client."""
    while True:
        try:
            time.sleep(900)
            _openai_client()
            logger.debug("[telemetry] Proactive OpenAI warm-up complete")
        except Exception as exc:
            logger.warning("[telemetry] Proactive OpenAI warm-up failed: %s", exc)
            time.sleep(60)


threading.Thread(target=_proactive_token_refresh, daemon=True, name="token-refresh").start()
