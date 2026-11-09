"""本地小模型（llama-server / Ollama）与云端 DeepSeek 的调用封装。"""

from __future__ import annotations

import json

import httpx

from . import config, prompts


class LLMError(RuntimeError):
    """调用模型失败，main.py 会把它转成 HTTP 502。"""


def _post(url: str, payload: dict, headers: dict | None = None):
    try:
        # 不走系统代理：本机服务无需代理，同时规避畸形 NO_PROXY 导致的 URL 解析错误
        response = httpx.post(url, json=payload, headers=headers or {}, timeout=300, trust_env=False)
    except httpx.HTTPError as exc:
        raise LLMError(f"无法连接 {url}：{exc}") from exc
    if response.status_code >= 400:
        raise LLMError(f"{url} 返回 HTTP {response.status_code}：{response.text[:300]}")
    return response.json()


def local_alive() -> bool:
    if config.LOCAL_BACKEND == "ollama":
        url = f"{config.OLLAMA_BASE_URL}/api/tags"
    else:
        url = f"{config.LOCAL_BASE_URL}/health"
    try:
        return httpx.get(url, timeout=3, trust_env=False).status_code == 200
    except httpx.HTTPError:
        return False


def local_info() -> dict:
    if config.LOCAL_BACKEND == "ollama":
        return {"backend": "ollama", "model": config.OLLAMA_MODEL, "base_url": config.OLLAMA_BASE_URL}
    return {"backend": "llamacpp", "model": config.LOCAL_MODEL, "base_url": config.LOCAL_BASE_URL}


def _local_chat(system: str, user: str, json_mode: bool = True, max_tokens: int = 1024) -> str:
    if config.LOCAL_BACKEND == "ollama":
        payload = {
            "model": config.OLLAMA_MODEL,
            "stream": False,
            "options": {"temperature": 0, "num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        data = _post(f"{config.OLLAMA_BASE_URL}/api/chat", payload)
        return (data.get("message") or {}).get("content", "")

    payload = {
        "model": config.LOCAL_MODEL,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_schema", "json_schema": {"schema": prompts.EXTRACT_SCHEMA}}
    data = _post(f"{config.LOCAL_BASE_URL}/v1/chat/completions", payload)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"llama-server 返回结构异常：{str(data)[:300]}") from exc


def _parse_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f"模型没有返回合法 JSON：{content[:300]}") from exc
        else:
            raise LLMError(f"模型没有返回合法 JSON：{content[:300]}") from None
    if not isinstance(value, dict):
        raise LLMError(f"模型输出的 JSON 不是对象：{content[:300]}")
    return value


def extract(text: str) -> dict:
    """让小模型按契约输出实体 JSON。"""
    content = _local_chat(prompts.EXTRACT_SYSTEM, text, json_mode=True, max_tokens=2048)
    return _parse_json(content)


def _deepseek_chat(system: str, user: str, json_mode: bool = False, temperature: float = 0.3) -> str:
    if not config.DEEPSEEK_API_KEY:
        raise LLMError("未配置 DEEPSEEK_API_KEY，请写入 .env")
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "temperature": temperature,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"大模型返回结构异常：{str(data)[:300]}") from exc


def analyze_report(encrypted_text: str, legend_text: str, refs_text: str = "") -> str:
    """单轮云端分析：直接返回 Markdown 报告。"""
    user = prompts.ANALYZE_TASK + encrypted_text + "\n\n" + legend_text
    if refs_text:
        user += "\n\n" + refs_text
    return _deepseek_chat(prompts.ANALYZE_SYSTEM, user, temperature=0.3)
