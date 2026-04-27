"""公众号-券商映射管理"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from bson import ObjectId
from app.api.admin_deps import mongo_col as _mongo_col, now_utc
from app.models.broker import BrokerAccountCreate, BrokerAccountUpdate, BrokerAccountItem
from config import MONGODB_CONFIG
from pymongo import MongoClient, ASCENDING

router = APIRouter(prefix="/admin/broker-accounts", tags=["admin - broker accounts"])


def _col():
    cfg = MONGODB_CONFIG
    col = MongoClient(cfg["uri"])[cfg["db_name"]]["broker_accounts"]
    col.create_index([("account_name", ASCENDING)], unique=True, background=True)
    return col


def _fmt(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "account_name": doc["account_name"],
        "broker_name": doc["broker_name"],
        "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at", "").isoformat() if doc.get("updated_at") else None,
    }


@router.get("", summary="公众号-券商映射列表")
def list_broker_accounts(
    broker_name: Optional[str] = Query(None, description="按券商名过滤"),
    account_name: Optional[str] = Query(None, description="按公众号名模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    col = _col()
    query = {}
    if broker_name:
        query["broker_name"] = broker_name
    if account_name:
        query["account_name"] = {"$regex": account_name, "$options": "i"}

    total = col.count_documents(query)
    docs = col.find(query).sort("broker_name", ASCENDING).skip((page - 1) * page_size).limit(page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_fmt(d) for d in docs],
    }


@router.get("/brokers", summary="获取所有券商名称列表")
def list_brokers():
    col = _col()
    brokers = col.distinct("broker_name")
    return {"brokers": sorted(brokers)}


@router.get("/lookup", summary="按公众号名查询所属券商")
def lookup_broker(account_name: str = Query(..., description="公众号名称")):
    col = _col()
    doc = col.find_one({"account_name": account_name})
    if not doc:
        raise HTTPException(status_code=404, detail="未找到该公众号")
    return {"account_name": doc["account_name"], "broker_name": doc["broker_name"]}


@router.post("", summary="新增公众号-券商映射", status_code=201)
def create_broker_account(req: BrokerAccountCreate):
    col = _col()
    now = now_utc()
    try:
        result = col.insert_one({
            "account_name": req.account_name,
            "broker_name": req.broker_name,
            "created_at": now,
            "updated_at": now,
        })
    except Exception:
        raise HTTPException(status_code=409, detail=f"公众号 '{req.account_name}' 已存在")
    doc = col.find_one({"_id": result.inserted_id})
    return _fmt(doc)


@router.put("/{doc_id}", summary="修改公众号-券商映射")
def update_broker_account(doc_id: str, req: BrokerAccountUpdate):
    if not req.account_name and not req.broker_name:
        raise HTTPException(status_code=400, detail="account_name 和 broker_name 不能同时为空")
    col = _col()
    try:
        oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 id")

    update = {k: v for k, v in {"account_name": req.account_name, "broker_name": req.broker_name}.items() if v is not None}
    update["updated_at"] = now_utc()
    result = col.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"status": "ok"}


@router.delete("/{doc_id}", summary="删除公众号-券商映射")
def delete_broker_account(doc_id: str):
    col = _col()
    try:
        oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 id")
    result = col.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"status": "ok"}
