"""Word(.docx) 读取：正文段落 + 表格单元格，按文档顺序压成纯文本。"""

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


def _iter_blocks(doc):
    """按 body 中子元素的真实顺序产出段落与表格。"""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def read_docx(path: str) -> str:
    """返回纯文本；段落之间空行分隔，表格行用 " | " 连接。页眉页脚/图片忽略。"""
    doc = Document(path)
    blocks = []
    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                blocks.append(text)
        else:
            for row in block.rows:
                cells = []
                for cell in row.cells:
                    value = " ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                    if value:
                        cells.append(value)
                if cells:
                    blocks.append(" | ".join(cells))
    return "\n\n".join(blocks)
