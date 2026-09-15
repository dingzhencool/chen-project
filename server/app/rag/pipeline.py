"""RAG Pipeline：文档入库链路 + 问答生成链路。"""
import asyncio
import traceback
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import crud_doc
from app.models.document import Document
from app.rag.document_parser import document_parser
from app.rag.embedding import EmbeddingUnavailableError, embedding_service
from app.rag.llm_client import llm_client
from app.rag.prompt_templates import build_rag_prompt
from app.rag.retriever import retriever
from app.rag.text_chunker import text_chunker
from app.rag.vector_store import VectorRecord, SearchHit, get_vector_store
from app.utils.logger import get_logger

logger = get_logger("rag.pipeline")


# ============ 文档入库链路 ============

@dataclass
class DocumentIngestResult:
    doc_id: int
    success: bool
    status: str
    chunk_count: int = 0
    error: Optional[str] = None


def process_document_ingest(db: Session, doc_id: int, kb_id: int) -> DocumentIngestResult:
    """同步执行文档解析→分块→向量化→入库，更新 Document 的 status / chunk_count / error_msg。"""
    doc = crud_doc.get(db, id=doc_id)
    if not doc:
        return DocumentIngestResult(doc_id=doc_id, success=False, status="failed", error="文档不存在")
    # processing 状态（上传新文档时展示给用户看）；启动重放不走此入口，避免状态抖动
    doc.status = "processing"
    doc.error_msg = None
    db.commit()
    logger.info("[Ingest] 开始处理 doc=%s kb=%s file=%s", doc_id, kb_id, doc.filename)
    return _run_ingest(db, doc, kb_id)


def _run_ingest(db: Session, doc, kb_id: int) -> DocumentIngestResult:
    """共享的入库实现：供上传触发与启动重放共用，不重复改 status=pending（避免写库时被外面已判定为 ready 的记录"回退"）。"""
    try:
        parsed = document_parser.parse(doc.file_path, file_type=doc.file_type)
        chunks = text_chunker.chunk(
            parsed.text,
            extra_meta={"doc_id": doc.id, "kb_id": kb_id, "filename": doc.filename},
        )
        if not chunks:
            doc.status = "ready"
            doc.chunk_count = 0
            db.commit()
            logger.warning("[Ingest] 文档无可分块内容 doc=%s kb=%s", doc.id, kb_id)
            return DocumentIngestResult(doc_id=doc.id, success=True, status="ready", chunk_count=0)

        texts = [c.content for c in chunks]
        logger.info("[Ingest] 分块完成 doc=%s chunks=%s 开始 embedding...", doc.id, len(chunks))
        # 向量模型不可用时 embed() 直接抛 EmbeddingUnavailableError（含服务端真实原因，
        # 如免费额度耗尽），由入库捕获写入文档 error_msg；不再有任何假向量降级。
        emb_result = embedding_service().embed(texts)
        logger.info("[Ingest] Embedding 完成 doc=%s provider=%s dim=%s",
                    doc.id, emb_result.provider, emb_result.dim)

        records: List[VectorRecord] = []
        for i, c in enumerate(chunks):
            vec = emb_result.embeddings[i] if i < len(emb_result.embeddings) else [0.0] * emb_result.dim
            records.append(
                VectorRecord(
                    doc_id=doc.id,
                    chunk_index=c.index,
                    text=c.content,
                    vector=vec,
                    metadata={"filename": doc.filename, "kb_id": kb_id},
                )
            )

        store = get_vector_store()
        store.delete_by_document(kb_id, doc.id)  # 幂等：先删旧的
        store.add(kb_id, records)
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error_msg = None
        db.commit()
        logger.info(
            "[Ingest] 入库完成 doc=%s chunks=%s status=ready",
            doc.id, len(chunks),
        )
        return DocumentIngestResult(
            doc_id=doc.id, success=True, status="ready", chunk_count=len(chunks)
        )
    except Exception as e:
        # EmbeddingUnavailableError 的消息本身就是面向用户的可读提示，不拼异常类名
        err_msg = str(e) if isinstance(e, EmbeddingUnavailableError) else f"{type(e).__name__}: {str(e)}"
        logger.error(
            "[Ingest] 处理失败 doc=%s kb=%s err=%s\n%s",
            doc.id, kb_id, err_msg, traceback.format_exc(),
        )
        doc.status = "failed"
        doc.error_msg = err_msg[:500]
        db.commit()
        return DocumentIngestResult(
            doc_id=doc.id, success=False, status="failed", error=err_msg
        )


# ============ 启动向量库重放 ============

def replay_all_ready_documents(db_factory) -> Dict[str, int]:
    """启动时把数据库中所有 status=ready 的文档重新投递到向量库（幂等）。
    用于内存向量库重启后恢复；Chroma 持久化场景下也安全运行。
    返回统计信息：{'total': N, 'success': M, 'skipped': S, 'failed': F, 'elapsed_ms': ms}。
    """
    import time as _time
    t0 = _time.time()
    db = db_factory()
    total = success = skipped = failed = 0
    try:
        from app.models.document import Document
        store_name = get_vector_store().name
        # 重放仅为「内存向量库重启后数据全失」设计的自愈手段。Chroma 是持久化存储，
        # 向量已落盘，每次启动全量重放既浪费（大库 Embedding 耗时数分钟），又会在集合
        # 状态异常时反复 delete+upsert；换模型/修库应显式运行 rebuild_vectors.py。
        if store_name != "memory":
            logger.info(
                "[Replay] 向量库=%s 为持久化存储，跳过重放（如需重建请运行 rebuild_vectors.py）",
                store_name,
            )
            return {"total": 0, "success": 0, "skipped": 0, "failed": 0, "elapsed_ms": 0}
        qs = db.query(Document).filter(Document.status == "ready").order_by(Document.id.asc())
        docs = qs.all()
        total = len(docs)
        logger.info(
            "[Replay] 向量库=%s，开始重放所有 ready 文档：count=%s",
            store_name, total,
        )
        for doc in docs:
            if not doc.file_path or not __import__("os").path.exists(doc.file_path):
                logger.warning("[Replay] 跳过 doc=%s（%s）：文件不存在 path=%s", doc.id, doc.filename, doc.file_path)
                skipped += 1
                continue
            try:
                r = _run_ingest(db, doc, doc.kb_id)
                if r.success:
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.error("[Replay] 重放失败 doc=%s（%s）err=%s", doc.id, doc.filename, str(e))
        elapsed_ms = int((_time.time() - t0) * 1000)
        logger.info(
            "[Replay] 重放完成 total=%s success=%s skipped=%s failed=%s elapsed_ms=%s",
            total, success, skipped, failed, elapsed_ms,
        )
        return {"total": total, "success": success, "skipped": skipped, "failed": failed, "elapsed_ms": elapsed_ms}
    finally:
        db.close()


# ============ 问答生成链路 ============

@dataclass
class RagAnswerResult:
    hits: List[SearchHit]
    sources: List[Dict[str, Any]]  # 用于写入 Message.sources
    prompt_tokens: int = 0


def _lookup_doc_names(db: Optional[Session], hits: List[SearchHit]) -> Dict[int, str]:
    result: Dict[int, str] = {}
    # 1) 先用向量条目中携带的 metadata['filename'] 兜底，保证 db 未提供或查不到时仍有展示名
    for h in hits:
        if h.doc_id and h.metadata:
            fn = h.metadata.get("filename") or h.metadata.get("document_name") or ""
            if fn:
                result.setdefault(h.doc_id, fn)
    doc_ids = sorted({h.doc_id for h in hits if h.doc_id and h.doc_id not in result})
    if not doc_ids or db is None:
        return result
    try:
        rows = db.query(Document.id, Document.filename).filter(Document.id.in_(doc_ids)).all()
        for r in rows:
            result[r.id] = r.filename
    except Exception as e:
        logger.warning("[RAG] 查询文档名失败 err=%s，使用 metadata 兜底。", str(e))
    return result


def rag_prepare_context(db: Session, kb_id: Optional[int], query: str) -> RagAnswerResult:
    """执行检索 + 组装引用信息。

    过滤保险：只保留 score > 0 的非噪声命中，并对 (doc_id, chunk_index) 去重，
    避免向量/嵌入异常导致 0 分占位泄漏到 UI。
    """
    hits: List[SearchHit] = []
    if kb_id:
        hits = retriever.retrieve(kb_id, query)

    # 过滤 1：只保留正分数；并按 (doc_id, chunk_index) 去重（同一块只保留最高分）
    cleaned: List[SearchHit] = []
    seen: Dict[Tuple[int, int], int] = {}  # (doc_id, chunk_index) -> index in cleaned
    for h in hits:
        if not h or h.score is None or float(h.score) <= 0.0:
            continue
        key = (int(h.doc_id or 0), int(h.chunk_index or 0))
        sc = float(h.score)
        if key in seen:
            prev_idx = seen[key]
            if sc > float(cleaned[prev_idx].score):
                cleaned[prev_idx] = h
        else:
            seen[key] = len(cleaned)
            cleaned.append(h)
    cleaned.sort(key=lambda x: float(x.score), reverse=True)

    doc_names = _lookup_doc_names(db, cleaned)
    # 过滤 2：兜底删除不一致——删除文档时如果 Chroma 删除异常（L202-205 吞错）会残留「孤魂向量」，
    # 它们的 doc_id 在 DB 已查不到（物理删），document_name 为空。这种来源不能泄漏给 UI，
    # 否则会出现「来源 N 相似度 0.xx」，用户不知道引用的是什么文件。
    valid_cleaned: List[SearchHit] = []
    valid_sources: List[Dict[str, Any]] = []
    for h in cleaned:
        name = doc_names.get(h.doc_id, "")
        if not name:
            logger.warning(
                "[RAG] 过滤孤魂向量：doc_id=%s chunk=%s score=%.4f 在 Document 表不存在（可能删除时 Chroma 清理失败）",
                h.doc_id, h.chunk_index, float(h.score or 0),
            )
            continue
        valid_cleaned.append(h)
        valid_sources.append({
            "document_id": h.doc_id,
            "document_name": name,
            "chunk_index": h.chunk_index,
            "content": h.text,
            "score": float(h.score),
        })
    return RagAnswerResult(hits=valid_cleaned, sources=valid_sources)


async def rag_answer_stream(
    db: Session,
    kb_id: Optional[int],
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[Tuple[str, Optional[int], RagAnswerResult], None]:
    """RAG 流式生成：yields (delta_text, incremental_tokens, answer_result)
    - 最后一个 yield 会携带 final token 数（之前 token 字段为 None）。
    """
    t0 = asyncio.get_event_loop().time() if asyncio.get_event_loop() else None
    answer_ctx = rag_prepare_context(db, kb_id, query)
    system_prompt, user_msg = build_rag_prompt(query, answer_ctx.hits)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_msg})
    logger.info(
        "[RAG] 问答链路 kb=%s hits=%s query=%s",
        kb_id, len(answer_ctx.hits), query[:80],
    )
    total_tokens = 0
    async for delta, tok in llm_client().chat_stream(messages):
        if tok is not None:
            total_tokens = tok
        yield delta, tok if tok is not None else None, answer_ctx
    # finalization
    answer_ctx.prompt_tokens = total_tokens
    logger.info("[RAG] 生成完成 tokens=%s elapsed_ms=%.0f", total_tokens,
                ((asyncio.get_event_loop().time() - t0) * 1000) if t0 else 0.0)
