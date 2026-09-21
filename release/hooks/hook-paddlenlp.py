from pathlib import Path

from PyInstaller.utils.hooks import get_package_paths


_, paddle_dir = get_package_paths("paddle")
binaries = [(str(Path(paddle_dir) / "libs" / "mklml.dll"), "paddle/libs")]
module_collection_mode = {
    "paddlenlp.transformers": "py",
    "scipy.stats._distn_infrastructure": "py",
}
