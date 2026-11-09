"""评测公共逻辑：跑通 小模型 -> 规则兜底 -> 替换，并与金标对齐。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import anonymize, contract, llm, privacy_guard, rules  # noqa: E402

DATA = ROOT / "data"
RESULTS = ROOT / "results"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_pipeline(text: str, use_rules: bool = True) -> dict:
    """返回模型原始输出、规则合并后的输出、加密文本与映射；失败时带 error。"""
    try:
        raw_model = llm.extract(text)
    except llm.LLMError as exc:
        return {"error": str(exc), "raw_model": None, "mapping": [], "encrypted": text}
    raw = rules.supplement(text, raw_model) if use_rules else raw_model
    try:
        encrypted, mapping = anonymize.anonymize(text, raw)
    except ValueError as exc:
        return {"error": str(exc), "raw_model": raw_model, "mapping": [], "encrypted": text}
    return {"error": "", "raw_model": raw_model, "mapping": mapping, "encrypted": encrypted}


def contract_violations(raw, text: str) -> list[str]:
    if not isinstance(raw, dict):
        return ["输出不是 JSON 对象"]
    entities = raw.get("entities")
    if not isinstance(entities, list):
        return ["缺少 entities 数组"]
    issues = []
    for index, item in enumerate(entities):
        if not isinstance(item, dict):
            issues.append(f"#{index} 不是对象")
            continue
        category = str(item.get("category", "")).strip()
        if category not in contract.CATEGORIES:
            issues.append(f"#{index} 非法类别 {category!r}")
        relation = str(item.get("relation", "")).strip()
        if relation and category in contract.RELATION_WHITELIST and relation not in contract.RELATION_WHITELIST[category]:
            issues.append(f"#{index} 非法关系 {relation!r}")
        aliases = item.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        if not aliases:
            issues.append(f"#{index} 缺少别名")
        for alias in aliases:
            alias = str(alias).strip()
            if alias and alias not in text:
                issues.append(f"#{index} 别名不在原文 {alias!r}")
            if alias and not contract.alias_is_sane(alias, category):
                issues.append(f"#{index} 别名不合规 {alias!r}")
    return issues


def evaluate_sample(sample: dict, use_rules: bool = True) -> dict:
    text = sample["text"]
    result = run_pipeline(text, use_rules=use_rules)
    mapping = result["mapping"]
    encrypted = result["encrypted"]

    gold = sample.get("entities", [])
    gold_alias = {alias: entity for entity in gold for alias in entity["aliases"]}
    pred_alias = {alias: entry for entry in mapping for alias in entry["aliases"]}

    recalled = [entity for entity in gold if any(a in pred_alias for a in entity["aliases"])]
    true_positive = sum(1 for entry in mapping if any(a in gold_alias for a in entry["aliases"]))
    relation_ok = 0
    for entity in recalled:
        entry = next(pred_alias[a] for a in entity["aliases"] if a in pred_alias)
        if entry.get("relation", "") == entity["relation"]:
            relation_ok += 1

    patient = next((entity for entity in gold if entity["placeholder"] == "来访者"), None)
    patient_ok = None
    if patient:
        patient_ok = any(pred_alias.get(a, {}).get("placeholder") == "来访者" for a in patient["aliases"])

    extra = sorted({alias for alias in pred_alias if alias not in gold_alias})
    leaked = sorted({alias for alias in gold_alias if alias in encrypted})
    guard_blocks = privacy_guard.blocking(privacy_guard.scan_text(encrypted, mapping))

    key_points = sample.get("key_points", [])
    keypoint_hits = [phrase for phrase in key_points if phrase in encrypted]
    protected = sample.get("protected_terms", [])
    protected_hits = [term for term in protected if term in encrypted]

    return {
        "id": sample["id"],
        "error": result["error"],
        "gold_entities": len(gold),
        "pred_entities": len(mapping),
        "precision": true_positive / len(mapping) if mapping else (1.0 if not gold else 0.0),
        "recall": len(recalled) / len(gold) if gold else 1.0,
        "relation_accuracy": relation_ok / len(recalled) if recalled else None,
        "patient_placeholder_ok": patient_ok,
        "over_redacted_aliases": extra,
        "leaked_aliases": leaked,
        "guard_blocks": [item["message"] for item in guard_blocks],
        "contract_violations": contract_violations(result["raw_model"], text),
        "json_valid": result["raw_model"] is not None and not result["error"],
        "keypoint_coverage": len(keypoint_hits) / len(key_points) if key_points else 1.0,
        "protected_retention": len(protected_hits) / len(protected) if protected else 1.0,
        "length_ratio": len(encrypted) / len(text) if text else 1.0,
        "mapping": mapping,
        "encrypted": encrypted,
    }


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    with_gold = [row for row in rows if row["gold_entities"]]
    relation_rows = [row for row in with_gold if row["relation_accuracy"] is not None]
    patient_rows = [row for row in with_gold if row["patient_placeholder_ok"] is not None]
    return {
        "n": n,
        "json_valid_rate": sum(row["json_valid"] for row in rows) / n,
        "avg_contract_violations": sum(len(row["contract_violations"]) for row in rows) / n,
        "entity_precision": sum(row["precision"] for row in rows) / n,
        "entity_recall": sum(row["recall"] for row in rows) / n,
        "relation_accuracy": (
            sum(row["relation_accuracy"] for row in relation_rows) / len(relation_rows) if relation_rows else None
        ),
        "patient_placeholder_accuracy": (
            sum(bool(row["patient_placeholder_ok"]) for row in patient_rows) / len(patient_rows)
            if patient_rows else None
        ),
        "direct_leak_rate": sum(1 for row in rows if row["leaked_aliases"]) / n,
        "guard_block_rate": sum(1 for row in rows if row["guard_blocks"]) / n,
        "over_redaction_rate": (
            sum(len(row["over_redacted_aliases"]) for row in rows)
            / max(1, sum(row["pred_entities"] for row in rows))
        ),
        "keypoint_coverage": sum(row["keypoint_coverage"] for row in rows) / n,
        "protected_retention": sum(row["protected_retention"] for row in rows) / n,
        "avg_length_ratio": sum(row["length_ratio"] for row in rows) / n,
    }


def print_summary(summary: dict) -> None:
    def pct(value):
        return "n/a" if value is None else f"{value * 100:.1f}%"

    print(f"样本数: {summary['n']}")
    print(f"JSON 合法率: {pct(summary['json_valid_rate'])}")
    print(f"平均契约违规/篇: {summary['avg_contract_violations']:.2f}")
    print(f"实体精确率: {pct(summary['entity_precision'])}  召回率: {pct(summary['entity_recall'])}")
    print(f"关系准确率: {pct(summary['relation_accuracy'])}")
    print(f"来访者占位符正确率: {pct(summary['patient_placeholder_accuracy'])}")
    print(f"直接泄漏率: {pct(summary['direct_leak_rate'])}")
    print(f"发送前扫描阻断率: {pct(summary['guard_block_rate'])}")
    print(f"过度脱敏率: {pct(summary['over_redaction_rate'])}")
    print(f"关键信息保留率: {pct(summary['keypoint_coverage'])}")
    print(f"受保护泛化词保留率: {pct(summary['protected_retention'])}")
