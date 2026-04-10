# 韭研 BIZ 服务 API 文档

Base URL: `http://<host>:30011/biz/v1`

数据存储：Elasticsearch。所有列表接口均基于 ES 全文检索实现，支持关键词高亮。

---

## 1. 首页信息流

**GET** `/biz/v1/feed`

首页各 Tab 的文章列表，按发布时间倒序。无关键词时返回最新内容。

### Query Parameters

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| tab | string | 是 | - | 内容类型：`综合` `点评` `纪要` `研报` |
| filter | string | 否 | `全部` | 子筛选项，见下表 |
| include_ir | boolean | 否 | false | 纪要 Tab：是否包含投关活动 |
| include_wechat | boolean | 否 | true | 研报 Tab：是否包含公众号 |
| page | integer | 否 | 1 | 页码，从 1 开始 |
| page_size | integer | 否 | 20 | 每页条数，最大 50 |

**filter 可选值：**

| tab | filter 可选值 |
|-----|--------------|
| 综合 | `全部` `点评预期差` `公告预期差` `自选股信息流` `早报` `晚报` |
| 点评 | `全部` `机构` `网络` `图片` |
| 纪要 | `全部` `机构` `网络` |
| 研报 | `全部` `机构` `网络` |

### 示例请求

```
GET /biz/v1/feed?tab=点评&filter=机构&page=1&page_size=20
```

### 响应示例

```json
{
  "total": 1280,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": "doc_abc123",
      "title": "核心逻辑：低空经济产业链深度剖析",
      "content": "根据最新供应链消息反馈，核心组件环节近期出现了明显的排产上修信号…",
      "date": "2024-05-20 14:30",
      "tags": ["#低空经济产业链"],
      "companies": ["宁德时代", "中金公司"],
      "author": "lv**sj",
      "pages": null
    }
  ]
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| total | integer | 符合条件的总条数 |
| page | integer | 当前页码 |
| page_size | integer | 每页条数 |
| items | array | 文章列表 |
| items[].id | string | 文章唯一 ID（ES doc _id） |
| items[].title | string | 标题 |
| items[].content | string | 摘要或正文片段，建议 200 字以内 |
| items[].date | string | 发布时间，格式 `YYYY-MM-DD HH:mm` |
| items[].tags | string[] | 话题标签，如 `#低空经济产业链` |
| items[].companies | string[] | 关联公司名称列表 |
| items[].author | string\|null | 分享者（脱敏），可为 null |
| items[].pages | integer\|null | 页数，仅研报有值，其余为 null |

---

## 2. 全文检索

**GET** `/biz/v1/search`

关键词全文检索，支持多 Tab 切换和高级筛选。基于 ES `multi_match` 实现，支持按时间或综合相关度排序。

### Query Parameters

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| q | string | 是 | - | 搜索关键词，1~100 字 |
| tab | string | 否 | `综合` | `综合` `点评` `纪要` `研报` `图表` `公告` `互动` `社媒` |
| filter | string | 否 | `全部` | 子筛选项，见下表 |
| sort | string | 否 | `time` | 排序方式：`time`（时间倒序）`score`（相关度） |
| page | integer | 否 | 1 | 页码，从 1 开始 |
| page_size | integer | 否 | 25 | 每页条数，图表 Tab 建议 16，其余 25 |
| page_min | integer | 否 | - | 研报页数下限（可选） |
| page_max | integer | 否 | - | 研报页数上限（可选） |
| date_start | string | 否 | - | 研报日期筛选起始，格式 `YYYY-MM-DD` |
| date_end | string | 否 | - | 研报日期筛选截止，格式 `YYYY-MM-DD` |

**filter 可选值：**

| tab | filter 可选值 |
|-----|--------------|
| 纪要 | `全部` `机构` `投关活动` `网络` |
| 研报 | `全部` `机构` `三方` `公众号` `网络` `深度报告` |
| 社媒 | `全部` `公众号` `公司` |
| 其余 Tab | 无子筛选 |

### 示例请求

```
GET /biz/v1/search?q=低空经济&tab=研报&filter=机构&sort=time&page=1&page_size=25
```

### 响应示例（非综合 Tab）

```json
{
  "total": 234,
  "page": 1,
  "page_size": 25,
  "items": [
    {
      "id": "doc_xyz789",
      "title": "低空经济产业链深度报告",
      "content": "根据最新市场调研，<em>低空经济</em>板块近期呈现明显景气度提升信号…",
      "date": "2024-03-27 14:30",
      "institution": "中金公司",
      "stock_name": "宁德时代",
      "stock_code": "300750",
      "tags": ["#低空经济"],
      "pages": 32,
      "images": null
    }
  ]
}
```

### 响应示例（综合 Tab）

综合 Tab 额外返回各子类型命中数量，用于 Tab 上的数字角标：

```json
{
  "section_counts": {
    "点评": 156,
    "纪要": 89,
    "研报": 234,
    "图表": 45,
    "公告": 178,
    "互动": 92,
    "社媒": 37
  },
  "items": [
    {
      "id": "doc_xyz789",
      "title": "低空经济产业链深度报告",
      "content": "…",
      "date": "2024-03-27 14:30",
      "tab": "研报",
      "institution": "中金公司",
      "stock_name": null,
      "stock_code": null,
      "tags": [],
      "pages": 32,
      "images": null
    }
  ]
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| total | integer | 当前 Tab 符合条件的总条数 |
| page | integer | 当前页码 |
| page_size | integer | 每页条数 |
| section_counts | object | 仅综合 Tab 返回，各子类型命中数 |
| items | array | 文章列表 |
| items[].id | string | 文章唯一 ID |
| items[].title | string | 标题，含 ES highlight `<em>` 标签 |
| items[].content | string | 摘要，含 ES highlight `<em>` 标签 |
| items[].date | string | 发布时间 |
| items[].tab | string | 仅综合 Tab 返回，文章所属类型 |
| items[].institution | string\|null | 机构名称 |
| items[].stock_name | string\|null | 关联股票名称 |
| items[].stock_code | string\|null | 关联股票代码 |
| items[].tags | string[] | 话题标签 |
| items[].pages | integer\|null | 页数，仅研报有值 |
| items[].images | string[]\|null | 图片 URL 列表，仅图表 Tab 有值 |

> **ES highlight 说明**：`title` 和 `content` 字段中，命中关键词会被 `<em>` 标签包裹，前端负责将 `<em>` 渲染为高亮样式（黄色背景）。

---

## 错误响应

所有接口错误格式统一：

```json
{
  "detail": "错误描述信息"
}
```

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误 |
| 401 | 未登录或 token 失效 |
| 422 | 参数校验失败 |
| 500 | 服务内部错误 |
| 503 | ES 服务不可用 |
