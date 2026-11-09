"""生成中文合成心理档案数据：训练/验证/测试 + 金标实体 + 重识别候选。

全部人物、学校、地址、账号均为虚构；固定随机种子，可复现。
用法：python data_gen/generate.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MALE_NAMES = [
    "王浩然", "李泽宇", "张子轩", "刘思远", "陈嘉豪", "杨宇航", "黄俊杰", "赵明轩", "周天佑", "吴凯文",
    "徐志强", "孙博文", "马晨曦", "朱瑞霖", "胡一鸣", "郭子健", "何雨泽", "高梓涵", "林致远", "罗嘉诚",
    "梁俊熙", "宋承泽", "唐子墨", "许景行", "邓皓宇", "曹文博", "彭宇辰", "蒋昊然", "蔡明远", "潘星辰",
]
FEMALE_NAMES = [
    "林晓雨", "苏婉清", "陈静怡", "李梦琪", "王雨桐", "张欣妍", "刘诗涵", "杨紫萱", "黄思彤", "赵若曦",
    "周语嫣", "吴静姝", "徐嘉怡", "孙悦然", "马晓彤", "朱可欣", "胡梦瑶", "郭雨欣", "何静雯", "高文静",
    "梁诗琪", "宋佳宁", "唐可馨", "许清越", "邓雅雯", "曹思妍", "彭雨薇", "蒋欣怡", "蔡文静", "潘若彤",
]
SURNAMES = "王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗梁宋唐许邓曹彭蒋蔡潘"

SCHOOLS = [
    "市第一中学", "实验中学", "育才中学", "第七中学", "华英中学", "第十二中学",
    "滨河中学", "明德中学", "启慧中学", "城南中学", "江北实验中学", "高新外国语学校",
]
UNIVERSITIES = ["江州大学", "明海大学", "东林大学", "华信大学", "临江大学"]
HOSPITALS = ["市人民医院", "滨江医院", "康宁医院", "第二人民医院", "安宁医院", "市中心医院", "仁和医院"]
ADDRESSES = [
    "阳光小区3栋502", "锦绣花园7栋1201", "滨河小区2栋301", "梧桐里5号院",
    "翠湖公寓B座806", "新华路12号", "学府花园1栋902", "春江苑4栋1103",
]
COMPANIES = ["恒信科技", "华远集团", "星海传媒", "启明教育", "远航物流"]

KEYPOINT_POOL = [
    "情绪低落", "入睡困难", "注意力下降", "成绩下降", "食欲下降", "回避社交",
    "焦虑", "无自伤意念", "持续两个月", "建议每周一次咨询", "无明显焦虑",
    "情绪平稳", "建议保持规律作息", "一个月后复评",
]

GENERIC_PROTECTED = ["母亲", "父亲", "学校", "家里", "朋友", "老师", "同学", "复诊", "咨询", "成绩"]


def _pick_names(rng: random.Random, count: int) -> list[str]:
    pools = MALE_NAMES + FEMALE_NAMES
    for _ in range(200):
        names = rng.sample(pools, count)
        if not any(a != b and a in b for a in names for b in names):
            return names
    raise RuntimeError("姓名池无法满足互不包含约束")


def _phone(rng): return "138" + "".join(rng.choice("0123456789") for _ in range(8))
def _qq(rng): return str(rng.randint(100000, 999999999))
def _wechat(rng): return "wx_" + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6)) + str(rng.randint(10, 99))
def _email(rng): return "user" + str(rng.randint(1000, 9999)) + "@example.com"
def _student_id(rng): return "2023" + "".join(rng.choice("0123456789") for _ in range(6))
def _id_card(rng): return "11010120080101" + "".join(rng.choice("0123456789") for _ in range(4))
def _bank_card(rng): return "6222" + "".join(rng.choice("0123456789") for _ in range(15))


def _ctx(rng: random.Random) -> dict:
    names = _pick_names(rng, 9)
    patient = names[0]
    gender = "女" if patient in FEMALE_NAMES else "男"
    ctx = {
        "patient": patient,
        "gender": gender,
        "grade": rng.choice(["初二", "初三", "高一", "高二", "高三"]),
        "age": 0,
        "school": rng.choice(SCHOOLS),
        "prev_school": rng.choice(SCHOOLS),
        "university": rng.choice(UNIVERSITIES),
        "hospital": rng.choice(HOSPITALS),
        "address": rng.choice(ADDRESSES),
        "company": rng.choice(COMPANIES),
        "classmate": names[1],
        "teacher_name": names[2],
        "mother": names[3],
        "father": names[4],
        "friend": names[5],
        "roommate": names[6],
        "partner": names[7],
        "doctor": names[8],
        "neighbor": names[1],
        "phone": _phone(rng),
        "wechat": _wechat(rng),
        "qq": _qq(rng),
        "email": _email(rng),
        "student_id": _student_id(rng),
        "id_card": _id_card(rng),
        "bank_card": _bank_card(rng),
    }
    ctx["teacher"] = rng.choice([ctx["teacher_name"], SURNAMES[rng.randrange(len(SURNAMES))] + "老师"])
    ctx["classmate_role"] = rng.choice(["同桌", "同学"])
    ctx["teacher_role"] = rng.choice(["班主任", "老师"])
    ctx["age"] = {"初二": 14, "初三": 15, "高一": 16, "高二": 17, "高三": 18}[ctx["grade"]] + rng.choice([0, 0, 1])
    ctx["nickname"] = "小" + patient[-1] if rng.random() < 0.25 else ""
    return ctx


def _template(ctx: dict, rng: random.Random) -> tuple[list[str], dict, list[str]]:
    """返回 (段落列表, 使用的实体字段, 受保护泛化词)。字段值形如 (value, category, relation)。"""
    c = ctx
    used = {"patient": (c["patient"], "人物", "本人")}

    def person(field, relation, alias=None):
        used[field] = (alias or c[field], "人物", relation)

    def location(field, relation, alias=None):
        used[field] = (alias or c[field], "地点", relation)

    def account(field, relation):
        used[field] = (c[field], "账号", relation)

    choice = rng.randrange(14)
    if choice == 0:
        person("classmate", c["classmate_role"])
        person("teacher", c["teacher_role"])
        location("school", "学校")
        account("phone", "电话")
        if c["nickname"]:
            used["patient"] = ([c["patient"], c["nickname"]], "人物", "本人")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，{c['school']}{c['grade']}学生。",
            "主诉：近两个月情绪低落，入睡困难，白天注意力下降，月考成绩下降。",
            f"诱因：{c['classmate_role']}{c['classmate']}多次在班级群里嘲讽来访者，{c['teacher_role']}{c['teacher']}知情后调解效果有限。",
            "来访者与母亲关系紧张，曾因手机使用发生争执，但无自伤意念。",
            f"联系方式：手机 {c['phone']}。",
        ]
        protected = ["母亲", "班级群", "手机"]
    elif choice == 1:
        person("mother", "母亲")
        person("father", "父亲")
        location("hospital", "医院")
        location("address", "家庭住址")
        account("phone", "电话")
        account("wechat", "微信")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁。",
            "近三个月因父母离异情绪低落，夜间失眠，食欲下降。",
            f"母亲{c['mother']}在{c['hospital']}工作，父亲{c['father']}长期在外地，来访者与母亲关系紧张。",
            f"现住{c['address']}，与外婆同住，无自伤意念。",
            f"联系电话 {c['phone']}，微信 {c['wechat']}。",
        ]
        protected = ["父母", "母亲", "父亲", "外婆"]
    elif choice == 2:
        person("teacher", c["teacher_role"])
        person("classmate", "同桌")
        location("school", "学校")
        account("wechat", "微信")
        account("email", "邮箱")
        paras = [
            f"{c['patient']}，{c['gender']}，{c['age']}岁，{c['school']}{c['grade']}学生。",
            "临近期末出现明显焦虑，入睡困难，注意力下降，成绩下滑。",
            f"{c['teacher_role']}{c['teacher']}建议其到咨询室，同桌{c['classmate']}陪同前来。",
            "来访者无自伤意念，愿每周一次咨询。",
            f"微信 {c['wechat']}，邮箱 {c['email']}。",
        ]
        protected = ["班主任", "同桌", "咨询"]
    elif choice == 3:
        c["age"] = rng.randint(19, 22)
        person("roommate", "室友")
        person("teacher", "老师")
        location("university", "学校")
        location("address", "家庭住址")
        account("phone", "电话")
        account("qq", "QQ")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，{c['university']}大二学生，住{c['address']}。",
            f"与室友{c['roommate']}因作息问题多次争执，近期情绪低落、回避社交。",
            f"辅导员{c['teacher']}介入调解，效果有限。",
            f"手机 {c['phone']}，QQ {c['qq']}。",
        ]
        protected = ["室友", "辅导员"]
    elif choice == 4:
        person("partner", "恋人")
        person("friend", "朋友")
        person("teacher", c["teacher_role"])
        location("school", "学校")
        account("qq", "QQ")
        account("wechat", "微信")
        paras = [
            f"{c['patient']}，{c['gender']}，{c['age']}岁，{c['school']}{c['grade']}学生。",
            f"近一个月因与恋人{c['partner']}分手出现情绪低落，入睡困难，注意力下降。",
            f"朋友{c['friend']}建议其求助，{c['teacher_role']}{c['teacher']}已知情。",
            f"QQ {c['qq']}，微信 {c['wechat']}。",
        ]
        protected = ["恋人", "朋友", "求助"]
    elif choice == 5:
        person("classmate", "同学")
        person("teacher", c["teacher_role"])
        location("school", "学校")
        account("wechat", "微信")
        account("qq", "QQ")
        paras = [
            f"来访者{c['patient']}，{c['age']}岁，{c['school']}学生。",
            f"近期在社交平台被同学{c['classmate']}辱骂，出现焦虑、回避社交。",
            f"{c['teacher_role']}{c['teacher']}与母亲均已知情，来访者无自伤意念。",
            f"微信号 {c['wechat']}，QQ {c['qq']}。",
        ]
        protected = ["社交平台", "母亲", "知情"]
    elif choice == 6:
        person("mother", "母亲")
        person("doctor", "医生")
        location("hospital", "医院")
        account("id_card", "身份证")
        account("phone", "电话")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，由母亲{c['mother']}陪同到{c['hospital']}复诊。",
            "诊断为中重度抑郁，近两周入睡困难、食欲下降，无自伤意念。",
            f"医生{c['doctor']}建议继续每周一次咨询。",
            f"身份证 {c['id_card']}，手机 {c['phone']}。",
        ]
        protected = ["母亲", "复诊", "咨询"]
    elif choice == 7:
        person("teacher", c["teacher_role"])
        location("prev_school", "学校")
        location("school", "学校")
        location("address", "家庭住址")
        account("phone", "电话")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，原就读于{c['prev_school']}，本学期转入{c['school']}。",
            "因适应困难出现情绪低落、注意力下降，成绩下降。",
            f"{c['teacher_role']}{c['teacher']}反映其近期常独自待在教室。",
            f"家庭住址 {c['address']}，手机 {c['phone']}。",
        ]
        protected = ["班主任", "教室"]
    elif choice == 8:
        c["age"] = rng.randint(19, 22)
        person("roommate", "室友")
        person("teacher", "老师")
        location("university", "学校")
        account("email", "邮箱")
        account("student_id", "学号")
        paras = [
            f"来访者{c['patient']}，{c['age']}岁，{c['university']}大三学生。",
            "因论文压力出现焦虑、入睡困难，成绩下降。",
            f"室友{c['roommate']}陪同前来，辅导员{c['teacher']}已知情。",
            f"邮箱 {c['email']}，学号 {c['student_id']}。",
        ]
        protected = ["室友", "辅导员", "论文"]
    elif choice == 9:
        person("neighbor", "邻居")
        person("mother", "母亲")
        location("address", "家庭住址")
        account("phone", "电话")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，现住{c['address']}。",
            f"因楼上邻居{c['neighbor']}长期噪音问题产生冲突，近期焦虑、失眠。",
            f"母亲{c['mother']}陪同来访，联系电话 {c['phone']}，无自伤意念。",
        ]
        protected = ["邻居", "母亲", "噪音"]
    elif choice == 10:
        used = {}
        paras = rng.choice([
            [
                "来访者近一周睡眠尚可，情绪平稳，无明显焦虑。",
                "学校课业压力一般，与家人关系融洽，无自伤意念。",
                "建议保持规律作息，一个月后复评。",
            ],
            [
                "来访者近期情绪稳定，食欲正常，睡眠质量尚可。",
                "与同学相处融洽，未再出现明显焦虑。",
                "建议继续观察，两周后复评。",
            ],
            [
                "来访者自述近期压力有所缓解，注意力较前改善。",
                "家庭氛围平稳，无自伤意念。",
                "建议保持运动习惯，一个月后复评。",
            ],
            [
                "来访者本周情绪波动较小，能够正常上课。",
                "与朋友交流增多，无明显回避社交。",
                "建议记录情绪日记，下次咨询时讨论。",
            ],
        ])
        paras.append(f"本次为第{rng.randint(2, 24)}次复诊，间隔约{rng.choice([1, 2, 3, 4, 6, 8])}周。")
        protected = ["学校", "家人", "同学", "家庭"]
    elif choice == 11:
        used = {}
        account("phone", "电话")
        account("wechat", "微信")
        account("email", "邮箱")
        paras = [
            "来访者未透露姓名，仅留下联系方式。",
            f"手机 {c['phone']}，微信 {c['wechat']}，邮箱 {c['email']}。",
            "主诉近期入睡困难，注意力下降，无自伤意念。",
        ]
        protected = ["联系方式"]
    elif choice == 12:
        person("mother", "母亲")
        person("father", "父亲")
        location("school", "学校")
        location("hospital", "医院")
        location("address", "家庭住址")
        account("phone", "电话")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，{c['school']}{c['grade']}学生。",
            f"父母长期在外地，由外婆照顾。母亲{c['mother']}在{c['hospital']}工作，父亲{c['father']}偶尔回家。",
            "近期因家庭矛盾情绪低落、入睡困难，无自伤意念。",
            f"现住{c['address']}，手机 {c['phone']}。",
        ]
        protected = ["父母", "外婆", "母亲", "父亲"]
    else:
        person("teacher", "班主任")
        person("classmate", "同桌")
        location("school", "学校")
        account("wechat", "微信")
        paras = [
            f"来访者{c['patient']}，{c['gender']}，{c['age']}岁，{c['school']}学生。",
            f"因被班主任{c['teacher']}当众批评，出现情绪低落、回避社交、注意力下降。",
            f"同桌{c['classmate']}反映其近期常在课后独自哭泣。",
            f"微信 {c['wechat']}。",
        ]
        protected = ["班主任", "同桌", "课后"]

    return paras, used, protected


def _build_gold(text: str, used: dict, ctx: dict) -> list[dict]:
    entries = []
    for field, value in used.items():
        aliases, category, relation = value
        if isinstance(aliases, str):
            aliases = [aliases]
        else:
            aliases = list(aliases)
        entries.append({"field": field, "aliases": aliases, "category": category, "relation": relation})

    # 按首次出现位置排序，给人物/地点/账号编号
    entries.sort(key=lambda e: min(text.find(a) for a in e["aliases"]))
    counters = {"人物": 0, "地点": 0, "账号": 0}
    gold = []
    for entry in entries:
        if entry["field"] == "patient":
            placeholder = "来访者"
        else:
            index = counters[entry["category"]]
            counters[entry["category"]] += 1
            placeholder = f"{entry['category']}{chr(ord('A') + index)}"
        gold.append(
            {
                "placeholder": placeholder,
                "category": entry["category"],
                "relation": entry["relation"],
                "aliases": entry["aliases"],
                "note": "",
            }
        )
    return gold


def _keypoints(text: str) -> list[str]:
    return [phrase for phrase in KEYPOINT_POOL if phrase in text]


def _protected(text: str, gold: list[dict], candidates: list[str]) -> list[str]:
    aliases = [a for entity in gold for a in entity["aliases"]]
    values = []
    for term in GENERIC_PROTECTED + candidates:
        if term in text and not any(term in alias for alias in aliases):
            values.append(term)
    return sorted(set(values))


def _attack_targets(gold: list[dict], ctx: dict, rng: random.Random) -> list[dict]:
    targets = []
    for entity in gold:
        if entity["category"] != "人物":
            continue
        placeholder = entity["placeholder"]
        if placeholder == "来访者":
            true_name = ctx["patient"]
        else:
            field = next((k for k, v in ctx.items() if isinstance(v, str) and v in entity["aliases"]), "")
            true_name = ctx.get(field, entity["aliases"][0])
        if entity["aliases"][0].endswith("老师"):
            pool = [s + "老师" for s in SURNAMES[:20] if s + "老师" != true_name]
            true_value = true_name if true_name.endswith("老师") else entity["aliases"][0]
            decoys = rng.sample(pool, 9)
        else:
            pool = [n for n in MALE_NAMES + FEMALE_NAMES if n != true_name]
            true_value = true_name
            decoys = rng.sample(pool, 9)
        candidates = decoys + [true_value]
        rng.shuffle(candidates)
        targets.append({"placeholder": placeholder, "true": true_value, "candidates": candidates})
    return targets


def _make_sample(index: int, rng: random.Random, split: str) -> dict:
    ctx = _ctx(rng)
    paras, used, protected = _template(ctx, rng)
    text = "\n".join(paras)
    gold = _build_gold(text, used, ctx)
    sample = {
        "id": f"{split}-{index:04d}",
        "text": text,
        "entities": gold,
        "key_points": _keypoints(text),
        "protected_terms": _protected(text, gold, protected),
    }
    if split == "test":
        sample["attack_targets"] = _attack_targets(gold, ctx, rng)
    return sample


def main() -> None:
    DATA.mkdir(exist_ok=True)
    rng = random.Random(20261108)
    seen = set()
    for split, count in (("train", 600), ("valid", 80), ("test", 30)):
        rows = []
        attempts = 0
        while len(rows) < count:
            attempts += 1
            if attempts > count * 200:
                raise RuntimeError(f"{split} 无法生成足够的不重复样本")
            sample = _make_sample(len(rows), rng, split)
            if sample["text"] in seen:
                continue
            seen.add(sample["text"])
            rows.append(sample)
        path = DATA / f"synth_{split}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{path.name}: {len(rows)} 条")

    # 训练格式：只保留 text 与实体金标
    with (DATA / "train_sft.jsonl").open("w", encoding="utf-8") as out:
        for line in (DATA / "synth_train.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            out.write(json.dumps({"text": row["text"], "entities": row["entities"]}, ensure_ascii=False) + "\n")
    print("train_sft.jsonl: 训练用合并文件")


if __name__ == "__main__":
    main()
