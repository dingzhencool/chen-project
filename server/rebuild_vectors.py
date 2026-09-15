# -*- coding: utf-8 -*-
"""向量库一键重建脚本（更换 Embedding 模型后使用）。

为什么需要它：
    Chroma 集合在首次写入时锁定向量维度（collections.dimension），且不同模型即使维度
    相同，向量空间也不兼容。换模型后必须「删除旧集合 → 用磁盘原始文件重新解析/切片/
    向量化」。本脚本自动完成全流程，原始文件和 MySQL 文档记录不受影响，无需重新上传。

用法（在 server/ 目录下执行）：
    # 预览将重建哪些知识库/文档（不执行任何写操作）
    python rebuild_vectors.py --dry-run

    # 重建全部知识库（ready + failed 的文档）
    python rebuild_vectors.py --yes

    # 只重建指定知识库
    python rebuild_vectors.py --kb-id 22 26 --yes

    # 只重建 ready 的文档（不含历史 failed）
    python rebuild_vectors.py --status ready --yes

流程（执行前请先停止后端服务）：
    1. 预检向量模型可用性（embed 探针，打印模型名/维度），不可用立即终止；
    2. 从 MySQL 汇总待重建文档，校验磁盘原始文件是否存在；
    3. 全量重建：直接清空整个 Chroma 目录（连 sqlite 一起全新，杜绝孤儿 HNSW 段）；
       指定 --kb-id：逐库 delete_collection 后重建 client 再写，避免段缓存错乱；
    4. 逐文档复用正式入库链路 process_document_ingest（解析→切片→向量化→写入）；
    5. 逐文档校验 Chroma 分块数 == MySQL chunk_count，并回写 kb.embedding_model；
    6. 输出成功/失败汇总，失败不中断其余文档，可直接重跑（全程幂等）。
"""
import argparse
import os
import shutil
import sys
import time

# 允许从任意 cwd 运行：把本脚本所在目录（server/）加入 sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import func

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.rag.embedding import EmbeddingUnavailableError, embedding_service
from app.rag.pipeline import process_document_ingest
from app.rag.vector_store import get_vector_store
from app.utils.logger import get_logger

logger = get_logger("tools.rebuild")


def _probe_embedding():
    """预检向量模型：不可用直接抛错，避免清完集合才发现无法重建。返回 (provider, dim)。"""
    svc = embedding_service()
    print("正在探测向量模型 ...")
    result = svc.embed(["rebuild probe"])
    dim = len(result.embeddings[0])
    model = settings.EMBEDDING_MODEL
    print(f"  ✓ 模型可用：provider={result.provider} model={model} dim={dim}\n")
    return model, dim


def _collect_plan(db, kb_ids, statuses):
    """汇总重建计划：[(kb, [doc, ...]), ...] 与缺失文件清单。"""
    q = (
        db.query(Document, KnowledgeBase)
        .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
        .filter(Document.status.in_(statuses))
        .order_by(Document.kb_id, Document.id)
    )
    if kb_ids:
        q = q.filter(Document.kb_id.in_(kb_ids))
    rows = q.all()

    grouped = {}
    missing_files = []
    for doc, kb in rows:
        grouped.setdefault(kb, []).append(doc)
        if not doc.file_path or not os.path.exists(doc.file_path):
            missing_files.append(doc)
    return grouped, missing_files


def _print_plan(grouped, missing_files, model, dim):
    total_docs = sum(len(ds) for ds in grouped.values())
    total_chunks = sum(d.chunk_count or 0 for ds in grouped.values() for d in ds)
    print("=" * 68)
    print(f"重建计划（目标模型：{model}，维度：{dim}）")
    print("=" * 68)
    for kb, docs in sorted(grouped.items(), key=lambda x: x[0].id):
        chunks = sum(d.chunk_count or 0 for d in docs)
        print(f"  知识库 #{kb.id}「{kb.name}」  文档 {len(docs)} 个，"
              f"旧分块合计 {chunks}  →  将删除集合 kb_{kb.id} 后整体重建")
    print("-" * 68)
    print(f"  合计：{len(grouped)} 个知识库，{total_docs} 个文档，旧分块 {total_chunks} 个")
    if missing_files:
        print(f"  ⚠ 磁盘原始文件缺失 {len(missing_files)} 个（将跳过，无法重建）：")
        for d in missing_files[:10]:
            print(f"      - doc#{d.id} kb#{d.kb_id} {d.filename}  path={d.file_path}")
        if len(missing_files) > 10:
            print(f"      ... 另有 {len(missing_files) - 10} 个")
    print("=" * 68)


def _confirm(prompt):
    try:
        ans = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("y", "yes", "是")


def main():
    parser = argparse.ArgumentParser(description="向量库一键重建（换 Embedding 模型后使用）")
    parser.add_argument("--kb-id", nargs="*", type=int, default=None,
                        help="只重建指定知识库 ID，多个用空格分隔；不传则重建全部")
    parser.add_argument("--status", default="ready,failed",
                        help="参与重建的文档状态，逗号分隔，默认 ready,failed")
    parser.add_argument("--dry-run", action="store_true", help="只预览计划，不执行写操作")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认")
    args = parser.parse_args()

    statuses = [s.strip() for s in args.status.split(",") if s.strip()]
    invalid = [s for s in statuses if s not in ("pending", "processing", "ready", "failed")]
    if invalid:
        print(f"非法状态：{invalid}，可选 pending/processing/ready/failed")
        return 2

    # 1) 预检向量模型（不清任何数据前先确认可用）
    #    dry-run 不写数据，探针失败时仅标注，仍允许预览计划；正式执行必须通过预检。
    model, dim = settings.EMBEDDING_MODEL, "?"
    try:
        model, dim = _probe_embedding()
    except EmbeddingUnavailableError as e:
        if args.dry_run:
            print(f"[提示] 向量模型当前不可用（dry-run 仍可预览，正式执行会被阻止）：\n  {e}\n")
        else:
            print(f"✗ 向量模型不可用，已终止（未删除任何数据）：\n  {e}")
            return 3
    except Exception as e:
        if args.dry_run:
            print(f"[提示] 向量模型探测异常（dry-run 仍可预览）：{type(e).__name__}: {e}\n")
        else:
            print(f"✗ 向量模型探测异常，已终止（未删除任何数据）：{type(e).__name__}: {e}")
            return 3

    db = SessionLocal()
    try:
        # 2) 汇总计划
        grouped, missing_files = _collect_plan(db, args.kb_id, statuses)
        if not grouped:
            print("没有符合条件的文档，无需重建。")
            return 0
        _print_plan(grouped, missing_files, model, dim)

        if args.dry_run:
            print("\n[dry-run] 预览结束，未执行任何写操作。去掉 --dry-run 正式执行。")
            return 0
        if not args.yes and not _confirm("\n确认删除上述集合并用新模型整体重建？输入 y 继续："):
            print("已取消。")
            return 0

        missing_ids = {d.id for d in missing_files}
        # 注意：import 链路中的 retriever 模块级单例在脚本启动时已初始化 ChromaVectorStore
        # 并打开了 chroma.sqlite3，所以 store 必须在删目录之前拿到（用于先释放句柄）。
        store = get_vector_store()

        # 全量重建（未指定 --kb-id）：删除整个向量库目录，连 chroma.sqlite3 一起全新创建，
        # 彻底避免历史上「同进程 delete_collection + create_collection 同名集合」遗留的
        # 孤儿 HNSW 段（query 时报 "Error creating hnsw segment reader: Nothing found on disk"）。
        # Windows 下必须先 close() 释放本进程持有的 sqlite/段文件句柄，否则 rmtree 报 WinError 32；
        # 同时执行前需确保后端服务已停止。
        if not args.kb_id:
            chroma_path = settings.VECTOR_DB_PATH
            if os.path.isdir(chroma_path):
                print(f"\n▶ 全量重建：清空旧向量库目录 {chroma_path} ...")
                try:
                    if store.name == "chroma":
                        store.close()
                    shutil.rmtree(chroma_path)
                    if store.name == "chroma":
                        store.reset_client()
                    print("  ✓ 旧目录已清空，将以全新 SQLite + 段文件重建")
                except OSError as e:
                    print(f"✗ 清空向量库目录失败（请确认后端服务已停止）：{type(e).__name__}: {e}")
                    return 4

        t0 = time.time()
        succeeded, failed, skipped = [], [], []

        # 3) 按知识库重建
        for kb, docs in sorted(grouped.items(), key=lambda x: x[0].id):
            print(f"\n▶ 知识库 #{kb.id}「{kb.name}」：删除旧集合 kb_{kb.id} ...")
            try:
                store.delete_by_kb(kb.id)
                print(f"  ✓ 旧集合已删除")
            except Exception as e:
                print(f"  ! 删除集合异常（继续尝试重建）：{type(e).__name__}: {e}")

            for doc in docs:
                if doc.id in missing_ids:
                    skipped.append((doc, "磁盘原始文件不存在"))
                    continue
                t1 = time.time()
                try:
                    result = process_document_ingest(db, doc_id=doc.id, kb_id=kb.id)
                    if not result.success:
                        failed.append((doc, result.error or "未知错误"))
                        print(f"  ✗ doc#{doc.id} {doc.filename} 失败：{result.error}")
                        continue
                    # 校验：Chroma 实际分块数 == MySQL chunk_count
                    actual = len(store.get_document_chunks(kb.id, doc.id))
                    if actual != result.chunk_count:
                        failed.append((doc, f"分块数校验不一致：DB={result.chunk_count} Chroma={actual}"))
                        print(f"  ✗ doc#{doc.id} {doc.filename} 分块数不一致 DB={result.chunk_count} "
                              f"Chroma={actual}")
                        continue
                    succeeded.append(doc)
                    print(f"  ✓ doc#{doc.id} {doc.filename}  {actual} 块  "
                          f"({time.time() - t1:.1f}s)")
                except Exception as e:
                    failed.append((doc, f"{type(e).__name__}: {e}"))
                    print(f"  ✗ doc#{doc.id} {doc.filename} 异常：{type(e).__name__}: {e}")

            # 回写知识库记录的嵌入模型标识（便于日后判断是否需要重建）
            try:
                kb.embedding_model = model
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("回写 kb.embedding_model 失败 kb=%s err=%s", kb.id, e)

        # 4) 汇总
        elapsed = time.time() - t0
        print("\n" + "=" * 68)
        print(f"重建完成，耗时 {elapsed:.1f}s")
        print(f"  成功 {len(succeeded)}  失败 {len(failed)}  跳过 {len(skipped)}")
        if failed:
            print("  失败明细：")
            for d, err in failed:
                print(f"    - doc#{d.id} kb#{d.kb_id} {d.filename}：{err[:160]}")
            print("  提示：修复问题后直接重跑本脚本即可（流程幂等，已成功的文档会安全重做）。")
        if skipped:
            print("  跳过明细（原始文件缺失，需重新上传该文档）：")
            for d, err in skipped:
                print(f"    - doc#{d.id} kb#{d.kb_id} {d.filename}")
        print("=" * 68)
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
