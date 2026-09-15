from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="用户名")
    email: Optional[EmailStr] = Field(default=None, max_length=128, description="邮箱")
    nickname: Optional[str] = Field(default=None, max_length=64, description="昵称")
    avatar: Optional[str] = Field(default=None, max_length=512, description="头像")


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=64, description="密码")


class UserLogin(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=64, description="昵称")
    email: Optional[EmailStr] = Field(default=None, max_length=128, description="邮箱")
    avatar: Optional[str] = Field(default=None, max_length=512, description="头像")


class UserPasswordUpdate(BaseModel):
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=64, description="新密码")


class UserInDB(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserOut(UserInDB):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
