"""规则兜底：账号与"角色+姓名"不依赖小模型，用正则强制补抽。"""

import re

from .contract import alias_is_sane

ACCOUNT_RULES = (
    ("身份证", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("电话", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("邮箱", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("QQ", re.compile(r"(?:QQ|qq|扣扣)\s*号?\s*[:：]?\s*([1-9]\d{4,11})")),
    ("微信", re.compile(r"(?:微信号|微信|WeChat|wechat)\s*[:：]?\s*([A-Za-z][-_A-Za-z0-9]{5,19})")),
    ("学号", re.compile(r"学号\s*[:：]?\s*([A-Za-z0-9]{6,20})")),
    ("银行卡", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
)

# 地点名里不允许出现这些粘连字，避免把"原就读于""现住"吞进地名
_LOC_GLUE = "的是了在和与就也都还又很更最不没来去上下于从到往向给对为被把将让找陪带住现读转考工作长期曾经常每多次知情况问题因为由于"
_LOC_BASE = r"[^\s，。、；：！？" + _LOC_GLUE + r"]"
_LOC_CTX = r"(?:^|[，。；：！？、\s]|[在于到从入读考住址])"

SCHOOL_RE = re.compile(_LOC_CTX + r"(" + _LOC_BASE + r"{2,10}?(?:中学|小学|大学|学院|学校|附中|职高))")
HOSPITAL_RE = re.compile(_LOC_CTX + r"(" + _LOC_BASE + r"{2,10}?(?:医院|卫生院|诊所))")
ADDRESS_RE = re.compile(
    _LOC_CTX + r"(" + _LOC_BASE + r"{2,10}?(?:小区|花园|公寓|新村|家园|苑)"
    r"[A-Za-z0-9]{0,3}(?:[栋座][0-9]{1,4}室?|[0-9]{1,4}号院?))"
)
STREET_RE = re.compile(_LOC_CTX + r"(" + _LOC_BASE + r"{2,10}?(?:路|街|巷|大道|里)[0-9]{1,4}号院?)")

NOT_A_LOCATION_PREFIX = (
    "建议", "希望", "要求", "感谢", "关注", "联系", "鼓励", "提醒", "告知",
    "表示", "认为", "社区", "当地", "附近", "这家", "那家", "一家", "该校",
)

LOCATION_RULES = (
    ("学校", SCHOOL_RE),
    ("医院", HOSPITAL_RE),
    ("家庭住址", ADDRESS_RE),
    ("家庭住址", STREET_RE),
)

ROLE_RELATION = {
    "来访者": "本人",
    "患者": "本人",
    "母亲": "母亲",
    "父亲": "父亲",
    "妈妈": "母亲",
    "爸爸": "父亲",
    "同桌": "同桌",
    "同学": "同学",
    "室友": "室友",
    "朋友": "朋友",
    "同事": "同事",
    "邻居": "邻居",
    "恋人": "恋人",
    "女友": "恋人",
    "男友": "恋人",
    "女朋友": "恋人",
    "男朋友": "恋人",
    "班主任": "班主任",
    "老师": "老师",
    "导师": "老师",
    "导员": "老师",
    "校长": "老师",
    "医生": "医生",
    "辅导员": "老师",
    "学长": "同学",
    "学姐": "同学",
    "学弟": "同学",
    "学妹": "同学",
    "组长": "其他",
    "阿姨": "其他亲属",
    "叔叔": "其他亲属",
    "舅舅": "其他亲属",
    "姑姑": "其他亲属",
}

_BOUNDARY = (
    "，。、；：！？\\s在是说的反映多次多知情知工作长期曾与向给被把将让找陪带"
    "和也还已正于从到对为不没有会要能可就都很每常总经去来回住读上下"
    "因介偶建当安评选查治康恢稳好转复诊询聊谈讲问答帮照顾关支"
    "分劝沟借"
    "辱骂欺嘲讽争吵打威胁骚扰排斥孤立批评指责"
    "$"
)
_NAME_END = r"(?=[" + _BOUNDARY + r"]|一起|一同)"

# 中文姓名首字约束：把"建议家""关系紧"这类动词短语挡在门外
SURNAMES = frozenset("王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗梁宋唐许邓曹彭蒋蔡潘"
                     "沈冯苏卢魏薛范杜丁程傅钟姜崔谭廖陆汪金石戴贾韦夏邹方白孟秦江侯顾龙万段雷钱汤尹黎易常武乔贺赖龚文"
                     "韩谢于叶田董袁郑曾萧吕姚熊康毛邱傅阎")
# 来访者可能写昵称（小明、阿杰），不限姓氏；其他人一律按"姓氏+1~2字"约束
SELF_RE = re.compile(r"(来访者|患者)\s*[：:]?\s*([\u4e00-\u9fff]{2,3})" + _NAME_END)
_ROLE_NAMES = sorted((role for role in ROLE_RELATION if role not in ("来访者", "患者")), key=len, reverse=True)
ROLE_RE = re.compile(
    r"(" + "|".join(_ROLE_NAMES) + r")"
    r"([" + "".join(sorted(SURNAMES)) + r"][\u4e00-\u9fff]{1,2})" + _NAME_END
)
# "室友周芳和陈尹亮"里的第二个人没有角色词，沿第一个姓名向后追并列人名
COORD_RE = re.compile(
    r"(?:以及|还有|和|与|及|、|跟)\s*"
    r"([" + "".join(sorted(SURNAMES)) + r"][\u4e00-\u9fff]{1,2})" + _NAME_END
)

# 名字以这些词开头时，多半命中的是动词短语而不是姓名
NOT_NAME_PREFIX = frozenset("与和找说让给在是的对为被把将陪带")

NOT_A_NAME = frozenset({
    "长期", "多次", "知情", "工作", "外地", "家里", "学校", "医院", "父母", "家人",
    "治疗", "咨询", "情况", "问题", "情绪", "睡眠", "成绩", "电话", "微信", "手机",
    "目前", "最近", "已经", "正在", "一直", "平时", "经常", "因为", "由于", "现在",
    "当时", "后来", "感到", "出现", "表示", "认为", "希望", "建议", "评估",
    "压力", "高强度", "焦虑", "抑郁", "学业", "作息", "状态", "关注", "支持",
    "陪伴", "沟通", "交流", "冲突", "矛盾", "关系", "家庭", "生活", "学习",
})

# 贪心匹配偶尔多吃一个字（李梅反映 -> 李梅反），这些字不做姓名结尾
_UNLIKELY_NAME_TAIL = frozenset(
    "反映的了是在和与也都就很每常总经去来回报住读上下曾多因于被把将让找陪带给向对为不没有会要能可分劝沟借好复当选评查"
)


def extract_accounts(text: str) -> list[dict]:
    """按出现顺序抽账号，同一片段只归入最具体的一类。"""
    found = []
    taken = []
    for relation, regex in ACCOUNT_RULES:
        for match in regex.finditer(text):
            value = match.group(1) if match.groups() else match.group(0)
            start, end = match.span(1) if match.groups() else match.span(0)
            if not value:
                continue
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            taken.append((start, end))
            found.append({"relation": relation, "alias": value, "start": start})

    found.sort(key=lambda item: item["start"])
    return [
        {
            "category": "账号",
            "relation": item["relation"],
            "aliases": [item["alias"]],
            "note": f"规则补抽：{item['relation']}",
        }
        for item in found
    ]


def _clean_rule_name(name: str) -> str:
    """贪心匹配偶尔多吃一个字（李梅反映 -> 李梅反），按非常用结尾字回退。"""
    while len(name) > 2 and name[-1] in _UNLIKELY_NAME_TAIL:
        name = name[:-1]
    return name


def _person_name_ok(name: str, seen: set) -> bool:
    return (
        name not in NOT_A_NAME
        and name not in seen
        and name[0] not in NOT_NAME_PREFIX
        and alias_is_sane(name, "人物")
    )


def _coord_relation(role: str) -> str:
    """并列人名沿用前一个人的关系；父母类无法确定，降级为"其他亲属"。"""
    relation = ROLE_RELATION.get(role, "其他")
    return "其他亲属" if relation in ("父亲", "母亲") else relation


def _coordinated_names(text: str, start: int) -> list[str]:
    names = []
    pos = start
    while True:
        match = COORD_RE.match(text, pos)
        if not match:
            break
        names.append(match.group(1))
        pos = match.end()
    return names


def extract_people(text: str) -> list[dict]:
    """只抽"角色词 + 姓名"这种高置信写法，并扩展"室友A和B"这类并列人名。"""
    found = []
    seen = set()
    matches = [(m.start(), "self", m) for m in SELF_RE.finditer(text)]
    matches += [(m.start(), "role", m) for m in ROLE_RE.finditer(text)]

    def add(name: str, relation: str, note: str) -> None:
        seen.add(name)
        found.append(
            {
                "category": "人物",
                "relation": relation,
                "aliases": [name],
                "note": note,
            }
        )

    for _, kind, match in sorted(matches, key=lambda pair: pair[0]):
        role, name = match.group(1), _clean_rule_name(match.group(2))
        if not _person_name_ok(name, seen):
            continue
        add(name, ROLE_RELATION[role], f"规则补抽：{role}")
        if kind != "role":
            continue
        for extra in _coordinated_names(text, match.end()):
            extra = _clean_rule_name(extra)
            if _person_name_ok(extra, seen):
                add(extra, _coord_relation(role), f"规则补抽：{role}并列")
    return found


def extract_locations(text: str) -> list[dict]:
    """只抽带具体前缀的地名：光秃秃的"学校/医院"不抽，避免过度脱敏。"""
    found = []
    seen = set()
    taken = []
    for relation, regex in LOCATION_RULES:
        for match in regex.finditer(text):
            value = match.group(1)
            start, end = match.span(1)
            if value.startswith(NOT_A_LOCATION_PREFIX):
                continue
            if value in seen or any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            seen.add(value)
            taken.append((start, end))
            found.append({"relation": relation, "alias": value, "start": start})

    found.sort(key=lambda item: item["start"])
    return [
        {
            "category": "地点",
            "relation": item["relation"],
            "aliases": [item["alias"]],
            "note": f"规则补抽：{item['relation']}",
        }
        for item in found
    ]


def _next_placeholder(prefix: str, used: set) -> str:
    index = 0
    while f"{prefix}{chr(ord('A') + index)}" in used:
        index += 1
    return f"{prefix}{chr(ord('A') + index)}"


def _split_conflicts(merged: list, rule_rel: dict, used_placeholders: set) -> list:
    """模型把不同实体塞进同一条时，按规则给出的关系拆成多条。"""
    out = []
    for item in merged:
        category = item.get("category")
        aliases = item.get("aliases") or []
        relations = []
        for alias in aliases:
            rel = rule_rel.get(alias)
            if rel and rel[0] == category and rel[1] not in relations:
                relations.append(rel[1])
        if len(relations) < 2:
            out.append(item)
            continue

        primary = relations[0]
        groups = {primary: []}
        for alias in aliases:
            rel = rule_rel.get(alias)
            key = rel[1] if rel and rel[0] == category and rel[1] in relations else primary
            groups.setdefault(key, []).append(alias)

        item["aliases"] = groups.pop(primary)
        item["relation"] = primary
        out.append(item)
        for relation, group in groups.items():
            clone = dict(item)
            clone["aliases"] = group
            clone["relation"] = relation
            clone["placeholder"] = _next_placeholder(category, used_placeholders)
            used_placeholders.add(clone["placeholder"])
            out.append(clone)
    return out


def _split_placeholder_reuse(merged: list, used_placeholders: set) -> list:
    """同一占位符被模型复用到关系不同的实体上时，后续条目换新占位符。"""
    seen = {}
    out = []
    for item in merged:
        placeholder = str(item.get("placeholder", ""))
        relation = str(item.get("relation", "")).strip()
        first = seen.get(placeholder)
        if placeholder and placeholder != "来访者" and first and relation and first != relation:
            placeholder = _next_placeholder(item.get("category", "人物"), used_placeholders)
            item["placeholder"] = placeholder
            used_placeholders.add(placeholder)
            first = None
        if placeholder and not seen.get(placeholder):
            seen[placeholder] = relation or seen.get(placeholder, "")
        out.append(item)
    return out


def supplement(text: str, raw) -> dict:
    """把规则命中的人物/地点/账号并入小模型输出；已被模型覆盖的别名不重复添加。"""
    if not isinstance(raw, dict):
        return raw
    entities = raw.get("entities")
    if not isinstance(entities, list):
        return raw

    merged = [item for item in entities if isinstance(item, dict)]
    known_aliases = set()
    used_placeholders = set()
    for item in merged:
        aliases = item.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        # 小模型偶尔把"彭雨薇,曹文博"塞进一个字符串，按分隔符拆开
        split = []
        for alias in aliases:
            split.extend(part for part in re.split(r"[,，、;；\s]+", str(alias)) if part)
        item["aliases"] = split
        known_aliases.update(split)
        used_placeholders.add(str(item.get("placeholder", "")))

    rule_entities = extract_people(text) + extract_locations(text) + extract_accounts(text)
    rule_rel = {}
    for entity in rule_entities:
        for alias in entity["aliases"]:
            rule_rel.setdefault(alias, (entity["category"], entity["relation"]))
    merged = _split_placeholder_reuse(_split_conflicts(merged, rule_rel, used_placeholders), used_placeholders)

    def override_relation(entity, alias):
        """规则里的角色/类型是原文写明的，比模型猜的可靠，命中同一别名时覆盖。"""
        for item in merged:
            if item.get("category") == entity["category"] and alias in (item.get("aliases") or []):
                item["relation"] = entity["relation"]
                return

    for entity in rule_entities:
        alias = entity["aliases"][0]
        if alias in known_aliases:
            override_relation(entity, alias)
            continue

        # 模型只抽到"锦绣花园"，规则抽到完整"锦绣花园7栋1201"：升级原条目而不是新增
        upgrade = next(
            (old for old in list(known_aliases) if old and old != alias and old in alias and old in text),
            "",
        )
        if upgrade:
            target = next(
                (
                    item
                    for item in merged
                    if item.get("category") == entity["category"]
                    and upgrade in (item.get("aliases") or [])
                ),
                None,
            )
            if target is None:
                upgrade = ""
            else:
                target["aliases"][target["aliases"].index(upgrade)] = alias
                target["relation"] = entity["relation"]
                known_aliases.discard(upgrade)
                known_aliases.add(alias)
                continue
        # 已有更长的覆盖写法，短写法不再单独成条（拼接错的别名不算数）
        if any(alias != known and alias in known and known in text for known in known_aliases):
            continue

        if entity["category"] == "人物" and entity["relation"] == "本人":
            patient = next((item for item in merged if item.get("placeholder") == "来访者"), None)
            if patient is not None:
                patient.setdefault("aliases", []).append(alias)
                known_aliases.add(alias)
                continue
            entity["placeholder"] = "来访者"
        elif entity["category"] == "人物":
            entity["placeholder"] = _next_placeholder("人物", used_placeholders)
        elif entity["category"] == "地点":
            entity["placeholder"] = _next_placeholder("地点", used_placeholders)
        else:
            entity["placeholder"] = _next_placeholder("账号", used_placeholders)

        used_placeholders.add(entity["placeholder"])
        known_aliases.add(alias)
        merged.append(entity)
    return {**raw, "entities": merged}
