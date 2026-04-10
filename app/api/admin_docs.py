"""文档审核、发布、下架、reindex"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.core.es_client import ESClient
from app.api.admin_deps import now_utc, mongo_col

router = APIRouter(prefix="/admin", tags=["admin - docs"])


class BatchEnableRequest(BaseModel):
    doc_ids:             Optional[list[str]] = None
    doc_type:            Optional[str]       = None
    source:              Optional[str]       = None
    requests_per_second: float               = 500


class BatchReindexRequest(BaseModel):
    doc_ids:             Optional[list[str]] = None
    doc_type:            Optional[str]       = None
    source:              Optional[str]       = None
    requests_per_second: float               = 500


@router.get("/docs/pending", summary="查看待审核文档列表")
def list_pending(
    doc_type:  Optional[str] = Query(None),
    source:    Optional[str] = Query(None),
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(20, ge=1, le=100),
):
    col   = mongo_col()
    query: dict = {"indexes.es.pub_status": "pending", "indexes.es.status": "done"}
    if doc_type:
        query["doc_type"] = doc_type
    if source:
        query["source"] = source
    skip  = (page - 1) * page_size
    total = col.count_documents(query)
    docs  = list(col.find(query, {"content": 0}).sort("created_at", -1).skip(skip).limit(page_size))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"total": total, "page": page, "page_size": page_size, "docs": docs}


@router.post("/docs/{doc_id}/enable", summary="发布文档")
def enable_doc(doc_id: str):
    col = mongo_col()
    es  = ESClient()
    col.update_one({"_id": doc_id}, {"$set": {"indexes.es.pub_status": "published", "updated_at": now_utc()}})
    try:
        es.es.update(index=es.index, id=doc_id, body={"doc": {"status": "published"}})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 更新失败: {e}")
    return {"doc_id": doc_id, "status": "published"}


@router.post("/docs/{doc_id}/disable", summary="下架文档")
def disable_doc(doc_id: str):
    col = mongo_col()
    es  = ESClient()
    col.update_one({"_id": doc_id}, {"$set": {"indexes.es.pub_status": "pending", "updated_at": now_utc()}})
    try:
        es.es.update(index=es.index, id=doc_id, body={"doc": {"status": "pending"}})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 更新失败: {e}")
    return {"doc_id": doc_id, "status": "pending"}


@router.post("/docs/batch/enable", summary="批量发布文档")
def batch_enable(req: BatchEnableRequest):
    col = mongo_col()
    es  = ESClient()
    if req.doc_ids:
        mongo_filter = {"_id": {"$in": req.doc_ids}}
        es_query     = {"terms": {"_id": req.doc_ids}}
    else:
        mongo_filter: dict = {"indexes.es.pub_status": "pending"}
        es_filters = [{"term": {"status": "pending"}}]
        if req.doc_type:
            mongo_filter["doc_type"] = req.doc_type
            es_filters.append({"term": {"doc_type": req.doc_type}})
        if req.source:
            mongo_filter["source"] = req.source
            es_filters.append({"term": {"source": req.source}})
        es_query = {"bool": {"filter": es_filters}}
    result = col.update_many(mongo_filter, {"$set": {"indexes.es.pub_status": "published", "updated_at": now_utc()}})
    try:
        es.es.update_by_query(
            index=es.index,
            body={"query": es_query, "script": {"source": "ctx._source.status = 'published'", "lang": "painless"}},
            requests_per_second=req.requests_per_second, conflicts="proceed",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 批量更新失败: {e}")
    return {"modified": result.modified_count}


@router.post("/docs/{doc_id}/reindex", summary="重置单条文档 ES 索引")
def reindex_doc(doc_id: str):
    col = mongo_col()
    es  = ESClient()
    col.update_one({"_id": doc_id}, {"$set": {
        "indexes.es.status": "pending", "indexes.es.indexed_at": None,
        "indexes.es.error": "", "updated_at": now_utc(),
    }})
    try:
        es.es.update(index=es.index, id=doc_id, body={"doc": {"status": "pending"}})
    except Exception:
        pass
    return {"doc_id": doc_id, "result": "reindex scheduled"}


@router.post("/docs/batch/reindex", summary="批量重置 ES 索引")
def batch_reindex(req: BatchReindexRequest):
    col = mongo_col()
    es  = ESClient()
    if req.doc_ids:
        mongo_filter = {"_id": {"$in": req.doc_ids}}
        es_query     = {"terms": {"_id": req.doc_ids}}
    else:
        mongo_filter = {}
        es_filters: list = []
        if req.doc_type:
            mongo_filter["doc_type"] = req.doc_type
            es_filters.append({"term": {"doc_type": req.doc_type}})
        if req.source:
            mongo_filter["source"] = req.source
            es_filters.append({"term": {"source": req.source}})
        es_query = {"bool": {"filter": es_filters}} if es_filters else {"match_all": {}}
    result = col.update_many(mongo_filter, {"$set": {
        "indexes.es.status": "pending", "indexes.es.indexed_at": None,
        "indexes.es.error": "", "updated_at": now_utc(),
    }})
    try:
        es.es.update_by_query(
            index=es.index,
            body={"query": es_query, "script": {"source": "ctx._source.status = 'pending'", "lang": "painless"}},
            requests_per_second=req.requests_per_second, conflicts="proceed",
        )
    except Exception as e:
        print(f"[admin] batch reindex ES 失败: {e}")
    return {"modified": result.modified_count}
