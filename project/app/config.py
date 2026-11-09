"""集中读取环境变量。只从 .env / 进程环境取值，代码里不写死密钥。"""

import os

from dotenv import load_dotenv

load_dotenv()

# 本地小模型：llamacpp（llama-server）优先，Ollama 作为备选
LOCAL_BACKEND = os.getenv("LOCAL_BACKEND", "llamacpp").strip().lower()
LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL", "http://127.0.0.1:8080")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "qwen2.5-1.5b-ft")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

# 云端大模型（DeepSeek，OpenAI 兼容）
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
