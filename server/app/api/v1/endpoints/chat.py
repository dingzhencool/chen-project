from typing import List

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps.user import CurrentUser, SessionDep
from app.schemas.common import ApiResponse, PageData, ok
from app.schemas.conversation import (
    ChatMessage,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.services import chat_service

router = APIRouter()


@router.post("/conversations", response_model=ApiResponse[ConversationOut])
async def create_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    obj_in: ConversationCreate,
):
    data, msg = chat_service.create_conversation(session, obj_in=obj_in, user=current_user)
    return ok(data, msg)


@router.get("/conversations", response_model=ApiResponse[PageData[ConversationOut]])
async def list_conversations(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    data = chat_service.get_conversation_list(
        session, user=current_user, page=page, page_size=page_size
    )
    return ok(data)


@router.put("/conversations/{conv_id}", response_model=ApiResponse[ConversationOut])
async def update_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    conv_id: int,
    obj_in: ConversationUpdate,
):
    data, msg = chat_service.update_conversation(
        session, id=conv_id, user=current_user, obj_in=obj_in
    )
    return ok(data, msg)


@router.delete("/conversations/{conv_id}", response_model=ApiResponse[None])
async def delete_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    conv_id: int,
):
    msg = chat_service.delete_conversation(session, id=conv_id, user=current_user)
    return ok(message=msg)


@router.get("/conversations/{conv_id}/messages", response_model=ApiResponse[List[MessageOut]])
async def get_messages(
    session: SessionDep,
    current_user: CurrentUser,
    conv_id: int,
):
    data = chat_service.get_messages(session, conversation_id=conv_id, user=current_user)
    return ok(data)


@router.post("/conversations/{conv_id}/chat")
async def chat(
    session: SessionDep,
    current_user: CurrentUser,
    conv_id: int,
    obj_in: ChatMessage,
):
    return StreamingResponse(
        chat_service.chat_stream(
            session, conversation_id=conv_id, user=current_user, obj_in=obj_in
        ),
        media_type="text/event-stream",
    )
