"""
BIZ 层请求/响应模型
"""
from typing import Optional
from pydantic import BaseModel, Field


# ---------- Feed ----------

class FeedRequest(BaseModel):
    tab: str = Field(..., description="综合 点评 纪要 研报")
    filter: str = Field("全部", description="子筛选项")
    include_ir: bool = Field(False, description="纪要Tab：是否包含投关活动")
    include_wechat: bool = Field(True, description="研报Tab：是否包含公众号")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=50)


class FeedItem(BaseModel):
    id: str
    title: Optional[str] = None
    content: Optional[str] = None
    date: str
    source: Optional[str] = None
    stock_code: list[str] = []
    industry: list[str] = []
    theme: list[str] = []
    institute: Optional[str] = None
    src_url: Optional[str] = None
    tags: list[str] = []               # 保留兼容，当前为空
    companies: list[str] = []          # 保留兼容，当前为空
    author: Optional[str] = None
    pages: Optional[int] = None


class FeedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FeedItem]


# ---------- Search ----------

class BizSearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=100)
    tab: str = Field("综合", description="综合 点评 纪要 研报 公告")
    filter: str = Field("全部")
    sort: str = Field("time", description="time 或 score")
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=100)
    page_min: Optional[int] = None
    page_max: Optional[int] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None


class SearchItem(BaseModel):
    id: str
    title: Optional[str] = None
    content: Optional[str] = None
    date: str
    tab: Optional[str] = None          # 仅综合Tab返回
    source: Optional[str] = None
    institution: Optional[str] = None
    stock_name: Optional[str] = None   # 暂留空，待后续补充
    stock_code: Optional[str] = None
    industry: list[str] = []
    theme: list[str] = []
    src_url: Optional[str] = None
    tags: list[str] = []
    pages: Optional[int] = None
    images: Optional[list[str]] = None


class BizSearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    section_counts: Optional[dict] = None  # 仅综合Tab
    items: list[SearchItem]


# ---------- Article Detail ----------

class ArticleDetail(BaseModel):
    id: str
    title: Optional[str] = None
    content: Optional[str] = None
    date: str
    tab: Optional[str] = None
    source: Optional[str] = None
    institution: Optional[str] = None
    stock_name: Optional[str] = None
    stock_code: Optional[str] = None
    industry: list[str] = []
    theme: list[str] = []
    src_url: Optional[str] = None
    tags: list[str] = []
    pages: Optional[int] = None
    images: Optional[list[str]] = None
