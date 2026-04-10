"""ES 索引管理"""
from fastapi import APIRouter
from app.core.es_client import ESClient

router = APIRouter(prefix="/admin", tags=["admin - index"])


@router.get("/index/stats", summary="ES 索引统计")
def index_stats():
    es = ESClient()
    try:
        stats = es.es.indices.stats(index=es.index)
        total = stats["_all"]["primaries"]["docs"]["count"]
        size  = stats["_all"]["primaries"]["store"]["size_in_bytes"]
        return {"index": es.index, "doc_count": total, "size_bytes": size}
    except Exception as e:
        return {"error": str(e)}


@router.post("/index/ensure", summary="确保 ES 索引存在（含 mapping）")
def ensure_index():
    ESClient().ensure_index()
    return {"message": "索引已就绪"}
