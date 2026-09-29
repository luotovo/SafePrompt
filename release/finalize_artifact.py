"""Expose license/notice material at the top level of a PyInstaller onedir artifact."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    internal = artifact / "_internal"
    if not (artifact / "SafePrompt.exe").is_file() or not internal.is_dir():
        raise FileNotFoundError(f"not a SafePrompt onedir artifact: {artifact}")
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "LGPL-COMPLIANCE.md", "PADDLENLP-ATTRIBUTION.md"):
        shutil.copyfile(internal / name, artifact / name)
    target = artifact / "LICENSES"
    target.mkdir(exist_ok=True)
    shutil.copytree(internal / "LICENSES", target, dirs_exist_ok=True)
    print(f"finalized license material at {artifact}")


if __name__ == "__main__":
    main()
