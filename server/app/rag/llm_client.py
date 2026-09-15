"""LLM 客户端：OpenAI 兼容流式接口（DashScope / DeepSeek / Kimi / 本地 Ollama），未配置 Key 或调用失败时自动降级 Mock。"""
import json
import time
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger("rag.llm")


class _MockLLM:
    name = "mock"

    @staticmethod
    def _build_reply(query: str, system_prompt: str) -> str:
        has_no_ref = "没有检索到任何相关文档" in system_prompt or "现有资料暂无法回答" in system_prompt
        if has_no_ref:
            return (
                f"您好！收到您的问题：「{query}」。\n\n"
                "💡 当前我使用的是 **Mock 模式**（未配置真实 LLM API Key 或大模型临时不可用），且本次未检索到知识库中的参考文档。\n\n"
                "您可以：\n"
                "1. 打开「知识库管理」，新建一个知识库并上传相关文档（PDF / DOCX / TXT / MD）；\n"
                "2. 在 `.env` 中配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 以启用真实大模型；\n"
                "3. 重新开始对话，我将基于上传的文档内容结合大模型为您回答。"
            )
        return (
            f"好的，我已阅读参考资料并结合您的问题整理如下回答：\n\n"
            f"针对您提问的「{query}」：\n\n"
            "**核心结论（示例回答 / Mock 模式）**：\n"
            "当前使用的是 Mock LLM，这是一段演示性回复，实际部署时会替换为真实大模型的生成结果。\n\n"
            "**要点**：\n"
            "- 请在 `.env` 中配置 `LLM_API_KEY`、`LLM_BASE_URL`（例如 DashScope、DeepSeek、Kimi、Ollama 等兼容 OpenAI 协议的接口）及 `LLM_MODEL`；\n"
            "- 参考资料已正确命中并拼接至 Prompt，真实 LLM 会结合这些资料生成具体答案并附带引用标注 [Doc#id]；\n"
            "- 本回复未展示真实引用，但检索链路已经打通，切换为真实 LLM 后即可看到带引用的专业回答。"
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[Tuple[str, Optional[int]], None]:
        last_user = ""
        system_prompt = ""
        for m in messages:
            if m.get("role") == "user":
                last_user = m.get("content", "")
            elif m.get("role") == "system":
                system_prompt = m.get("content", "")
        reply = self._build_reply(last_user, system_prompt)
        step = 3
        tokens_used = 0
        for i in range(0, len(reply), step):
            delta = reply[i:i + step]
            tokens_used += 1
            yield delta, None
            await self._sleep(0.012)
        yield "", tokens_used

    def chat(self, messages: List[Dict[str, str]], **kw) -> Tuple[str, int]:
        collected: List[str] = []
        total_tokens = 0
        import asyncio

        async def runner():
            nonlocal total_tokens
            async for delta, tok in self.chat_stream(messages, **kw):
                if delta:
                    collected.append(delta)
                if tok is not None:
                    total_tokens = tok

        asyncio.run(runner())
        return "".join(collected), total_tokens

    @staticmethod
    async def _sleep(seconds: float):
        import asyncio
        await asyncio.sleep(seconds)


class _OpenAICompatibleLLM:
    def __init__(self, base_url: str, api_key: str, model: str, name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = name
        self._mock_fallback = _MockLLM()

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[Tuple[str, Optional[int]], None]:
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        total_tokens = 0
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=30.0)) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    try:
                        resp.raise_for_status()
                    except Exception:
                        # 捕获 HTTP 错误体
                        body = ""
                        try:
                            body = await resp.aread()
                        except Exception:
                            pass
                        raise RuntimeError(f"HTTP {resp.status_code}: {body[:300]}")
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = obj.get("choices") or []
                        usage = obj.get("usage")
                        if usage:
                            total_tokens = int(usage.get("total_tokens") or total_tokens)
                        for c in choices:
                            delta = (c.get("delta") or {}).get("content", "")
                            finish = c.get("finish_reason")
                            if delta:
                                yield delta, None
                            if finish:
                                break
        except Exception as e:
            logger.error(
                "[LLM] 流式调用失败，降级为 Mock。provider=%s model=%s err=%s",
                self.name, self.model, str(e),
            )
            async for d, t in self._mock_fallback.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield d, t
            return
        yield "", total_tokens or None

    def chat(self, messages: List[Dict[str, str]], **kw) -> Tuple[str, int]:
        if kw.get("temperature") is None:
            kw["temperature"] = settings.LLM_TEMPERATURE
        if kw.get("max_tokens") is None:
            kw["max_tokens"] = settings.LLM_MAX_TOKENS
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "messages": messages, "stream": False, **{k: v for k, v in kw.items() if v is not None}}
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"].get("content", "")
                usage = data.get("usage") or {}
                return content, int(usage.get("total_tokens") or len(content))
        except Exception as e:
            logger.error(
                "[LLM] 同步调用失败，降级为 Mock。provider=%s model=%s err=%s",
                self.name, self.model, str(e),
            )
            return self._mock_fallback.chat(messages, **kw)


class LLMClient:
    _instance = None

    def __init__(self):
        self._impl = self._select_impl()
        logger.info("[LLM] 使用 provider=%s model=%s", self._impl.name,
                    getattr(self._impl, "model", "-"))

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _select_impl():
        if settings.LLM_API_KEY and settings.LLM_BASE_URL and settings.LLM_MODEL:
            try:
                return _OpenAICompatibleLLM(
                    base_url=settings.LLM_BASE_URL,
                    api_key=settings.LLM_API_KEY,
                    model=settings.LLM_MODEL,
                    name=f"openai-compat:{settings.LLM_MODEL}",
                )
            except Exception as e:
                logger.warning("[LLM] 真实 LLM 初始化失败，降级为 mock: %s", str(e))
        else:
            logger.warning(
                "[LLM] LLM_API_KEY 未配置，启用 Mock LLM。"
                " 请在 .env 中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 以启用真实生成。"
            )
        return _MockLLM()

    @property
    def provider_name(self) -> str:
        return self._impl.name

    async def chat_stream(self, messages: List[Dict[str, str]], **kw) -> AsyncGenerator[Tuple[str, Optional[int]], None]:
        async for delta, tok in self._impl.chat_stream(messages, **kw):
            yield delta, tok

    def chat(self, messages: List[Dict[str, str]], **kw) -> Tuple[str, int]:
        return self._impl.chat(messages, **kw)


llm_client = LLMClient.instance
