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

    async def _stream_once(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[Tuple[str, Optional[int], Optional[str]], None]:
        """发起一次流式请求，逐个 yield (content_delta, total_tokens, finish_reason)。

        思考型模型（如 deepseek-v4-flash）会把思维链放在 delta.reasoning_content，
        该部分不透传给调用方（属于内部推理），只记录字符数用于日志；正文取 delta.content。
        网络/HTTP 异常向上抛出，由 chat_stream 统一决定降级策略。
        """
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
        total_tokens: Optional[int] = None
        reasoning_chars = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                try:
                    resp.raise_for_status()
                except Exception:
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
                        total_tokens = int(usage.get("total_tokens") or 0) or total_tokens
                    for c in choices:
                        delta_obj = c.get("delta") or {}
                        content = delta_obj.get("content", "") or ""
                        rc = delta_obj.get("reasoning_content")
                        if rc:
                            reasoning_chars += len(rc)
                        finish = c.get("finish_reason")
                        if content:
                            yield content, total_tokens, finish
                        elif finish:
                            yield "", total_tokens, finish
        logger.debug(
            "[LLM] 单次流结束 model=%s max_tokens=%s reasoning_chars=%s total_tokens=%s",
            self.model, max_tokens, reasoning_chars, total_tokens,
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        _is_retry: bool = False,
    ) -> AsyncGenerator[Tuple[str, Optional[int]], None]:
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        budget = max_tokens or settings.LLM_MAX_TOKENS
        content_parts: List[str] = []
        total_tokens: Optional[int] = None
        finish_reason: Optional[str] = None
        try:
            async for delta, tok, finish in self._stream_once(messages, temperature, budget):
                if delta:
                    content_parts.append(delta)
                    yield delta, None
                if tok:
                    total_tokens = tok
                if finish:
                    finish_reason = finish
        except Exception as e:
            logger.error(
                "[LLM] 流式调用失败，降级为 Mock。provider=%s model=%s err=%s",
                self.name, self.model, str(e),
            )
            async for d, t in self._mock_fallback.chat_stream(
                messages, temperature=temperature, max_tokens=budget
            ):
                yield d, t
            return

        # 思考模型把预算全部耗在 reasoning_content 上时，正文一个字都没产出就被
        # finish_reason=length 截断（历史故障：UI 只剩引用来源、回答空白且无任何报错）。
        # 此时尚未向前端吐过任何正文，自动以翻倍预算静默重试一次；仍失败则显式报错，
        # 绝不允许"零正文 + 200 成功"这种静默空答。
        if not "".join(content_parts).strip() and finish_reason == "length":
            MAX_RETRY_BUDGET = 32768
            if not _is_retry and budget < MAX_RETRY_BUDGET:
                new_budget = min(budget * 2, MAX_RETRY_BUDGET)
                logger.warning(
                    "[LLM] 正文为空且输出被 max_tokens=%s 截断（思维链耗尽预算），翻倍至 %s 重试 model=%s",
                    budget, new_budget, self.model,
                )
                async for d, t in self.chat_stream(
                    messages, temperature=temperature, max_tokens=new_budget, _is_retry=True
                ):
                    yield d, t
                return
            raise RuntimeError(
                f"大模型输出被 token 上限截断（max_tokens={budget}），思维链耗尽预算导致正文未生成。"
                f"请在 .env 调大 LLM_MAX_TOKENS（当前 {budget}，建议 8192 或更高）后重试。"
            )
        yield "", total_tokens

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
            with httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                choice = (data.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content", "") or ""
                finish = choice.get("finish_reason")
                usage = data.get("usage") or {}
                # 与流式一致：思考模型正文为空且 length 截断时，翻倍预算重试一次
                if not content.strip() and finish == "length":
                    budget = int(kw["max_tokens"] or settings.LLM_MAX_TOKENS)
                    if budget < 32768:
                        new_budget = min(budget * 2, 32768)
                        logger.warning(
                            "[LLM] 非流式正文为空且被 max_tokens=%s 截断，翻倍至 %s 重试 model=%s",
                            budget, new_budget, self.model,
                        )
                        kw["max_tokens"] = new_budget
                        return self.chat(messages, **kw)
                    raise RuntimeError(
                        f"大模型输出被 token 上限截断（max_tokens={budget}），正文未生成，请调大 LLM_MAX_TOKENS。"
                    )
                return content, int(usage.get("total_tokens") or len(content))
        except RuntimeError:
            raise
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
