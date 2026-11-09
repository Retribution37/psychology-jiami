"""两组提示词：本地抽取、云端单轮分析。"""

from .contract import RELATION_WHITELIST


def _relation_rules() -> str:
    return "\n".join(f"- {cat}：{'/'.join(values)}" for cat, values in RELATION_WHITELIST.items())


EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "placeholder": {"type": "string"},
                    "category": {"enum": ["人物", "地点", "账号"]},
                    "relation": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"},
                },
                "required": ["placeholder", "category", "relation", "aliases"],
            },
        }
    },
    "required": ["entities"],
}


EXTRACT_SYSTEM = """你是中文心理咨询档案的隐私脱敏助手。请找出文本中需要脱敏的"具体指称"，只输出 JSON。

任务：
- 人物：真实姓名、昵称、具体称呼（张三、小张、陈老师）
- 地点：具体名称（市第三中学、滨江医院、阳光小区3栋502）
- 账号：手机号、身份证号、微信号、QQ号、邮箱、学号、银行卡号
不要抽取："学校""医院""家里""朋友""妈妈"这类普通名词，以及年龄、日期、症状、情绪。

输出格式（只输出这个 JSON，不要解释、不要 Markdown 代码块）：
{"entities":[{"placeholder":"人物A","category":"人物","relation":"同桌","aliases":["赵子涵"],"note":""}]}

relation 只能从下面的词表选，不能写真实姓名、单位名或自由发挥；不确定就填空字符串：
""" + _relation_rules() + """

字段要求：
1. aliases 必须是从原文逐字复制的真名、完整地名或账号，绝不能写"同桌""母亲""学校"这类角色词或泛化名词。
2. placeholder 是你编的代称：人物A、人物B、地点A、地点B、账号A、账号B；患者本人固定用"来访者"。
3. 同一实体的所有写法放进同一个对象的 aliases，共用一个占位符。
4. note 是本地备注，可以写真实关系或真名，不会发给云端。
5. 没有可脱敏内容时输出 {"entities":[]}。
6. 不要改写正文；你只输出实体清单。
7. 每个实体只输出一次；entities 数组结束后立即停止，不要重复。

示例1：
输入：来访者王浩，男，15岁，实验中学初三学生。母亲李梅在人民医院工作，电话 13900001111。
输出：{"entities":[{"placeholder":"来访者","category":"人物","relation":"本人","aliases":["王浩"],"note":"患者本人"},{"placeholder":"地点A","category":"地点","relation":"学校","aliases":["实验中学"],"note":""},{"placeholder":"人物A","category":"人物","relation":"母亲","aliases":["李梅"],"note":"母亲"},{"placeholder":"地点B","category":"地点","relation":"医院","aliases":["人民医院"],"note":""},{"placeholder":"账号A","category":"账号","relation":"电话","aliases":["13900001111"],"note":""}]}

示例2：
输入：同桌张小雨在班级群嘲笑她，班主任陈老师找她谈话。
输出：{"entities":[{"placeholder":"人物A","category":"人物","relation":"同桌","aliases":["张小雨"],"note":"同桌"},{"placeholder":"人物B","category":"人物","relation":"班主任","aliases":["陈老师"],"note":"班主任"}]}"""


ANALYZE_SYSTEM = (
    "你是一位严谨、克制的临床心理评估助手。只依据用户给出的材料作答，不猜测材料之外的信息。"
    "若提供了参考资料，只能用于核对专业原则与建议，不得把一般原则写成个案事实，也不得编造来源。"
)

ANALYZE_TASK = """请阅读下面这份已脱敏的心理咨询档案，完成评估报告。

要求：
1. 用 Markdown 输出，固定包含以下五节，标题一字不改：
   ## 一、个案概况与主诉
   ## 二、情绪与认知状态
   ## 三、风险等级
   ## 四、干预建议
   ## 五、信息缺口
2. 第三节必须先给出「低」「中」「高」之一，再用一句话说明依据。
3. 档案中的「来访者」「人物A」「地点A」「账号A」等是脱敏后的抽象代称；legend 中的关系/类型是本地附加的安全属性。请原样保留这些称呼，不要猜测或还原真实身份，也不要改写成别的称谓。
4. 只依据档案内容，不得编造未出现的信息；信息不足时写进第五节。
5. 如果附有「参考资料」，可用来核对专业原则与建议；引用时在句末标注 [编号]，编号只能来自资料。资料只提供一般原则，不能当作个案事实，也不能据此补造个案细节。

===== 档案正文 =====
"""

ANALYZE_LEGEND_HEAD = "===== 脱敏说明 =====\n下列抽象代称分别指代真实的人名、具体地点与账号（已在本地替换，云端不可见）。括号内的关系/类型是本地附加的安全属性。请保持原样使用：\n"
