"""Reranker：调用 DashScope gte-rerank 对召回候选项做语义精排。

设计原则：
- 失败不阻断问答：rerank 失败时回退到向量原始分数排序，问答继续。
- 与 embedding.py 一致的错误日志风格：保留服务端 code/message/request_id 以便排查。
- 不做本地 Mock 降级：未配置 Key 时直接跳过 rerank，回退原顺序。

DashScope rerank API：
- Endpoint: https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/
- Body: {"model":"gte-rerank","input":{"query":"...","documents":[...]},
         "parameters":{"top_n":N,"return_documents":false}}
- Response: {"output":{"results":[{"index":0,"relevance_score":0.95}, ...]}}
"""
import json
from typing import List, Optional

import httpx

from app.core.config import settings
from app.rag.vector_store import SearchHit
from app.utils.logger import get_logger

logger = get_logger("rag.reranker")

# DashScope rerank 原生端点（不走 OpenAI 兼容模式）
_DEFAULT_RERANK_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
_DEFAULT_RERANK_MODEL = "gte-rerank"


class RerankerUnavailableError(RuntimeError):
    """Reranker 不可用（未配置 / 调用失败）。不阻断问答，仅日志记录。"""


class Reranker:
    """DashScope gte-rerank 封装。单例风格，与 EmbeddingService 一致。"""

    _instance: "Optional[Reranker]" = None

    def __init__(self):
        self.base_url = (settings.RERANK_BASE_URL or _DEFAULT_RERANK_BASE_URL).rstrip("/")
        # Key 解析顺序：独立 RERANK_API_KEY > EMBEDDING_API_KEY > LLM_API_KEY
        # DashScope 同一账号可复用同一 Key
        self.api_key = settings.RERANK_API_KEY or settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self.model = settings.RERANK_MODEL or _DEFAULT_RERANK_MODEL
        self.top_n = settings.RERANK_TOP_N
        # 未配置 Key 时标记禁用，rerank 调用直接跳过
        self.enabled = bool(self.api_key) and bool(settings.RERANK_ENABLED)
        if self.enabled:
            logger.info(
                "[Reranker] 已启用 endpoint=%s model=%s top_n=%s",
                self.base_url, self.model, self.top_n,
            )
        else:
            reason = "RERANK_ENABLED=false" if not settings.RERANK_ENABLED else "未配置 RERANK_API_KEY/EMBEDDING_API_KEY/LLM_API_KEY"
            logger.info("[Reranker] 未启用 rerank（%s），问答将直接使用向量原始排序", reason)

    @classmethod
    def instance(cls) -> "Reranker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def rerank(self, query: str, hits: List[SearchHit]) -> List[SearchHit]:
        """对 hits 做语义重排，返回按 rerank 分数降序的新列表。

        失败时返回原 hits（按输入顺序），不抛异常，由上层继续问答流程。
        命中数 < 2 时无需 rerank。
        """
        if not self.enabled or not query or len(hits) < 2:
            return hits

        # DashScope 文档数上限 25，超过则取向量分数最高的前 25 条参与 rerank
        candidates = hits[:25] if len(hits) > 25 else hits
        documents = [h.text or "" for h in candidates]

        url = f"{self.base_url}/services/rerank/text-rerank/"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "top_n": min(self.top_n, len(documents)),
                "return_documents": False,
            },
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                body = r.json()
        except Exception as e:
            # 解析服务端错误体（与 embedding.py 风格一致）
            status = getattr(getattr(e, "response", None), "status_code", None)
            resp_text = ""
            code = msg = req_id = None
            try:
                resp_text = e.response.text
                err_body = json.loads(resp_text)
                code = err_body.get("code")
                msg = err_body.get("message")
                req_id = err_body.get("request_id")
            except Exception:
                resp_text = resp_text[:500] if resp_text else ""
            logger.warning(
                "[Reranker] 调用失败 status=%s model=%s code=%r msg=%r req_id=%r "
                "raw=%s ex=%s → 回退向量原始排序",
                status, self.model, code, msg, req_id,
                resp_text.replace("\n", " "), str(e),
            )
            return hits

        try:
            results = body["output"]["results"]
        except (KeyError, TypeError) as e:
            logger.warning(
                "[Reranker] 响应结构异常 body=%s ex=%s → 回退向量原始排序",
                json.dumps(body, ensure_ascii=False)[:300], str(e),
            )
            return hits

        # results[i].index 指向 documents 数组的下标（即 candidates 数组的下标）
        # 用 rerank 分数替换原 score，并加 metadata 标记来源
        reranked: List[SearchHit] = []
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score")
            if idx is None or score is None or idx < 0 or idx >= len(candidates):
                continue
            h = candidates[idx]
            # 复制一份避免污染原对象
            new_h = SearchHit(
                doc_id=h.doc_id,
                chunk_index=h.chunk_index,
                text=h.text,
                score=float(score),
                metadata={**(h.metadata or {}), "_rerank_score": float(score)},
            )
            reranked.append(new_h)

        if not reranked:
            logger.warning("[Reranker] rerank 返回空结果 → 回退向量原始排序")
            return hits

        # 参与了但未进 top_n 的候选项追加在尾部（保留向量分数排序）
        seen_idx = {item.get("index") for item in results}
        leftover = [h for i, h in enumerate(candidates) if i not in seen_idx]
        final = reranked + leftover

        logger.info(
            "[Reranker] 重排完成 query=%s candidates=%s reranked=%s top_score=%.4f",
            query[:60], len(candidates), len(reranked),
            float(reranked[0].score) if reranked else 0.0,
        )
        return final


reranker = Reranker.instance
