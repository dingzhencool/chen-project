from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.conversation import Conversation, Message
from app.schemas.conversation import ConversationCreate, ConversationUpdate


class CRUDConversation(CRUDBase[Conversation, ConversationCreate, ConversationUpdate]):
    def create_with_user(
        self,
        db: Session,
        *,
        obj_in: ConversationCreate,
        user_id: int,
    ) -> Conversation:
        obj_in_data = obj_in.model_dump()
        db_obj = Conversation(**obj_in_data, user_id=user_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_multi_by_user(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Conversation], int]:
        query = db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.is_active == True,  # noqa: E712
        )
        total = query.with_entities(func.count(Conversation.id)).scalar() or 0
        items = query.order_by(Conversation.updated_at.desc()).offset(skip).limit(limit).all()
        return items, total

    def get_by_user(self, db: Session, *, id: int, user_id: int) -> Optional[Conversation]:
        return (
            db.query(Conversation)
            .filter(Conversation.id == id, Conversation.user_id == user_id)
            .first()
        )


class CRUDMessage(CRUDBase[Message, dict, dict]):
    def get_multi_by_conversation(
        self,
        db: Session,
        *,
        conversation_id: int,
        skip: int = 0,
        limit: int = 200,
    ) -> List[Message]:
        return (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )


crud_conv = CRUDConversation(Conversation)
crud_msg = CRUDMessage(Message)
