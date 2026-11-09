"""检索层评测：用人工标注的查询检查主题命中率、MRR 与资料纯净度。

python eval/run_retrieval.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import RESULTS
from app import kb

CASES = [
    {"query": "来访者说活着没意思，已经写好遗书，想把东西送人", "topics": ["风险评估"]},
    {"query": "最近两周反复用刀片划手臂，说这样能缓解情绪", "topics": ["风险评估"]},
    {"query": "情绪低落，什么都不想干，觉得自己是累赘，持续两个月", "topics": ["抑郁"]},
    {"query": "考试前心慌手抖，担心考不好，注意力集中不了", "topics": ["焦虑"]},
    {"query": "三个月来每周三晚入睡困难，早醒，白天没精神", "topics": ["睡眠"]},
    {"query": "睡前总是想事情，越躺越清醒，白天疲劳", "topics": ["睡眠"]},
    {"query": "与室友因为卫生和噪音多次争吵，宿舍群里互相指责", "topics": ["家庭与关系"]},
    {"query": "和女友分手后反复查看她的动态，回避共同课程", "topics": ["家庭与关系"]},
    {"query": "被同学起外号并在群里嘲笑，不敢去教室", "topics": ["家庭与关系"]},
    {"query": "母亲每天多次打电话查问，来访者觉得被控制，争吵后离家", "topics": ["家庭与关系"]},
    {"query": "咨询师能不能直接给来访者下诊断并建议吃药", "topics": ["伦理与法律"]},
    {"query": "挂科两门，毕业论文拖了很久，临近毕业很迷茫", "topics": ["大学生心理"]},
    {"query": "报告如何区分咨询师的推断和档案事实", "topics": ["报告写作", "伦理与法律"]},
    {"query": "如何帮助来访者识别自动思维，布置家庭作业", "topics": ["CBT与咨询技术"]},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(RESULTS / "retrieval.json"))
    args = parser.parse_args()

    rows = []
    hit1 = hit3 = 0
    reciprocal = 0.0
    for case in CASES:
        cards = kb.retrieve(case["query"])
        topics = [card["topic"] for card in cards]
        rank = next((i for i, topic in enumerate(topics, 1) if topic in case["topics"]), None)
        hit1 += int(rank == 1)
        hit3 += int(bool(rank) and rank <= 3)
        reciprocal += 1 / rank if rank else 0.0
        rows.append(
            {
                "query": case["query"],
                "expected_topics": case["topics"],
                "returned": [{"id": card["id"], "topic": card["topic"], "title": card["title"]} for card in cards],
                "first_hit_rank": rank,
            }
        )

    total = len(CASES)
    refs = kb.format_references(kb.retrieve("来访者情绪低落，失眠，和室友冲突"))
    secret_patterns = [kb.PLACEHOLDER_RE, re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), re.compile(r"\b\d{17}[\dXx]\b")]
    leak = [pattern.pattern for pattern in secret_patterns if pattern.search(refs)]

    summary = {
        "n_queries": total,
        "hit_at_1": hit1 / total,
        "hit_at_3": hit3 / total,
        "mrr": reciprocal / total,
        "avg_refs": sum(len(row["returned"]) for row in rows) / total,
        "kb_cards": kb.count(),
        "reference_leak_patterns": leak,
    }

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"查询数: {total}")
    print(f"主题 Hit@1: {summary['hit_at_1'] * 100:.1f}%")
    print(f"主题 Hit@3: {summary['hit_at_3'] * 100:.1f}%")
    print(f"MRR: {summary['mrr']:.3f}")
    print(f"平均参考条数: {summary['avg_refs']:.1f}")
    print(f"知识卡: {summary['kb_cards']}")
    print("资料纯净度: " + ("通过" if not leak else f"发现风险 {leak}"))
    print(f"结果写入: {out}")


if __name__ == "__main__":
    main()
