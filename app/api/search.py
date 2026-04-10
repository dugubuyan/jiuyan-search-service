"""
搜索 API 路由
"""
from fastapi import APIRouter, HTTPException
from app.models.search import SearchRequest, SearchResponse, DocHit
from app.core.es_client import ESClient

router = APIRouter(prefix="/search", tags=["search"])
_es = None


def get_es() -> ESClient:
    global _es
    if _es is None:
        _es = ESClient()
    return _es


@router.post("", response_model=SearchResponse, summary="全文检索")
def search(req: SearchRequest):
    """
    全文检索接口，支持：
    - 关键词全文检索（title 权重 3x，content 权重 1x）
    - doc_type / source / stock_code / industry / institute 精确过滤
    - date_from / date_to 日期范围过滤
    - 分页（page / page_size）
    - 命中片段高亮
    """
    try:
        resp = get_es().search(
            q=req.q,            doc_type=req.doc_type,
            source=req.source,
            stock_code=req.stock_code,
            date_from=req.date_from,
            date_to=req.date_to,
            industry=req.industry,
            institute=req.institute,
            page=req.page,
            page_size=req.page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    total = resp["hits"]["total"]["value"]
    hits  = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        hl  = h.get("highlight", {})
        # 优先取 content 高亮片段，其次 title
        snippet = None
        if hl.get("content"):
            snippet = hl["content"][0]
        elif hl.get("title"):
            snippet = hl["title"][0]

        hits.append(DocHit(
            doc_id=src.get("doc_id", h["_id"]),
            title=src.get("title", ""),
            doc_type=src.get("doc_type", ""),
            source=src.get("source", ""),
            date=src.get("date", ""),
            stock_code=src.get("stock_code", []),
            src_url=src.get("src_url", ""),
            tags=src.get("tags", {}),
            highlight=snippet,
            score=h["_score"] or 0.0,
        ))

    return SearchResponse(
        total=total,
        page=req.page,
        page_size=req.page_size,
        hits=hits,
    )
