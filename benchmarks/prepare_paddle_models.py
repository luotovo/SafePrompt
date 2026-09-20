from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

# PaddleNLP 2.6 Taskflow loads legacy .pdmodel files. Paddle 3 defaults to PIR
# .json unless this flag is set before importing Paddle.
os.environ.setdefault("FLAGS_enable_pir_api", "0")

from paddlenlp import Taskflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("uie-nano", "taskflow-ner"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.kind == "uie-nano":
        task = Taskflow("information_extraction", schema=["人名", "组织机构"], model="uie-nano",
                        home_path=str(args.output), device_id=-1)
    else:
        task = Taskflow("ner", mode="fast", home_path=str(args.output), device_id=-1)
    source_path = Path(task.task_path())
    task_path = source_path / "static"
    support_files = (["config.json", "vocab.txt", "special_tokens_map.json", "tokenizer_config.json"]
                     if args.kind == "uie-nano" else ["tag.dic", "q2b.dic", "word.dic"])
    for name in support_files:
        shutil.copy2(source_path / name, task_path / name)
    metadata = {"kind": args.kind, "task_path": str(task_path)}
    (args.output / "snapshot.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
