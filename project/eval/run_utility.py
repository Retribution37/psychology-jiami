"""效用层评测：关键信息保留、泛化词保留、占位符完整性、长度变化。

默认只用抽取结果做离线统计：
python eval/run_utility.py --results results/base_1.5b_rules_test30.json

接入云端报告（需要 DEEPSEEK_API_KEY；mock 云端只验证流程，不代表效果）：
python eval/run_utility.py --results ... --cloud --judge
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import DATA, RESULTS, load_jsonl
from app import anonymize, kb, llm, privacy_guard


def load_rows(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["id"]: row for row in payload["rows"]}


def placeholder_stats(text: str, mapping: list) -> tuple[int, int]:
    missing = sum(1 for entry in mapping if entry["placeholder"] not in text)
    known = {entry["placeholder"] for entry in mapping} | {"来访者"}
    unknown = len(
        {match.group(1) for match in privacy_guard.PLACEHOLDER_RE.finditer(text) if match.group(1) not in known}
    )
    return missing, unknown


def cloud_report(encrypted: str, mapping: list) -> dict:
    legend = anonymize.legend(mapping)
    references = kb.retrieve(encrypted, [str(entry.get("relation", "")) for entry in mapping])
    refs_text = kb.format_references(references)
    report_encrypted = llm.analyze_report(encrypted, legend, refs_text)
    report_encrypted = kb.sanitize_citations(report_encrypted, len(references))
    return {
        "report_encrypted": report_encrypted,
        "report_restored": anonymize.reverse(report_encrypted, mapping),
        "references": len(references),
    }


def judge_report(report: str) -> dict | None:
    system = "你是心理档案报告评审。只输出 JSON，不要解释。"
    user = (
        "请按 1-5 分评价这份报告（5 最好）：\n"
        "1) structure 结构完整\n2) key_facts 覆盖档案关键事实\n"
        "3) actionability 建议可执行\n4) no_fabrication 没有编造信息\n"
        "只输出 {\"structure\":n,\"key_facts\":n,\"actionability\":n,\"no_fabrication\":n}\n\n"
        f"报告：\n{report[:4000]}"
    )
    try:
        data = llm._parse_json(llm._deepseek_chat(system, user, json_mode=True, temperature=0))
    except llm.LLMError:
        return None
    scores = {}
    for key in ("structure", "key_facts", "actionability", "no_fabrication"):
        value = data.get(key)
        if isinstance(value, (int, float)) and 1 <= value <= 5:
            scores[key] = float(value)
    return scores or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA / "synth_test.jsonl")
    parser.add_argument("--results", type=Path, default=RESULTS / "base_1.5b_rules_test30.json")
    parser.add_argument("--out", type=Path, default=RESULTS / "utility.json")
    parser.add_argument("--cloud", action="store_true", help="调用云端生成报告（需要 API key）")
    parser.add_argument("--judge", action="store_true", help="调用云端按 rubric 打分（隐含 --cloud）")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    samples = load_jsonl(args.data)
    if args.limit:
        samples = samples[: args.limit]
    rows = load_rows(args.results)

    details = []
    keypoint_sum = protected_sum = length_sum = 0.0
    mapping_sum = missing_sum = unknown_sum = 0
    judged = []
    cloud_rows = []

    for sample in samples:
        row = rows.get(sample["id"])
        if row is None:
            continue
        encrypted, mapping = row["encrypted"], row["mapping"]
        missing, unknown = placeholder_stats(encrypted, mapping)

        key_points = sample.get("key_points", [])
        keypoint_rate = (sum(1 for phrase in key_points if phrase in encrypted) / len(key_points)) if key_points else 1.0
        protected = sample.get("protected_terms", [])
        protected_rate = (sum(1 for term in protected if term in encrypted) / len(protected)) if protected else 1.0

        detail = {
            "id": sample["id"],
            "keypoint_coverage": keypoint_rate,
            "protected_retention": protected_rate,
            "length_ratio": len(encrypted) / len(sample["text"]) if sample["text"] else 1.0,
            "mapping_size": len(mapping),
            "missing_placeholders": missing,
            "unknown_placeholders": unknown,
        }

        if args.cloud or args.judge:
            try:
                result = cloud_report(encrypted, mapping)
            except llm.LLMError as exc:
                detail["cloud_error"] = str(exc)
            else:
                restored = result["report_restored"]
                report_keypoint = (
                    sum(1 for phrase in key_points if phrase in restored) / len(key_points) if key_points else 1.0
                )
                detail.update(
                    references=result["references"],
                    report_keypoints=report_keypoint,
                    report_chars=len(restored),
                )
                cloud_rows.append(
                    {
                        "id": sample["id"],
                        "report_restored": restored,
                        "report_encrypted": result["report_encrypted"],
                    }
                )
                if args.judge:
                    scores = judge_report(restored)
                    if scores:
                        detail["judge"] = scores
                        judged.append(scores)

        keypoint_sum += keypoint_rate
        protected_sum += protected_rate
        length_sum += detail["length_ratio"]
        mapping_sum += len(mapping)
        missing_sum += missing
        unknown_sum += unknown
        details.append(detail)

    n = len(details)
    summary = {
        "n_samples": n,
        "keypoint_coverage": keypoint_sum / n if n else None,
        "protected_retention": protected_sum / n if n else None,
        "avg_length_ratio": length_sum / n if n else None,
        "avg_mapping_size": mapping_sum / n if n else None,
        "missing_placeholder_count": missing_sum,
        "unknown_placeholder_count": unknown_sum,
        "report_keypoint_coverage": (
            sum(item.get("report_keypoints", 0.0) for item in details if "report_keypoints" in item)
            / max(1, sum(1 for item in details if "report_keypoints" in item))
            if any("report_keypoints" in item for item in details)
            else None
        ),
        "judge_avg": (
            {key: sum(score.get(key, 0) for score in judged) / len(judged) for key in judged[0]}
            if judged
            else None
        ),
        "avg_references": (
            sum(item.get("references", 0) for item in details if "references" in item)
            / max(1, sum(1 for item in details if "references" in item))
            if any("references" in item for item in details)
            else None
        ),
    }

    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "rows": details, "cloud_reports": cloud_rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    pct = lambda value: "n/a" if value is None else f"{value * 100:.1f}%"
    print(f"样本数: {summary['n_samples']}")
    print(f"加密文本关键信息保留率: {pct(summary['keypoint_coverage'])}")
    print(f"受保护泛化词保留率: {pct(summary['protected_retention'])}")
    print(f"平均长度比: {summary['avg_length_ratio']:.3f}" if summary["avg_length_ratio"] is not None else "n/a")
    print(f"平均对应表规模: {summary['avg_mapping_size']:.1f}" if summary["avg_mapping_size"] is not None else "n/a")
    print(f"映射占位符缺失: {summary['missing_placeholder_count']}  未知占位符: {summary['unknown_placeholder_count']}")
    if summary["report_keypoint_coverage"] is not None:
        print(f"云端报告回译后关键信息覆盖率: {pct(summary['report_keypoint_coverage'])}")
    if summary["avg_references"] is not None:
        print(f"平均检索参考条数: {summary['avg_references']:.1f}")
    if summary["judge_avg"]:
        print("云端 rubric 均分（1-5）: " + ", ".join(f"{k}={v:.1f}" for k, v in summary["judge_avg"].items()))
    print(f"结果写入: {args.out}")


if __name__ == "__main__":
    main()
