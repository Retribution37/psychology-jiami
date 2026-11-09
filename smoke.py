"""离线自检：不需要小模型、不需要 API key。覆盖契约 v2 / 替换 / 回译 / 泄漏扫描 / 知识库检索 / RAG 注入。"""

import os
import tempfile

from docx import Document

from app import anonymize, docx_io, kb, privacy_guard, rules

SAMPLE = [
    "来访者小明，男，16 岁，实验中学高二学生。",
    "近一个月因同桌王浩的言语嘲讽出现情绪低落，回家后常把自己关在房间。",
    "母亲李梅反映其夜间失眠，联系电话 13800138000，微信 xiaoming_2008。",
]

RAW = {
    "entities": [
        # 故意把患者本人标成人物A，验证清洗层会归一为来访者
        {"placeholder": "人物A", "category": "人物", "relation": "本人", "aliases": ["小明"], "note": "患者本人"},
        {"placeholder": "人物A", "category": "人物", "relation": "同桌", "aliases": ["王浩"], "note": "同桌"},
        {"placeholder": "人物B", "category": "人物", "relation": "母亲", "aliases": ["李梅"], "note": "母亲"},
        {"placeholder": "地点A", "category": "地点", "relation": "学校", "aliases": ["实验中学"], "note": ""},
        {"placeholder": "地点B", "category": "地点", "relation": "家庭住址", "aliases": ["阳光小区3栋502"], "note": "家庭住址"},
        {"placeholder": "账号A", "category": "账号", "relation": "电话", "aliases": ["13800138000"], "note": "电话"},
        {"placeholder": "账号B", "category": "账号", "relation": "微信", "aliases": ["xiaoming_2008"], "note": "微信"},
        # 以下都该被契约校验丢掉
        {"placeholder": "人物C", "category": "人物", "relation": "同桌", "aliases": ["原文里没有的人"], "note": ""},
        {"placeholder": "人物D", "category": "人物", "relation": "同桌", "aliases": ["的"], "note": "功能词"},
        {"placeholder": "人物E", "category": "人物", "relation": "同桌", "aliases": ["人物"], "note": "占位符词"},
        {"placeholder": "人物F", "category": "人物", "relation": "同桌", "aliases": ["王"], "note": "单字"},
    ]
}


def make_docx() -> str:
    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    doc = Document()
    for line in SAMPLE:
        doc.add_paragraph(line)
    row = doc.add_table(rows=1, cols=2).rows[0]
    row.cells[0].text = "家庭住址"
    row.cells[1].text = "阳光小区3栋502"
    doc.save(path)
    return path


def test_docx_and_anonymize() -> tuple[str, list]:
    path = make_docx()
    try:
        text = docx_io.read_docx(path)
    finally:
        os.unlink(path)

    assert "小明" in text and "阳光小区3栋502" in text, "docx 解析丢内容"
    assert "家庭住址 | 阳光小区3栋502" in text, "表格没有按行拼接"

    encrypted, mapping = anonymize.anonymize(text, RAW)
    for secret in ("小明", "王浩", "李梅", "实验中学", "阳光小区3栋502", "13800138000", "xiaoming_2008"):
        assert secret not in encrypted, f"加密后仍出现：{secret}"
    for token in ("来访者", "人物A", "人物B", "地点A", "地点B", "账号A", "账号B"):
        assert token in encrypted, f"占位符缺失：{token}"
    assert "来访者来访者" not in encrypted, "患者占位符叠字没有合并"
    assert len(mapping) == 7, f"对应表条数不对：{len(mapping)}"
    assert all(m["placeholder"] not in ("人物C", "人物D", "人物E", "人物F") for m in mapping), "非法别名未被丢弃"

    by_ph = {m["placeholder"]: m for m in mapping}
    assert by_ph["人物A"]["relation"] == "同桌", "关系属性丢失"
    assert by_ph["人物A"]["aliases"] == ["王浩"], "别名列表异常"

    legend = anonymize.legend(mapping)
    for secret in ("小明", "王浩", "阳光小区3栋502"):
        assert secret not in legend, "脱敏说明泄露了真名"
    assert "人物A（人物代称，关系：同桌）" in legend, "legend 没有关系属性"
    assert "同桌" in legend and "患者本人" not in legend, "legend 混入了 note"
    assert legend.index("来访者") < legend.index("人物A"), "来访者应排第一"

    report = "## 三、风险等级\n**中**：来访者与人物A有持续冲突，地点B为其主要压力场景。\n- 建议：联系人物B"
    restored = anonymize.reverse(report, mapping)
    assert "王浩" in restored and "阳光小区3栋502" in restored and "小明" in restored, "回译失败"
    assert "人物A" not in restored, "回译后仍残留占位符"

    assert anonymize.reverse("人物 A 说话", mapping) == "人物 A 说话", "严格逐字回译被破坏"

    same, empty = anonymize.anonymize(text, {"entities": []})
    assert same == text and empty == []

    for bad in (None, [], {"entities": "oops"}):
        try:
            anonymize.anonymize(text, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"非法输入未报错：{bad!r}")
    return text, mapping


def test_contract_fallback(text: str) -> None:
    raw = {
        "entities": [
            {"placeholder": "人物A", "category": "人物", "relation": "编造的关系", "aliases": ["王浩"], "note": ""},
            {"placeholder": "人物A", "category": "地点", "relation": "学校", "aliases": ["实验中学"], "note": ""},
            {"placeholder": "人物B", "category": "人物", "relation": "班主任", "aliases": ["李梅"], "note": ""},
        ]
    }
    _, mapping = anonymize.anonymize(text, raw)
    by_ph = {m["placeholder"]: m for m in mapping}
    assert by_ph["人物A"]["relation"] == "", "非法关系应清空但实体保留"
    assert by_ph["人物A"]["category"] == "人物", "同名占位符不应被改类别"
    assert "实验中学" not in [a for m in mapping for a in m["aliases"]], "串类别的别名不应并入"


def test_guard(text: str, mapping: list) -> None:
    encrypted, _ = anonymize.anonymize(text, RAW)
    issues = privacy_guard.scan_text(encrypted, mapping)
    assert not privacy_guard.blocking(issues), f"正常加密文本被误报：{issues}"

    leaky = encrypted + "\n补充：王浩的电话 13900139000。"
    issues = privacy_guard.scan_text(leaky, mapping)
    kinds = {item["kind"] for item in privacy_guard.blocking(issues)}
    assert "alias" in kinds, "残留别名未被拦截"
    assert "phone" in kinds, "手机号未被正则拦截"
    assert "13900139000" not in str(issues), "扫描结果不应回显完整号码"

    warning = privacy_guard.scan_text(encrypted + " 人物Z说……", mapping)
    assert not privacy_guard.blocking(warning), "未知占位符不应阻断"
    assert any(item["kind"] == "unknown_placeholder" for item in warning), "未知占位符应提示"


def test_rules(text: str) -> None:
    accounts = rules.extract_accounts(text)
    relations = {item["relation"] for item in accounts}
    assert {"电话", "微信"} <= relations, f"规则漏抽账号：{relations}"

    people = {item["aliases"][0]: item["relation"] for item in rules.extract_people(text)}
    assert people.get("小明") == "本人", f"来访者没被规则识别：{people}"
    assert people.get("王浩") == "同桌" and people.get("李梅") == "母亲", f"角色+姓名漏抽：{people}"

    # 回归：女友/导员等扩展角色、"A和B"并列人名、贪心多吃字
    extra = rules.extract_people(
        "同期与同班女友江安分手，与室友周芳和陈尹亮争执，经过导员陈沉劝导。"
        "母亲李梅反映来访者高二时失眠。"
    )
    extra_rel = {item["aliases"][0]: item["relation"] for item in extra}
    assert extra_rel.get("江安") == "恋人", f"女友没被识别：{extra_rel}"
    assert extra_rel.get("周芳") == "室友" and extra_rel.get("陈尹亮") == "室友", f"并列人名漏抽：{extra_rel}"
    assert extra_rel.get("陈沉") == "老师", f"导员没被识别或名字被截断：{extra_rel}"
    assert extra_rel.get("李梅") == "母亲" and "李梅反" not in extra_rel, f"贪心匹配吃了多余字：{extra_rel}"
    assert "高二时" not in extra_rel, "时间短语被误抽成人名"

    raw = {"entities": [{"placeholder": "账号A", "category": "账号", "relation": "电话", "aliases": ["13800138000"], "note": ""}]}
    merged = rules.supplement(text, raw)
    aliases = [a for item in merged["entities"] for a in item["aliases"]]
    assert aliases.count("13800138000") == 1, "规则补抽重复添加了电话"
    assert "李梅" in aliases and "王浩" in aliases, "规则没有补上被模型漏掉的人名"
    placeholders = [item["placeholder"] for item in merged["entities"]]
    assert len(placeholders) == len(set(placeholders)), f"占位符冲突：{placeholders}"
    assert "来访者" in placeholders, "患者本人没有使用来访者占位符"

    rich = (
        "来访者林晓雨，女，16岁，市第一中学高二学生，原就读于明德中学。"
        "母亲周敏在市人民医院工作，现住锦绣花园7栋1201，手机 13900139000。"
    )
    locs = {item["aliases"][0]: item["relation"] for item in rules.extract_locations(rich)}
    assert locs.get("市第一中学") == "学校" and locs.get("市人民医院") == "医院", f"地点漏抽：{locs}"
    assert locs.get("锦绣花园7栋1201") == "家庭住址", f"门牌号漏抽：{locs}"
    assert "学校" not in locs and "医院" not in locs, "泛化词被过度脱敏"
    assert not rules.extract_locations("建议学校加强关注，感谢学校支持。"), "泛化句被误抽成地名"

    partial = {"entities": [{"placeholder": "地点A", "category": "地点", "relation": "家庭住址", "aliases": ["锦绣花园"], "note": ""}]}
    upgraded = rules.supplement(rich, partial)
    up_aliases = [a for item in upgraded["entities"] for a in item["aliases"]]
    assert up_aliases.count("锦绣花园7栋1201") == 1, "残片地址没有升级为完整门牌"
    assert "锦绣花园" not in up_aliases, "升级后残片别名仍然残留"

    new_place = rules.supplement(rich, {"entities": []})
    new_ph = {item["placeholder"] for item in new_place["entities"]}
    assert any(p.startswith("地点") for p in new_ph), "规则补抽的地点没有分配占位符"
    assert "来访者" in new_ph, "开头的裸姓名没有识别为患者本人"

    # 同一别名被两个占位符抢：只保留先出现的那个，避免回译时串线
    dup = {
        "entities": [
            {"placeholder": "人物A", "category": "人物", "relation": "同桌", "aliases": ["王浩"], "note": ""},
            {"placeholder": "人物B", "category": "人物", "relation": "朋友", "aliases": ["王浩"], "note": ""},
        ]
    }
    _, dup_map = anonymize.anonymize(text, dup)
    assert [m["placeholder"] for m in dup_map] == ["人物A"], "重复别名没有被去重"


def test_kb(mapping: list) -> None:
    assert kb.available(), "知识库没有加载"
    assert kb.count() >= 50, f"知识卡数量异常：{kb.count()}"

    risk_cards = kb.retrieve("来访者说活着没意思，晚上睡不着，已经写过遗书")
    assert risk_cards, "风险文本没有召回任何知识卡"
    assert any(card["topic"] == "风险评估" for card in risk_cards), "风险文本没有召回风险评估卡"

    sleep_cards = kb.retrieve("最近三个月每周有三天入睡困难，早醒，白天没精神")
    assert any(card["topic"] == "睡眠" for card in sleep_cards), "失眠文本没有召回睡眠卡"

    eth_cards = kb.retrieve("咨询师能不能直接给来访者下诊断、开药")
    assert any(card["topic"] == "伦理与法律" for card in eth_cards), "伦理问题没有召回伦理卡"

    refs = kb.format_references(risk_cards)
    assert refs.startswith("===== 参考资料") and "[1]" in refs, "参考资料格式不对"

    secrets = [str(m.get("original", "")) for m in mapping]
    secrets += [str(alias) for m in mapping for alias in m.get("aliases", [])]
    for secret in (s for s in secrets if s):
        assert secret not in refs, f"参考资料泄漏真实信息：{secret}"

    cleaned = kb.sanitize_citations("依据[1]和[9]，另有[2]", len(risk_cards))
    assert "[9]" not in cleaned and "[1]" in cleaned and "[2]" in cleaned, "越界引用没有清理"


def test_rag_pipeline() -> None:
    from app import llm, main

    captured = {}
    original = llm.analyze_report

    def fake_report(text: str, legend_text: str, refs_text: str = "") -> str:
        captured["refs"] = refs_text
        return "## 一、概况\n依据[1]与[9]。\n"

    llm.analyze_report = fake_report
    try:
        result = main.analyze(main.AnalyzeIn(encrypted_text="来访者说活着没意思，晚上睡不着，和室友冲突。", mapping=[]))
    finally:
        llm.analyze_report = original

    assert "参考资料" in captured.get("refs", ""), "RAG 参考资料没有注入云端提示词"
    assert result["references"], "响应没有返回参考依据"
    assert "gaps" not in result and "rounds" not in result, "响应仍残留两轮协议字段"
    assert "[1]" in result["report_encrypted"], "合法引用被误删"
    assert "[9]" not in result["report_encrypted"], "越界引用没有清理"


def main() -> None:
    text, mapping = test_docx_and_anonymize()
    test_contract_fallback(text)
    test_guard(text, mapping)
    test_rules(text)
    test_kb(mapping)
    test_rag_pipeline()
    print("SMOKE PASS：docx / 契约 v2 / 替换 / 对应表 / legend / 回译 / 泄漏扫描 / 规则兜底 / 知识库检索 / RAG 注入 全部通过")


if __name__ == "__main__":
    main()
