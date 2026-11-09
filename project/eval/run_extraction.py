"""抽取评测：python eval/run_extraction.py --data data/synth_test.jsonl --out results/extraction_base.json"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from common import DATA, RESULTS, aggregate, evaluate_sample, load_jsonl, print_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA / "synth_test.jsonl")
    parser.add_argument("--out", type=Path, default=RESULTS / "extraction.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--label", default="local")
    parser.add_argument("--no-rules", action="store_true", help="只评模型裸输出，不叠加规则兜底")
    args = parser.parse_args()

    samples = load_jsonl(args.data)
    if args.limit:
        samples = samples[: args.limit]

    rows = []
    started = time.time()
    for index, sample in enumerate(samples, 1):
        row = evaluate_sample(sample, use_rules=not args.no_rules)
        rows.append(row)
        print(f"[{index}/{len(samples)}] {sample['id']} err={bool(row['error'])} recall={row['recall']:.2f} leak={len(row['leaked_aliases'])}")

    summary = aggregate(rows)
    summary["label"] = args.label
    summary["elapsed_sec"] = round(time.time() - started, 1)
    summary["avg_latency_sec"] = round(summary["elapsed_sec"] / len(samples), 2) if samples else 0

    args.out.parent.mkdir(exist_ok=True)
    payload = {"summary": summary, "rows": rows}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print_summary(summary)
    print(f"平均单篇耗时: {summary['avg_latency_sec']}s")
    print(f"结果写入: {args.out}")

    worst = sorted(rows, key=lambda row: (row["recall"], -len(row["leaked_aliases"])))[:5]
    print("\n召回最差样本：")
    for row in worst:
        print(f"- {row['id']} recall={row['recall']:.2f} leaked={row['leaked_aliases']} 过度={row['over_redacted_aliases']}")


if __name__ == "__main__":
    main()
