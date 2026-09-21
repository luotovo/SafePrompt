from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    args = parser.parse_args()
    process = subprocess.Popen([str(args.executable.resolve())], cwd=args.cwd.resolve())
    time.sleep(args.wait_seconds)
    alive = process.poll() is None
    if alive:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    payload = {
        "executable": str(args.executable.resolve()),
        "cwd": str(args.cwd.resolve()),
        "pid": process.pid,
        "alive_after_seconds": args.wait_seconds if alive else None,
        "exit_code_after_probe_stop": process.returncode,
    }
    args.output.resolve().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0 if alive else 1


if __name__ == "__main__":
    raise SystemExit(run())
