"""
search-service 入口
"""
import uvicorn
from fastapi import FastAPI
from app.api.search import router as search_router
from app.api.admin import router as admin_router
from app.api.biz import router as biz_router

app = FastAPI(
    title="Knowledge Search Service",
    description="基于 Elasticsearch 的知识库全文检索服务，数据来源于 MongoDB + OSS",
    version="1.0.0",
)

app.include_router(search_router)
app.include_router(admin_router)
app.include_router(biz_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=30011, reload=True)
