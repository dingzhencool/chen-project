from typing import Annotated, Optional

import jwt
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BizException
from app.core.security import decode_access_token
from app.crud import crud_user
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False)

SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[Optional[str], Depends(oauth2_scheme)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    if not token:
        raise BizException(code=401, message="Not authenticated", status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise BizException(code=401, message="Invalid token", status_code=status.HTTP_401_UNAUTHORIZED)
    except jwt.PyJWTError:
        raise BizException(code=401, message="Invalid token", status_code=status.HTTP_401_UNAUTHORIZED)
    user = crud_user.get(session, id=int(user_id))
    if not user:
        raise BizException(code=404, message="User not found", status_code=status.HTTP_404_NOT_FOUND)
    if not user.is_active:
        raise BizException(code=403, message="Inactive user", status_code=status.HTTP_403_FORBIDDEN)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
