from fastapi import APIRouter, Depends

from app.api.deps.user import CurrentUser, SessionDep
from app.schemas.common import ApiResponse, ok
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserOut,
    UserPasswordUpdate,
    UserUpdate,
    Token,
)
from app.services import user_service

router = APIRouter()


@router.post("/register", response_model=ApiResponse[Token])
async def register(session: SessionDep, obj_in: UserCreate):
    token, msg = user_service.register(session, obj_in=obj_in)
    return ok(token, msg)


@router.post("/login", response_model=ApiResponse[Token])
async def login(session: SessionDep, obj_in: UserLogin):
    token, msg = user_service.login(session, obj_in=obj_in)
    return ok(token, msg)


@router.get("/me", response_model=ApiResponse[UserOut])
async def get_me(current_user: CurrentUser):
    return ok(user_service.get_profile(current_user))


@router.put("/me", response_model=ApiResponse[UserOut])
async def update_me(session: SessionDep, current_user: CurrentUser, obj_in: UserUpdate):
    data = user_service.update_profile(session, user=current_user, obj_in=obj_in.model_dump(exclude_unset=True))
    return ok(data, "更新成功")


@router.put("/me/password", response_model=ApiResponse[None])
async def change_password(session: SessionDep, current_user: CurrentUser, obj_in: UserPasswordUpdate):
    msg = user_service.update_password(session, user=current_user, obj_in=obj_in)
    return ok(message=msg)
