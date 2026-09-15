import os
import re
import time
import traceback
import uuid
from typing import Optional, Tuple

from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import BizException
from app.crud import crud_doc, crud_kb
from app.models.user import User
from app.rag.pipeline import process_document_ingest
from app.schemas.common import page_data, PageData
from app.schemas.document import DocumentOut
from app.utils.logger import doc_logger


class DocumentService:
    ALLOWED_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown",
        ".png", ".jpg", ".jpeg", ".webp", ".bmp",  # 图片：入库时由视觉模型 OCR/理解后转文本
    }
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    def _validate_file(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            doc_logger.warning(
                "[DOC_UPLOAD] 文件格式校验失败 | filename=%s ext=%s allowed=%s",
                filename, ext, self.ALLOWED_EXTENSIONS,
            )
            raise BizException(
                code=40005,
                message=f"不支持的文件格式：{ext}，支持格式：{self.ALLOWED_EXTENSIONS}",
            )
        return ext

    def _ensure_upload_dir(self, kb_id: int) -> str:
        kb_dir = os.path.join(settings.UPLOAD_DIR, f"kb_{kb_id}")
        os.makedirs(kb_dir, exist_ok=True)
        return kb_dir

    async def upload(
        self,
        db: Session,
        *,
        kb_id: int,
        user: User,
        file: UploadFile,
    ) -> Tuple[DocumentOut, str]:
        start = time.time()
        doc_logger.info(
            "[DOC_UPLOAD] 开始上传 | kb_id=%s user_id=%s username=%s filename=%s content_type=%s",
            kb_id, user.id, user.username, file.filename, file.content_type,
        )
        try:
            kb = crud_kb.get_by_owner(db, id=kb_id, owner_id=user.id)
            if not kb:
                doc_logger.warning(
                    "[DOC_UPLOAD] 知识库不存在 | kb_id=%s user_id=%s", kb_id, user.id,
                )
                raise BizException(code=40401, message="知识库不存在")
            if not file.filename:
                doc_logger.warning(
                    "[DOC_UPLOAD] 文件名为空 | kb_id=%s user_id=%s", kb_id, user.id,
                )
                raise BizException(code=40006, message="文件名不能为空")

            ext = self._validate_file(file.filename)
            doc_logger.info(
                "[DOC_UPLOAD] 文件校验通过 | kb_id=%s ext=%s", kb_id, ext,
            )

            kb_dir = self._ensure_upload_dir(kb_id)
            stored_name = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(kb_dir, stored_name)

            doc_logger.info(
                "[DOC_UPLOAD] 开始读取文件 | kb_id=%s filename=%s", kb_id, file.filename,
            )
            content = await file.read()
            file_size = len(content)
            doc_logger.info(
                "[DOC_UPLOAD] 文件读取完成 | kb_id=%s filename=%s size_bytes=%s size_human=%s",
                kb_id, file.filename, file_size, self._human_size(file_size),
            )

            if file_size > self.MAX_FILE_SIZE:
                elapsed = (time.time() - start) * 1000
                doc_logger.warning(
                    "[DOC_UPLOAD] 文件过大 | kb_id=%s size_bytes=%s max_bytes=%s elapsed_ms=%.2f",
                    kb_id, file_size, self.MAX_FILE_SIZE, elapsed,
                )
                raise BizException(
                    code=40007,
                    message=f"文件过大（{self._human_size(file_size)}），最大支持 {self._human_size(self.MAX_FILE_SIZE)}",
                )

            doc_logger.info(
                "[DOC_UPLOAD] 写入磁盘 | kb_id=%s file_path=%s size_bytes=%s",
                kb_id, file_path, file_size,
            )
            with open(file_path, "wb") as f:
                f.write(content)

            doc_data = {
                "kb_id": kb_id,
                "filename": file.filename,
                "stored_name": stored_name,
                "file_path": file_path,
                "file_type": ext.lstrip("."),
                "file_size": file_size,
                "status": "pending",
                "uploaded_by": user.id,
            }
            doc = crud_doc.create(db, obj_in=doc_data)
            doc_id = doc.id

            # ---------- 解析+向量化入库（CPU/网络密集型同步代码，必须丢进线程池） ----------
            # 直接在 async def 里调用会阻塞 uvicorn 事件循环：138 块文档 embedding 约 55 秒，
            # 期间整个服务无法响应任何其他请求（前端列表请求 30s 超时即源于此）。
            # run_in_threadpool 让阻塞逻辑在工作线程执行，事件循环保持空闲；
            # db 会话同一时刻只被该工作线程使用（当前协程正在 await），无并发访问，安全。
            doc_logger.info(
                "[DOC_UPLOAD] 文件已保存，开始解析+向量化 doc=%s kb=%s", doc_id, kb_id,
            )
            ingest_result = await run_in_threadpool(
                process_document_ingest, db, doc_id=doc_id, kb_id=kb_id
            )

            elapsed = (time.time() - start) * 1000
            if ingest_result.success:
                doc_logger.info(
                    "[DOC_UPLOAD] 全部完成 | doc_id=%s kb_id=%s filename=%s size=%s chunks=%s elapsed_ms=%.2f",
                    doc_id, kb_id, file.filename, self._human_size(file_size),
                    ingest_result.chunk_count, elapsed,
                )
            else:
                doc_logger.error(
                    "[DOC_UPLOAD] 入库失败 | doc_id=%s kb_id=%s filename=%s elapsed_ms=%.2f error=%s",
                    doc_id, kb_id, file.filename, elapsed, ingest_result.error,
                )

            # 重新刷新实体，获取最新 status / chunk_count
            db.refresh(doc)
            out = DocumentOut.model_validate(doc)
            if ingest_result.success:
                return out, f"上传并向量化成功（分块 {ingest_result.chunk_count}）"
            # 向量化失败：错误原因（如向量模型额度耗尽）随响应返回，前端直接弹给用户
            return out, f"上传完成但向量化失败：{ingest_result.error}"
        except BizException:
            raise
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            doc_logger.error(
                "[DOC_UPLOAD] 上传失败 | kb_id=%s user_id=%s filename=%s elapsed_ms=%.2f error=%s\n%s",
                kb_id, user.id, file.filename, elapsed, str(e), traceback.format_exc(),
            )
            raise

    def get_list(
        self,
        db: Session,
        *,
        kb_id: int,
        user: User,
        page: int,
        page_size: int,
    ) -> PageData[DocumentOut]:
        doc_logger.debug(
            "[DOC_LIST] 查询文档列表 | kb_id=%s user_id=%s page=%s page_size=%s",
            kb_id, user.id, page, page_size,
        )
        kb = crud_kb.get_by_owner(db, id=kb_id, owner_id=user.id)
        if not kb:
            doc_logger.warning(
                "[DOC_LIST] 知识库不存在 | kb_id=%s user_id=%s", kb_id, user.id,
            )
            raise BizException(code=40401, message="知识库不存在")
        skip = (page - 1) * page_size
        items, total = crud_doc.get_multi_by_kb(db, kb_id=kb_id, skip=skip, limit=page_size)
        doc_list = [DocumentOut.model_validate(d) for d in items]
        result = page_data(doc_list, total, page, page_size)
        doc_logger.debug(
            "[DOC_LIST] 查询完成 | kb_id=%s total=%s", kb_id, total,
        )
        return result

    def delete(self, db: Session, *, id: int, user: User) -> str:
        start = time.time()
        doc_logger.warning(
            "[DOC_DELETE] 开始删除文档 | doc_id=%s user_id=%s", id, user.id,
        )
        try:
            doc = crud_doc.get(db, id=id)
            if not doc:
                doc_logger.warning(
                    "[DOC_DELETE] 文档不存在 | doc_id=%s user_id=%s", id, user.id,
                )
                raise BizException(code=40402, message="文档不存在")
            kb = crud_kb.get_by_owner(db, id=doc.kb_id, owner_id=user.id)
            if not kb:
                doc_logger.warning(
                    "[DOC_DELETE] 无权限操作 | doc_id=%s user_id=%s kb_id=%s", id, user.id, doc.kb_id,
                )
                raise BizException(code=40302, message="无权限操作")
            # 同步从向量库删除（必须成功，否则不允许后续 DB/文件删除，防止 Chroma 残留成为「孤魂向量」）
            from app.rag.vector_store import get_vector_store
            store = get_vector_store()
            store.delete_by_document(doc.kb_id, id)
            if os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                    doc_logger.info(
                        "[DOC_DELETE] 文件已删除 | doc_id=%s file_path=%s", id, doc.file_path,
                    )
                except OSError as e:
                    doc_logger.warning(
                        "[DOC_DELETE] 文件删除失败（继续删除DB记录） | doc_id=%s file_path=%s error=%s",
                        id, doc.file_path, str(e),
                    )
            crud_doc.remove(db, id=id)
            elapsed = (time.time() - start) * 1000
            doc_logger.warning(
                "[DOC_DELETE] 删除成功 | doc_id=%s elapsed_ms=%.2f", id, elapsed,
            )
            return "删除成功"
        except BizException:
            raise
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            doc_logger.error(
                "[DOC_DELETE] 删除失败 | doc_id=%s user_id=%s elapsed_ms=%.2f error=%s\n%s",
                id, user.id, elapsed, str(e), traceback.format_exc(),
            )
            raise

    # ===================== 引用验真（Source Verification）=====================

    # 文件类型 -> 浏览器可内联预览的 MIME
    _INLINE_MEDIA_TYPES = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "txt": "text/plain; charset=utf-8",
        "md": "text/plain; charset=utf-8",
        "markdown": "text/plain; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
    }

    # PDF 解析时每页注入的锚点：--- Page N ---（见 document_parser._parse_pdf）
    _PAGE_MARK_RE = re.compile(r"---\s*Page\s+(\d+)\s*---")

    def _get_owned_document(self, db: Session, doc_id: int, user: User):
        """统一的文档归属校验：存在 + 所属知识库 owner 是当前用户。"""
        doc = crud_doc.get(db, id=doc_id)
        if not doc:
            raise BizException(code=40402, message="文档不存在")
        kb = crud_kb.get_by_owner(db, id=doc.kb_id, owner_id=user.id)
        if not kb:
            doc_logger.warning(
                "[DOC_VERIFY] 无权限访问 | doc_id=%s user_id=%s kb_id=%s", doc_id, user.id, doc.kb_id,
            )
            raise BizException(code=40302, message="无权限访问该文档")
        return doc

    @classmethod
    def _page_marks(cls, text: str):
        """取出一段文本中按出现顺序排列的所有页码锚点。"""
        return [int(m.group(1)) for m in cls._PAGE_MARK_RE.finditer(text or "")]

    def _infer_page_range(self, chunks: list, pos: int, window: int = 20) -> Tuple[Optional[int], Optional[int]]:
        """推断 chunks[pos] 覆盖的页码范围。

        PDF 锚点 '--- Page N ---' 只在每一页的页首出现一次，而分块按固定长度切，
        落在页面中段的 chunk 自身不含锚点。因此采用窗口推断：
        - 起始页：当前块内第一个锚点；没有则向前回溯最近块的最后一个锚点；
        - 结束页：当前块内最后一个锚点；没有则向后找到下一个页首锚点并 -1，再退化为起始页。
        window 为前后最多扫描的块数（一页正文通常 1~3 块，20 块 ≈ 上万字，足够覆盖）。
        """
        current_marks = self._page_marks(chunks[pos]["text"])
        if current_marks:
            return current_marks[0], current_marks[-1]

        start_page = None
        for back in range(pos - 1, max(-1, pos - 1 - window), -1):
            marks = self._page_marks(chunks[back]["text"])
            if marks:
                start_page = marks[-1]  # 紧邻当前块之前的页
                break

        end_page = start_page
        for fwd in range(pos + 1, min(len(chunks), pos + 1 + window)):
            marks = self._page_marks(chunks[fwd]["text"])
            if marks:
                end_page = max(start_page or 1, marks[0] - 1)  # 下一页页首之前都属于当前页
                break
        return start_page, end_page

    def preview_chunk(
        self, db: Session, *, doc_id: int, chunk_index: int, user: User
    ) -> dict:
        """引用验真：返回命中块原文 + 前后相邻块上下文 + PDF 页码，供前端对照 AI 回答。"""
        doc = self._get_owned_document(db, doc_id, user)
        from app.rag.vector_store import get_vector_store
        store = get_vector_store()
        chunks = store.get_document_chunks(doc.kb_id, doc_id)
        if not chunks:
            doc_logger.warning("[DOC_VERIFY] 向量库无分块 doc_id=%s（可能入库失败或已重建）", doc_id)
            raise BizException(code=40402, message="该文档暂无可定位的原文分块")

        idx_map = {row["chunk_index"]: i for i, row in enumerate(chunks)}
        if chunk_index not in idx_map:
            raise BizException(code=40402, message=f"分块 {chunk_index} 不存在")
        pos = idx_map[chunk_index]
        current = chunks[pos]
        prev_row = chunks[pos - 1] if pos > 0 else None
        next_row = chunks[pos + 1] if pos + 1 < len(chunks) else None

        page_start, page_end = self._infer_page_range(chunks, pos)
        doc_logger.info(
            "[DOC_VERIFY] 验真查询 doc_id=%s chunk=%s/%s page=%s~%s user=%s",
            doc_id, chunk_index, len(chunks) - 1, page_start, page_end, user.id,
        )
        return {
            "document_id": doc_id,
            "document_name": doc.filename,
            "file_type": doc.file_type,
            "chunk_index": chunk_index,
            "chunk_total": len(chunks),
            "page_start": page_start,
            "page_end": page_end,
            "inline_previewable": doc.file_type in ("pdf", "png", "jpg", "jpeg", "webp", "bmp", "txt", "md", "markdown"),
            "current": current["text"],
            "prev": prev_row["text"] if prev_row else None,
            "next": next_row["text"] if next_row else None,
        }

    def get_file_for_preview(
        self, db: Session, *, doc_id: int, user: User
    ) -> Tuple[str, str, str, str]:
        """带鉴权返回 (绝对路径, 原始文件名, 文件类型, MIME)，供 FileResponse 内联预览/下载。"""
        doc = self._get_owned_document(db, doc_id, user)
        abs_path = os.path.abspath(doc.file_path)
        upload_root = os.path.abspath(settings.UPLOAD_DIR)
        # 防目录穿越：文件必须在上传根目录下
        if not abs_path.startswith(upload_root + os.sep) or not os.path.isfile(abs_path):
            doc_logger.error("[DOC_VERIFY] 物理文件缺失或越界 doc_id=%s path=%s", doc_id, abs_path)
            raise BizException(code=40402, message="原文件不存在或已被移动")
        media_type = self._INLINE_MEDIA_TYPES.get(doc.file_type, "application/octet-stream")
        return abs_path, doc.filename, doc.file_type, media_type

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
