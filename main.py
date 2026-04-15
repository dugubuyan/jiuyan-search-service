"""
search-service 入口
"""
import time
import uvicorn
from fastapi import FastAPI, Request
from app.core.logger import logger
from app.api.search import router as search_router
from app.api.admin import router as admin_router
from app.api.biz import router as biz_router

app = FastAPI(
    title="Knowledge Search Service",
    description="基于 Elasticsearch 的知识库全文检索服务，数据来源于 MongoDB + OSS",
    version="1.0.0",
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = (time.time() - start) * 1000
    logger.info(f"{request.method} {request.url.path} {response.status_code} {ms:.1f}ms")
    return response


app.include_router(search_router)
app.include_router(admin_router)
app.include_router(biz_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import os
    is_dev = os.getenv("APP_ENV", "production") != "production"
    logger.info("starting search-service on port 30011")
    uvicorn.run("main:app", host="0.0.0.0", port=30011, reload=is_dev)
