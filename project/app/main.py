"""FastAPI 入口：上传 -> 小模型加密 -> 发送前扫描 -> 云端单轮评估 -> 回译。服务端无状态。"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import anonymize, config, docx_io, kb, llm, privacy_guard, rules
from .contract import CATEGORIES

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="心理档案去标识化 · 大小模型协同")


class MappingEntry(BaseModel):
    placeholder: str
    category: str
    original: str = ""
    aliases: list[str] = Field(default_factory=list)
    relation: str = ""
    count: int = 0
    note: str = ""

    @field_validator("placeholder")
    @classmethod
    def _placeholder_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("placeholder 不能为空")
        return value

    @field_validator("category")
    @classmethod
    def _category_valid(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"category 必须是 {CATEGORIES}")
        return value


class AnalyzeIn(BaseModel):
    encrypted_text: str
    mapping: list[MappingEntry] = Field(default_factory=list)


class GuardIn(BaseModel):
    text: str
    mapping: list[MappingEntry] = Field(default_factory=list)


class DecryptIn(BaseModel):
    text: str
    mapping: list[MappingEntry] = Field(default_factory=list)


def _mapping_dicts(entries: list[MappingEntry]) -> list[dict]:
    return [entry.model_dump() for entry in entries]


@app.get("/api/health")
def health():
    info = llm.local_info()
    return {
        "local_alive": llm.local_alive(),
        "local_backend": info["backend"],
        "local_model": info["model"],
        "local_base_url": info["base_url"],
        "llm_key": bool(config.DEEPSEEK_API_KEY),
        "deepseek_model": config.DEEPSEEK_MODEL,
        "kb_cards": kb.count(),
    }


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    """接收 .docx，交给小模型抽取隐私实体，返回加密文本、对应表与发送前扫描结果。"""
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "只支持 .docx，请先把文档另存为 .docx")

    fd, path = tempfile.mkstemp(suffix=".docx")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(await file.read())
        text = docx_io.read_docx(path)
    except Exception as exc:
        raise HTTPException(400, f"无法解析这个 .docx：{exc}") from exc
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    if not text.strip():
        raise HTTPException(400, "文档里没有可提取的文字")

    try:
        raw = rules.supplement(text, llm.extract(text))
        encrypted, mapping = anonymize.anonymize(text, raw)
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(502, f"小模型输出不合规：{exc}") from exc

    issues = privacy_guard.scan_text(encrypted, mapping)
    return {"encrypted_text": encrypted, "mapping": mapping, "guard_issues": issues}


@app.post("/api/guard")
def guard(payload: GuardIn):
    """发送前扫描：不调用云端，只在本机检查别名残留与常见账号格式。"""
    issues = privacy_guard.scan_text(payload.text, _mapping_dicts(payload.mapping))
    return {
        "issues": issues,
        "blocked": bool(privacy_guard.blocking(issues)),
        "summary": privacy_guard.describe(issues),
    }


@app.post("/api/analyze")
def analyze(payload: AnalyzeIn):
    """扫描通过后：检索本地知识库，云端单轮生成报告，本地回译。"""
    text = payload.encrypted_text.strip()
    if not text:
        raise HTTPException(400, "加密文本为空")
    mapping = _mapping_dicts(payload.mapping)

    issues = privacy_guard.scan_text(text, mapping)
    if privacy_guard.blocking(issues):
        raise HTTPException(422, "发送前扫描未通过：" + privacy_guard.describe(issues) + "，请修改加密文本后重试。")

    legend_text = anonymize.legend(mapping)
    references = kb.retrieve(text, [str(entry.get("relation", "")) for entry in mapping])
    refs_text = kb.format_references(references)
    try:
        report = llm.analyze_report(text, legend_text, refs_text)
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    report = kb.sanitize_citations(report, len(references))

    return {
        "report_encrypted": report,
        "report_restored": anonymize.reverse(report, mapping),
        "guard_issues": issues,
        "legend": legend_text,
        "references": kb.public_refs(references),
    }


@app.post("/api/deanonymize")
def deanonymize(payload: DecryptIn):
    return {"restored": anonymize.reverse(payload.text, _mapping_dicts(payload.mapping))}


app.mount("/", StaticFiles(directory=str(BASE_DIR / "web"), html=True), name="web")
