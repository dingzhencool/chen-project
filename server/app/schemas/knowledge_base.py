from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KbBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="知识库名称")
    description: Optional[str] = Field(default=None, max_length=512, description="知识库描述")
    embedding_model: Optional[str] = Field(default=None, max_length=128, description="嵌入模型")
    retrieval_top_k: Optional[int] = Field(default=6, ge=1, le=50, description="检索 TopK")
    similarity_threshold: Optional[float] = Field(default=0.6, ge=0, le=1, description="相似度阈值")
    chunk_size: Optional[int] = Field(default=500, ge=100, le=2000, description="分块大小")
    chunk_overlap: Optional[int] = Field(default=50, ge=0, le=500, description="分块重叠")
    is_public: Optional[bool] = Field(default=False, description="是否公开")


class KbCreate(KbBase):
    pass


class KbUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128, description="知识库名称")
    description: Optional[str] = Field(default=None, max_length=512, description="知识库描述")
    embedding_model: Optional[str] = Field(default=None, max_length=128, description="嵌入模型")
    retrieval_top_k: Optional[int] = Field(default=None, ge=1, le=50, description="检索 TopK")
    similarity_threshold: Optional[float] = Field(default=None, ge=0, le=1, description="相似度阈值")
    chunk_size: Optional[int] = Field(default=None, ge=100, le=2000, description="分块大小")
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=500, description="分块重叠")
    is_public: Optional[bool] = Field(default=None, description="是否公开")
    is_active: Optional[bool] = Field(default=None, description="是否启用")


class KbInDB(KbBase):
    id: int
    owner_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KbOut(KbInDB):
    doc_count: Optional[int] = Field(default=0, description="文档数量")
