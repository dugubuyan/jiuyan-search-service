"""敏感词管理"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.api.admin_deps import now_utc, mongo_sensitive

router = APIRouter(prefix="/admin", tags=["admin - sensitive"])


class SensitiveWordRequest(BaseModel):
    word:        str
    source_type: Optional[str] = None   # None = 全局，"remark_pai" 等 = 渠道专属


@router.get("/sensitive-words", summary="查看敏感词列表")
def list_sensitive_words(
    source_type: Optional[str] = Query(None, description="渠道过滤，为空返回全部"),
):
    col   = mongo_sensitive()
    query = {} if source_type is None else {"$or": [
        {"source_type": None},
        {"source_type": {"$exists": False}},
        {"source_type": source_type},
    ]}
    words = list(col.find(query, {"_id": 0, "word": 1, "source_type": 1, "created_at": 1}))
    return {"total": len(words), "words": words}


@router.post("/sensitive-words", summary="添加敏感词")
def add_sensitive_word(req: SensitiveWordRequest):
    col = mongo_sensitive()
    col.create_index([("word", 1), ("source_type", 1)], unique=True, name="word_source")
    try:
        col.insert_one({"word": req.word.strip(), "source_type": req.source_type, "created_at": now_utc()})
    except Exception:
        raise HTTPException(status_code=409, detail="敏感词已存在")
    return {"word": req.word, "source_type": req.source_type, "result": "added"}


@router.delete("/sensitive-words", summary="删除敏感词")
def delete_sensitive_word(req: SensitiveWordRequest):
    col   = mongo_sensitive()
    query: dict = {"word": req.word}
    if req.source_type is not None:
        query["source_type"] = req.source_type
    count = col.delete_many(query).deleted_count
    if count == 0:
        raise HTTPException(status_code=404, detail="敏感词不存在")
    return {"word": req.word, "deleted": count}
