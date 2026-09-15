from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(128), nullable=False, comment="知识库名称")
    description = Column(String(512), nullable=True, comment="知识库描述")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="所属用户 ID")
    embedding_model = Column(String(128), nullable=True, comment="嵌入模型")
    retrieval_top_k = Column(Integer, default=6, comment="检索 TopK")
    similarity_threshold = Column(String(16), default="0.6", comment="相似度阈值")
    chunk_size = Column(Integer, default=500, comment="分块大小")
    chunk_overlap = Column(Integer, default=50, comment="分块重叠")
    is_public = Column(Boolean, default=False, comment="是否公开")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    owner = relationship("User", backref="knowledge_bases")
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
