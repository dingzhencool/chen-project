import json
import time
from typing import AsyncGenerator, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import BizException
from app.crud import crud_conv, crud_msg
from app.models.conversation import Message
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.rag.pipeline import RagAnswerResult, rag_answer_stream
from app.schemas.common import page_data, PageData
from app.schemas.conversation import (
    ChatMessage,
    ChatSource,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.utils.logger import get_logger

logger = get_logger("app.chat")


class ChatService:
    def create_conversation(
        self,
        db: Session,
        *,
        obj_in: ConversationCreate,
        user: User,
    ) -> Tuple[ConversationOut, str]:
        conv = crud_conv.create_with_user(db, obj_in=obj_in, user_id=user.id)
        logger.info(
            "[Chat] 创建对话 conv=%s user=%s kb=%s title=%s",
            conv.id, user.id, conv.kb_id, conv.title,
        )
        return ConversationOut.model_validate(conv), "创建成功"

    def get_conversation_list(
        self,
        db: Session,
        *,
        user: User,
        page: int,
        page_size: int,
    ) -> PageData[ConversationOut]:
        skip = (page - 1) * page_size
        items, total = crud_conv.get_multi_by_user(
            db, user_id=user.id, skip=skip, limit=page_size
        )
        conv_list = [ConversationOut.model_validate(c) for c in items]
        return page_data(conv_list, total, page, page_size)

    def get_messages(
        self,
        db: Session,
        *,
        conversation_id: int,
        user: User,
    ) -> List[MessageOut]:
        conv = crud_conv.get_by_user(db, id=conversation_id, user_id=user.id)
        if not conv:
            raise BizException(code=40403, message="对话不存在")
        messages = crud_msg.get_multi_by_conversation(db, conversation_id=conversation_id, limit=500)
        result: List[MessageOut] = []
        for m in messages:
            msg = MessageOut.model_validate(m)
            if m.sources:
                try:
                    raw = json.loads(m.sources)
                    if isinstance(raw, list):
                        # 过滤保险 2（历史脏数据）：只保留 score > 0 的来源；对 (doc_id, chunk_index) 去重
                        dedup: Dict[Tuple[int, int], Dict] = {}
                        for s in raw:
                            if not isinstance(s, dict):
                                continue
                            sc = float(s.get("score") or 0.0)
                            if sc <= 0.0:
                                continue
                            key = (int(s.get("document_id") or 0), int(s.get("chunk_index") or 0))
                            if key in dedup:
                                if sc > float(dedup[key].get("score") or 0.0):
                                    dedup[key] = s
                            else:
                                dedup[key] = s
                        cleaned_list = sorted(
                            dedup.values(),
                            key=lambda x: float(x.get("score") or 0.0),
                            reverse=True,
                        )
                        msg.sources = cleaned_list if cleaned_list else None
                    else:
                        msg.sources = None
                except (json.JSONDecodeError, TypeError):
                    msg.sources = None
            result.append(msg)
        return result

    def update_conversation(
        self,
        db: Session,
        *,
        id: int,
        user: User,
        obj_in: ConversationUpdate,
    ) -> Tuple[ConversationOut, str]:
        conv = crud_conv.get_by_user(db, id=id, user_id=user.id)
        if not conv:
            raise BizException(code=40403, message="对话不存在")

        # 先执行通用字段更新（title / is_active，CRUDBase.update 会跳过 None）
        conv = crud_conv.update(db, db_obj=conv, obj_in=obj_in)

        # 手动处理 kb_id：因为 CRUDBase.update 过滤 None，无法表达"取消关联"语义。
        # 使用 model_dump(exclude_unset=True) 判断字段是否被显式传入。
        raw_update = obj_in.model_dump(exclude_unset=True)
        if "kb_id" in raw_update:
            new_kb_id = raw_update["kb_id"]
            old_kb_id = conv.kb_id  # 先保存旧值用于日志（setattr 后 conv.kb_id 就变了）
            # 越权校验：新的 kb_id 必须属于当前用户（或 None 取消关联）
            if new_kb_id is not None:
                kb = db.query(KnowledgeBase).filter(
                    KnowledgeBase.id == new_kb_id,
                    KnowledgeBase.owner_id == user.id,
                    KnowledgeBase.is_active == True,  # noqa: E712
                ).first()
                if not kb:
                    raise BizException(code=40301, message="知识库不存在或无权访问")
            conv.kb_id = new_kb_id
            db.add(conv)
            db.commit()
            db.refresh(conv)
            logger.info(
                "[Chat] 更新对话关联知识库 conv=%s user=%s old_kb=%s new_kb=%s",
                conv.id, user.id, old_kb_id, new_kb_id,
            )
        return ConversationOut.model_validate(conv), "更新成功"

    def delete_conversation(self, db: Session, *, id: int, user: User) -> str:
        conv = crud_conv.get_by_user(db, id=id, user_id=user.id)
        if not conv:
            raise BizException(code=40403, message="对话不存在")
        crud_conv.remove(db, id=id)
        logger.info("[Chat] 删除对话 conv=%s user=%s", id, user.id)
        return "删除成功"

    @staticmethod
    def _build_history(db: Session, conversation_id: int) -> List[Dict[str, str]]:
        msgs = crud_msg.get_multi_by_conversation(db, conversation_id=conversation_id, limit=20)
        history: List[Dict[str, str]] = []
        for m in msgs:
            if m.role in ("user", "assistant"):
                history.append({"role": m.role, "content": m.content})
        return history

    async def chat_stream(
        self,
        db: Session,
        *,
        conversation_id: int,
        user: User,
        obj_in: ChatMessage,
    ) -> AsyncGenerator[str, None]:
        conv = crud_conv.get_by_user(db, id=conversation_id, user_id=user.id)
        if not conv:
            raise BizException(code=40403, message="对话不存在")

        start_ts = time.time()

        # 选 kb 优先级：消息级 override_kb_id > 会话级 conv.kb_id
        # 顶部下拉切换后下一条消息立即用 override，不依赖 DB 持久化完成
        kb_override = getattr(obj_in, "override_kb_id", None)
        if kb_override is not None:
            effective_kb_id = kb_override
            kb_source = "override"
        else:
            effective_kb_id = conv.kb_id
            kb_source = "conv"

        # 越权校验：effective_kb_id 非 None 时必须属于当前 user
        if effective_kb_id is not None:
            kb = db.query(KnowledgeBase).filter(
                KnowledgeBase.id == effective_kb_id,
                KnowledgeBase.owner_id == user.id,
                KnowledgeBase.is_active == True,  # noqa: E712
            ).first()
            if not kb:
                raise BizException(code=40301, message="知识库不存在或无权访问")

        logger.info(
            "[Chat] 对话请求 conv=%s user=%s effective_kb=%s kb_source=%s query_len=%s",
            conv.id, user.id, effective_kb_id, kb_source, len(obj_in.content),
        )

        # 1. 保存用户消息
        user_msg = crud_msg.create(
            db,
            obj_in={
                "conversation_id": conversation_id,
                "role": "user",
                "content": obj_in.content,
            },
        )
        yield f"data: {json.dumps({'type': 'user', 'message': MessageOut.model_validate(user_msg).model_dump(mode='json')}, ensure_ascii=False)}\n\n"

        # 2. 准备历史（不含刚保存的这条 user）
        history = self._build_history(db, conversation_id)
        # 去除刚插入的这条，避免在 LLM 里重复用户问题
        if history and history[-1].get("role") == "user" and history[-1].get("content") == obj_in.content:
            history = history[:-1]

        # 3. RAG 流式生成
        answer_ctx: RagAnswerResult | None = None
        assistant_content_parts: List[str] = []
        tokens: int = 0
        last_ctx: RagAnswerResult | None = None

        try:
            async for delta, tok, ctx in rag_answer_stream(
                db,
                kb_id=effective_kb_id,
                query=obj_in.content,
                history=history,
            ):
                if delta:
                    assistant_content_parts.append(delta)
                    chunk = {
                        "type": "delta",
                        "conversation_id": conversation_id,
                        "delta": delta,
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                if tok is not None:
                    tokens = tok
                last_ctx = ctx
        except Exception as e:
            # 检索/生成阶段失败（如 Embedding 额度耗尽降级、维度不匹配）：
            # 不能让 SSE 连接直接中断（前端只能拿到模糊的网络错误），
            # 显式发 error 事件，并把可读原因拼进助手消息落库。
            err_text = str(e)
            logger.error("[Chat] RAG 生成失败 conv=%s err=%s", conversation_id, err_text)
            yield f"data: {json.dumps({'type': 'error', 'message': err_text}, ensure_ascii=False)}\n\n"
            assistant_content_parts.append(f"\n\n[服务提示] {err_text}")
        answer_ctx = last_ctx

        final_content = "".join(assistant_content_parts)
        latency_ms = int((time.time() - start_ts) * 1000)

        # 4. 保存助手消息与引用来源
        sources_list: List[ChatSource] = []
        sources_json = "[]"
        if answer_ctx and answer_ctx.sources:
            # 过滤保险 3（最后一关）：再次按 score > 0 过滤 + (doc_id, chunk_index) 去重
            dedup: Dict[Tuple[int, int], Dict] = {}
            for s in answer_ctx.sources:
                if not isinstance(s, dict):
                    continue
                sc = float(s.get("score") or 0.0)
                if sc <= 0.0:
                    continue
                key = (int(s.get("document_id") or 0), int(s.get("chunk_index") or 0))
                if key in dedup:
                    if sc > float(dedup[key].get("score") or 0.0):
                        dedup[key] = s
                else:
                    dedup[key] = s
            cleaned_sources = sorted(
                dedup.values(),
                key=lambda x: float(x.get("score") or 0.0),
                reverse=True,
            )
            if cleaned_sources:
                sources_json = json.dumps(cleaned_sources, ensure_ascii=False)
                try:
                    for s in cleaned_sources:
                        sources_list.append(ChatSource(
                            document_id=s.get("document_id"),
                            document_name=s.get("document_name", ""),
                            chunk_index=s.get("chunk_index"),
                            content=s.get("content", ""),
                            score=float(s.get("score", 0.0)),
                        ))
                except Exception as e:
                    logger.warning("[Chat] sources 解析失败 err=%s", str(e))
                    sources_list = []

        assistant_msg = crud_msg.create(
            db,
            obj_in={
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": final_content,
                "sources": sources_json,
                "tokens": tokens or len(final_content),
                "latency_ms": latency_ms,
            },
        )
        # ⚠️ MessageOut.model_validate(assistant_msg) 直接读 ORM sources 字段，拿到的是 DB 里存储的 JSON 字符串，
        # 而非 list。前端只会消费 message.sources，不会用 done.sources 独立字段（契约此前断裂）。
        # 这里显式把 message.sources 覆盖成真实 list，让 message.sources === done.sources === 真实来源数组
        final_msg_out = MessageOut.model_validate(assistant_msg).model_dump(mode="json")
        final_msg_out["sources"] = [s.model_dump() for s in sources_list]
        done_chunk = {
            "type": "done",
            "message": final_msg_out,
            "sources": final_msg_out["sources"],  # 保持独立字段兼容脚本
        }
        yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
        logger.info(
            "[Chat] 对话完成 conv=%s effective_kb=%s kb_source=%s tokens=%s latency_ms=%s sources=%s",
            conv.id, effective_kb_id, kb_source, tokens or len(final_content), latency_ms,
            len(sources_list),
        )
