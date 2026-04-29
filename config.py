import os
from dotenv import load_dotenv

load_dotenv()

ES_CONFIG = {
    "hosts":    os.getenv("ES_HOSTS", "http://localhost:9200"),
    "username": os.getenv("ES_USERNAME", ""),
    "password": os.getenv("ES_PASSWORD", ""),
    "index":    os.getenv("ES_INDEX", "documents"),
    "browse_max_pages": int(os.getenv("ES_BROWSE_MAX_PAGES", "100")),
    "browse_max_offset": int(os.getenv("ES_BROWSE_MAX_OFFSET", "1000")),
}

MONGODB_CONFIG = {
    "uri":             os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
    "db_name":         os.getenv("MONGODB_DB", "knowledgebase"),
    "collection_name": os.getenv("MONGODB_COLLECTION", "documents"),
    "tasks_collection": os.getenv("MONGODB_TASKS_COLLECTION", "pipeline_tasks"),
}

OSS_CONFIG = {
    "access_key_id":     os.getenv("OSS_ACCESS_KEY_ID", ""),
    "access_key_secret": os.getenv("OSS_ACCESS_KEY_SECRET", ""),
    "endpoint":          os.getenv("OSS_ENDPOINT", "oss-cn-shanghai.aliyuncs.com"),
}
