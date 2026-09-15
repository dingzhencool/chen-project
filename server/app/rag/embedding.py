"""Embedding 封装：OpenAI 兼容接口（DashScope text-embedding-v3 等）。

设计原则（不做本地 Mock 降级）：
向量模型不可用（未配置 Key、额度耗尽、网络故障等）时，直接抛出带服务端错误原因的
EmbeddingUnavailableError，由上层在问答消息框 / 文档失败状态中明确提示用户。
绝不静默生成假向量——假向量会污染向量库（维度不一致写入失败）或产生垃圾检索结果，
且用户无法分辨"模型说的"和"随机噪声"。
"""
import json
from dataclasses import dataclass
from typing import List, Optional

import httpx

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger("rag.embedding")


class EmbeddingUnavailableError(RuntimeError):
    """向量模型不可用（未配置 / 额度不足 / 调用失败）。消息文本可直接展示给用户。"""


# 常见服务端错误码 → 用户可读的中文原因
_FRIENDLY_ERROR_HINTS = {
    "AllocationQuota.FreeTierOnly": "向量模型免费额度已用尽，请在阿里云百炼控制台充值或关闭「仅使用免费额度」模式",
    "QuotaExceeded": "向量模型调用额度/限流已超限，请稍后重试或提升配额",
    "Throttling.RateQuota": "向量模型调用频率超限，请稍后重试",
    "InvalidApiKey": "向量模型 API Key 无效或已失效，请检查 .env 配置",
    "AuthenticationError": "向量模型鉴权失败（API Key 无效或已过期），请检查 .env 配置",
    "InvalidParameter": "向量模型请求参数不被接受（如模型名/批量大小），请联系管理员检查配置",
    "Model.NotFound": "向量模型不存在或无访问权限，请检查 EMBEDDING_MODEL 配置",
}


@dataclass
class EmbeddingResult:
    embeddings: List[List[float]]
    dim: int
    provider: str


class OpenAICompatibleEmbeddingProvider:
    """OpenAI 兼容 /embeddings 接口（DashScope compatible-mode 等），同步客户端。"""

    def __init__(self, base_url: str, api_key: str, model: str, name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = name
        self._dim_cache: Optional[int] = None

    @property
    def dim(self) -> int:
        if self._dim_cache is None:
            # 维度探测本身就是一次真实调用：失败直接抛错，不猜测维度
            self._dim_cache = len(self.embed(["dimension probe"])[0])
        return self._dim_cache

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # ⚠️ DashScope compatible-mode 批量限制极严：text-embedding-v3 /v1/embeddings 单批 input 不能超过 10 条
        # （OpenAI 官方兼容模式通常是 2048，但 DashScope 多模型共享限流更紧）。
        # 服务端响应体：InvalidParameter / "batch size is invalid, it should not be larger than 10.: input.contents"
        batch_size = 10
        result: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            payload = {"model": self.model, "input": batch, "encoding_format": "float"}
            try:
                with httpx.Client(timeout=60.0) as client:
                    r = client.post(url, headers=headers, json=payload)
                    r.raise_for_status()
                    data = r.json()
                    sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                    result.extend([list(d["embedding"]) for d in sorted_data])
            except Exception as e:
                # 按 Experience 100008473：必须解析并保留服务端错误体（status + code/message/request_id），
                # 否则上层只会看到 "Client error 400"，无法区分额度不足/参数错误/Key 失效。
                status = getattr(getattr(e, "response", None), "status_code", None)
                resp_text = ""
                code = msg = req_id = None
                try:
                    resp_text = e.response.text
                except Exception:
                    pass
                if resp_text:
                    try:
                        body = json.loads(resp_text)
                        err = body.get("error") or {}
                        code = err.get("code")
                        msg = err.get("message")
                        req_id = body.get("request_id") or err.get("request_id")
                    except Exception:
                        resp_text = resp_text[:500]
                logger.error(
                    "[Embedding] HTTP 失败 provider=%s status=%s "
                    "endpoint=%s model=%r input_len=%r(这批) total_n=%s | dashscope_code=%r dashscope_msg=%r req_id=%r | raw=%s | ex=%s",
                    self.name, status,
                    url, self.model, len(batch), len(texts),
                    code, msg, req_id,
                    resp_text.replace("\n", " ") if resp_text else "",
                    str(e),
                )
                detail = ""
                friendly = _FRIENDLY_ERROR_HINTS.get(code) if code else None
                if friendly:
                    detail = f"：{friendly}"
                elif code or msg:
                    # 未收录的错误码：保留服务端原始 code/message 供排查
                    detail = f"：服务端返回 code={code!r}，message={msg!r}"
                else:
                    detail = f"：{str(e)[:300]}"
                rid = f"（request_id={req_id}）" if req_id and friendly else ""
                raise EmbeddingUnavailableError(
                    f"向量模型不可用（HTTP {status}）{detail}{rid}"
                ) from e
        return result


class EmbeddingService:
    """单例。初始化只读取配置、不做网络冒烟；首次 embed 即真实调用，
    因此服务恢复（充值/换 Key）后无需重启进程即可自愈。"""

    _instance: "Optional[EmbeddingService]" = None

    def __init__(self):
        self._provider: Optional[OpenAICompatibleEmbeddingProvider] = None
        self.config_error: Optional[str] = None

        emb_base_url = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL or ""
        emb_api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY or ""
        missing = [
            name for name, val in (
                ("EMBEDDING_BASE_URL", emb_base_url),
                ("EMBEDDING_API_KEY", emb_api_key),
                ("EMBEDDING_MODEL", settings.EMBEDDING_MODEL),
            ) if not val
        ]
        if missing:
            self.config_error = (
                "向量模型未配置（缺少 " + " / ".join(missing) + "），请在服务端 .env 中补全后重启"
            )
            logger.error("[Embedding] %s", self.config_error)
            return

        self._provider = OpenAICompatibleEmbeddingProvider(
            base_url=emb_base_url,
            api_key=emb_api_key,
            model=settings.EMBEDDING_MODEL,
            name=f"openai-compat:{settings.EMBEDDING_MODEL}",
        )
        logger.info("[Embedding] 已配置 provider=%s endpoint=%s", self._provider.name, self._provider.base_url)

    @classmethod
    def instance(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _require_provider(self) -> OpenAICompatibleEmbeddingProvider:
        if self._provider is None:
            raise EmbeddingUnavailableError(self.config_error or "向量模型不可用")
        return self._provider

    @property
    def dim(self) -> int:
        return self._require_provider().dim

    @property
    def provider_name(self) -> str:
        return self._require_provider().name

    def embed(self, texts: List[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(embeddings=[], dim=0, provider="none")
        provider = self._require_provider()
        vectors = provider.embed([t if t else "" for t in texts])
        dim = len(vectors[0]) if vectors else 0
        logger.debug("[Embedding] 完成 n=%s dim=%s", len(vectors), dim)
        return EmbeddingResult(embeddings=vectors, dim=dim, provider=provider.name)

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text]).embeddings[0]


embedding_service = EmbeddingService.instance
