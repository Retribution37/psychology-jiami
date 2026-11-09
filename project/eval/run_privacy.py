"""隐私层评测：残留 PII、别名残留、占位符完整性、重识别攻击。

默认复用抽取评测的结果文件，不重复跑本地模型：
python eval/run_privacy.py --results results/base_1.5b_rules_test30.json

可选本地模型重识别攻击（每篇多花几秒）：
python eval/run_privacy.py --results ... --local-attack
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from common import DATA, RESULTS, load_jsonl
from app import llm, privacy_guard


def load_rows(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["id"]: row for row in payload["rows"]}


def residual_pii(text: str) -> list[dict]:
    found = []
    for kind, regex, label in privacy_guard.REGEX_RULES:
        for match in regex.finditer(text):
            value = match.group(1) if match.groups() else match.group(0)
            found.append({"kind": kind, "label": label, "preview": privacy_guard.mask(value)})
    return found


def alias_residual(text: str, mapping: list) -> list[str]:
    hits = []
    for entry in mapping:
        secrets = {entry.get("original", "")} | set(entry.get("aliases", []))
        for secret in secrets:
            if secret and secret in text:
                hits.append(entry["placeholder"])
                break
    return hits


def placeholder_integrity(text: str, mapping: list) -> tuple[list[str], list[str]]:
    missing = [entry["placeholder"] for entry in mapping if entry["placeholder"] not in text]
    known = {entry["placeholder"] for entry in mapping} | {"来访者"}
    unknown = sorted(
        {match.group(1) for match in privacy_guard.PLACEHOLDER_RE.finditer(text) if match.group(1) not in known}
    )
    return missing, unknown


def local_guess(text: str, placeholder: str, candidates: list[str]) -> str:
    system = "你是重识别攻击者，只能从候选名单里选一个姓名，不要解释。"
    user = (
        f"去标识化档案：\n{text[:1200]}\n\n"
        f"其中「{placeholder}」指代某个人。候选名单：{'、'.join(candidates)}。\n"
        "只回复一个候选姓名。"
    )
    try:
        reply = llm._local_chat(system, user, json_mode=False, max_tokens=32)
    except llm.LLMError:
        return ""
    for name in candidates:
        if name in reply:
            return name
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA / "synth_test.jsonl")
    parser.add_argument("--results", type=Path, default=RESULTS / "base_1.5b_rules_test30.json")
    parser.add_argument("--out", type=Path, default=RESULTS / "privacy.json")
    parser.add_argument("--local-attack", action="store_true")
    parser.add_argument("--seed", type=int, default=20261108)
    args = parser.parse_args()

    samples = load_jsonl(args.data)
    rows = load_rows(args.results)
    rng = random.Random(args.seed)

    details = []
    random_hits = verbatim_hits = local_hits = 0
    targets_total = 0

    for sample in samples:
        row = rows.get(sample["id"])
        if row is None:
            continue
        text, mapping = row["encrypted"], row["mapping"]
        pii = residual_pii(text)
        aliases = alias_residual(text, mapping)
        missing, unknown = placeholder_integrity(text, mapping)

        attacks = []
        for target in sample.get("attack_targets", []):
            true_name = target["true"]
            entry = next((item for item in mapping if true_name in item["aliases"]), None)
            leaked = true_name in text
            random_guess = rng.choice(target["candidates"])
            verbatim_guess = true_name if leaked else random_guess
            local_guess_name = ""
            if args.local_attack and entry is not None:
                local_guess_name = local_guess(text, entry["placeholder"], target["candidates"])

            targets_total += 1
            random_hits += random_guess == true_name
            verbatim_hits += verbatim_guess == true_name
            local_hits += local_guess_name == true_name
            attacks.append(
                {
                    "placeholder": entry["placeholder"] if entry else "",
                    "true": true_name,
                    "visible_placeholder": bool(entry),
                    "leaked": leaked,
                    "random_guess": random_guess,
                    "verbatim_guess": verbatim_guess,
                    "local_guess": local_guess_name,
                }
            )

        details.append(
            {
                "id": sample["id"],
                "residual_pii": pii,
                "alias_residual": aliases,
                "missing_placeholders": missing,
                "unknown_placeholders": unknown,
                "attacks": attacks,
            }
        )

    n = len(details)
    summary = {
        "n_samples": n,
        "residual_pii_rate": sum(1 for row in details if row["residual_pii"]) / n if n else 0.0,
        "alias_residual_rate": sum(1 for row in details if row["alias_residual"]) / n if n else 0.0,
        "missing_placeholder_count": sum(len(row["missing_placeholders"]) for row in details),
        "unknown_placeholder_count": sum(len(row["unknown_placeholders"]) for row in details),
        "direct_leak_rate": sum(1 for row in details if any(a["leaked"] for a in row["attacks"])) / n if n else 0.0,
        "attack_targets": targets_total,
        "reid_random_top1": random_hits / targets_total if targets_total else None,
        "reid_verbatim_top1": verbatim_hits / targets_total if targets_total else None,
        "reid_local_top1": local_hits / targets_total if (args.local_attack and targets_total) else None,
    }

    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "rows": details}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    pct = lambda value: "n/a" if value is None else f"{value * 100:.1f}%"
    print(f"样本数: {summary['n_samples']}")
    print(f"残留正则 PII 比例: {pct(summary['residual_pii_rate'])}")
    print(f"别名残留比例: {pct(summary['alias_residual_rate'])}")
    print(f"映射占位符缺失: {summary['missing_placeholder_count']}  未知占位符: {summary['unknown_placeholder_count']}")
    print(f"直接泄漏率: {pct(summary['direct_leak_rate'])}")
    print(f"重识别 top-1（随机猜测基线 10%）: {pct(summary['reid_random_top1'])}")
    print(f"重识别 top-1（利用明文泄漏）: {pct(summary['reid_verbatim_top1'])}")
    if args.local_attack:
        print(f"重识别 top-1（本机小模型攻击）: {pct(summary['reid_local_top1'])}")
    print(f"结果写入: {args.out}")


if __name__ == "__main__":
    main()
