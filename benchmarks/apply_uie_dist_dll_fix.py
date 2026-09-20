from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--dist-dir", type=Path, required=True)
args = parser.parse_args()

source = args.source.resolve()
destination = (args.dist_dir.resolve() / "_internal" / "paddle" / "libs" / source.name)
if not source.is_file():
    raise FileNotFoundError(source)
if not destination.parent.is_dir():
    raise FileNotFoundError(destination.parent)
shutil.copy2(source, destination)
print(json.dumps({
    "source": str(source),
    "destination": str(destination),
    "bytes": destination.stat().st_size,
    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
}, ensure_ascii=False))
