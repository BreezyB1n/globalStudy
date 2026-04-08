# GlobalStudy AI 子任务 2 技术方案

## 1. 子任务定位

### 1.1 子任务名称

数据源清单与官网采集方案

### 1.2 子任务目标

建立一套面向学校官网的可控采集机制，使系统能够对 10 到 15 所代表性学校的硕士项目页面进行手动触发抓取、原始留档和失败重试，为后续结构化抽取和向量建库提供可靠输入。

### 1.3 完成标准

- 可以维护学校与项目入口 URL 清单
- 可以用 Firecrawl 抓取指定页面
- 抓取结果按学校和项目落盘
- 页面元数据完整记录
- 支持全量抓取和局部重抓

## 2. 负责范围

纳入范围：

- 学校项目 URL 清单维护
- Firecrawl API 调用
- 原始 Markdown 或 HTML 内容保存
- 页面级元数据保存
- 抓取失败日志与重试策略

不纳入范围：

- 从页面中抽取业务字段
- chunk 切分与 embedding
- 问答逻辑

## 3. 数据源策略

### 3.1 数据来源约束

只允许使用学校官网页面，不采集：

- 中介网站
- 聚合搜索结果页
- 论坛或博客页面
- 第三方项目列表页

### 3.2 入口维护策略

第一版不做自动全站发现，采用人工维护入口清单。

推荐维护文件：

```text
data/processed/source_catalog.json
```

建议结构：

```json
[
  {
    "school_slug": "imperial",
    "school_name": "Imperial College London",
    "country": "UK",
    "program_slug": "msc-artificial-intelligence",
    "program_name": "MSc Artificial Intelligence",
    "degree_type": "MSc",
    "pages": [
      {
        "page_type": "overview",
        "url": "https://..."
      },
      {
        "page_type": "entry_requirements",
        "url": "https://..."
      }
    ]
  }
]
```

设计要求：

- 一个项目可以挂多个页面
- 每个页面必须有 `page_type`
- `school_slug` 与 `program_slug` 要稳定，方便后续落盘和重建

## 4. 抓取流程设计

### 4.1 总流程

```text
读取 source_catalog
-> 过滤目标学校/项目
-> 调用 Firecrawl 抓取页面
-> 保存原始内容
-> 保存页面元数据
-> 记录成功或失败日志
```

### 4.2 抓取脚本

建议主脚本：

```text
scripts/crawl_sources.py
```

建议支持参数：

- `--school imperial`
- `--program msc-artificial-intelligence`
- `--page-type entry_requirements`
- `--all`
- `--force`

说明：

- `--all` 触发全量抓取
- `--force` 表示即使已有原始文件也重新抓取

### 4.3 Firecrawl 调用策略

优先抓取 Markdown，必要时保留 HTML 作为兜底。

建议获取的数据：

- 页面正文 Markdown
- 页面标题
- 原始 URL
- 抓取时间
- HTTP 状态或抓取结果状态

要求：

- 单次抓取失败不能中断全批次任务
- 要保留失败详情，方便手工修正 URL 或重试

## 5. 原始文件组织

### 5.1 目录设计

```text
data/raw/
  imperial/
    msc-artificial-intelligence/
      overview.md
      overview.meta.json
      entry_requirements.md
      entry_requirements.meta.json
  oxford/
    msc-computer-science/
      overview.md
```

### 5.2 元数据文件建议

每个页面同时保存一个元数据文件：

```json
{
  "school_slug": "imperial",
  "school_name": "Imperial College London",
  "program_slug": "msc-artificial-intelligence",
  "program_name": "MSc Artificial Intelligence",
  "page_type": "entry_requirements",
  "page_title": "Entry requirements",
  "source_url": "https://...",
  "fetched_at": "2026-04-08T10:00:00+08:00",
  "content_hash": "sha256:...",
  "status": "success"
}
```

设计价值：

- 后续抽取和建库不用再回查入口清单
- 能基于 `content_hash` 判断页面是否变更
- 可以为局部重建提供精确输入

## 6. 抓取质量控制

### 6.1 页面合法性检查

抓取成功后，需要做基础校验：

- 内容不能为空
- 内容长度不能明显异常
- 页面标题与项目不完全无关
- URL 必须仍然指向学校官网域名

### 6.2 去重策略

如果同一页面被重复抓取：

- 优先保留最新成功结果
- 如果 `content_hash` 未变化，可以跳过后续重复处理

### 6.3 失败分类

建议将失败原因至少分为：

- URL 无效
- 页面跳转或 404
- Firecrawl 返回失败
- 内容过短或疑似无正文
- 学校站点反爬或页面结构异常

## 7. 与后续模块的接口边界

### 7.1 输出给结构化抽取模块

输出内容：

- 原始 Markdown 文件
- 页面级元数据 JSON

结构化抽取模块只读取落盘结果，不直接调用 Firecrawl。

### 7.2 输出给向量建库模块

同样只输出原始页面内容和元数据。

切分、清洗、向量化必须由子任务 4 处理，避免采集脚本承担过多职责。

## 8. 风险与处理

### 8.1 风险一：学校官网结构差异大

处理方式：

- 放弃全站自动爬取
- 采用人工维护入口清单
- 页面类型用人工语义标注，不依赖 URL 自动猜测

### 8.2 风险二：抓取内容不稳定

处理方式：

- 原始文件永久留档
- 每次抓取记录时间和哈希
- 支持指定学校和项目局部重抓

### 8.3 风险三：部分内容在 PDF 或 JS 动态页中

处理方式：

- 第一版优先选择可直接抓取的官网正文页
- 确实必要时再补充 PDF 解析，但不作为本任务默认目标

## 9. 验收标准

- 入口清单能覆盖选定学校与项目
- 运行抓取脚本后，`data/raw/` 下出现规范化目录
- 每个页面都具备正文文件和元数据文件
- 失败页面有独立日志记录
- 支持对单个学校或项目重复执行抓取

## 10. 本子任务交付结果

完成本子任务后，项目应具备稳定的原始语料来源。后续无论是字段抽取还是向量检索，都必须以这一层留档文件为唯一可信输入。
