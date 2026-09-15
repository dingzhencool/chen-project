from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True, comment="关联知识库 ID")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户 ID")
    title = Column(String(255), nullable=False, default="新对话", comment="对话标题")
    mode = Column(String(16), default="chat", comment="模式：chat/qa")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at.asc()")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, comment="对话 ID")
    role = Column(String(16), nullable=False, comment="角色：user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    sources = Column(Text, nullable=True, comment="引用来源 JSON")
    tokens = Column(Integer, default=0, comment="消耗 token 数")
    latency_ms = Column(Integer, default=0, comment="响应延迟 ms")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    conversation = relationship("Conversation", back_populates="messages")
