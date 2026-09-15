"""向量存储：优先使用 Chroma，未安装时降级为基于内存 + 余弦相似度的实现。"""
import math
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger("rag.vector")


@dataclass
class VectorRecord:
    doc_id: int
    chunk_index: int
    text: str
    vector: List[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchHit:
    doc_id: int
    chunk_index: int
    text: str
    score: float
    metadata: dict


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        dot += a[i] * b[i]
        na += a[i] * a[i]
        nb += b[i] * b[i]
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ================ 内存实现 ================

class InMemoryVectorStore:
    name = "memory"

    def __init__(self):
        self._lock = threading.RLock()
        # kb_id -> list[VectorRecord]
        self._collections: Dict[int, List[VectorRecord]] = {}

    def close(self):
        """内存存储无句柄需释放，与 ChromaVectorStore.close 对齐接口。"""
        return

    def _col(self, kb_id: int) -> List[VectorRecord]:
        if kb_id not in self._collections:
            self._collections[kb_id] = []
        return self._collections[kb_id]

    def add(self, kb_id: int, records: List[VectorRecord]):
        if not records:
            return
        with self._lock:
            col = self._col(kb_id)
            col.extend(records)
            logger.info("[VectorStore] 添加向量 kb=%s records=%s total=%s", kb_id, len(records), len(col))

    def delete_by_document(self, kb_id: int, doc_id: int):
        with self._lock:
            col = self._col(kb_id)
            before = len(col)
            self._collections[kb_id] = [r for r in col if r.doc_id != doc_id]
            removed = before - len(self._collections[kb_id])
            logger.info("[VectorStore] 删除文档向量 kb=%s doc=%s removed=%s", kb_id, doc_id, removed)

    def delete_by_kb(self, kb_id: int):
        with self._lock:
            if kb_id in self._collections:
                removed = len(self._collections[kb_id])
                del self._collections[kb_id]
                logger.info("[VectorStore] 清空知识库 kb=%s removed=%s", kb_id, removed)

    def get_document_chunks(self, kb_id: int, doc_id: int) -> List[Dict]:
        """取回某文档的全部分块原文（按 chunk_index 升序），供引用验真展示。"""
        with self._lock:
            col = list(self._collections.get(kb_id, []))
        rows = [
            {"chunk_index": r.chunk_index, "text": r.text}
            for r in col if r.doc_id == doc_id
        ]
        rows.sort(key=lambda x: x["chunk_index"])
        return rows

    def search(self, kb_id: int, query_vector: List[float], top_k: int, threshold: float) -> List[SearchHit]:
        with self._lock:
            col = list(self._collections.get(kb_id, []))
        if not col:
            return []
        scored: List[Tuple[float, VectorRecord]] = []
        for r in col:
            score = _cosine(query_vector, r.vector)
            if score >= threshold:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHit(
                doc_id=r.doc_id,
                chunk_index=r.chunk_index,
                text=r.text,
                score=s,
                metadata=dict(r.metadata),
            )
            for s, r in scored[:top_k]
        ]


# ================ Chroma 实现（可选依赖）================

class ChromaVectorStore:
    name = "chroma"

    def __init__(self):
        import chromadb
        os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
        self._client = chromadb.PersistentClient(path=settings.VECTOR_DB_PATH)
        self._lock = threading.RLock()
        logger.info("[VectorStore] Chroma 已加载 path=%s", settings.VECTOR_DB_PATH)

    @staticmethod
    def _col_name(kb_id: int) -> str:
        return f"kb_{kb_id}"

    def _get_or_create(self, kb_id: int):
        name = self._col_name(kb_id)
        try:
            return self._client.get_collection(name)
        except Exception:
            return self._client.create_collection(name=name, metadata={"kb_id": kb_id})

    def close(self):
        """关闭 PersistentClient，释放对 chroma.sqlite3 与段文件的句柄（Windows 下删除
        向量库目录前必须调用，否则 rmtree 报 WinError 32）。"""
        with self._lock:
            try:
                self._client.close()
                logger.info("[VectorStore] Chroma client 已关闭")
            except Exception:
                pass

    def reset_client(self):
        """关闭并重建 PersistentClient，丢弃 Chroma system 对 collection/segment 的内存缓存。

        必须在 delete_collection 之后、create_collection 同名集合之前调用：同一 client 内
        删完同名集合立刻重建时，缓存的 segment 引用会指向已删除的 HNSW 段文件，后续
        col.query() 报 "Error creating hnsw segment reader: Nothing found on disk"。
        也可用于 close() + 删除目录后重新打开全新数据目录。
        """
        with self._lock:
            old = self._client
            try:
                old.close()
            except Exception:
                pass
            import chromadb
            self._client = chromadb.PersistentClient(path=settings.VECTOR_DB_PATH)
            logger.info("[VectorStore] Chroma client 已重置（清除集合段缓存）")

    def add(self, kb_id: int, records: List[VectorRecord]):
        if not records:
            return
        with self._lock:
            col = self._get_or_create(kb_id)
            ids = [f"{r.doc_id}_{r.chunk_index}" for r in records]
            documents = [r.text for r in records]
            embeddings = [r.vector for r in records]
            metadatas = []
            for r in records:
                m = {"doc_id": int(r.doc_id), "chunk_index": int(r.chunk_index)}
                if r.metadata:
                    for k, v in r.metadata.items():
                        if isinstance(v, (str, int, float, bool)):
                            m[k] = v
                        else:
                            m[k] = str(v)
                metadatas.append(m)
            col.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
            logger.info("[VectorStore] Chroma 添加 kb=%s records=%s", kb_id, len(records))

    def delete_by_document(self, kb_id: int, doc_id: int):
        with self._lock:
            try:
                col = self._get_or_create(kb_id)
                where = {"doc_id": int(doc_id)}
                data = col.get(where=where, include=[])
                if data.get("ids"):
                    col.delete(ids=data["ids"])
                    logger.info("[VectorStore] Chroma 删除文档 kb=%s doc=%s n=%s", kb_id, doc_id, len(data["ids"]))
            except Exception as e:
                logger.warning("[VectorStore] Chroma 删除文档失败 kb=%s doc=%s err=%s", kb_id, doc_id, str(e))

    def delete_by_kb(self, kb_id: int):
        with self._lock:
            name = self._col_name(kb_id)
            existed = False
            try:
                self._client.delete_collection(name)
                existed = True
                logger.info("[VectorStore] Chroma 删除知识库 kb=%s", kb_id)
            except Exception:
                pass
        # 删除集合后重建 client，确保紧接着的同名 create_collection 不复用旧 HNSW 段缓存
        if existed:
            self.reset_client()

    def search(self, kb_id: int, query_vector: List[float], top_k: int, threshold: float) -> List[SearchHit]:
        with self._lock:
            col = self._get_or_create(kb_id)
            if col.count() == 0:
                return []
            res = col.query(
                query_embeddings=[query_vector],
                n_results=top_k * 2,
                include=["documents", "metadatas", "distances"],
            )
        hits: List[SearchHit] = []
        docs = res["documents"][0] if res.get("documents") else []
        metas = res["metadatas"][0] if res.get("metadatas") else []
        dists = res["distances"][0] if res.get("distances") else []
        for i in range(len(docs)):
            distance = dists[i] if i < len(dists) else 2.0
            # Chroma 默认使用 L2 距离，转换为近似相似度 [0,1]
            approx_score = 1.0 - min(distance, 2.0) / 2.0
            if approx_score < threshold:
                continue
            meta = metas[i] if i < len(metas) else {}
            hits.append(
                SearchHit(
                    doc_id=int(meta.get("doc_id", 0)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    text=docs[i],
                    score=approx_score,
                    metadata=meta,
                )
            )
        hits.sort(key=lambda x: x.score, reverse=True)
        return hits[:top_k]

    def get_document_chunks(self, kb_id: int, doc_id: int) -> List[Dict]:
        """取回某文档的全部分块原文（按 chunk_index 升序），供引用验真展示。

        Chroma 入库时主键 id 形如 "{doc_id}_{chunk_index}"，用 metadata where 过滤后
        直接 get，不走向量检索（验真要的是原文，不是相似度）。
        """
        with self._lock:
            try:
                col = self._get_or_create(kb_id)
                data = col.get(where={"doc_id": int(doc_id)}, include=["documents", "metadatas"])
            except Exception as e:
                logger.warning("[VectorStore] Chroma 取文档分块失败 kb=%s doc=%s err=%s", kb_id, doc_id, str(e))
                return []
        rows: List[Dict] = []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        for i, text in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            rows.append({"chunk_index": int(meta.get("chunk_index", 0)), "text": text})
        rows.sort(key=lambda x: x["chunk_index"])
        return rows


# ================ Factory ================

_store: Optional[object] = None
_store_lock = threading.Lock()


def get_vector_store():
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                try:
                    import chromadb  # noqa: F401
                    _store = ChromaVectorStore()
                except ImportError:
                    logger.warning("[VectorStore] chromadb 未安装，使用内存向量存储（重启后数据丢失）。pip install chromadb 可启用持久化。")
                    _store = InMemoryVectorStore()
                except Exception as e:
                    logger.warning("[VectorStore] Chroma 初始化失败，降级为内存存储: %s", str(e))
                    _store = InMemoryVectorStore()
    return _store
