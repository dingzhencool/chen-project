from fastapi import APIRouter, Depends

from app.api.v1.endpoints import auth, kb, documents, chat
from app.api.deps.user import get_current_user

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(kb.router, prefix="/knowledge-bases", tags=["KnowledgeBase"], dependencies=[Depends(get_current_user)])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"], dependencies=[Depends(get_current_user)])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"], dependencies=[Depends(get_current_user)])
