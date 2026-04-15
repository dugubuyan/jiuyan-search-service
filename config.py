import os
from dotenv import load_dotenv

load_dotenv()

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

ES_CONFIG = {
    "hosts":    os.getenv("ES_HOSTS", "http://localhost:9200"),
    "username": os.getenv("ES_USERNAME", ""),
    "password": os.getenv("ES_PASSWORD", ""),
    "index":    os.getenv("ES_INDEX", "documents"),
    # 无关键词纯浏览时的最大页数限制，超过返回 400
    # 有关键词全文检索不受此限制（ES 默认 10000 条上限）
    "browse_max_pages": int(os.getenv("ES_BROWSE_MAX_PAGES", "100")),
}

MONGODB_CONFIG = {
    "uri":             os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
    "db_name":         os.getenv("MONGODB_DB", "knowledgebase"),
    "collection_name": os.getenv("MONGODB_COLLECTION", "documents"),
    "tasks_collection": os.getenv("MONGODB_TASKS_COLLECTION", "pipeline_tasks"),
}
