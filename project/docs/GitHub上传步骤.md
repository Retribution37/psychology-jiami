# 项目上传 GitHub 步骤

> 适用：把当前 `D:\jiami\project` 作为代码仓库上传到 GitHub，模型和 llama.cpp 二进制单独分发。
> 更新日期：2026-11-09

---

## 0. 先明确什么能传、什么不能传

GitHub 单文件硬限制 **100MB**，所以下面这些东西不能直接 `git add`：

| 内容 | 大小 | 去处 |
|---|---|---|
| `project/` 代码、合成数据、文档、评测结果 | 约 4.8MB | Git 仓库 |
| `models/qwen2.5-1.5b-ft-q4_k_m.gguf` | 941MB | GitHub Release（单附件上限 2GB） |
| `models/` 其余基座、合并权重、f16 GGUF | 1–3GB/个 | 网盘 / Hugging Face / ModelScope，不进仓库 |
| `tools/llama-vulkan/` 可执行文件 | 102MB | llama.cpp 官方 Release，或本项目 Release |
| `NAP2-privacy-rewrite-main/` | 32MB | 建议只放来源链接；要传就保留全部许可证 |
| `_handoff/` 里的 12GB 交接包 | 12GB | 网盘，绝不上传 |
| `.env`、API key | — | 永远不传 |

本项目当前**没有** `.env`，数据全部是合成的，不涉及真实心理档案。

---

## 1. 修改 `.gitignore`

把 `project/.gitignore` 改成：

```gitignore
.venv/
.env
__pycache__/
*.pyc
pip-*
```

`pip-*` 是之前 pip 安装留下的临时目录，不加会被提交进去。

---

## 2. 在 GitHub 创建空仓库

1. 打开 <https://github.com/new>。
2. Repository name 填英文名，例如 `psych-archive-privacy`。
3. 选择 Public 或 Private（课程作业建议 Private，答辩前再决定是否公开）。
4. **不要勾选** Add a README file、Add .gitignore、Choose a license。
5. 点 Create repository，先不要关页面，后面要用到仓库地址。

---

## 3. 本地初始化并提交

打开 CMD，逐条执行：

```bat
cd /d D:\jiami\project

git init
git add .
git status
```

### 检查 `git status`

确认列表里只有代码、数据、文档、结果，**没有** `.env`、`models/`、`_handoff/`。确认后再提交：

```bat
git commit -m "心理档案去标识化：大小模型协同系统"
git branch -M main
git remote add origin https://github.com/你的用户名/psych-archive-privacy.git
git push -u origin main
```

如果第一次使用 git，提示需要身份信息，先执行：

```bat
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

> 注意：一定要在 `D:\jiami\project` 里执行 `git init`。
> 不要在 `D:\jiami` 里执行，否则 12GB 的模型和工作区都会被纳入版本控制。

---

## 4. 登录认证

GitHub 不接受账号密码推送，二选一：

### 方式 A：GitHub Desktop（推荐给不熟悉命令行的同学）

1. 安装 GitHub Desktop，登录 GitHub 账号。
2. File → Add local repository → 选择 `D:\jiami\project`。
3. 如果提示不是仓库，点 create a repository。
4. 点 Publish repository，选择 Public/Private，完成。

### 方式 B：Personal Access Token

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)。
2. Generate new token，勾选 `repo` 权限，设置有效期。
3. 执行 `git push` 时，用户名填 GitHub 用户名，密码粘贴 token。
4. token 不要发给任何人，不要写进代码或文档。

---

## 5. 把微调模型上传到 Release

1. 打开仓库页面 → Releases → Draft a new release。
2. Tag 填 `v1.0`，Title 填 `微调模型 Q4_K_M`。
3. 上传 `D:\jiami\models\qwen2.5-1.5b-ft-q4_k_m.gguf`（941MB，小于 2GB 上限）。
4. Publish release。
5. 复制附件下载地址，写进 README 的“本地小模型”一节。

如果浏览器上传 941MB 经常中断，可以改用 ModelScope、Hugging Face 或网盘，README 里放链接即可。

---

## 6. 组员拿到仓库后怎么跑

```bat
git clone https://github.com/你的用户名/psych-archive-privacy.git D:\jiami\project
```

然后补齐仓库外的大文件：

1. 从 Release 下载 `qwen2.5-1.5b-ft-q4_k_m.gguf`，放到 `D:\jiami\models\`。
2. 从 llama.cpp 官方 Release 下载 Windows Vulkan 版，解压到 `D:\jiami\tools\llama-vulkan\`。
3. 进入 `D:\jiami\project`，按 README 安装依赖并启动：
   - `llama-server` 监听 8080
   - 后端监听 8000
   - 可选假云端监听 8090
4. 没有 DeepSeek key 时，用假云端联调单轮分析链路；假云端不能用于效果评价。
5. 详细说明见仓库根目录的 `交接说明-先读我.txt`（如果没上传，见 README 与本文档）。

最终目录应该是：

```text
D:\jiami\
├─ project\      git clone 下来的代码
├─ models\       手动放入的 GGUF
└─ tools\        手动放入的 llama.cpp
```

---

## 7. 许可证与引用

- Qwen2.5-1.5B-Instruct：Apache-2.0。
- llama.cpp：MIT。
- NAP2-privacy-rewrite-main：数据集 CC BY-NC 4.0（仅限非商业），代码 Apache-2.0，源自 PERSONA-CHAT。
- 如果仓库包含 NAP2 数据，必须保留 `LICENSE`、`LICENSE-DATA`、`NOTICE`，并在 README 注明来源与引用。
- 更稳妥的做法是不上传数据本体，只写来源链接和引用信息。

---

## 8. 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| `remote: error: File ... is 941.00 MB; this exceeds GitHub's file size limit of 100.00 MB` | 把模型 `git add` 了 | `git rm --cached` 移除，加入 `.gitignore`，模型改走 Release |
| `push` 要求输入密码后被拒 | GitHub 不支持密码 | 改用 token 或 GitHub Desktop |
| `git status` 里出现 12GB 文件 | 在 `D:\jiami` 初始化了仓库 | 删掉 `D:\jiami\.git` 后在 `project` 重新初始化 |
| 组员 clone 后启动报找不到模型 | 模型不在仓库里 | 按第 6 节手动放到 `D:\jiami\models\` |
| 页面扫描报 422 | 加密文本里仍有真名或号码 | 修改加密文本后重试 |
| 分析报 502 | 没有配置 `DEEPSEEK_API_KEY` | 填 `.env`，或先用假云端 |

---

## 9. 一次性命令速查

```bat
cd /d D:\jiami\project
git init
git add .
git status
git commit -m "心理档案去标识化：大小模型协同系统"
git branch -M main
git remote add origin https://github.com/你的用户名/psych-archive-privacy.git
git push -u origin main
```

推送完成后：

1. 检查仓库首页文件列表，确认没有 `.env` 和大文件。
2. 创建 `v1.0` Release，上传 941MB 的 GGUF。
3. 把下载链接补进 README。
4. 告诉组员：clone 代码后，把模型和 llama.cpp 放到 `D:\jiami\models\`、`D:\jiami\tools\`。
