import time
import traceback
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import BizException
from app.crud import crud_doc, crud_kb
from app.models.user import User
from app.schemas.common import page_data, PageData
from app.schemas.knowledge_base import KbCreate, KbOut, KbUpdate
from app.utils.logger import kb_logger


class KbService:
    def create(self, db: Session, *, obj_in: KbCreate, user: User) -> Tuple[KbOut, str]:
        start = time.time()
        kb_logger.info(
            "[KB_CREATE] 开始创建知识库 | user_id=%s username=%s name=%s description=%s is_public=%s",
            user.id, user.username, obj_in.name, obj_in.description, obj_in.is_public,
        )
        try:
            kb = crud_kb.create_with_owner(db, obj_in=obj_in, owner_id=user.id)
            elapsed = (time.time() - start) * 1000
            kb_logger.info(
                "[KB_CREATE] 创建成功 | kb_id=%s owner_id=%s elapsed_ms=%.2f",
                kb.id, user.id, elapsed,
            )
            kb_out = KbOut.model_validate(kb)
            kb_out.doc_count = 0
            return kb_out, "创建成功"
        except BizException:
            raise
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            kb_logger.error(
                "[KB_CREATE] 创建失败 | user_id=%s name=%s elapsed_ms=%.2f error=%s\n%s",
                user.id, obj_in.name, elapsed, str(e), traceback.format_exc(),
            )
            raise

    def get_list(
        self,
        db: Session,
        *,
        user: User,
        page: int,
        page_size: int,
        keyword: Optional[str] = None,
    ) -> PageData[KbOut]:
        kb_logger.debug(
            "[KB_LIST] 查询知识库列表 | user_id=%s page=%s page_size=%s keyword=%s",
            user.id, page, page_size, keyword,
        )
        skip = (page - 1) * page_size
        items, total = crud_kb.get_multi_by_owner(
            db, owner_id=user.id, skip=skip, limit=page_size, keyword=keyword
        )
        kb_out_list: List[KbOut] = []
        for kb in items:
            kb_out = KbOut.model_validate(kb)
            kb_out.doc_count = crud_doc.count_by_kb(db, kb_id=kb.id)
            kb_out_list.append(kb_out)
        result = page_data(kb_out_list, total, page, page_size)
        kb_logger.debug(
            "[KB_LIST] 查询完成 | user_id=%s total=%s", user.id, total,
        )
        return result

    def get_detail(self, db: Session, *, id: int, user: User) -> KbOut:
        kb_logger.debug(
            "[KB_DETAIL] 查询知识库详情 | kb_id=%s user_id=%s", id, user.id,
        )
        kb = crud_kb.get_by_owner(db, id=id, owner_id=user.id)
        if not kb:
            kb_logger.warning(
                "[KB_DETAIL] 知识库不存在 | kb_id=%s user_id=%s", id, user.id,
            )
            raise BizException(code=40401, message="知识库不存在")
        kb_out = KbOut.model_validate(kb)
        kb_out.doc_count = crud_doc.count_by_kb(db, kb_id=kb.id)
        return kb_out

    def update(self, db: Session, *, id: int, user: User, obj_in: KbUpdate) -> Tuple[KbOut, str]:
        start = time.time()
        kb_logger.info(
            "[KB_UPDATE] 开始更新知识库 | kb_id=%s user_id=%s update_fields=%s",
            id, user.id, obj_in.model_dump(exclude_unset=True),
        )
        try:
            kb = crud_kb.get_by_owner(db, id=id, owner_id=user.id)
            if not kb:
                kb_logger.warning(
                    "[KB_UPDATE] 知识库不存在 | kb_id=%s user_id=%s", id, user.id,
                )
                raise BizException(code=40401, message="知识库不存在")
            kb = crud_kb.update(db, db_obj=kb, obj_in=obj_in)
            elapsed = (time.time() - start) * 1000
            kb_logger.info(
                "[KB_UPDATE] 更新成功 | kb_id=%s elapsed_ms=%.2f", id, elapsed,
            )
            kb_out = KbOut.model_validate(kb)
            kb_out.doc_count = crud_doc.count_by_kb(db, kb_id=kb.id)
            return kb_out, "更新成功"
        except BizException:
            raise
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            kb_logger.error(
                "[KB_UPDATE] 更新失败 | kb_id=%s user_id=%s elapsed_ms=%.2f error=%s\n%s",
                id, user.id, elapsed, str(e), traceback.format_exc(),
            )
            raise

    def delete(self, db: Session, *, id: int, user: User) -> str:
        start = time.time()
        kb_logger.warning(
            "[KB_DELETE] 开始删除知识库 | kb_id=%s user_id=%s", id, user.id,
        )
        try:
            kb = crud_kb.get_by_owner(db, id=id, owner_id=user.id)
            if not kb:
                kb_logger.warning(
                    "[KB_DELETE] 知识库不存在 | kb_id=%s user_id=%s", id, user.id,
                )
                raise BizException(code=40401, message="知识库不存在")
            crud_kb.remove(db, id=id)
            elapsed = (time.time() - start) * 1000
            kb_logger.warning(
                "[KB_DELETE] 删除成功 | kb_id=%s elapsed_ms=%.2f", id, elapsed,
            )
            return "删除成功"
        except BizException:
            raise
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            kb_logger.error(
                "[KB_DELETE] 删除失败 | kb_id=%s user_id=%s elapsed_ms=%.2f error=%s\n%s",
                id, user.id, elapsed, str(e), traceback.format_exc(),
            )
            raise
