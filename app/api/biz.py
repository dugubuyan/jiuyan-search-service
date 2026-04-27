"""
BIZ 层路由 — /biz/v1
对接前端业务接口，底层复用 ESClient
"""
import random
import re
import string
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import oss2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from app.core.es_client import ESClient
from app.core.logger import logger
from app.models.biz import (
    FeedItem, FeedResponse,
    SearchItem, BizSearchResponse,
    ArticleDetail,
)
from config import OSS_CONFIG

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
    """将 rec_time (unix timestamp ms 或 s) 转为 YYYY-MM-DD HH:mm（北京时间）"""
    if not rec_time:
        return ""
    ts = int(rec_time)
    # 兼容毫秒和秒
    if ts > 1e11:
        ts = ts // 1000
    tz_cst = timezone(timedelta(hours=8))
    dt = datetime.fromtimestamp(ts, tz=tz_cst)
    return dt.strftime("%Y-%m-%d %H:%M")


# tab -> doc_type 映射
# 综合 Tab 映射到 comprehensive，后续数据入库后生效
TAB_TO_DOC_TYPE = {
    "综合": "comprehensive",
    "点评": "remark",
    "纪要": "meeting",
    "研报": "research",
    "公告": "announcement",
    "互动": "interaction",
}

# filter -> source 映射
FILTER_TO_SOURCE = {
    "机构": "机构",
    "网络": "网络",
    "图片": "图片",
}


def _build_feed_filters(tab: str, filter_val: str, include_ir: bool, include_wechat: bool) -> list:
    filters = []

    if tab in TAB_TO_DOC_TYPE:
        filters.append({"term": {"doc_type": TAB_TO_DOC_TYPE[tab]}})
        # 纪要Tab：不含投关活动时排除 source=投资者关系
        if tab == "纪要" and not include_ir:
            filters.append({"bool": {"must_not": {"term": {"source": "投资者关系"}}}})
        # 研报Tab：不含公众号时排除 tags.format=公众号
        if tab == "研报" and not include_wechat:
            filters.append({"bool": {"must_not": {"term": {"tags.format.keyword": "公众号"}}}})
        # 机构/网络/图片 子筛选
        if filter_val in FILTER_TO_SOURCE:
            filters.append({"term": {"source": FILTER_TO_SOURCE[filter_val]}})

    return filters


def _is_oss_url(url: str | None) -> bool:
    """判断是否是 OSS 内部地址（oss:// 协议）"""
    return bool(url and url.startswith("oss://"))


def _mask_oss_src_url(raw_url: str | None) -> str | None:
    """OSS 内部地址对前端屏蔽（返回 null），普通外链原样返回"""
    return None if _is_oss_url(raw_url) else (raw_url or None)


def _base_feed_item(h: dict, title: str = None, content: str = None) -> FeedItem:
    src = h["_source"]
    tags_obj = src.get("tags") or {}
    return FeedItem(
        id=src.get("doc_id", h["_id"]),
        title=title,
        content=content,
        date=_rec_time_to_str(src.get("rec_time")),
        source=src.get("source"),
        stock_code=src.get("stock_code") or [],
        industry=tags_obj.get("industry") or [],
        theme=tags_obj.get("theme") or [],
        institute=tags_obj.get("institute") or None,
        src_url=_mask_oss_src_url(src.get("src_url")),
        tags=[tags_obj["tag_type"]] if tags_obj.get("tag_type") else [],
        companies=[],
        author=_fake_author(),
        pages=tags_obj.get("page_count") or None,
    )


def _remark_title(title: str, content: str) -> str | None:
    """点评 title 去重：若 title 是正文截断，返回 None"""
    if not title or not content:
        return title or None
    clean = title.rstrip("….").rstrip()
    clean_normalized = re.sub(r'\s+', '', clean)
    content_normalized = re.sub(r'\s+', '', content)
    if clean_normalized and content_normalized.startswith(clean_normalized):
        return None
    return title


def _hit_to_remark(h: dict) -> FeedItem:
    src = h["_source"]
    title = _remark_title(src.get("title", ""), src.get("content", ""))
    return _base_feed_item(h, title=title, content=src.get("content"))


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
    tags_obj = src.get("tags") or {}

    title = src.get("title", "")
    if hl.get("title"):
        title = hl["title"][0]

    content = None
    doc_type = src.get("doc_type", "")
    if doc_type == "remark":
        title = _remark_title(title, src.get("content", ""))
        content = hl["content"][0] if hl.get("content") else src.get("content")
    elif doc_type == "interaction":
        content = hl["content"][0] if hl.get("content") else src.get("content")
    elif hl.get("content"):
        content = hl["content"][0]
    tab_label = None
    if include_tab:
        reverse = {v: k for k, v in TAB_TO_DOC_TYPE.items()}
        tab_label = reverse.get(doc_type)

    stock_codes = src.get("stock_code") or []

    return SearchItem(
        id=src.get("doc_id", h["_id"]),
        title=title,
        content=content,
        date=_rec_time_to_str(src.get("rec_time")),
        tab=tab_label,
        source=src.get("source"),
        institution=tags_obj.get("institute") or None,
        stock_name=None,
        stock_code=stock_codes[0] if stock_codes else None,
        industry=tags_obj.get("industry") or [],
        theme=tags_obj.get("theme") or [],
        src_url=_mask_oss_src_url(src.get("src_url")),
        tags=[tags_obj["tag_type"]] if tags_obj.get("tag_type") else [],
        pages=tags_obj.get("page_count") or None,
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
        logger.error(f"feed error tab={tab}: {e}", exc_info=True)
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
        # source 子筛选：点评/纪要/研报 均支持
        if tab in ("点评", "纪要", "研报") and filter in FILTER_TO_SOURCE:
            extra_filters.append({"term": {"source": FILTER_TO_SOURCE[filter]}})
    else:
        # 未知 tab，直接返回空结果
        return BizSearchResponse(total=0, page=page, page_size=page_size, section_counts=None, items=[])

    # 日期过滤
    if date_start or date_end:
        date_range = {}
        if date_start:
            date_range["gte"] = date_start
        if date_end:
            date_range["lte"] = date_end
        extra_filters.append({"range": {"date": date_range}})

    # 研报页数过滤
    if page_min is not None or page_max is not None:
        page_range = {}
        if page_min is not None:
            page_range["gte"] = page_min
        if page_max is not None:
            page_range["lte"] = page_max
        extra_filters.append({"range": {"tags.page_count": page_range}})

    # 排序
    if sort == "score":
        order = [{"_score": "desc"}, {"rec_time": "desc"}]
    else:
        order = [{"rec_time": "desc"}]

    must = [{"multi_match": {
        "query": q,
        "fields": ["title^3", "content"],
        "type": "best_fields",
        "operator": "and",
    }}]

    # 点评和互动返回全文高亮（number_of_fragments=0），其他返回片段
    if tab in ("点评", "互动"):
        highlight_cfg = {
            "fields": {
                "content": {"number_of_fragments": 0},
                "title":   {"number_of_fragments": 0},
            },
            "pre_tags":  ["<em>"],
            "post_tags": ["</em>"],
        }
    else:
        highlight_cfg = True

    try:
        resp = get_es().search_raw(
            must=must,
            extra_filters=extra_filters,
            sort=order,
            page=page,
            page_size=page_size,
            highlight=highlight_cfg,
        )
    except Exception as e:
        logger.error(f"search error q={q} tab={tab}: {e}", exc_info=True)
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


@router.get("/articles/{id}", response_model=ArticleDetail, summary="文章详情")
def article_detail(id: str):
    doc = get_es().get_by_id(id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文章不存在")

    src = doc["_source"]
    stock_codes = src.get("stock_code") or []
    tags_obj = src.get("tags") or {}
    reverse_tab = {v: k for k, v in TAB_TO_DOC_TYPE.items()}

    return ArticleDetail(
        id=src.get("doc_id", doc["_id"]),
        title=src.get("title"),
        content=src.get("content"),
        date=_rec_time_to_str(src.get("rec_time")),
        tab=reverse_tab.get(src.get("doc_type", "")),
        source=src.get("source"),
        institution=tags_obj.get("institute") or None,
        stock_name=None,
        stock_code=stock_codes[0] if stock_codes else None,
        industry=tags_obj.get("industry") or [],
        theme=tags_obj.get("theme") or [],
        src_url=_mask_oss_src_url(src.get("src_url")),
        tags=[tags_obj["tag_type"]] if tags_obj.get("tag_type") else [],
        pages=tags_obj.get("page_count") or None,
        images=None,
    )


def _parse_oss_key(src_url: str) -> tuple[str, str] | None:
    """
    从 oss:// 地址中解析出 (bucket, key)。
    格式：oss://<bucket>/<key>
    返回 (bucket, key) 元组，无法识别时返回 None。
    """
    if not src_url.startswith("oss://"):
        return None
    rest = src_url[6:]  # 去掉 "oss://"
    slash = rest.find("/")
    if slash == -1:
        return None
    bucket = rest[:slash]
    key = rest[slash + 1:]
    return (bucket, key) if bucket and key else None


@router.get("/articles/{id}/file", summary="文章文件预览/下载")
def article_file(
    id: str,
    mode: str = Query("preview", description="preview（内嵌预览）或 download（强制下载）"),
):
    """
    流式代理 OSS 文件，支持 PDF 预览和下载。
    - mode=preview：Content-Disposition: inline，浏览器直接预览
    - mode=download：Content-Disposition: attachment，强制下载
    - src_url 为普通外链时重定向到外链
    """
    doc = get_es().get_by_id(id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文章不存在")

    src = doc["_source"]
    src_url = src.get("src_url")

    if not src_url:
        raise HTTPException(status_code=404, detail="该文章暂无可下载文件")

    # 普通外链：直接重定向
    if not _is_oss_url(src_url):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=src_url)

    # OSS 内部地址：流式代理
    cfg = OSS_CONFIG
    if not cfg["access_key_id"]:
        raise HTTPException(status_code=503, detail="OSS 未配置，无法获取文件")

    parsed = _parse_oss_key(src_url)
    if not parsed:
        logger.error(f"无法从 src_url 解析 oss bucket/key: {src_url}")
        raise HTTPException(status_code=500, detail="文件路径解析失败")

    bucket_name, oss_key = parsed

    # 从 key 中取文件名，用于 Content-Disposition
    filename = oss_key.split("/")[-1]
    encoded_filename = quote(filename)

    if mode == "download":
        disposition = f"attachment; filename*=UTF-8''{encoded_filename}"
    else:
        disposition = f"inline; filename*=UTF-8''{encoded_filename}"

    # 根据扩展名推断 Content-Type
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type_map = {
        "pdf":  "application/pdf",
        "doc":  "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls":  "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "png":  "image/png",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    try:
        auth = oss2.Auth(cfg["access_key_id"], cfg["access_key_secret"])
        bucket = oss2.Bucket(auth, f"https://{cfg['endpoint']}", bucket_name)
        oss_obj = bucket.get_object(oss_key)
    except oss2.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"OSS 获取文件失败 doc_id={id} key={oss_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取文件失败")

    def iter_content(chunk_size: int = 1024 * 256):  # 256KB chunks
        try:
            for chunk in oss_obj:
                yield chunk
        finally:
            oss_obj.close()

    # TODO: 此处可记录下载次数用于计费
    logger.info(f"file_access doc_id={id} mode={mode} key={oss_key}")

    return StreamingResponse(
        iter_content(),
        media_type=content_type,
        headers={"Content-Disposition": disposition},
    )

