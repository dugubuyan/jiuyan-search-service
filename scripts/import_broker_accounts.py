"""
将 公众号券商对应表.csv 导入 MongoDB broker_accounts 集合
幂等：以 account_name 为 key，重复执行安全
用法：python scripts/import_broker_accounts.py
"""
import csv
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient, ASCENDING
from config import MONGODB_CONFIG

CSV_PATH = Path(__file__).parent.parent / "gongzhonghao.csv"
SKIP_BROKERS = {"其他机构"}
SKIP_ROWS = {"表格 1", "公众号名称"}  # 噪音行


def main():
    cfg = MONGODB_CONFIG
    col = MongoClient(cfg["uri"])[cfg["db_name"]]["broker_accounts"]
    col.create_index([("account_name", ASCENDING)], unique=True, background=True)

    now = datetime.now(timezone.utc)
    upserted = skipped = 0

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            account_name = row[0].strip()
            broker_name = row[1].strip() if len(row) > 1 else ""

            # 跳过噪音行和空行
            if not account_name or account_name in SKIP_ROWS:
                skipped += 1
                continue
            if not broker_name or broker_name in SKIP_BROKERS:
                skipped += 1
                continue

            col.update_one(
                {"account_name": account_name},
                {"$set": {"broker_name": broker_name, "updated_at": now},
                 "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            upserted += 1

    print(f"完成：upserted={upserted}, skipped={skipped}")


if __name__ == "__main__":
    main()
