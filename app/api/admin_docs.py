"""文档审核、发布、下架、reindex、编辑"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.core.es_client import ESClient
from app.api.admin_deps import mongo_col

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


class DocEditRequest(BaseModel):
    title:   Optional[str] = None
    content: Optional[str] = None


# pub_status（ES status 字段）-> 前端展示值映射
_PUB_STATUS_MAP = {"published": "enabled", "pending": "pending"}
_PUB_STATUS_REVERSE = {"enabled": "published", "disabled": "pending", "pending": "pending"}


@router.get("/docs", summary="全量文档列表")
def list_docs(
    doc_type:   Optional[str] = Query(None),
    source:     Optional[str] = Query(None),
    pub_status: Optional[str] = Query(None, description="pending/enabled/disabled，不传返回全部"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(20, ge=1, le=100),
):
    es = ESClient()
    filters = []
    if doc_type:
        filters.append({"term": {"doc_type": doc_type}})
    if source:
        filters.append({"term": {"source": source}})
    if pub_status:
        es_status = _PUB_STATUS_REVERSE.get(pub_status, pub_status)
        filters.append({"term": {"status": es_status}})

    query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
    body = {
        "query": query,
        "sort": [{"rec_time": "desc"}],
        "from": (page - 1) * page_size,
        "size": page_size,
        "_source": {"excludes": ["content"]},
    }
    resp  = es.es.search(index=es.index, body=body)
    total = resp["hits"]["total"]["value"]
    docs  = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        docs.append({
            "_id": h["_id"],
            **src,
            "indexes": {"es": {"pub_status": _PUB_STATUS_MAP.get(src.get("status", ""), src.get("status", ""))}},
        })
    return {"total": total, "page": page, "page_size": page_size, "docs": docs}


@router.get("/docs/pending", summary="待审核文档列表（兼容旧接口）")
def list_pending(
    doc_type:  Optional[str] = Query(None),
    source:    Optional[str] = Query(None),
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(20, ge=1, le=100),
):
    return list_docs(doc_type=doc_type, source=source, pub_status="pending", page=page, page_size=page_size)


@router.post("/docs/{doc_id}/enable", summary="发布文档")
def enable_doc(doc_id: str):
    es = ESClient()
    try:
        es.es.update(index=es.index, id=doc_id, body={"doc": {"status": "published"}})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 更新失败: {e}")
    return {"status": "ok"}


@router.post("/docs/{doc_id}/disable", summary="下架文档")
def disable_doc(doc_id: str):
    es = ESClient()
    try:
        es.es.update(index=es.index, id=doc_id, body={"doc": {"status": "pending"}})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 更新失败: {e}")
    return {"status": "ok"}


@router.put("/docs/{doc_id}", summary="编辑文章 title/content")
def edit_doc(doc_id: str, req: DocEditRequest):
    if not req.title and not req.content:
        raise HTTPException(status_code=400, detail="title 和 content 不能同时为空")
    es  = ESClient()
    doc = {}
    if req.title is not None:
        doc["title"] = req.title
    if req.content is not None:
        doc["content"] = req.content
    try:
        es.es.update(index=es.index, id=doc_id, body={"doc": doc})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 更新失败: {e}")
    return {"status": "ok"}


@router.post("/docs/batch/enable", summary="批量发布文档")
def batch_enable(req: BatchEnableRequest):
    es = ESClient()
    if req.doc_ids:
        es_query = {"terms": {"_id": req.doc_ids}}
    else:
        es_filters = [{"term": {"status": "pending"}}]
        if req.doc_type:
            es_filters.append({"term": {"doc_type": req.doc_type}})
        if req.source:
            es_filters.append({"term": {"source": req.source}})
        es_query = {"bool": {"filter": es_filters}}
    try:
        resp = es.es.update_by_query(
            index=es.index,
            body={"query": es_query, "script": {"source": "ctx._source.status = 'published'", "lang": "painless"}},
            requests_per_second=req.requests_per_second, conflicts="proceed",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES 批量更新失败: {e}")
    return {"updated": resp.get("updated", 0)}


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
