#!/usr/bin/env python
"""
批量发布指定 doc_type 的 pending 文档。

用法：
    python scripts/publish_by_doctype.py --doc_type research
    python scripts/publish_by_doctype.py --doc_type remark --source 机构
    python scripts/publish_by_doctype.py --doc_type announcement --dry_run
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.es_client import ESClient


def main():
    parser = argparse.ArgumentParser(description="批量发布 pending 文档")
    parser.add_argument("--doc_type", required=True, help="文档类型，如 research / remark / meeting / announcement / interaction")
    parser.add_argument("--source", default=None, help="来源渠道过滤（可选），如 机构 / 网络")
    parser.add_argument("--dry_run", action="store_true", help="只统计数量，不实际发布")
    parser.add_argument("--rps", type=float, default=500, help="requests_per_second，默认 500")
    args = parser.parse_args()

    es = ESClient()

    # 构建查询
    filters = [
        {"term": {"status": "pending"}},
        {"term": {"doc_type": args.doc_type}},
    ]
    if args.source:
        filters.append({"term": {"source": args.source}})
    query = {"bool": {"filter": filters}}

    # 先统计数量
    count_resp = es.es.count(index=es.index, body={"query": query})
    total = count_resp["count"]
    print(f"doc_type={args.doc_type} source={args.source or '全部'} 待发布数量: {total}")

    if total == 0:
        print("无需操作。")
        return

    if args.dry_run:
        print("dry_run 模式，不执行发布。")
        return

    confirm = input(f"确认发布 {total} 条文档？(y/N) ").strip().lower()
    if confirm != "y":
        print("已取消。")
        return

    # 阿里云 Serverless ES 不支持 Painless 脚本，改用 scroll + bulk update
    updated = 0
    page_size = 500
    resp = es.es.search(
        index=es.index,
        body={"query": query, "_source": False, "size": page_size},
        scroll="2m",
    )
    scroll_id = resp["_scroll_id"]

    while True:
        hits = resp["hits"]["hits"]
        if not hits:
            break

        actions = []
        for h in hits:
            actions.append({"update": {"_index": es.index, "_id": h["_id"]}})
            actions.append({"doc": {"status": "published"}})

        bulk_resp = es.es.bulk(operations=actions, refresh=False)
        batch_updated = sum(1 for item in bulk_resp["items"] if item.get("update", {}).get("result") in ("updated", "noop"))
        updated += batch_updated
        print(f"  已处理 {updated}/{total}...")

        resp = es.es.scroll(scroll_id=scroll_id, scroll="2m")

    try:
        es.es.clear_scroll(scroll_id=scroll_id)
    except Exception:
        pass

    print(f"发布完成，updated={updated}")


if __name__ == "__main__":
    main()
