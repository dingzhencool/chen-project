from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    kb_id: int
    filename: str
    stored_name: str
    file_path: str
    file_type: Optional[str] = None
    file_size: int = 0
    chunk_count: int = 0
    status: str = "pending"
    error_msg: Optional[str] = None
    uploaded_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentProcessStatus(BaseModel):
    document_id: int
    status: str
    progress: int = 0
    error_msg: Optional[str] = None
