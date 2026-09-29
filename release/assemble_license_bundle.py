"""Assemble the redistributable license bundle from exact installed/official sources."""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path


OFFICIAL = {
    "Qt/LGPL-3.0-only.txt": "https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/LGPL-3.0-only.txt",
    "Qt/GPL-3.0-only.txt": "https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/GPL-3.0-only.txt",
    "OpenSSL/LICENSE.txt": "https://raw.githubusercontent.com/openssl/openssl/openssl-3.0.11/LICENSE.txt",
    "PaddleNLP/LICENSE.txt": "https://raw.githubusercontent.com/PaddlePaddle/PaddleNLP/v2.6.1/LICENSE",
}


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--python-license", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "licenses")
    args = parser.parse_args()
    site = args.venv.resolve() / "Lib" / "site-packages"
    output = args.output.resolve()
    repo = Path(__file__).resolve().parent.parent

    copies = {
        repo / "LICENSE": output / "SafePrompt" / "LICENSE.txt",
        site / "onnxruntime" / "LICENSE": output / "ONNXRuntime" / "LICENSE.txt",
        site / "onnxruntime" / "ThirdPartyNotices.txt": output / "ONNXRuntime" / "ThirdPartyNotices.txt",
        args.python_license.resolve(): output / "Python" / "LICENSE.txt",
        site / "six-1.17.0.dist-info" / "LICENSE": output / "six" / "LICENSE.txt",
        site / "pynput-1.8.2.dist-info" / "licenses" / "COPYING.LGPL": output / "pynput" / "COPYING.LGPL",
        site / "pyreadline3-3.5.6.dist-info" / "licenses" / "LICENSE.md": output / "pyreadline3" / "LICENSE.md",
        site / "PyInstaller-6.22.3.dist-info" / "licenses" / "COPYING.txt": output / "PyInstaller" / "COPYING.txt",
    }
    for source, target in copies.items():
        copy_file(source, target)

    numpy_source = site / "numpy-2.5.3.dist-info" / "licenses"
    for source in numpy_source.rglob("*"):
        if source.is_file():
            copy_file(source, output / "NumPy" / source.relative_to(numpy_source))

    for relative, url in OFFICIAL.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            target.write_bytes(response.read())

    for package in ("PySide6", "Shiboken6"):
        metadata = next(site.glob(f"{package.lower()}-6.11.2.dist-info/METADATA"))
        copy_file(metadata, output / package / "WHEEL-METADATA.txt")
    print(f"assembled {sum(1 for p in output.rglob('*') if p.is_file())} files in {output}")


if __name__ == "__main__":
    main()
