"""
管理 API 汇总入口
各功能模块：
  admin_index.py     — ES 索引管理
  admin_docs.py      — 文档审核、发布、下架、reindex
  admin_pipeline.py  — Pipeline 任务监控
  admin_sensitive.py — 敏感词管理
"""
from fastapi import APIRouter
from app.api.admin_index     import router as index_router
from app.api.admin_docs      import router as docs_router
from app.api.admin_pipeline  import router as pipeline_router
from app.api.admin_sensitive import router as sensitive_router

router = APIRouter()
router.include_router(index_router)
router.include_router(docs_router)
router.include_router(pipeline_router)
router.include_router(sensitive_router)
