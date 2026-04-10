# search-service

基于 Elasticsearch 的知识库全文检索与管理服务，使用 FastAPI 构建。

提供两类功能：
- 全文检索 API（对外）：关键词搜索、多维过滤、分页浏览、命中高亮
- 管理平台 API（内部）：文档审核发布、敏感词管理、pipeline 任务监控

---

## 系统依赖

本服务运行时需要连接以下外部服务：

- **Elasticsearch**：存储全文索引，需安装 IK 分词插件（阿里云 ES 集群已内置）
- **MongoDB**：存储文档元数据、任务状态、敏感词库，与数据采集工程共享同一实例

数据由上游采集工程（pre-process）负责写入，本服务只负责读取和管理，不直接采集数据。

---

## MongoDB 数据结构说明

本服务依赖以下三个 MongoDB collection：

### documents（文档元数据）

每条文档的核心字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | string | 文档唯一 ID（sha256） |
| `title` | string | 标题 |
| `doc_type` | string | 文档类型：`remark` / `meeting` / `research` / `announcement` |
| `source` | string | 来源：`机构` / `网络` / `研报` 等 |
| `date` | string | 日期 `YYYY-MM-DD` |
| `rec_time` | int | Unix 时间戳，排序用 |
| `stock_code` | list | 股票代码列表，如 `["SH600519"]` |
| `tags` | object | 标签：`industry` / `theme` / `institute` / `tag_type` |
| `oss_key` | string | OSS 存储路径（原始文档） |
| `indexes.es.status` | string | ES 写入状态：`pending` / `done` / `failed` / `filtered` |
| `indexes.es.pub_status` | string | 发布状态：`pending`（待审核）/ `published`（已发布） |
| `indexes.es.reason` | string | 过滤原因（仅 filtered 时有值）：`sensitive_word` / `content_too_short` |

### pipeline_tasks（任务状态）

记录采集工程每个任务的处理状态：

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | string | `{source_type}:{task_key}:{stage}` |
| `source_type` | string | 来源类型：`remark_pai` / `remark_zsxq` / `meeting_pai` / `research` / `announcement` |
| `task_key` | string | 日期字符串（`YYYY-MM-DD`）或游标标识（`cursor:{max_id}`） |
| `stage` | string | 阶段：`fetch` / `store` / `refine` |
| `status` | string | `pending` / `running` / `done` / `failed` |
| `item_count` | int | 处理条数 |
| `error_msg` | string | 失败原因 |
| `updated_at` | int | Unix 时间戳 |

游标 source（remark_pai / remark_zsxq / meeting_pai）还有一条特殊记录：
- `_id` = `{source_type}:__cursor__`，字段 `max_id` 记录当前游标位置

### sensitive_words（敏感词库）

| 字段 | 类型 | 说明 |
|------|------|------|
| `word` | string | 敏感词 |
| `source_type` | string | 适用渠道，`null` 表示全局生效 |
| `created_at` | datetime | 创建时间 |

---

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 ES 和 MongoDB 连接信息
uvicorn main:app --reload --port 8000
```

交互式 API 文档：http://localhost:8000/docs

---

## 环境变量

复制 `.env.example` 为 `.env` 并填入真实值：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ES_HOSTS` | ES 地址，多个用逗号分隔 | `http://localhost:9200` |
| `ES_USERNAME` | ES 用户名 | 空 |
| `ES_PASSWORD` | ES 密码 | 空 |
| `ES_INDEX` | ES 索引名 | `documents` |
| `ES_BROWSE_MAX_PAGES` | 无关键词浏览最大页数，超过返回 400 | `100` |
| `MONGODB_URI` | MongoDB 连接串 | `mongodb://localhost:27017` |
| `MONGODB_DB` | 数据库名 | `knowledgebase` |
| `MONGODB_COLLECTION` | 文档 collection 名 | `documents` |
| `MONGODB_TASKS_COLLECTION` | 任务 collection 名 | `pipeline_tasks` |

---

## API 完整说明

### GET /health

健康检查，返回 `{"status": "ok"}`。

---

### POST /search — 全文检索

所有检索结果自动过滤 `status=published`，待审核内容对用户不可见。

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | 否 | 关键词，为空时按 `rec_time` 倒序分页浏览 |
| `doc_type` | string | 否 | 文档类型：`remark` / `meeting` / `research` / `announcement` |
| `source` | string | 否 | 来源：`机构` / `网络` / `研报` / `年报` 等 |
| `stock_code` | string | 否 | 股票代码，如 `SH600519` |
| `date_from` | string | 否 | 日期起始 `YYYY-MM-DD` |
| `date_to` | string | 否 | 日期截止 `YYYY-MM-DD` |
| `industry` | string | 否 | 行业标签 |
| `institute` | string | 否 | 机构名称 |
| `page` | int | 否 | 页码，从 1 开始，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 10，最大 100 |

**排序规则：**
- 有关键词：相关度评分降序，`rec_time` 作为次要排序
- 无关键词：纯按 `rec_time` 降序，最大页数受 `ES_BROWSE_MAX_PAGES` 限制

**响应体：**

```json
{
  "total": 128,
  "page": 1,
  "page_size": 10,
  "hits": [
    {
      "doc_id": "abc123...",
      "title": "茅台2024年年度报告",
      "doc_type": "announcement",
      "source": "年报",
      "date": "2024-03-28",
      "stock_code": ["SH600519"],
      "src_url": "",
      "tags": {"industry": ["白酒"], "institute": "", "theme": [], "tag_type": ""},
      "highlight": "...营业收入同比增长 <em>15%</em>...",
      "score": 8.42
    }
  ]
}
```

**示例：**

```bash
# 关键词搜索
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "营业收入", "doc_type": "remark", "page": 1, "page_size": 10}'

# 无关键词分页浏览（按时间倒序）
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "meeting", "page": 1, "page_size": 20}'
```

---

## 管理 API（/admin/*）

### ES 索引管理

#### GET /admin/index/stats

查看 ES 索引统计信息。

```bash
curl http://localhost:8000/admin/index/stats
# {"index": "documents", "doc_count": 124040, "size_bytes": 1234567890}
```

#### POST /admin/index/ensure

初始化 ES 索引（含 mapping），已存在则跳过。正常情况下索引由上游采集工程自动创建，此接口用于索引被误删或需要手动重建时调用。

```bash
curl -X POST http://localhost:8000/admin/index/ensure
```

---

### 文档审核

文档写入 ES 时，需要人工审核的渠道（remark_pai / remark_zsxq / meeting_pai）默认 `status=pending`，不对外可见，需通过以下接口发布。

#### GET /admin/docs/pending

查看待审核文档列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| `doc_type` | string | 文档类型过滤（可选） |
| `source` | string | 来源过滤（可选） |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 每页条数，默认 20，最大 100 |

#### POST /admin/docs/{doc_id}/enable

发布单条文档（`pending → published`），同步更新 MongoDB 和 ES。

#### POST /admin/docs/{doc_id}/disable

下架单条文档（`published → pending`），同步更新 MongoDB 和 ES。

#### POST /admin/docs/batch/enable

批量发布文档，支持按 `doc_ids` 列表或 `doc_type`/`source` 条件批量操作。

```json
{
  "doc_ids": ["id1", "id2"],        // 可选，为空则按条件批量
  "doc_type": "remark",             // 可选
  "source": "机构",                  // 可选
  "requests_per_second": 500        // ES update_by_query 限速，默认 500
}
```

#### POST /admin/docs/{doc_id}/reindex

重置单条文档的 ES 索引状态为 `pending`，同时将 ES 中该文档下架。上游采集工程下次运行时会自动重新写入 ES。适用于需要重新处理某条文档的场景。

#### POST /admin/docs/batch/reindex

批量重置 ES 索引，请求体同 `batch/enable`。

---

### Pipeline 任务监控

监控上游采集工程（pre-process）的任务执行状态。

#### GET /admin/pipeline/tasks

查看任务列表，支持按 `source_type` 和 `status` 过滤，分页返回。

| 参数 | 说明 |
|------|------|
| `source_type` | `remark_pai` / `remark_zsxq` / `meeting_pai` / `research` / `announcement` |
| `status` | `pending` / `running` / `done` / `failed` |
| `page` / `page_size` | 分页，page_size 最大 200 |

#### GET /admin/pipeline/stats

按 `source_type.stage.status` 汇总任务数量，用于快速了解整体处理进度。

```json
{
  "remark_pai.fetch.done": 120,
  "remark_pai.store.done": 118,
  "remark_pai.store.failed": 2
}
```

#### GET /admin/pipeline/cursors

查看游标模式 source（remark_pai / remark_zsxq / meeting_pai）的当前游标位置（`max_id`）和最后更新时间。游标代表上游已处理到的数据位置，重启后从此处续跑。

#### GET /admin/pipeline/daily

按日期 + source_type 汇总任务处理情况，用于排查某天某渠道是否有遗漏。

| 参数 | 说明 |
|------|------|
| `source_type` | 渠道过滤（可选） |
| `days` | 最近 N 天，默认 30，最大 365 |

响应示例：

```json
{
  "days": 3,
  "data": {
    "2026-03-24": {
      "remark_pai":  {"done": 242, "failed": 0, "pending": 0, "running": 0},
      "remark_zsxq": {"done": 1764, "failed": 0, "pending": 0, "running": 0}
    }
  }
}
```

#### POST /admin/pipeline/reset-failed

将 `failed` 状态的任务重置为 `pending`，上游采集工程下次运行时会自动重试。

| 参数 | 说明 |
|------|------|
| `source_type` | 渠道过滤（可选，为空则重置所有渠道） |
| `stage` | 阶段过滤：`fetch` / `store` / `refine`（可选） |

---

### 敏感词管理

敏感词库存储在 MongoDB `sensitive_words` collection，上游采集工程写入 ES 前实时读取（缓存 TTL 60 秒），命中敏感词的文档不会写入 ES（标记为 `filtered`）。

支持两种粒度：
- 全局词（`source_type=null`）：对所有渠道生效
- 渠道专属词（`source_type="remark_pai"` 等）：仅对指定渠道生效

#### GET /admin/sensitive-words

查看词库。`source_type` 参数为空时返回全部，指定时返回该渠道词 + 全局词。

#### POST /admin/sensitive-words

添加敏感词。

```json
{"word": "违禁词", "source_type": null}
{"word": "渠道专属词", "source_type": "remark_zsxq"}
```

#### DELETE /admin/sensitive-words

删除敏感词，请求体同添加。

---

## ES Index Mapping

| 字段 | 类型 | 分析器 | 说明 |
|------|------|--------|------|
| `doc_id` | keyword | — | 文档唯一 ID |
| `title` | text | ik_max_word / ik_smart | 标题，检索权重 3x |
| `content` | text | ik_max_word / ik_smart | 正文全文 |
| `doc_type` | keyword | — | 文档类型 |
| `source` | keyword | — | 来源 |
| `date` | date | — | 日期 `YYYY-MM-DD` |
| `rec_time` | long | — | Unix 时间戳，排序用 |
| `stock_code` | keyword | — | 股票代码列表 |
| `status` | keyword | — | `published` / `pending` |
| `tags.industry` | keyword | — | 行业标签 |
| `tags.institute` | keyword | — | 机构名称 |
| `tags.theme` | keyword | — | 主题标签 |
| `tags.tag_type` | keyword | — | 标签类型 |

---

## 目录结构

```
search-service/
├── app/
│   ├── api/
│   │   ├── search.py           # 检索路由
│   │   ├── admin.py            # 管理路由汇总入口
│   │   ├── admin_deps.py       # 公共依赖（MongoDB 连接、时间工具）
│   │   ├── admin_index.py      # ES 索引管理
│   │   ├── admin_docs.py       # 文档审核/发布/reindex
│   │   ├── admin_pipeline.py   # Pipeline 任务监控
│   │   └── admin_sensitive.py  # 敏感词管理
│   ├── core/
│   │   └── es_client.py        # ES 客户端 + mapping + 搜索逻辑
│   └── models/
│       └── search.py           # Pydantic 请求/响应模型
├── config.py                   # 配置（读取环境变量）
├── main.py                     # FastAPI 入口
├── requirements.txt
├── .env.example
└── README.md
```
