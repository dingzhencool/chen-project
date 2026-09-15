from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.deps.user import CurrentUser, SessionDep
from app.schemas.common import ApiResponse, PageData, ok
from app.schemas.document import DocumentOut
from app.services import document_service
from app.utils.logger import doc_logger

router = APIRouter()


@router.post("/upload", response_model=ApiResponse[DocumentOut])
async def upload_document(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    kb_id: int = Form(...),
    file: UploadFile = File(...),
):
    doc_logger.info(
        "[DOC_UPLOAD_API] 请求入口 | kb_id=%s user_id=%s filename=%s remote_addr=%s",
        kb_id,
        current_user.id,
        file.filename,
        request.client.host if request.client else "unknown",
    )
    data, msg = await document_service.upload(
        session, kb_id=kb_id, user=current_user, file=file
    )
    return ok(data, msg)


@router.get("", response_model=ApiResponse[PageData[DocumentOut]])
async def list_documents(
    session: SessionDep,
    current_user: CurrentUser,
    kb_id: int = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    data = document_service.get_list(
        session, kb_id=kb_id, user=current_user, page=page, page_size=page_size
    )
    return ok(data)


@router.delete("/{doc_id}", response_model=ApiResponse[None])
async def delete_document(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    doc_id: int,
):
    doc_logger.warning(
        "[DOC_DELETE_API] 请求入口 | doc_id=%s user_id=%s remote_addr=%s",
        doc_id,
        current_user.id,
        request.client.host if request.client else "unknown",
    )
    msg = document_service.delete(session, id=doc_id, user=current_user)
    return ok(message=msg)


@router.get("/{doc_id}/chunks/{chunk_index}")
async def preview_document_chunk(
    session: SessionDep,
    current_user: CurrentUser,
    doc_id: int,
    chunk_index: int,
):
    """引用验真：取某条引用对应分块的原文 + 前后相邻分块 + PDF 页码。"""
    data = document_service.preview_chunk(
        session, doc_id=doc_id, chunk_index=chunk_index, user=current_user
    )
    return ok(data)


@router.get("/{doc_id}/file")
async def preview_document_file(
    session: SessionDep,
    current_user: CurrentUser,
    doc_id: int,
):
    """带鉴权返回原文件（inline）：PDF/图片浏览器内联打开，前端可用 #page=N 跳页；DOCX 等触发下载。"""
    abs_path, filename, file_type, media_type = document_service.get_file_for_preview(
        session, doc_id=doc_id, user=current_user
    )
    doc_logger.info(
        "[DOC_VERIFY_API] 原文件预览 doc_id=%s type=%s user_id=%s",
        doc_id, file_type, current_user.id,
    )
    return FileResponse(
        abs_path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
    )
