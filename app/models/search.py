"""
请求/响应 Pydantic 模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    q: Optional[str] = Field(None, description="全文检索关键词，为空时按时间倒序分页浏览")
    doc_type: Optional[str] = Field(None, description="文档类型过滤: announcement/remark/meeting/research")
    source: Optional[str] = Field(None, description="来源过滤: 年报/半年报/招股书/投资者关系/机构/网络/研报")
    stock_code: Optional[str] = Field(None, description="股票代码过滤，如 SH600519")
    date_from: Optional[str] = Field(None, description="日期起始 YYYY-MM-DD")
    date_to: Optional[str] = Field(None, description="日期截止 YYYY-MM-DD")
    industry: Optional[str] = Field(None, description="行业标签过滤")
    institute: Optional[str] = Field(None, description="机构名称过滤")
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(10, ge=1, le=100, description="每页条数")


class DocHit(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    source: str
    date: str
    stock_code: list[str]
    src_url: str
    tags: dict
    highlight: Optional[str] = None   # 命中片段高亮
    score: float


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    hits: list[DocHit]
