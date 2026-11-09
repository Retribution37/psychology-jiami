"""把金标 JSONL 转成与线上调用一致的对话格式，供 LoRA 训练使用。

用法：python train/prepare_sft.py
产出：data/train_messages.jsonl、data/valid_messages.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.prompts import EXTRACT_SYSTEM  # noqa: E402

FIELDS = ("placeholder", "category", "relation", "aliases", "note")


def convert(src: Path, dst: Path) -> int:
    count = 0
    with src.open(encoding="utf-8") as reader, dst.open("w", encoding="utf-8") as writer:
        for line in reader:
            if not line.strip():
                continue
            sample = json.loads(line)
            entities = [
                {field: entity.get(field, "" if field != "aliases" else []) for field in FIELDS}
                for entity in sample["entities"]
            ]
            answer = json.dumps({"entities": entities}, ensure_ascii=False, separators=(",", ":"))
            record = {
                "messages": [
                    {"role": "system", "content": EXTRACT_SYSTEM},
                    {"role": "user", "content": sample["text"]},
                    {"role": "assistant", "content": answer},
                ]
            }
            writer.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    data = ROOT / "data"
    train_count = convert(data / "synth_train.jsonl", data / "train_messages.jsonl")
    valid_count = convert(data / "synth_valid.jsonl", data / "valid_messages.jsonl")
    print(f"train={train_count} valid={valid_count}")
    print(f"输出: {data / 'train_messages.jsonl'}")
    print(f"输出: {data / 'valid_messages.jsonl'}")


if __name__ == "__main__":
    main()
