"""发送前的隐私扫描：别名精确匹配、正则、占位符完整性。

blocking=True 的问题会阻止请求发往云端；warning 只提示。
"""

import re

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
QQ_RE = re.compile(r"(?:QQ|qq|扣扣)\s*号?\s*[:：]?\s*([1-9]\d{4,11})")
WECHAT_RE = re.compile(r"(?:微信号|微信|WeChat|wechat)\s*[:：]?\s*([A-Za-z][-_A-Za-z0-9]{5,19})")
BANK_RE = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
PLACEHOLDER_RE = re.compile(r"(来访者|人物[A-Z]|地点[A-Z]|账号[A-Z])")

REGEX_RULES = (
    ("phone", PHONE_RE, "手机号"),
    ("id_card", ID_RE, "身份证号"),
    ("email", EMAIL_RE, "邮箱"),
    ("qq", QQ_RE, "QQ 号"),
    ("wechat", WECHAT_RE, "微信号"),
    ("bank_card", BANK_RE, "银行卡号"),
)


def mask(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def scan_text(text: str, mapping: list) -> list[dict]:
    issues = []
    seen = set()

    for entry in mapping:
        secrets = {entry.get("original", "")} | set(entry.get("aliases", []))
        for secret in secrets:
            if secret and secret in text:
                key = ("alias", entry["placeholder"])
                if key not in seen:
                    seen.add(key)
                    issues.append(
                        {
                            "kind": "alias",
                            "blocking": True,
                            "placeholder": entry["placeholder"],
                            "preview": mask(secret),
                            "message": f"{entry['placeholder']} 的原名/别名仍在文本中",
                        }
                    )
                break

    for kind, regex, label in REGEX_RULES:
        for match in regex.finditer(text):
            value = match.group(1) if match.groups() else match.group(0)
            key = (kind, value)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                {
                    "kind": kind,
                    "blocking": True,
                    "placeholder": "",
                    "preview": mask(value),
                    "message": f"疑似{label}未脱敏",
                }
            )

    # "来访者"本身是通用称谓，没在映射表里也不算未知占位符
    known = {entry["placeholder"] for entry in mapping} | {"来访者"}
    for match in PLACEHOLDER_RE.finditer(text):
        placeholder = match.group(1)
        if placeholder not in known and ("unknown", placeholder) not in seen:
            seen.add(("unknown", placeholder))
            issues.append(
                {
                    "kind": "unknown_placeholder",
                    "blocking": False,
                    "placeholder": placeholder,
                    "preview": placeholder,
                    "message": f"占位符 {placeholder} 不在映射表中",
                }
            )
    return issues


def blocking(issues: list[dict]) -> list[dict]:
    return [item for item in issues if item.get("blocking")]


def describe(issues: list[dict]) -> str:
    return "；".join(item["message"] for item in blocking(issues)) or "未发现阻断级风险"
