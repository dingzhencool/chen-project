"""文本分块：递归字符分块，兼容中英文。"""
import re
from dataclasses import dataclass
from typing import List

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger("rag.chunker")


@dataclass
class Chunk:
    index: int
    content: str
    start_char: int
    end_char: int
    metadata: dict


class TextChunker:
    DEFAULT_SEPARATORS = [
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
        ";",
        "；",
        ".",
        "!",
        "?",
        ", ",
        "，",
        " ",
        "",
    ]

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def _split_once(self, text: str, separator: str) -> List[str]:
        if not separator:
            return list(text)
        parts = text.split(separator)
        if separator and separator in ("\n\n", "\n", "。", "！", "？", ";", "；", ".", "!", "?"):
            parts = [p + separator for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
        return [p for p in parts if p]

    def _merge_small(self, splits: List[str], separator: str) -> List[str]:
        merged: List[str] = []
        buf = ""
        for part in splits:
            if len(buf) + len(separator) + len(part) <= self.chunk_size:
                buf = (buf + separator + part) if buf else part
            else:
                if buf:
                    merged.append(buf)
                buf = part
        if buf:
            merged.append(buf)
        return merged

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        if not text:
            return []
        sep_idx = 0
        for i, s in enumerate(separators):
            if s and s in text:
                sep_idx = i
                break
        sep = separators[sep_idx]
        splits = self._split_once(text, sep)
        merged = self._merge_small(splits, sep)
        good: List[str] = []
        for m in merged:
            if len(m) <= self.chunk_size:
                good.append(m)
            else:
                if sep_idx + 1 >= len(separators):
                    # 最小分隔符都大于 chunk_size，硬切
                    for i in range(0, len(m), self.chunk_size - self.chunk_overlap):
                        piece = m[i:i + self.chunk_size]
                        if piece:
                            good.append(piece)
                else:
                    good.extend(self._recursive_split(m, separators[sep_idx + 1:]))
        # 加 overlap
        result: List[str] = []
        for i, g in enumerate(good):
            if i > 0 and self.chunk_overlap > 0:
                tail = good[i - 1][-self.chunk_overlap:]
                if not g.startswith(tail):
                    g = tail + g
            result.append(g[:self.chunk_size])
        return result

    def chunk(self, text: str, extra_meta: dict = None) -> List[Chunk]:
        if not text:
            return []
        logger.debug("[Chunker] 开始分块 chars=%s chunk_size=%s overlap=%s", len(text), self.chunk_size, self.chunk_overlap)
        texts = self._recursive_split(text, self.DEFAULT_SEPARATORS)
        chunks: List[Chunk] = []
        pos = 0
        for i, t in enumerate(texts):
            start = text.find(t, max(0, pos - 100))
            if start < 0:
                start = pos
            end = start + len(t)
            pos = end
            chunks.append(Chunk(index=i, content=t, start_char=start, end_char=end, metadata=extra_meta or {}))
        logger.info("[Chunker] 分块完成 chunks=%s", len(chunks))
        return chunks


text_chunker = TextChunker()
