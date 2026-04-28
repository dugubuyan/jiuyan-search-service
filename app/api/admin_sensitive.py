"""敏感词管理"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.api.admin_deps import now_utc, mongo_sensitive

router = APIRouter(prefix="/admin", tags=["admin - sensitive"])


class SensitiveWordRequest(BaseModel):
    word:        str
    source_type: Optional[str] = None   # None = 全局，"remark_pai" 等 = 渠道专属


class SensitiveWordUpdateRequest(BaseModel):
    word:         str                    # 原词
    source_type:  Optional[str] = None  # 原 source_type
    new_word:     Optional[str] = None  # 新词，不传则不改
    new_source_type: Optional[str] = None  # 新 source_type，不传则不改


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


@router.put("/sensitive-words", summary="修改敏感词")
def update_sensitive_word(req: SensitiveWordUpdateRequest):
    if req.new_word is None and req.new_source_type is None:
        raise HTTPException(status_code=400, detail="new_word 和 new_source_type 不能同时为空")
    col = mongo_sensitive()
    query: dict = {"word": req.word, "source_type": req.source_type}
    update: dict = {}
    if req.new_word is not None:
        update["word"] = req.new_word.strip()
    if req.new_source_type is not None:
        update["source_type"] = req.new_source_type
    result = col.update_one(query, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="敏感词不存在")
    return {"status": "ok"}


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
