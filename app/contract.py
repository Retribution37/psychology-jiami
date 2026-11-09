"""契约常量：类别、关系词表、别名 sanity。

改契约时，prompts.py / anonymize.py / web / docs 四处要同步。
"""

import re

CATEGORIES = ("人物", "地点", "账号")

CATEGORY_LABEL = {"人物": "人物代称", "地点": "地点代称", "账号": "账号代称"}

RELATION_LABEL = {"人物": "关系", "地点": "类型", "账号": "类型"}

RELATION_WHITELIST = {
    "人物": (
        "本人", "父亲", "母亲", "父母", "子女", "兄弟姐妹", "其他亲属",
        "配偶", "恋人", "朋友", "同学", "同桌", "室友", "同事",
        "老师", "班主任", "邻居", "医生", "其他",
    ),
    "地点": ("学校", "家庭住址", "医院", "单位", "常去地点", "其他"),
    "账号": ("电话", "微信", "QQ", "邮箱", "身份证", "学号", "银行卡", "其他"),
}

PLACEHOLDER_TOKENS = ("来访者", "人物", "地点", "账号")

# 只放功能词，不放"家/学校"这类可能出现在正文里的名词
STOPWORD_ALIASES = frozenset({
    "的", "了", "是", "我", "你", "他", "她", "它", "们", "这", "那", "在",
    "有", "和", "与", "就", "都", "也", "很", "不", "没", "人", "说", "要",
    "会", "到", "去", "来", "上", "下", "中", "里", "外", "个", "一", "二",
    "三", "四", "五", "六", "七", "八", "九", "十",
})

# 泛化名词/角色词不能当别名，否则会把正文替坏或造成过度脱敏
GENERIC_ALIASES = frozenset({
    "家庭", "家里", "家人", "单位", "学校", "医院", "公司", "外地", "班级",
    "朋友", "母亲", "父亲", "妈妈", "爸爸", "父母", "老师", "同学", "同桌",
    "班主任", "患者", "本人", "对象", "领导", "亲戚", "外婆", "外公",
    "爷爷", "奶奶", "姥姥", "姥爷", "本周", "上周", "下周", "今天", "昨天",
    "明天", "每天", "最近", "目前",
})

# 年级、泛化互动描述这类词被模型当成实体时直接丢弃
GENERIC_RE = re.compile(
    r"^(?:\d{1,3}\s*岁|大[一二三四]学生?|初[一二三]学生?|高[一二三]学生?|"
    r"大学|中学|小学|高中|初中|研究生|本科|博士|"
    r"本?周[一二三四五六日天]?|"
    r"(?:交流|沟通|相处|接触)(?:增|减|多|少|增多|减少|增加|频繁|变多|变少)?)$"
)

# 学段+时间词（高二时、大二那年）不是姓名，是临床时间信息，必须保留在正文里
TIME_PHRASE_RE = re.compile(
    r"^(?:高[一二三]|初[一二三]|大[一二三四]|研[一二三]|小学|初中|高中|大学|本科|硕士|博士)"
    r"(?:时|时期|阶段|那年|期间)$|"
    r"^(?:当时|那时|此时|此刻|近日|近期|最近|目前|后来|随后|此前|之前|之后|从小|"
    r"小时候|童年|幼时|暑假|寒假|上半年|下半年)$"
)

# 小模型常用的近义关系词，映射回受控词表
RELATION_SYNONYMS = {
    "人物": {
        "来访者": "本人", "患者": "本人", "妈妈": "母亲", "爸爸": "父亲",
        "家属": "其他亲属", "医师": "医生", "心理咨询师": "医生",
    },
    "地点": {
        "住址": "家庭住址", "居住地": "家庭住址", "家庭地址": "家庭住址",
        "地址": "家庭住址", "大学": "学校", "中学": "学校", "小学": "学校",
        "公司": "单位",
    },
    "账号": {
        "手机": "电话", "手机号": "电话", "电话号码": "电话",
        "微信号": "微信", "电子邮箱": "邮箱", "qq": "QQ", "QQ号": "QQ",
        "身份证号": "身份证", "银行卡号": "银行卡",
    },
}


def normalize_relation(category: str, value) -> str:
    """非法/编造的关系一律清空，但实体保留（隐私优先）。"""
    value = str(value or "").strip()
    value = RELATION_SYNONYMS.get(category, {}).get(value, value)
    if category in RELATION_WHITELIST and value in RELATION_WHITELIST[category]:
        return value
    return ""


def alias_is_sane(alias: str, category: str) -> bool:
    """挡住会把正文替换坏或破坏占位符的别名。"""
    alias = alias.strip()
    if not alias or alias in STOPWORD_ALIASES or alias in GENERIC_ALIASES:
        return False
    if GENERIC_RE.match(alias):
        return False
    if TIME_PHRASE_RE.match(alias):
        return False
    if len(alias) < 2:
        return False
    if any(token in alias for token in PLACEHOLDER_TOKENS):
        return False
    if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in alias):
        return False
    if "自述" in alias:
        return False
    return True
