"""文档解析模块：支持 TXT / MD / PDF / DOCX / DOC，可选依赖优雅降级。"""
import os
from dataclasses import dataclass
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger("rag.parser")


@dataclass
class ParsedDocument:
    text: str
    metadata: dict


class DocumentParser:
    @staticmethod
    def _read_text(file_path: str, encoding: str = "utf-8") -> str:
        for enc in (encoding, "utf-8", "gbk", "utf-16", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                raise RuntimeError(f"读取文本失败：{e}")
        raise RuntimeError("无法识别文件编码")

    @staticmethod
    def _parse_pdf(file_path: str) -> str:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("[Parser] PyMuPDF 未安装，PDF 将降级为提取文件名作为占位内容。pip install pymupdf 可启用真实解析。")
            base = os.path.basename(file_path)
            return f"[PDF 文件：{base}]\n（PDF 解析组件 PyMuPDF 未安装，此处为占位文本。请安装 pymupdf 后重新上传以提取真实内容。）"
        try:
            parts: list[str] = []
            with fitz.open(file_path) as doc:
                for i, page in enumerate(doc):
                    text = page.get_text("text") or ""
                    parts.append(f"--- Page {i + 1} ---\n{text}")
            return "\n".join(parts)
        except Exception as e:
            logger.error("[Parser] PDF 解析失败 file=%s error=%s", file_path, str(e))
            raise RuntimeError(f"PDF 解析失败：{e}")

    @staticmethod
    def _parse_docx(file_path: str) -> str:
        try:
            from docx import Document
        except ImportError:
            logger.warning("[Parser] python-docx 未安装，DOCX 将降级为占位文本。pip install python-docx 可启用真实解析。")
            base = os.path.basename(file_path)
            return f"[DOCX 文件：{base}]\n（DOCX 解析组件 python-docx 未安装，此处为占位文本。请安装 python-docx 后重新上传以提取真实内容。）"
        try:
            doc = Document(file_path)
            parts: list[str] = [p.text for p in doc.paragraphs if p and p.text]
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    parts.append(" | ".join(cells))
            return "\n".join(parts)
        except Exception as e:
            logger.error("[Parser] DOCX 解析失败 file=%s error=%s", file_path, str(e))
            raise RuntimeError(f"DOCX 解析失败：{e}")

    @staticmethod
    def _parse_image(file_path: str) -> str:
        """图片（png/jpg/jpeg/webp/bmp）：调多模态视觉模型做 OCR + 图像理解，转写为文本入库。

        图片无法直接走文本 Embedding，这里把它转成忠实于画面内容的文字后，
        后续 切片/向量化/检索 与普通文档完全复用同一条链路。
        """
        try:
            from app.rag.vision import vision_service
        except ImportError as e:
            raise RuntimeError(f"视觉解析模块不可用：{e}")
        base = os.path.basename(file_path)
        logger.info("[Parser] 开始视觉解析图片 file=%s", file_path)
        text = vision_service().describe_image(file_path)
        # 头部保留来源文件名，检索/引用时能明确这段文字来自哪张图片
        return f"[图片文件：{base}]\n{text}"

    def parse(self, file_path: str, file_type: Optional[str] = None) -> ParsedDocument:
        if not os.path.exists(file_path):
            raise RuntimeError(f"文件不存在：{file_path}")
        ext = (file_type or os.path.splitext(file_path)[1]).lower().lstrip(".")
        ext_map = {
            "txt": self._parse_txt,
            "md": self._parse_md,
            "markdown": self._parse_md,
            "pdf": self._parse_pdf,
            "docx": self._parse_docx,
            "doc": self._parse_doc,
            "png": self._parse_image,
            "jpg": self._parse_image,
            "jpeg": self._parse_image,
            "webp": self._parse_image,
            "bmp": self._parse_image,
        }
        parser_fn = ext_map.get(ext)
        if not parser_fn:
            raise RuntimeError(f"不支持的文件类型：{ext}")
        logger.info("[Parser] 开始解析 file=%s type=%s", file_path, ext)
        text = parser_fn(file_path)
        text_len = len(text)
        logger.info("[Parser] 解析完成 file=%s chars=%s", file_path, text_len)
        return ParsedDocument(text=text, metadata={"file_type": ext, "chars": text_len})

    @staticmethod
    def _parse_txt(file_path: str) -> str:
        return DocumentParser._read_text(file_path)

    @staticmethod
    def _parse_md(file_path: str) -> str:
        return DocumentParser._read_text(file_path)

    @staticmethod
    def _parse_doc(file_path: str) -> str:
        base = os.path.basename(file_path)
        logger.warning("[Parser] 老版 .doc 未支持，降级为占位文本。建议先转换为 .docx 再上传。")
        return f"[DOC 文件：{base}]\n（传统 .doc 格式暂不支持，请先转换为 .docx 或 .pdf 后重新上传以提取内容。）"


document_parser = DocumentParser()
