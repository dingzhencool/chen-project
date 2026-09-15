from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    kb_id: Optional[int] = Field(default=None, description="关联知识库 ID")
    title: str = Field(default="新对话", max_length=255, description="对话标题")
    mode: str = Field(default="chat", description="模式：chat/qa")


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255, description="对话标题")
    is_active: Optional[bool] = Field(default=None, description="是否激活")
    kb_id: Optional[int] = Field(default=None, description="关联知识库 ID（传 None 表示取消关联）")


class ConversationOut(BaseModel):
    id: int
    kb_id: Optional[int] = None
    user_id: int
    title: str
    mode: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sources: Optional[Any] = None
    tokens: int = 0
    latency_ms: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, description="用户消息")
    override_kb_id: Optional[int] = Field(
        default=None,
        description="本次请求优先使用的知识库 ID，覆盖 conv.kb_id；用于顶部下拉临时切换立即生效。"
                    "为 None 时继续使用 conv.kb_id。",
    )


class ChatSource(BaseModel):
    document_id: Optional[int] = None
    document_name: Optional[str] = None
    chunk_index: Optional[int] = None
    content: str = ""
    score: float = 0.0
