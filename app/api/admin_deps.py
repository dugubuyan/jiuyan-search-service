"""公共依赖：MongoDB 连接、时间工具"""
from datetime import datetime, timezone
from pymongo import MongoClient
from config import MONGODB_CONFIG


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def mongo_col():
    cfg = MONGODB_CONFIG
    return MongoClient(cfg["uri"])[cfg["db_name"]][cfg["collection_name"]]


def mongo_tasks():
    cfg = MONGODB_CONFIG
    return MongoClient(cfg["uri"])[cfg["db_name"]][cfg["tasks_collection"]]


def mongo_sensitive():
    cfg = MONGODB_CONFIG
    return MongoClient(cfg["uri"])[cfg["db_name"]]["sensitive_words"]
