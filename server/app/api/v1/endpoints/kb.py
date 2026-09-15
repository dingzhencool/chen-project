from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps.user import CurrentUser, SessionDep
from app.schemas.common import ApiResponse, PageData, ok
from app.schemas.knowledge_base import KbCreate, KbOut, KbUpdate
from app.services import kb_service
from app.utils.logger import kb_logger

router = APIRouter()


@router.post("", response_model=ApiResponse[KbOut])
async def create_kb(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    obj_in: KbCreate,
):
    kb_logger.info(
        "[KB_CREATE_API] 请求入口 | user_id=%s remote_addr=%s",
        current_user.id,
        request.client.host if request.client else "unknown",
    )
    data, msg = kb_service.create(session, obj_in=obj_in, user=current_user)
    return ok(data, msg)


@router.get("", response_model=ApiResponse[PageData[KbOut]])
async def list_kb(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    keyword: Optional[str] = Query(default=None),
):
    data = kb_service.get_list(
        session, user=current_user, page=page, page_size=page_size, keyword=keyword
    )
    return ok(data)


@router.get("/{kb_id}", response_model=ApiResponse[KbOut])
async def get_kb(session: SessionDep, current_user: CurrentUser, kb_id: int):
    data = kb_service.get_detail(session, id=kb_id, user=current_user)
    return ok(data)


@router.put("/{kb_id}", response_model=ApiResponse[KbOut])
async def update_kb(
    session: SessionDep,
    current_user: CurrentUser,
    kb_id: int,
    obj_in: KbUpdate,
):
    data, msg = kb_service.update(session, id=kb_id, user=current_user, obj_in=obj_in)
    return ok(data, msg)


@router.delete("/{kb_id}", response_model=ApiResponse[None])
async def delete_kb(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    kb_id: int,
):
    kb_logger.warning(
        "[KB_DELETE_API] 请求入口 | kb_id=%s user_id=%s remote_addr=%s",
        kb_id,
        current_user.id,
        request.client.host if request.client else "unknown",
    )
    msg = kb_service.delete(session, id=kb_id, user=current_user)
    return ok(message=msg)
