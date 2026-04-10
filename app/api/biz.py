"""
BIZ 层路由 — /biz/v1
对接前端业务接口，底层复用 ESClient
"""
import random
import string
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.core.es_client import ESClient
from app.models.biz import (
    FeedItem, FeedResponse,
    SearchItem, BizSearchResponse,
)

router = APIRouter(prefix="/biz/v1", tags=["biz"])

_es = None


def get_es() -> ESClient:
    global _es
    if _es is None:
        _es = ESClient()
    return _es


# ---------- 工具函数 ----------

def _fake_author() -> str:
    """临时：随机生成 6~10 位英文字符作为脱敏作者名，后续替换为真实字段"""
    length = random.randint(6, 10)
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _rec_time_to_str(rec_time) -> str:
    """将 rec_time (unix timestamp ms 或 s) 转为 YYYY-MM-DD HH:mm"""
    if not rec_time:
        return ""
    ts = int(rec_time)
    # 兼容毫秒和秒
    if ts > 1e11:
        ts = ts // 1000
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


# tab -> doc_type 映射（综合是独立 doc_type，ES 暂无数据）
TAB_TO_DOC_TYPE = {
    "综合": "comprehensive",
    "点评": "remark",
    "纪要": "meeting",
    "研报": "research",
    "公告": "announcement",
}

# filter -> source 映射（机构/网络）
FILTER_TO_SOURCE = {
    "机构": "机构",
    "网络": "网络",
}


def _build_feed_filters(tab: str, filter_val: str, include_ir: bool, include_wechat: bool) -> list:
    filters = []

    if tab in TAB_TO_DOC_TYPE:
        filters.append({"term": {"doc_type": TAB_TO_DOC_TYPE[tab]}})
        # 纪要Tab：不含投关活动时排除 source=投资者关系
        if tab == "纪要" and not include_ir:
            filters.append({"bool": {"must_not": {"term": {"source": "投资者关系"}}}})
        # 研报Tab：不含公众号时排除
        if tab == "研报" and not include_wechat:
            filters.append({"bool": {"must_not": {"term": {"source": "公众号"}}}})
        # 机构/网络 子筛选
        if filter_val in FILTER_TO_SOURCE:
            filters.append({"term": {"source": FILTER_TO_SOURCE[filter_val]}})

    return filters


def _base_feed_item(h: dict, title: str = None, content: str = None) -> FeedItem:
    src = h["_source"]
    return FeedItem(
        id=src.get("doc_id", h["_id"]),
        title=title,
        content=content,
        date=_rec_time_to_str(src.get("rec_time")),
        tags=[],
        companies=[],
        author=_fake_author(),
        pages=src.get("pages"),
    )


def _hit_to_remark(h: dict) -> FeedItem:
    """点评：不传 title，返回全文"""
    src = h["_source"]
    return _base_feed_item(h, title=None, content=src.get("content"))


def _hit_to_default(h: dict) -> FeedItem:
    src = h["_source"]
    hl = h.get("highlight", {})
    content = hl.get("content", [None])[0] or (src.get("content") or "")[:200]
    return _base_feed_item(h, title=src.get("title", ""), content=content)


HIT_CONVERTER = {
    "点评": _hit_to_remark,
}


def _hit_to_feed_item(h: dict, tab: str = "") -> FeedItem:
    return HIT_CONVERTER.get(tab, _hit_to_default)(h)


def _hit_to_search_item(h: dict, include_tab: bool = False) -> SearchItem:
    src = h["_source"]
    hl = h.get("highlight", {})

    title = src.get("title", "")
    if hl.get("title"):
        title = hl["title"][0]

    content = None
    if hl.get("content"):
        content = hl["content"][0]

    doc_type = src.get("doc_type", "")
    tab_label = None
    if include_tab:
        reverse = {v: k for k, v in TAB_TO_DOC_TYPE.items()}
        tab_label = reverse.get(doc_type)

    stock_codes = src.get("stock_code", [])

    return SearchItem(
        id=src.get("doc_id", h["_id"]),
        title=title,
        content=content,
        date=_rec_time_to_str(src.get("rec_time")),
        tab=tab_label,
        institution=src.get("tags", {}).get("institute"),
        stock_name=None,   # 暂无，后续补充
        stock_code=stock_codes[0] if stock_codes else None,
        tags=[],           # 暂不实现
        pages=src.get("pages"),
        images=None,
    )


# ---------- 接口 ----------

@router.get("/feed", response_model=FeedResponse, summary="首页信息流")
def feed(
    tab: str = Query("综合"),
    filter: str = Query("全部"),
    include_ir: bool = Query(False),
    include_wechat: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    extra_filters = _build_feed_filters(tab, filter, include_ir, include_wechat)
    try:
        resp = get_es().search_raw(
            must=[{"match_all": {}}],
            extra_filters=extra_filters,
            sort=[{"rec_time": "desc"}],
            page=page,
            page_size=page_size,
            highlight=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    total = resp["hits"]["total"]["value"]
    items = [_hit_to_feed_item(h, tab=tab) for h in resp["hits"]["hits"]]
    return FeedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/search", response_model=BizSearchResponse, summary="全文检索")
def biz_search(
    q: str = Query(..., min_length=1, max_length=100),
    tab: str = Query("综合"),
    filter: str = Query("全部"),
    sort: str = Query("time"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    page_min: Optional[int] = Query(None),
    page_max: Optional[int] = Query(None),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
):
    is_all_tab = False  # 综合是独立 doc_type，不做聚合

    # 构建 doc_type 过滤
    extra_filters = []
    if tab in TAB_TO_DOC_TYPE:
        extra_filters.append({"term": {"doc_type": TAB_TO_DOC_TYPE[tab]}})
        if tab == "纪要" and filter in FILTER_TO_SOURCE:
            extra_filters.append({"term": {"source": FILTER_TO_SOURCE[filter]}})
        if tab == "研报" and filter in FILTER_TO_SOURCE:
            extra_filters.append({"term": {"source": FILTER_TO_SOURCE[filter]}})

    # 日期过滤
    if date_start or date_end:
        date_range = {}
        if date_start:
            date_range["gte"] = date_start
        if date_end:
            date_range["lte"] = date_end
        extra_filters.append({"range": {"date": date_range}})

    # 排序
    if sort == "score":
        order = [{"_score": "desc"}, {"rec_time": "desc"}]
    else:
        order = [{"rec_time": "desc"}]

    must = [{"multi_match": {
        "query": q,
        "fields": ["title^3", "content"],
        "type": "best_fields",
    }}]

    try:
        resp = get_es().search_raw(
            must=must,
            extra_filters=extra_filters,
            sort=order,
            page=page,
            page_size=page_size,
            highlight=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    total = resp["hits"]["total"]["value"]
    items = [_hit_to_search_item(h, include_tab=False) for h in resp["hits"]["hits"]]

    return BizSearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        section_counts=None,
        items=items,
    )

