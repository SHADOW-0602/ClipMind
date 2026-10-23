"""Start the ClipMind backend and frontend together (Ctrl+C stops both).

Usage:
    python scripts/dev.py
    python scripts/dev.py --no-reload

If a port is already serving, that half is left untouched. This makes the
script safe to run next to an existing dev server.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PORT = 8000
FRONTEND_PORT = 3000


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass


def spawn(command: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    kwargs: dict[str, object] = {"cwd": cwd}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ClipMind locally.")
    parser.add_argument("--no-reload", action="store_true", help="Disable uvicorn auto-reload.")
    args = parser.parse_args()

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []

    if port_open(BACKEND_PORT):
        print(f"Backend already listening on http://localhost:{BACKEND_PORT}")
    else:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ]
        if not args.no_reload:
            command.append("--reload")
        print("Starting backend: " + " ".join(command))
        processes.append(("backend", spawn(command, ROOT / "backend")))

    if port_open(FRONTEND_PORT):
        print(f"Frontend already listening on http://localhost:{FRONTEND_PORT}")
    else:
        npm = shutil.which("npm") or ("npm.cmd" if os.name == "nt" else "npm")
        print(f"Starting frontend: {npm} run dev")
        processes.append(("frontend", spawn([npm, "run", "dev"], ROOT / "frontend")))

    if not processes:
        print("\nClipMind is already running: http://localhost:3000")
        return 0

    print("\nClipMind starting. Open http://localhost:3000 (Ctrl+C to stop).\n")
    try:
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{name} exited with code {code}; stopping the other process.")
                    return code or 1
            time.sleep(0.75)
    except KeyboardInterrupt:
        print("\nStopping ClipMind...")
        return 0
    finally:
        for _, process in processes:
            stop(process)


if __name__ == "__main__":
    raise SystemExit(main())
