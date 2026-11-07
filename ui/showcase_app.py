from __future__ import annotations

import contextlib
import importlib
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

import uvicorn

try:
    import webview
except ImportError as exc:  # pragma: no cover - import guard for local launch
    raise SystemExit(
        "pywebview is required for the desktop showcase shell. "
        "Install it with: pip install pywebview"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HOST = "127.0.0.1"
API_PORT = 8201
UI_PORT = 8421
BRIDGE_PORT = 8810


def _load_env_file(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def _find_free_port(start: int) -> int:
    for port in range(start, start + 40):
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost port found near {start}.")


def _wait_for_health(url: str, timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


@dataclass
class LocalServer:
    port: int
    server: uvicorn.Server
    thread: threading.Thread

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"


def _start_uvicorn_thread(app_obj, port: int) -> LocalServer:
    config = uvicorn.Config(
        app_obj,
        host=HOST,
        port=port,
        log_level="warning",
        reload=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return LocalServer(port=port, server=server, thread=thread)


def _venv_python() -> Path:
    return ROOT / ".venv" / "Scripts" / "python.exe"


def _ensure_local_env() -> None:
    _load_env_file(ROOT / ".env")
    _load_env_file(ROOT / "scripts" / "bridge" / ".bridge.env", override=True)
    os.environ.setdefault("MCP_STORAGE_BACKEND", "local")
    if os.environ.get("BRIDGE_SECRET", "").strip():
        os.environ["GUI_BRIDGE_SECRET"] = os.environ["BRIDGE_SECRET"]
    elif os.environ.get("GUI_BRIDGE_SECRET", "").strip():
        os.environ["BRIDGE_SECRET"] = os.environ["GUI_BRIDGE_SECRET"]


def _bridge_process_env() -> dict[str, str]:
    env = dict(os.environ)
    secret = env.get("GUI_BRIDGE_SECRET", "").strip() or env.get("BRIDGE_SECRET", "").strip()
    if not secret:
        raise RuntimeError("Local bridge secret is missing. Set GUI_BRIDGE_SECRET or BRIDGE_SECRET in .env.")
    env["BRIDGE_SECRET"] = secret
    env["GUI_BRIDGE_SECRET"] = secret
    env.setdefault("BRIDGE_PORT", str(BRIDGE_PORT))
    return env


def _start_managed_bridge() -> tuple[subprocess.Popen, int]:
    bridge_script = ROOT / "scripts" / "bridge" / "gui_bridge.py"
    bridge_port = _find_free_port(BRIDGE_PORT)
    bridge_url = f"http://{HOST}:{bridge_port}"
    os.environ["GUI_BRIDGE_URL"] = bridge_url
    proc = subprocess.Popen(
        [str(_venv_python()), str(bridge_script)],
        cwd=str(ROOT),
        env={**_bridge_process_env(), "BRIDGE_PORT": str(bridge_port)},
    )
    if not _wait_for_health(f"{bridge_url}/health", timeout_s=25.0):
        proc.terminate()
        raise RuntimeError("Local GUI bridge failed to boot.")
    return proc, bridge_port


def _load_api_app():
    module = importlib.import_module("api.routes.main")
    return module.app


def _load_ui_app():
    module = importlib.import_module("ui.main")
    return module.app


def _open_fallback_browser(url: str) -> None:
    webbrowser.open(url)


def main() -> None:
    _ensure_local_env()

    bridge_proc: Optional[subprocess.Popen] = None
    api_server: Optional[LocalServer] = None
    ui_server: Optional[LocalServer] = None

    try:
        bridge_proc, _bridge_port = _start_managed_bridge()

        api_port = _find_free_port(API_PORT)
        os.environ["PIPELINE_URL"] = f"http://{HOST}:{api_port}"
        api_server = _start_uvicorn_thread(_load_api_app(), api_port)
        if not _wait_for_health(f"{api_server.url}/health"):
            raise RuntimeError("Local pipeline API failed to boot.")

        ui_port = _find_free_port(UI_PORT)
        ui_server = _start_uvicorn_thread(_load_ui_app(), ui_port)
        if not _wait_for_health(f"{ui_server.url}/health"):
            raise RuntimeError("Local showcase UI failed to boot.")

        default_job = os.environ.get("SHOWCASE_DEFAULT_JOB_ID", "").strip()
        query = f"?job_id={default_job}" if default_job else ""

        window = webview.create_window(
            title="MCP Factory Showcase",
            url=f"{ui_server.url}{query}",
            width=1500,
            height=980,
            x=60,
            y=40,
            min_size=(1200, 760),
            on_top=True,
            text_select=True,
        )
        try:
            webview.start(gui="edgechromium")
        except Exception:
            _open_fallback_browser(f"{ui_server.url}{query}")
            time.sleep(1.0)
    finally:
        if ui_server is not None:
            ui_server.server.should_exit = True
            ui_server.thread.join(timeout=5.0)
        if api_server is not None:
            api_server.server.should_exit = True
            api_server.thread.join(timeout=5.0)
        if bridge_proc is not None:
            bridge_proc.terminate()
            try:
                bridge_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                bridge_proc.kill()


if __name__ == "__main__":
    main()
