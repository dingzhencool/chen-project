from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="所属知识库 ID")
    filename = Column(String(255), nullable=False, comment="原始文件名")
    stored_name = Column(String(255), nullable=False, comment="存储文件名")
    file_path = Column(String(512), nullable=False, comment="存储路径")
    file_type = Column(String(32), nullable=True, comment="文件类型：pdf/docx/txt/md")
    file_size = Column(Integer, default=0, comment="文件大小（字节）")
    chunk_count = Column(Integer, default=0, comment="分块数量")
    status = Column(String(16), default="pending", comment="处理状态：pending/processing/ready/failed")
    error_msg = Column(String(512), nullable=True, comment="错误信息")
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="上传用户 ID")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
