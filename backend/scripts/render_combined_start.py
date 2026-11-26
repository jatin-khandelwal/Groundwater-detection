from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

from backend.app.config import DATABASE_PATH
from backend.app.db import database_exists, ensure_runtime_schema, initialize_database
from backend.scripts.render_start import bootstrap_admin, download_artifact


children: list[subprocess.Popen] = []


def stop_children(exit_code: int = 0) -> None:
    for process in reversed(children):
        if process.poll() is None:
            process.terminate()
    for process in reversed(children):
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    raise SystemExit(exit_code)


def handle_signal(_signal_number, _frame) -> None:
    stop_children(0)


def wait_for_api() -> None:
    deadline = time.monotonic() + 180
    url = "http://127.0.0.1:8001/health"
    while time.monotonic() < deadline:
        if children[0].poll() is not None:
            raise SystemExit("Local API process exited before becoming healthy.")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                status = json.load(response)
            if status.get("model_loaded") and status.get("database_ready"):
                print("Local API is ready; starting Streamlit.", flush=True)
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit("Local API did not become healthy within 180 seconds.")


def main() -> None:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    download_artifact()
    if not database_exists(DATABASE_PATH):
        initialize_database(DATABASE_PATH)
    ensure_runtime_schema(DATABASE_PATH)
    bootstrap_admin()

    port = os.environ.get("PORT", "10000")
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8001"]
    )
    children.append(api)
    wait_for_api()

    frontend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "frontend/streamlit_app.py",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            port,
            "--browser.gatherUsageStats",
            "false",
        ]
    )
    children.append(frontend)

    while True:
        for process in children:
            code = process.poll()
            if code is not None:
                stop_children(code)
        time.sleep(1)


if __name__ == "__main__":
    main()
