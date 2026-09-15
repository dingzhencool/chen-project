from datetime import timedelta
from typing import Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizException
from app.core.security import create_access_token, verify_password
from app.crud import crud_user
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, Token, UserOut, UserPasswordUpdate


class UserService:
    def register(self, db: Session, *, obj_in: UserCreate) -> Tuple[Token, str]:
        if crud_user.get_by_username(db, username=obj_in.username):
            raise BizException(code=40001, message="用户名已存在")
        if obj_in.email and crud_user.get_by_email(db, email=obj_in.email):
            raise BizException(code=40002, message="邮箱已被注册")
        user = crud_user.create(db, obj_in=obj_in)
        access_token = create_access_token(
            subject=str(user.id),
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        token = Token(access_token=access_token, token_type="bearer", user=UserOut.model_validate(user))
        return token, "注册成功"

    def login(self, db: Session, *, obj_in: UserLogin) -> Tuple[Token, str]:
        user = crud_user.authenticate(db, username=obj_in.username, password=obj_in.password)
        if not user:
            raise BizException(code=40003, message="用户名或密码错误")
        if not user.is_active:
            raise BizException(code=40301, message="账号已被禁用")
        access_token = create_access_token(
            subject=str(user.id),
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        token = Token(access_token=access_token, token_type="bearer", user=UserOut.model_validate(user))
        return token, "登录成功"

    def get_profile(self, user: User) -> UserOut:
        return UserOut.model_validate(user)

    def update_profile(self, db: Session, *, user: User, obj_in: dict) -> UserOut:
        user = crud_user.update(db, db_obj=user, obj_in=obj_in)
        return UserOut.model_validate(user)

    def update_password(self, db: Session, *, user: User, obj_in: UserPasswordUpdate) -> str:
        if not verify_password(obj_in.old_password, user.password_hash):
            raise BizException(code=40004, message="旧密码错误")
        crud_user.update_password(db, db_obj=user, new_password=obj_in.new_password)
        return "密码修改成功"
