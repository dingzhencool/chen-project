from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KbCreate, KbUpdate


class CRUDKnowledgeBase(CRUDBase[KnowledgeBase, KbCreate, KbUpdate]):
    def create_with_owner(
        self,
        db: Session,
        *,
        obj_in: KbCreate,
        owner_id: int,
    ) -> KnowledgeBase:
        obj_in_data = obj_in.model_dump()
        db_obj = KnowledgeBase(**obj_in_data, owner_id=owner_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_multi_by_owner(
        self,
        db: Session,
        *,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
        keyword: Optional[str] = None,
    ) -> Tuple[List[KnowledgeBase], int]:
        query = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == owner_id)
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    KnowledgeBase.name.like(like),
                    KnowledgeBase.description.like(like),
                )
            )
        total = query.with_entities(func.count(KnowledgeBase.id)).scalar() or 0
        items = query.order_by(KnowledgeBase.created_at.desc()).offset(skip).limit(limit).all()
        return items, total

    def get_by_owner(self, db: Session, *, id: int, owner_id: int) -> Optional[KnowledgeBase]:
        return (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.id == id, KnowledgeBase.owner_id == owner_id)
            .first()
        )


crud_kb = CRUDKnowledgeBase(KnowledgeBase)
