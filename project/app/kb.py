"""本地心理学知识库与轻量 BM25 检索。

知识卡来自公开指南、法律、伦理规范与开放教材，入库内容是转述摘要；
检索查询只使用脱敏文本和受控关系词，不接触真实身份。
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "kb"

PLACEHOLDER_RE = re.compile(r"(?:来访者|人物|地点|账号)[A-Z]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[a-zA-Z0-9]+")

# 单字噪声大，只在不是功能字时保留；真正起作用的是双字组合
_STOP_CHARS = set(
    "的了是在和与也都就还很每常总经去来上下中内外个一二三四五六七八九十"
    "我你他她它们这那有没不人到对为被把将让给从向于其之而且或如有可会能要又更最再才只"
)

_SYNONYMS = {
    "睡不着": ["失眠"],
    "睡不好": ["失眠", "睡眠"],
    "早醒": ["失眠", "睡眠"],
    "不想活": ["自杀"],
    "活着没意思": ["自杀"],
    "轻生": ["自杀"],
    "结束生命": ["自杀"],
    "自残": ["自伤", "自杀"],
    "情绪低落": ["抑郁"],
    "开心不起来": ["抑郁"],
    "没兴趣": ["抑郁", "兴趣减退"],
    "心慌": ["焦虑", "惊恐"],
    "紧张": ["焦虑"],
    "担心": ["焦虑", "担忧"],
    "分手": ["失恋"],
    "女友": ["恋人", "失恋"],
    "男友": ["恋人", "失恋"],
    "室友": ["宿舍", "冲突"],
    "宿舍": ["室友"],
    "嘲笑": ["欺凌"],
    "孤立": ["欺凌"],
    "排挤": ["欺凌"],
    "霸凌": ["欺凌"],
    "成绩": ["学业", "考试"],
    "挂科": ["学业"],
    "考试": ["学业", "焦虑"],
    "妈妈": ["母亲", "亲子"],
    "爸爸": ["父亲", "亲子"],
    "父母": ["亲子", "家庭"],
    "威胁": ["暴力", "安全"],
    "喝酒": ["酒精", "物质使用"],
    "游戏": ["网络", "游戏"],
}

_RISK_CUES = ("自杀", "自伤", "自残", "不想活", "轻生", "结束生命", "活着没意思", "遗书", "跳楼", "割腕")
_MAX_PER_TOPIC = 2
_MAX_FOR_TOP_TOPIC = 3


def _tokens(text: str) -> list[str]:
    text = PLACEHOLDER_RE.sub(" ", text)
    tokens = []
    for seq in _CJK_RE.findall(text):
        tokens.extend(ch for ch in seq if ch not in _STOP_CHARS)
        tokens.extend(
            seq[index:index + 2]
            for index in range(len(seq) - 1)
            if any(ch not in _STOP_CHARS for ch in seq[index:index + 2])
        )
    tokens.extend(word.lower() for word in _ASCII_RE.findall(text))
    return tokens


@lru_cache(maxsize=1)
def _index():
    sources = {}
    cards = []
    try:
        raw_sources = json.loads((KB_DIR / "sources.json").read_text(encoding="utf-8"))
        sources = {item["id"]: item for item in raw_sources if isinstance(item, dict)}
        for line in (KB_DIR / "knowledge.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            card = json.loads(line)
            if card.get("source") in sources:
                cards.append(card)
    except (OSError, json.JSONDecodeError):
        return [], {}, 0.0, {}

    docs = []
    for card in cards:
        text = " ".join(
            [card["title"]] * 3
            + [" ".join(card.get("tags", []))] * 2
            + [card["topic"]] * 2
            + [card["content"]]
        )
        docs.append(_tokens(text))

    df = {}
    for doc in docs:
        for token in set(doc):
            df[token] = df.get(token, 0) + 1
    total = len(docs)
    idf = {token: math.log(1 + (total - freq + 0.5) / (freq + 0.5)) for token, freq in df.items()}
    avgdl = sum(len(doc) for doc in docs) / total if total else 0.0
    return list(zip(cards, docs)), idf, avgdl, sources


def _query_tokens(text: str, relations: list[str] | None = None) -> list[str]:
    base = text + " " + " ".join(relations or [])
    tokens = _tokens(base)
    for cue, extras in _SYNONYMS.items():
        if cue in base:
            for extra in extras:
                tokens.extend(_tokens(extra))
    return tokens


def _bm25(query: list[str], document: list[str], idf: dict, avgdl: float) -> float:
    if not query or not document or not avgdl:
        return 0.0
    counts = {}
    for token in document:
        counts[token] = counts.get(token, 0) + 1
    score = 0.0
    k1, b = 1.2, 0.75
    for token in set(query):
        freq = counts.get(token, 0)
        if not freq:
            continue
        score += idf.get(token, 0.0) * freq * (k1 + 1) / (
            freq + k1 * (1 - b + b * len(document) / avgdl)
        )
    return score


def retrieve(text: str, relations: list[str] | None = None, k: int = 6) -> list[dict]:
    """按脱敏文本检索知识卡；主议题最多三张、其余议题最多两张，保证覆盖面。"""
    entries, idf, avgdl, _sources = _index()
    if not entries:
        return []
    query = _query_tokens(text, relations)
    if not query:
        return []

    ranked = []
    for index, (card, document) in enumerate(entries):
        score = _bm25(query, document, idf, avgdl)
        if score > 0:
            ranked.append((score, index, card))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    if not ranked or ranked[0][0] < 1.5:
        return []
    cutoff = max(1.5, ranked[0][0] * 0.3)
    top_topic = ranked[0][2]["topic"]

    selected = []
    topic_count = {}
    for score, _order, card in ranked:
        if score < cutoff:
            break
        topic = card["topic"]
        limit = _MAX_FOR_TOP_TOPIC if topic == top_topic else _MAX_PER_TOPIC
        if topic_count.get(topic, 0) >= limit:
            continue
        selected.append(card)
        topic_count[topic] = topic_count.get(topic, 0) + 1
        if len(selected) >= k:
            break

    if any(cue in text for cue in _RISK_CUES) and not any(card["topic"] == "风险评估" for card in selected):
        risk_card = next((card for _score, _order, card in ranked if card["topic"] == "风险评估"), None)
        if risk_card is not None:
            if len(selected) >= k:
                selected[-1] = risk_card
            else:
                selected.append(risk_card)
    return selected


def format_references(cards: list[dict]) -> str:
    """把检索结果拼成提示词里的编号参考资料。"""
    if not cards:
        return ""
    sources = _index()[3]
    lines = [
        "===== 参考资料（本地知识库检索，公开专业资料）=====",
        "下列资料用于核对专业原则与建议；引用时在句末标注 [编号]，不要编造资料，也不要把一般原则当作个案事实。",
    ]
    for index, card in enumerate(cards, 1):
        source = sources.get(card["source"], {})
        citation = str(source.get("title", ""))
        year = source.get("year")
        if year:
            citation = f"{citation}，{year}"
        lines.append(f"[{index}] {card['title']}（{citation}）")
        lines.append(card["content"])
    return "\n".join(lines)


def public_refs(cards: list[dict]) -> list[dict]:
    """返回给前端的来源元数据，不含知识卡正文。"""
    sources = _index()[3]
    refs = []
    for card in cards:
        source = sources.get(card["source"], {})
        refs.append(
            {
                "id": card["id"],
                "title": card["title"],
                "topic": card["topic"],
                "source": card["source"],
                "source_title": source.get("title", ""),
                "source_year": source.get("year"),
                "source_url": source.get("url", ""),
            }
        )
    return refs


_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def sanitize_citations(text: str, ref_count: int) -> str:
    """删掉超出参考资料范围的引用编号，避免模型编造来源。"""
    def replace(match: re.Match) -> str:
        return match.group(0) if 1 <= int(match.group(1)) <= ref_count else ""

    return _CITATION_RE.sub(replace, text)


def count() -> int:
    return len(_index()[0])


def available() -> bool:
    return bool(_index()[0])
