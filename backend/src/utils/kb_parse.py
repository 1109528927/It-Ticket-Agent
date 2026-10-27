"""知识库多格式解析：MD / PDF / DOCX 抽文本；图片可选 OCR / 图意说明。"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_EXTS = {".md", ".markdown", ".txt"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
ALLOWED_EXTS = TEXT_EXTS | PDF_EXTS | DOCX_EXTS | IMAGE_EXTS


def normalize_ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def assert_allowed(filename: str) -> str:
    ext = normalize_ext(filename)
    if ext not in ALLOWED_EXTS:
        raise ValueError(
            f"不支持的文件类型 {ext or '(无后缀)'}，允许：{', '.join(sorted(ALLOWED_EXTS))}"
        )
    return ext


def parse_file(path: str | Path, *, enable_ocr: bool = False) -> str:
    """统一入口：返回纯文本，供切分嵌入。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在: {p}")
    ext = normalize_ext(p.name)
    if ext in TEXT_EXTS:
        return _parse_text(p)
    if ext in PDF_EXTS:
        return _parse_pdf(p)
    if ext in DOCX_EXTS:
        return _parse_docx(p)
    if ext in IMAGE_EXTS:
        if not enable_ocr:
            raise ValueError("图片入库请勾选「OCR / 图意说明」")
        return _parse_image_vl(p)
    raise ValueError(f"不支持的文件类型: {ext}")


def _parse_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = ""
    else:
        text = raw.decode("utf-8", errors="ignore")
    text = text.strip()
    if not text:
        raise ValueError("文本文件为空")
    return text


def _parse_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            t = (page.extract_text() or "").strip()
        except Exception:
            logger.exception("PDF 第 %s 页抽文本失败", i + 1)
            t = ""
        if t:
            parts.append(t)
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("PDF 未抽出文本（可能是扫描件，请转图片并勾选 OCR）")
    return text


def _parse_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("DOCX 未抽出文本")
    return text


def _parse_image_vl(path: Path) -> str:
    """百炼视觉：抽文字 + 一两句图意。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("图片 OCR 需要配置 DASHSCOPE_API_KEY")

    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )
    model = os.getenv("KB_VL_MODEL", "qwen-vl-plus")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {
                        "type": "text",
                        "text": (
                            "请提取图中全部可见文字；若几乎无文字，"
                            "用一两句话说明图意与用途。只输出纯文本，不要 markdown。"
                        ),
                    },
                ],
            }
        ],
        temperature=0.1,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("视觉模型未返回有效说明")
    return text
