from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if args.command and args.command[0] == "--":
    args.command = args.command[1:]
if not args.command:
    parser.error("command is required")

args.output_dir.mkdir(parents=True, exist_ok=True)
started = time.perf_counter()
completed = subprocess.run(args.command, capture_output=True, check=False)
elapsed_ms = (time.perf_counter() - started) * 1000
(args.output_dir / "stdout.bin").write_bytes(completed.stdout)
(args.output_dir / "stderr.bin").write_bytes(completed.stderr)
(args.output_dir / "result.json").write_text(json.dumps({
    "command": args.command,
    "exit_code": completed.returncode,
    "elapsed_ms": elapsed_ms,
    "stdout_bytes": len(completed.stdout),
    "stderr_bytes": len(completed.stderr),
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"exit_code": completed.returncode, "elapsed_ms": elapsed_ms}))
