from typing import List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.document import Document


class CRUDDocument(CRUDBase[Document, dict, dict]):
    def get_multi_by_kb(
        self,
        db: Session,
        *,
        kb_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Document], int]:
        query = db.query(Document).filter(Document.kb_id == kb_id)
        total = query.with_entities(func.count(Document.id)).scalar() or 0
        items = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
        return items, total

    def count_by_kb(self, db: Session, *, kb_id: int) -> int:
        return db.query(func.count(Document.id)).filter(Document.kb_id == kb_id).scalar() or 0


crud_doc = CRUDDocument(Document)
