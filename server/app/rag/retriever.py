"""检索器：向量稠密检索 + 简单关键词重排 + 文档去重。

硬保险机制（按优先级）：
1) __init__ 启动指纹（fingerprint=RAG_RETRIEVER_V2_20260821）写入 INFO，用于确认新代码已加载。
2) 真 Embedding 下 threshold > 0.4 时强 clamp 到 0.35，并打 WARN。避免 .env/旧进程
   缓存的 0.6 把泛 query 全挡掉。
3) 全景最高分 ≥ 0.30 但被阈值挡住时，强制放行（比"零命中兜底"更早生效）。
4) 最终零命中兜底仍保留：实在没命中就取 top 相近 2 条给 LLM，不乱答。
"""
from typing import List

from app.core.config import settings
from app.rag.embedding import embedding_service
from app.rag.vector_store import SearchHit, get_vector_store
from app.utils.logger import get_logger

logger = get_logger("rag.retriever")

_FINGERPRINT = "RAG_RETRIEVER_V2_20260821"
_TRUE_EMB_CLAMP = 0.35       # 真 Embedding：若外部配置 > 0.4 就硬 clamp 到该值
_TRUE_EMB_WARN_TH = 0.40     # 超过此值会打 WARN
_SOFT_PASS_MIN_SCORE = 0.30  # 全景最高分 ≥ 此值但被阈值挡住时，强制放行


class Retriever:
    def __init__(self):
        self.store = get_vector_store()
        # 启动指纹：重启后在 app.log 中 grep 此字符串即可确认新代码生效
        logger.info("[Retriever] 初始化 fingerprint=%s store=%s default_threshold=%s top_k=%s",
                    _FINGERPRINT, self.store.name,
                    settings.SIMILARITY_THRESHOLD, settings.RETRIEVAL_TOP_K)

    def retrieve(
        self,
        kb_id: int,
        query: str,
        top_k: int = None,
        threshold: float = None,
    ) -> List[SearchHit]:
        if not query or kb_id is None:
            return []
        top_k = top_k or settings.RETRIEVAL_TOP_K
        threshold = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD
        # 向量模型不可用（未配置/额度耗尽/网络失败）时 embed_one 会直接抛
        # EmbeddingUnavailableError，由上层 SSE error 事件透传到消息框提示用户。
        provider = embedding_service().provider_name

        # --- 硬保险 2：阈值强 clamp（防止旧 .env/旧进程缓存 0.6 导致泛 query 零命中） ---
        if threshold > _TRUE_EMB_WARN_TH:
            clamped = _TRUE_EMB_CLAMP
            logger.warning(
                "[Retriever] 阈值过高 provider=%s configured=%.3f -> 强 clamp=%.3f "
                "(防止泛 query 零命中；如需调高请改 .env SIMILARITY_THRESHOLD 并确认 ≤ %.2f)",
                provider, threshold, clamped, _TRUE_EMB_WARN_TH)
            threshold = clamped

        logger.debug("[Retriever] 开始检索 kb=%s top_k=%s threshold=%s provider=%s fp=%s query=%s",
                     kb_id, top_k, threshold, provider, _FINGERPRINT, query[:80])
        query_vec = embedding_service().embed_one(query)

        # 分数全景：先跑一次不过滤的 top，把最接近的 3 条分数打到 DEBUG，便于调阈值。
        try:
            overview = self.store.search(kb_id, query_vec, top_k=min(top_k + 3, 20), threshold=-1000.0)
        except Exception as e:
            logger.warning("[Retriever] 全景检索失败 kb=%s err=%s，使用主检索结果", kb_id, str(e))
            overview = []
        if overview:
            logger.debug("[Retriever] 分数全景 kb=%s candidates=%s", kb_id, len(overview))
            for h in overview[:3]:
                logger.debug("  ^ score=%.4f doc=%s chunk=%s text=%s",
                             h.score, h.doc_id, h.chunk_index, (h.text or "")[:80].replace("\n", " "))

        # 主检索：带阈值
        hits: List[SearchHit] = self.store.search(kb_id, query_vec, top_k=top_k, threshold=threshold)

        # --- 硬保险 3：全景最高分 ≥ 0.30 但被阈值挡住 → 强制放行 ---
        if not hits and overview and overview[0].score >= _SOFT_PASS_MIN_SCORE:
            # 只要不过滤的最高分够，就取到第一个低于 0.3 的位置为止（最多 top_k 条）
            passed = []
            for h in overview:
                if h.score >= _SOFT_PASS_MIN_SCORE and len(passed) < top_k:
                    passed.append(h)
                    h.metadata = dict(h.metadata or {})
                    h.metadata["_retrieval_fallback"] = "softpass"
                else:
                    break
            if passed:
                hits = passed
                scores = ", ".join("%.3f" % h.score for h in hits)
                logger.info(
                    "[Retriever] 软放行（全景最高分≥%.2f）kb=%s n=%s scores=[%s]",
                    _SOFT_PASS_MIN_SCORE, kb_id, len(hits), scores)

        # 零命中兜底：不过滤取 top_k，至少给 LLM 提供最接近的候选，避免空上下文乱答。
        if not hits and overview:
            fallback_n = min(top_k, max(2, top_k // 2 or 2))
            hits = overview[:fallback_n]
            scores = ", ".join("%.3f" % h.score for h in hits)
            logger.info("[Retriever] 主检索零命中，启用兜底（放宽阈值）kb=%s n=%s scores=[%s]",
                        kb_id, len(hits), scores)
            for h in hits:
                h.metadata = dict(h.metadata or {})
                h.metadata["_retrieval_fallback"] = "1"

        # 关键词打分加成：命中越多用户关键词的 chunk，分数略抬高（仅用于排序）
        q_tokens = [t for t in set(query.lower().replace("\n", " ").split()) if len(t) > 0]
        if q_tokens:
            for h in hits:
                bonus = 0.0
                low = (h.text or "").lower()
                for tok in q_tokens:
                    if tok in low:
                        bonus += 0.02
                h.score = min(h.score + bonus, 1.0)
            hits.sort(key=lambda x: x.score, reverse=True)
        logger.info("[Retriever] 命中 hits=%s kb=%s provider=%s fp=%s",
                    len(hits), kb_id, provider, _FINGERPRINT)
        for h in hits[: min(3, len(hits))]:
            meta = h.metadata or {}
            fb = meta.get("_retrieval_fallback")
            tag = ""
            if fb == "softpass":
                tag = " [softpass]"
            elif fb == "1":
                tag = " [fallback]"
            logger.debug("  -> doc=%s chunk=%s score=%.3f%s text=%s",
                         h.doc_id, h.chunk_index, h.score, tag,
                         (h.text or "")[:60].replace("\n", " "))
        return hits[:top_k]


retriever = Retriever()
