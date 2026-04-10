"""
Elasticsearch 客户端封装
搜索时自动过滤 status=published，确保未审核内容不对外可见。
"""
from elasticsearch import Elasticsearch
from config import ES_CONFIG

# Index mapping — 与主工程 es_indexer 保持一致
INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "doc_id":     {"type": "keyword"},
            "title":      {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "content":    {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "doc_type":   {"type": "keyword"},
            "source":     {"type": "keyword"},
            "date":       {"type": "date", "format": "yyyy-MM-dd"},
            "rec_time":   {"type": "long"},
            "stock_code": {"type": "keyword"},
            "src_url":    {"type": "keyword", "index": False},
            "oss_key":    {"type": "keyword", "index": False},
            "status":     {"type": "keyword"},   # published / pending
            "tags": {
                "properties": {
                    "industry":  {"type": "keyword"},
                    "theme":     {"type": "keyword"},
                    "institute": {"type": "keyword"},
                    "tag_type":  {"type": "keyword"},
                }
            },
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 1,
    },
}


def get_es_client() -> Elasticsearch:
    cfg = ES_CONFIG
    kwargs = {"hosts": cfg["hosts"].split(",")}
    if cfg["username"]:
        kwargs["basic_auth"] = (cfg["username"], cfg["password"])
    return Elasticsearch(**kwargs)


class ESClient:
    def __init__(self):
        self.es = get_es_client()
        self.index = ES_CONFIG["index"]

    def ensure_index(self):
        if not self.es.indices.exists(index=self.index):
            self.es.indices.create(index=self.index, body=INDEX_MAPPING)
            print(f"[ES] 创建索引 {self.index}")
        else:
            print(f"[ES] 索引已存在 {self.index}")

    def bulk_index(self, docs: list[dict]):
        """批量写入，doc_id 作为 ES _id 实现幂等 upsert"""
        if not docs:
            return
        actions = []
        for doc in docs:
            actions.append({"index": {"_index": self.index, "_id": doc["doc_id"]}})
            actions.append(doc)
        resp = self.es.bulk(operations=actions, refresh=False)
        errors = [i for i in resp["items"] if "error" in i.get("index", {})]
        if errors:
            print(f"[ES] bulk 写入有 {len(errors)} 条错误")
        return len(docs) - len(errors)

    def search(
        self,
        q: str = None,
        doc_type: str = None,
        source: str = None,
        stock_code: str = None,
        date_from: str = None,
        date_to: str = None,
        industry: str = None,
        institute: str = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        browse_max_pages = ES_CONFIG.get("browse_max_pages", 100)
        has_keyword = bool(q and q.strip())

        # 无关键词时限制最大页数
        if not has_keyword and page > browse_max_pages:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"无关键词浏览最大支持 {browse_max_pages} 页，请缩小筛选范围",
            )

        filters = [{"term": {"status": "published"}}]
        if doc_type:
            filters.append({"term": {"doc_type": doc_type}})
        if source:
            filters.append({"term": {"source": source}})
        if stock_code:
            filters.append({"term": {"stock_code": stock_code}})
        if industry:
            filters.append({"term": {"tags.industry": industry}})
        if institute:
            filters.append({"term": {"tags.institute": institute}})
        if date_from or date_to:
            date_range = {}
            if date_from:
                date_range["gte"] = date_from
            if date_to:
                date_range["lte"] = date_to
            filters.append({"range": {"date": date_range}})

        if has_keyword:
            must = [{"multi_match": {
                "query":  q,
                "fields": ["title^3", "content"],
                "type":   "best_fields",
            }}]
            # 有关键词：相关度优先，rec_time 次要
            sort = [{"_score": "desc"}, {"rec_time": "desc"}]
        else:
            must = [{"match_all": {}}]
            # 无关键词：纯按时间倒序
            sort = [{"rec_time": "desc"}]

        body = {
            "query": {
                "bool": {
                    "must":   must,
                    "filter": filters,
                }
            },
            "sort":  sort,
            "from":  (page - 1) * page_size,
            "size":  page_size,
            "highlight": {
                "fields": {
                    "content": {"fragment_size": 150, "number_of_fragments": 1},
                    "title":   {"number_of_fragments": 0},
                },
                "pre_tags":  ["<em>"],
                "post_tags": ["</em>"],
            },
            "_source": {"excludes": ["content"]},
        }

        return self.es.search(index=self.index, body=body)

    def search_raw(
        self,
        must: list,
        extra_filters: list = None,
        sort: list = None,
        page: int = 1,
        page_size: int = 20,
        highlight: bool = False,
    ) -> dict:
        """供 BIZ 层直接传入 must/filters/sort 的底层搜索"""
        filters = [{"term": {"status": "pending"}}]
        if extra_filters:
            filters.extend(extra_filters)

        body = {
            "query": {
                "bool": {
                    "must": must,
                    "filter": filters,
                }
            },
            "sort": sort or [{"rec_time": "desc"}],
            "from": (page - 1) * page_size,
            "size": page_size,
            "_source": {},
        }

        if highlight:
            body["highlight"] = {
                "fields": {
                    "content": {"fragment_size": 200, "number_of_fragments": 1},
                    "title":   {"number_of_fragments": 0},
                },
                "pre_tags":  ["<em>"],
                "post_tags": ["</em>"],
            }

        return self.es.search(index=self.index, body=body)
