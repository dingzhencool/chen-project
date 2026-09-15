from app.services.user_service import UserService
from app.services.kb_service import KbService
from app.services.document_service import DocumentService
from app.services.chat_service import ChatService

user_service = UserService()
kb_service = KbService()
document_service = DocumentService()
chat_service = ChatService()

__all__ = ["user_service", "kb_service", "document_service", "chat_service"]
