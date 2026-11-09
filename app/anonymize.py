"""去标识化的纯逻辑：校验小模型输出 -> 替换 -> 对应表 -> 回译。

不依赖网络、不碰文件，方便 smoke.py 直接测。
"""

import re

from .contract import (
    CATEGORIES,
    CATEGORY_LABEL,
    RELATION_LABEL,
    alias_is_sane,
    normalize_relation,
)
from .prompts import ANALYZE_LEGEND_HEAD

_LEADING_PROFILE_RE = re.compile(r"^[，,\s]*(男|女|\d{1,2}\s*岁)")


def _is_patient(text: str, alias: str) -> bool:
    """归档开头的"姓名，女，16岁"也算患者本人。"""
    if any(f"{marker}{alias}" in text for marker in ("来访者", "患者", "姓名：", "姓名:")):
        return True
    return text.startswith(alias) and bool(_LEADING_PROFILE_RE.match(text[len(alias):]))


def _clean_entities(raw, text):
    """校验小模型输出：只保留合法且能在原文里找到的别名；同名占位符合并。"""
    if not isinstance(raw, dict):
        raise ValueError("小模型输出不是 JSON 对象")
    entities = raw.get("entities", [])
    if not isinstance(entities, list):
        raise ValueError("小模型输出缺少 entities 数组")

    merged = {}
    for item in entities:
        if not isinstance(item, dict):
            continue
        placeholder = str(item.get("placeholder", "")).strip()
        category = str(item.get("category", "")).strip()
        aliases = item.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        aliases = [str(a).strip() for a in aliases if str(a).strip()]
        if not placeholder or category not in CATEGORIES or not aliases:
            continue

        aliases = [a for a in aliases if alias_is_sane(a, category) and a in text]
        if not aliases:
            continue

        relation = normalize_relation(category, item.get("relation"))
        # 患者本人统一用"来访者"，不依赖小模型记住这条规则
        if category == "人物" and (relation == "本人" or _is_patient(text, aliases[0])):
            placeholder = "来访者"
            relation = "本人"

        # 同一个占位符被不同类别复用：保留第一条，避免人物/地点串线
        if placeholder in merged and merged[placeholder]["category"] != category:
            continue

        if placeholder in merged:
            merged[placeholder]["aliases"].extend(aliases)
            if not merged[placeholder]["relation"] and relation:
                merged[placeholder]["relation"] = relation
        else:
            merged[placeholder] = {
                "placeholder": placeholder,
                "category": category,
                "relation": relation,
                "aliases": aliases,
                "note": str(item.get("note", "")).strip(),
            }

    # 同一别名只归一个占位符
    entries = list(merged.values())
    owner = {}
    for entry in entries:
        kept = []
        for alias in entry["aliases"]:
            if owner.setdefault(alias, entry["placeholder"]) == entry["placeholder"]:
                kept.append(alias)
        entry["aliases"] = kept

    # 同类别的不同占位符抢同一个片段（"锦绣花园" vs 完整门牌）：保留更长写法
    for entry in entries:
        others = [
            alias
            for other in entries
            if other is not entry and other["category"] == entry["category"]
            for alias in other["aliases"]
        ]
        entry["aliases"] = [a for a in entry["aliases"] if not any(a != b and a in b for b in others)]

    mapping = []
    for entry in entries:
        aliases = sorted(set(entry["aliases"]), key=len, reverse=True)
        if not aliases:
            continue
        counts = {a: text.count(a) for a in aliases}
        original = sorted(aliases, key=lambda a: (counts[a], len(a)), reverse=True)[0]
        mapping.append(
            {
                "placeholder": entry["placeholder"],
                "category": entry["category"],
                "relation": entry["relation"],
                "original": original,
                "aliases": aliases,
                "count": sum(counts.values()),
            }
        )
    return mapping


def anonymize(text: str, raw) -> tuple[str, list]:
    """原文 + 小模型 JSON -> (加密文本, 对应表)。空 entities 时原样返回。"""
    mapping = _clean_entities(raw, text)
    pairs = sorted(
        ((alias, e["placeholder"]) for e in mapping for alias in e["aliases"]),
        key=lambda p: len(p[0]),
        reverse=True,
    )
    encrypted = text
    for alias, placeholder in pairs:
        encrypted = encrypted.replace(alias, placeholder)
    # 原文"来访者林晓雨"替换后会叠成"来访者来访者"，合并一次保持可读性
    encrypted = encrypted.replace("来访者来访者", "来访者")
    # 档案开头的"来访者：沈予安，男"替换后变成"来访者：来访者"，去掉重复标签
    for label in ("来访者", "患者"):
        for colon in ("：", ":"):
            encrypted = encrypted.replace(f"{label}{colon}{label}", label)
    return encrypted, mapping


def _legend_line(entry: dict) -> str:
    label = CATEGORY_LABEL.get(entry["category"], "代称")
    relation = entry.get("relation", "")
    if relation:
        return f"- {entry['placeholder']}（{label}，{RELATION_LABEL[entry['category']]}：{relation}）"
    return f"- {entry['placeholder']}（{label}）"


def legend(mapping: list) -> str:
    """给云端大模型的脱敏说明：只有占位符、类别和受控关系属性，绝不含真名与 note。"""
    if not mapping:
        return ANALYZE_LEGEND_HEAD + "（本档案未发现需要脱敏的实体。）"
    ordered = sorted(mapping, key=lambda e: e["placeholder"] != "来访者")
    lines = [_legend_line(e) for e in ordered]
    return ANALYZE_LEGEND_HEAD + "\n".join(lines)


def reverse(text: str, mapping: list) -> str:
    """严格逐字回译：长占位符优先，对不上的原样保留。"""
    pairs = sorted(((e["placeholder"], e["original"]) for e in mapping), key=lambda p: len(p[0]), reverse=True)
    restored = text
    for placeholder, original in pairs:
        restored = restored.replace(placeholder, original)
    return restored
