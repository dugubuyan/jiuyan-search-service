"""Pipeline 任务监控"""
import time
from typing import Optional
from fastapi import APIRouter, Query
from app.api.admin_deps import mongo_tasks

router = APIRouter(prefix="/admin", tags=["admin - pipeline"])


@router.get("/pipeline/tasks", summary="查看 pipeline 任务列表")
def pipeline_tasks(
    source_type: Optional[str] = Query(None),
    status:      Optional[str] = Query(None, description="pending/running/done/failed"),
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(50, ge=1, le=200),
):
    col   = mongo_tasks()
    query = {}
    if source_type:
        query["source_type"] = source_type
    if status:
        query["status"] = status
    skip  = (page - 1) * page_size
    total = col.count_documents(query)
    tasks = list(col.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size, "tasks": tasks}


@router.get("/pipeline/stats", summary="Pipeline 任务统计")
def pipeline_stats(source_type: Optional[str] = Query(None)):
    col   = mongo_tasks()
    match = {"source_type": source_type} if source_type else {}
    agg = [
        {"$match": match},
        {"$group": {"_id": {"source_type": "$source_type", "stage": "$stage", "status": "$status"},
                    "count": {"$sum": 1}}},
        {"$sort": {"_id.source_type": 1, "_id.stage": 1}},
    ]
    result: dict = {}
    for r in col.aggregate(agg):
        key = f"{r['_id']['source_type']}.{r['_id']['stage']}.{r['_id']['status']}"
        result[key] = r["count"]
    return result


@router.get("/pipeline/cursors", summary="游标 source 当前游标状态")
def pipeline_cursors():
    col     = mongo_tasks()
    sources = ["remark_pai", "remark_zsxq", "meeting_pai"]
    result  = {}
    for src in sources:
        doc = col.find_one({"_id": f"{src}:__cursor__"}, {"max_id": 1, "updated_at": 1})
        result[src] = {"max_id": doc.get("max_id"), "updated_at": doc.get("updated_at")} if doc else {"max_id": None, "updated_at": None}
    return result


@router.get("/pipeline/daily", summary="按日期 + source 汇总任务处理情况")
def pipeline_daily(
    source_type: Optional[str] = Query(None),
    days:        int           = Query(30, ge=1, le=365),
):
    col   = mongo_tasks()
    match: dict = {
        "task_key": {"$not": {"$regex": "^cursor:"}},
        "_id":      {"$not": {"$regex": "__cursor__"}},
    }
    if source_type:
        match["source_type"] = source_type
    agg = [
        {"$match": match},
        {"$group": {
            "_id": {"source_type": "$source_type", "task_key": "$task_key"},
            "done":    {"$sum": {"$cond": [{"$eq": ["$status", "done"]},    1, 0]}},
            "failed":  {"$sum": {"$cond": [{"$eq": ["$status", "failed"]},  1, 0]}},
            "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
            "running": {"$sum": {"$cond": [{"$eq": ["$status", "running"]}, 1, 0]}},
        }},
        {"$sort": {"_id.task_key": -1, "_id.source_type": 1}},
        {"$limit": days * 10},
    ]
    by_date: dict = {}
    for r in col.aggregate(agg):
        d   = r["_id"]["task_key"]
        src = r["_id"]["source_type"]
        if d not in by_date:
            by_date[d] = {}
        by_date[d][src] = {k: r[k] for k in ("done", "failed", "pending", "running")}
    return {"days": len(by_date), "data": by_date}


@router.post("/pipeline/reset-failed", summary="将 failed 任务重置为 pending")
def pipeline_reset_failed(
    source_type: Optional[str] = Query(None),
    stage:       Optional[str] = Query(None),
):
    col   = mongo_tasks()
    query: dict = {"status": "failed"}
    if source_type:
        query["source_type"] = source_type
    if stage:
        query["stage"] = stage
    result = col.update_many(query, {"$set": {"status": "pending", "updated_at": int(time.time())}})
    return {"reset": result.modified_count}
