"""离线联调用的假云端：模拟单轮评估报告，不用于任何效果评测。

运行：python tools/mock_cloud.py [port]
然后把 .env 配成 DEEPSEEK_API_KEY=mock DEEPSEEK_BASE_URL=http://127.0.0.1:8090/v1
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPORT = """## 一、个案概况与主诉
来访者近期出现情绪低落、入睡困难与注意力下降，主诉持续约两个月，已影响学业表现。主要压力来自与人物A的持续冲突。

## 二、情绪与认知状态
来访者存在明显的低落情绪与睡眠问题，尚未报告自伤意念。对主要压力事件的描述较具体。

## 三、风险等级
**中**：症状已影响日常学习与睡眠，但暂无自伤或伤人迹象。

## 四、干预建议
建议每周一次个体咨询，结合关系情境理解冲突，并持续关注睡眠与情绪变化；若症状加重，转介精神科评估。评估原则可参考 [1]。

## 五、信息缺口
真实姓名、具体地址、冲突频率等信息未在档案中给出，报告不对此做推断。
"""


def handle_chat(_body: dict) -> str:
    return REPORT


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        content = handle_chat(body)
        payload = json.dumps(
            {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]},
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    print(f"mock cloud listening on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
