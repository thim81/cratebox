#!/usr/bin/env python3
"""Ensure local CrateBox services are running, then proxy its HTTP MCP over stdio."""

from __future__ import annotations

import asyncio
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from fastmcp import Client, FastMCP
from fastmcp.server.providers.proxy import FastMCPProxy


ROOT = Path(__file__).resolve().parents[1]
CRATEBOX = ROOT / "cratebox"
API_URL = "http://127.0.0.1:8000"
MCP_URL = API_URL + "/mcp/"
UI_URL = "http://127.0.0.1:4444/"
LOCK_PATH = Path("/tmp/cratebox-local-services.lock")
API_LOG = Path("/tmp/cratebox-api.log")
UI_LOG = Path("/tmp/cratebox-ui.log")


def http_status(url: str) -> int | None:
    try:
        with urlopen(url, timeout=1) as response:
            return response.status
    except HTTPError as error:
        return error.code
    except (OSError, URLError, TimeoutError):
        return None


def tail(path: Path) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-30:])
    except OSError:
        return "(no service log was written)"


def start_process(command: list[str], *, cwd: Path, log_path: Path) -> subprocess.Popen:
    log = log_path.open("ab", buffering=0)
    try:
        return subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()


def wait_ready(url: str, process: subprocess.Popen, label: str, log_path: Path) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = http_status(url)
        if status == 200:
            return
        if status is not None and status != 200:
            raise RuntimeError(f"{label} answered HTTP {status} at {url}; check the configured local port.")
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited before becoming ready. Recent log output:\n{tail(log_path)}")
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {label} at {url}. Recent log output:\n{tail(log_path)}")


def ensure_services() -> None:
    with LOCK_PATH.open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        api_endpoint = API_URL + "/api/playlists/revision"
        api_status = http_status(api_endpoint)
        api_process = None
        if api_status is None:
            api_process = start_process(
                [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"],
                cwd=CRATEBOX, log_path=API_LOG,
            )
            wait_ready(api_endpoint, api_process, "CrateBox API/MCP", API_LOG)
        elif api_status != 200:
            raise RuntimeError(f"Port 8000 is occupied by an incompatible service (HTTP {api_status} at {api_endpoint}).")

        ui_status = http_status(UI_URL)
        if ui_status is None:
            npm = os.environ.get("NPM_BIN", "npm")
            ui_process = start_process(
                [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "4444", "--strictPort"],
                cwd=CRATEBOX, log_path=UI_LOG,
            )
            wait_ready(UI_URL, ui_process, "CrateBox UI", UI_LOG)
        elif ui_status != 200:
            raise RuntimeError(f"Port 4444 is occupied by an incompatible service (HTTP {ui_status} at {UI_URL}).")


async def check_mcp() -> None:
    async with Client(MCP_URL, timeout=10, init_timeout=10) as client:
        names = {tool.name for tool in await client.list_tools()}
        if "export_playlist" not in names or "lookup_similar_tracks" not in names:
            raise RuntimeError("The CrateBox MCP endpoint is reachable but its expected tools are unavailable.")


def main() -> int:
    try:
        ensure_services()
        asyncio.run(check_mcp())
        proxy: FastMCP = FastMCPProxy(
            client_factory=lambda: Client(MCP_URL, timeout=120, init_timeout=120),
            name="CrateBox",
            provider_error_strategy="raise",
        )
        proxy.run(transport="stdio", show_banner=False)
    except Exception as error:
        print(f"CrateBox MCP startup failed: {error}", file=sys.stderr)
        print("Check /tmp/cratebox-api.log and /tmp/cratebox-ui.log, then run `npm run dev:all` to diagnose manually.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
