# 心理档案去标识化 · 大小模型协同

本地 1.5B 小模型负责把 Word 档案里的**具体人名、具体地点、号码账号**换成 `人物A` / `地点A` / `账号A`，
并把对应表留在本机；云端 DeepSeek 只看到脱敏文本。云端**单轮**完成评估，报告返回后在本地严格逐字回译。
服务端无状态、不落盘、不回显真名。

> 这里的"加密"是**去标识化（伪名化）**，不是密码学加密——云端必须读懂占位符才能维持上下文连贯。
> 小模型失败时**失败关闭**（返回 502），绝不降级发送原文。

## 系统结构

```text
.docx ──python-docx──▶ 纯文本
                         │
              本地小模型（llama.cpp + Qwen2.5-1.5B）
                         │  实体 JSON（placeholder / category / relation / aliases / note）
                         ▼
              规则兜底 + 契约校验 + 逐字替换 ──▶ 对应表（只留在本地）
                         │
              发送前泄漏扫描（别名 + 正则 + 占位符完整性）
                         │  不通过 → 422 拒绝发送
                         ▼
  ┌──────────── 单轮云端评估 ────────────┐
  │ ① 脱敏文本 + legend + 参考资料 →     │
  │     DeepSeek                         │
  │ ② 五节评估报告 ←（含信息缺口一节）   │
  └──────────────────────────────────────┘
                         │
              本地回译 → 页面同时展示加密版与还原版
```

## 目录

```
app/main.py          FastAPI 入口：五个接口，服务端无状态
app/config.py        环境变量（本地模型、DeepSeek）
app/docx_io.py       .docx -> 纯文本（正文段落 + 表格）
app/rules.py         规则兜底：账号 / 人物 / 学校 / 医院 / 地址抽取与合并
app/anonymize.py     契约校验、实体清洗、逐字替换、legend、回译
app/contract.py      类别 / 关系词表、同义词映射、别名 sanity
app/privacy_guard.py 发送前泄漏扫描（别名、正则、占位符完整性）
app/kb.py            本地知识库加载与中文 BM25 检索
app/llm.py           llama.cpp / Ollama 与 DeepSeek 调用
app/prompts.py       抽取与单轮评估两组提示词
web/index.html       单页前端（原生 JS，无构建）
data_gen/generate.py 合成数据生成器（固定种子，全部虚构）
train/               SFT 数据转换 + LoRA 训练脚本
data/                600 训练 / 80 验证 / 30 测试 + 对话格式
data/kb/             15 个评估来源 + 60 张知识卡 + 来源评估说明
eval/                抽取、隐私、效用、检索四层评测
results/             已跑出的评测结果（JSON）
tools/mock_cloud.py  离线联调用的假云端（只验证链路，不用于效果评测）
smoke.py             离线自检，不需要模型和 key
docs/                整体框架、技术报告、早期微调指南
```

## 安装

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

## 本地小模型

当前演示使用微调后的 Qwen2.5-1.5B-Instruct（LoRA 合并 → GGUF Q4_K_M）+ llama.cpp Vulkan：

```bash
../tools/llama-vulkan/llama-server.exe \
  -m ../models/qwen2.5-1.5b-ft-q4_k_m.gguf \
  -ngl 99 -c 4096 --host 127.0.0.1 --port 8080
```

基座模型 `../models/qwen2.5-1.5b-instruct-q4_k_m.gguf` 仍保留作对照，换 `-m` 即可。
`/health` 返回 `{"status":"ok"}` 即可。也可以设 `LOCAL_BACKEND=ollama` 改用 Ollama，但默认路径是 llama.cpp。

## 配置

```bash
cp .env.example .env
```

| 变量 | 含义 | 默认 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 云端 key；缺失时健康徽标变红，分析接口返回 502 | 空 |
| `DEEPSEEK_MODEL` | 云端模型 id（按服务商实际名称填） | `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `LOCAL_BACKEND` | `llamacpp` 或 `ollama` | `llamacpp` |
| `LOCAL_BASE_URL` | llama-server 地址 | `http://127.0.0.1:8080` |
| `LOCAL_MODEL` | 健康徽标显示的模型标识（仅展示用） | `qwen2.5-1.5b-ft` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Ollama 兜底 | `http://127.0.0.1:11434` / `qwen2.5:7b-instruct` |

## 启动

```bash
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

打开 <http://127.0.0.1:8000>。右上角徽标自检本地模型与云端 key；本地模型不可达时"加密"不可用。

### 离线演示（假云端）

```bash
python tools/mock_cloud.py 8090
DEEPSEEK_API_KEY=mock DEEPSEEK_BASE_URL=http://127.0.0.1:8090/v1 \
  .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

假云端只返回固定报告，用来验证单轮链路与 UI，**不能用来评价效果**。

## 使用流程

1. 选 `.docx`，点「加密」：小模型抽取 → 规则兜底 → 契约校验 → 逐字替换 → 泄漏扫描；
2. 检查加密文本与对应表（关系列、真名、别名、出现次数），必要时手动修改；
3. 点「确认并分析」：服务端再次扫描；通过后本地检索知识库，把编号参考资料随脱敏文本发给云端；
4. 页面展示回译后的报告、参考依据与加密版报告；信息缺口统一写在报告第五节。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 本地后端/模型是否可达、key 是否配置、知识卡数量 |
| POST | `/api/extract` | multipart `file` → `{encrypted_text, mapping, guard_issues}` |
| POST | `/api/guard` | `{text, mapping}` → `{issues, blocked, summary}` |
| POST | `/api/analyze` | `{encrypted_text, mapping}` → `{report_encrypted, report_restored, legend, references}` |
| POST | `/api/deanonymize` | `{text, mapping}` → `{restored}` |

`mapping` 每项：`{placeholder, category, original, aliases, relation, count, note}`。
`note` 只留在本地，不发给云端。

## 知识库与 RAG

`data/kb/` 存放经过评估的公开专业资料转述：15 个来源、60 张知识卡，覆盖风险评估、抑郁、焦虑、睡眠、家庭与关系、CBT、伦理法律、报告写作、大学生心理。WHO mhGAP、NICE NG222/CG113、中国失眠指南（2023）、精神卫生法、中国心理学会伦理守则等作为 A 级来源；OpenStax 教材为 B 级背景资料；受版权保护的专著只做书目推荐，不复制正文入库。

分析时，`app/kb.py` 用脱敏文本 + 受控关系词做中文 BM25 检索（字段加权、同义词扩展、主题多样性、风险线索兜底），把 6 张以内的知识卡编号后放进云端提示词，要求模型用 `[n]` 引用并禁止编造来源；生成后再清理越界引用。前端展示的"参考依据"只含标题、主题、来源、年份与公开 URL。

- 来源评估、版权处理、检索设计与评测：`data/kb/README.md`
- 检索评测：`python eval/run_retrieval.py`（14 条查询，Hit@3 100%，MRR 0.917）

## 数据

全部人物、学校、地址、账号均为虚构，固定随机种子可复现；生成器保证文本全局唯一、训练/验证/测试无重叠。

```bash
python data_gen/generate.py
```

- `data/synth_train.jsonl` 600 条，`synth_valid.jsonl` 80 条，`synth_test.jsonl` 30 条；
- 每条含 `text`、金标 `entities`、`key_points`、`protected_terms`、`attack_targets`（10 候选重识别）；
- `data/train_sft.jsonl` 600 条，`{text, entities}`；
- `data/train_messages.jsonl` / `valid_messages.jsonl` 为对话格式（system 提示词与线上完全一致）。

## 微调

```bash
python train/prepare_sft.py

python train/lora_sft.py \
  --base D:/jiami/models/Qwen2.5-1.5B-Instruct \
  --out D:/jiami/models/qwen2.5-1.5b-lora \
  --epochs 3 --max-length 1024

python ../tools/llama-src/convert_hf_to_gguf.py \
  D:/jiami/models/qwen2.5-1.5b-lora/merged \
  --outfile D:/jiami/models/qwen2.5-1.5b-ft-f16.gguf --outtype f16

../tools/llama-vulkan/llama-quantize.exe \
  D:/jiami/models/qwen2.5-1.5b-ft-f16.gguf \
  D:/jiami/models/qwen2.5-1.5b-ft-q4_k_m.gguf Q4_K_M
```

LoRA：r=16、alpha=32、dropout=0.05、lr=2e-4、3 epochs、batch=1、梯度累积 8、seq=1024、bf16。
600 条训练集在 RTX 5060 Laptop 8GB 上约 37 分钟；最终 train loss 0.0046，valid loss 0.00044。
`../tools/llama-src` 是 llama.cpp 源码的稀疏检出（只需 `convert_hf_to_gguf.py` + `conversion/` + `gguf-py/`）。

## 评测

```bash
# 1) 抽取：小模型 + 规则兜底
python eval/run_extraction.py --data data/synth_test.jsonl \
  --out results/base_1.5b_rules_test30.json --label base_1.5b+rules

# 2) 隐私：复用上面的结果，不重复跑模型
python eval/run_privacy.py --results results/base_1.5b_rules_test30.json \
  --out results/privacy_base.json

# 3) 效用：离线统计；加 --cloud --judge 才调用云端生成报告并打分
python eval/run_utility.py --results results/base_1.5b_rules_test30.json \
  --out results/utility_base.json

# 4) 检索：不调用模型，检查知识卡召回与资料纯净度
python eval/run_retrieval.py
```

隐私脚本可选 `--local-attack` 增加"小模型从 10 个候选里猜真名"的攻击。

### 当前结果（30 篇合成测试集）

| 条件 | JSON 合法 | 实体精确率 | 实体召回 | 关系准确率 | 直接泄漏率 | 过度脱敏率 | 单篇耗时 |
|---|---|---|---|---|---|---|---|
| base 1.5B（裸输出） | 100% | 96.5% | 72.7% | 88.1% | 86.7% | 4.4% | 3.34s |
| base 1.5B + 规则兜底 | 100% | 100% | 100% | 100% | 0% | 0% | 4.71s |
| **微调 1.5B（裸输出）** | 100% | 100% | 100% | 100% | 0% | 0% | 5.16s |
| **微调 1.5B + 规则兜底** | 100% | 100% | 100% | 100% | 0% | 0% | 5.14s |

| 隐私指标（微调 + 规则） | 结果 |
|---|---|
| 残留正则 PII / 别名残留 | 0 / 0 |
| 占位符缺失 / 未知 | 0 / 0 |
| 重识别 top-1（随机基线 10%） | 10.7% |
| 重识别 top-1（利用明文泄漏） | 10.7% |

| 效用指标（微调 + 规则） | 结果 |
|---|---|
| 加密文本关键信息保留率 | 100% |
| 受保护泛化词保留率 | 100% |
| 平均长度比 | 0.822 |
| 平均对应表规模 | 5.7 项/篇 |

| 检索指标（14 条人工标注查询） | 结果 |
|---|---|
| 主题 Hit@1 / Hit@3 | 85.7% / 100% |
| MRR | 0.917 |
| 平均参考条数 | 4.6 |
| 资料纯净度（占位符 / 手机号 / 身份证） | 通过 |

**重要限定**：测试集是模板合成，与训练集同分布；微调后的 100% 属于分布内上界，不等于开放域泛化。
规则层又是在这批测试错误上迭代过的，因此 `base + 规则` 也可视为开发集数字。最干净的对照是
`base 裸输出 → 微调裸输出`（召回 72.7% → 100%，直接泄漏 86.7% → 0%）。真人盲评与独立测试集仍待补。

## 自检

```bash
python smoke.py
```

覆盖：docx 解析、账号/人物/地点规则、关系同义词、别名逐字校验、占位符冲突拆分、逐字替换与回译、泄漏扫描、知识库召回与 RAG 注入。不需要模型与 key。

## 已知局限

1. 测试集与训练集同模板分布，微调后的 100% 是分布内上界；规则层又在测试错误上迭代过，仍需独立集复测。
2. 数据全为模板合成，微调 valid loss 仅 0.00044，存在过拟合模板的风险；尚未做真人档案与人工盲评。
3. 泄漏扫描是别名精确匹配 + 正则，没有独立 NER 兜底。
4. 回译严格逐字："人物 A"（带空格）或 `**人物A**` 不会还原。
5. 超长文档整篇送模型，不做分块；超出上下文会被截断。
6. 对应表只在浏览器与本地进程内存，刷新即清空；页眉/页脚/批注/图片不脱敏。
7. 云端效用与 rubric 分数需要真实 key；目前只验证了假云端链路。
8. 知识库为 60 张转述卡片，覆盖有限；BM25 对隐晦改写可能漏检，RAG 也不能保证个案事实判断正确。
9. 受版权保护的教材未入库，只做书目推荐；指南与政策的时效性需定期复核。

## 文档

- [整体框架与实施计划](docs/整体框架与实施计划.md)
- [技术报告（初稿）](docs/技术报告.md)
- [架构设计与小模型微调指南（早期版本，契约部分以整体框架 v2 为准）](docs/架构设计与小模型微调指南.md)
- [知识库来源评估与 RAG 设计](data/kb/README.md)
