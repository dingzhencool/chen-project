"""视觉模型客户端：图片入库链路专用。

设计思路（图片如何进入以文本为核心的 RAG 系统）：
图片本身无法被 text-embedding 向量化，也无法被纯文本 LLM 直接阅读。
因此入库时先用多模态视觉模型（DashScope qwen-vl 系列，OpenAI 兼容协议）对图片做
OCR + 结构化理解，得到一段忠实于图片内容的文字，再复用既有的
「切片 → Embedding → Chroma → 检索 → 引用」链路，不引入第二套向量体系。

图片预处理：统一用 Pillow 读取，超边长等比缩小、转 JPEG，控制 base64 体积与平台限制。
"""
import base64
import io
import json
from typing import Tuple

import httpx

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger("rag.vision")

# 让视觉模型"看图说话"的固定指令：强调逐字 OCR、数字保真、表格还原、禁止编造
VISION_EXTRACT_PROMPT = (
    "你是企业知识库的图片解析器，请对这张图片做完整的内容提取，输出纯文本。要求：\n"
    "1. 逐字提取图中所有文字（标题、正文、表格、页眉页脚、批注、印章文字等），"
    "数字、金额、日期、人名必须原样保留，不得概括或省略；\n"
    "2. 表格按行还原，同一行的单元格用 | 分隔；\n"
    "3. 若包含流程图、架构图、图表或照片，先用文字说明其类型，再描述结构、关键数据与结论；\n"
    "4. 只输出从图片中提取到的内容，使用中文，使用换行和序号组织层次；"
    "不要使用 ** 加粗、# 标题等 Markdown 符号；不要输出任何与图片无关的解释或开场白。"
)


class VisionClient:
    """OpenAI 兼容多模态接口（DashScope qwen-vl），同步客户端（在 threadpool 中调用）。"""

    def __init__(self):
        self.base_url = settings.VISION_BASE_URL.rstrip("/")
        # Key 解析顺序：独立 VISION_API_KEY > EMBEDDING_API_KEY（同一 DashScope 账号可复用）> LLM_API_KEY
        self.api_key = settings.VISION_API_KEY or settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self.model = settings.VISION_MODEL
        logger.info(
            "[Vision] 初始化 provider=%s model=%s key_configured=%s",
            self.base_url, self.model, bool(self.api_key),
        )

    def _preprocess(self, file_path: str) -> Tuple[str, str]:
        """读取并标准化图片，返回 (base64 字符串, mime)。失败抛 RuntimeError。"""
        try:
            from PIL import Image
        except ImportError as e:
            raise RuntimeError("图片解析依赖 Pillow 未安装，请先 pip install Pillow") from e

        try:
            with Image.open(file_path) as im:
                im.load()
                orig_w, orig_h = im.size
                # 透明通道图转 RGB 前垫白底，避免黑底
                if im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    rgba = im.convert("RGBA")
                    bg.paste(rgba, mask=rgba.split()[-1])
                    im = bg
                else:
                    im = im.convert("RGB")

                # 等比缩小到最大边长以内
                max_side = settings.VISION_IMAGE_MAX_SIDE
                if max(im.size) > max_side:
                    ratio = max_side / float(max(im.size))
                    new_size = (max(1, int(im.size[0] * ratio)), max(1, int(im.size[1] * ratio)))
                    im = im.resize(new_size, Image.LANCZOS)
                    logger.info(
                        "[Vision] 图片缩放 %sx%s -> %sx%s (max_side=%s)",
                        orig_w, orig_h, new_size[0], new_size[1], max_side,
                    )

                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=settings.VISION_JPEG_QUALITY)
                raw = buf.getvalue()
        except Exception as e:
            raise RuntimeError(f"图片预处理失败（文件可能已损坏或不是有效图片）：{e}") from e

        logger.info("[Vision] 预处理完成 file=%s jpeg_bytes=%s", file_path, len(raw))
        return base64.b64encode(raw).decode("ascii"), "image/jpeg"

    def describe_image(self, file_path: str) -> str:
        """把一张图片转写为结构化文本。任何失败都抛 RuntimeError（上层会把文档置为 failed）。"""
        if not self.api_key:
            raise RuntimeError(
                "图片解析需要视觉模型 API Key，请在 .env 配置 VISION_API_KEY（或复用 EMBEDDING_API_KEY）"
            )

        img_b64, mime = self._preprocess(file_path)
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    {"type": "text", "text": VISION_EXTRACT_PROMPT},
                ],
            }],
            "temperature": 0.0,
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(settings.VISION_TIMEOUT, connect=30.0)) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                body = r.json()
        except Exception as e:
            # 与 embedding 客户端一致：解析服务端错误体，不丢失拒绝原因
            status = getattr(getattr(e, "response", None), "status_code", None)
            code = msg = None
            resp_text = ""
            try:
                resp_text = e.response.text
                err = (json.loads(resp_text).get("error") or {})
                code, msg = err.get("code"), err.get("message")
            except Exception:
                resp_text = resp_text[:500]
            logger.error(
                "[Vision] 视觉模型调用失败 status=%s model=%s code=%r msg=%r raw=%s ex=%s",
                status, self.model, code, msg, resp_text.replace("\n", " "), str(e),
            )
            detail = f"；视觉模型错误：code={code!r} msg={msg!r}" if code or msg else ""
            raise RuntimeError(f"视觉模型调用失败：{e}{detail}") from e

        try:
            text = (body["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"视觉模型返回结构异常：{json.dumps(body, ensure_ascii=False)[:300]}") from e

        if not text:
            raise RuntimeError("视觉模型返回了空内容（图片可能无法识别）")

        usage = body.get("usage") or {}
        logger.info(
            "[Vision] 图片转写完成 model=%s chars=%s tokens=%s",
            self.model, len(text), usage.get("total_tokens"),
        )
        return text


_vision_client: "VisionClient | None" = None


def vision_service() -> VisionClient:
    """单例获取视觉客户端（与 embedding_service() 风格一致）。"""
    global _vision_client
    if _vision_client is None:
        _vision_client = VisionClient()
    return _vision_client
