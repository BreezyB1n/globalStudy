# GlobalStudy AI 子任务 3 技术方案

## 1. 子任务定位

### 1.1 子任务名称

结构化抽取与 SQLite 建模方案

### 1.2 子任务目标

从学校官网原始页面中抽取项目级标准字段，建立本地 SQLite 结构化数据库，并为每个关键字段保存证据片段，使系统能够稳定回答字段型问题并支持后续溯源展示。

### 1.3 完成标准

- 建立稳定的 SQLite 表结构
- 可从原始 Markdown 中抽取字段
- 字段可空值表达清晰
- 字段与证据片段一一可追溯
- 支持全量抽取和局部重抽

## 2. 负责范围

纳入范围：

- SQLite 结构设计
- 抽取 JSON Schema 设计
- LLM 抽取提示词与校验策略
- 字段标准化与入库
- 证据片段入库

不纳入范围：

- 原始页面抓取
- embedding 与 ChromaDB
- 对外问答接口

## 3. 结构化字段设计

### 3.1 核心字段清单

建议以“能支撑高频问答”为原则，优先抽取以下字段：

- `school_name`
- `school_country`
- `program_name`
- `degree_type`
- `department`
- `study_mode`
- `duration`
- `tuition`
- `application_deadline`
- `language_requirement`
- `academic_requirement`
- `overview`

说明：

- 第一版不要追求字段过多，否则抽取稳定性会下降
- `overview` 允许保存压缩后的项目简介，用于快速回答基础介绍问题

### 3.2 字段标准化要求

为减少后续查询歧义，需要定义统一格式：

- `degree_type` 使用标准枚举，如 `MSc`、`MA`、`MPhil`
- `study_mode` 统一为 `full-time`、`part-time`、`hybrid`
- `duration` 保留原文表达，同时可选抽取标准月数
- `tuition` 保留币种和金额文本，不强制第一版换算
- `application_deadline` 若存在多个轮次，保留原文并可拆分辅助字段

## 4. SQLite 数据模型

### 4.1 `projects` 表

负责保存项目主信息，一条记录对应一个项目。

建议字段：

- `id`
- `school_slug`
- `school_name`
- `school_country`
- `program_slug`
- `program_name`
- `degree_type`
- `department`
- `study_mode`
- `duration`
- `tuition`
- `application_deadline`
- `language_requirement`
- `academic_requirement`
- `overview`
- `last_verified_at`
- `created_at`
- `updated_at`

约束建议：

- `school_slug + program_slug` 唯一
- 所有非必填字段允许 `NULL`

### 4.2 `source_pages` 表

负责保存每个项目关联的来源页面。

建议字段：

- `id`
- `project_id`
- `page_type`
- `page_title`
- `source_url`
- `raw_file_path`
- `content_hash`
- `fetched_at`

作用：

- 支撑字段证据和 chunk 元数据回链
- 支撑答辩时展示“项目信息来自哪些页面”

### 4.3 `field_evidences` 表

负责把结构化字段与证据文本关联起来。

建议字段：

- `id`
- `project_id`
- `field_name`
- `field_value`
- `evidence_text`
- `source_page_id`
- `created_at`

作用：

- 回答“学费是多少”“截止时间是什么时候”时可以直接返回字段值和证据
- 避免结构化值脱离来源页面

## 5. 抽取流程设计

### 5.1 总流程

```text
读取 raw 页面与 meta
-> 按项目聚合页面
-> 调用 LLM 按 JSON Schema 抽取字段
-> 对结果做字段校验与标准化
-> 写入 projects
-> 写入 source_pages
-> 写入 field_evidences
```

### 5.2 抽取粒度

建议以“项目”为抽取单位，而不是“单页”。

原因：

- 一个项目的信息通常分散在多个页面
- 单页抽取会导致字段残缺或相互覆盖
- 按项目聚合后再抽取，更接近最终问答需要

### 5.3 LLM 抽取策略

输入：

- 某个项目对应的多页 Markdown
- 每页的 `page_type`
- 预定义 JSON Schema

输出：

- 项目结构化字段
- 每个关键字段的证据文本
- 如果字段不存在，明确返回 `null`

约束要求：

- 不允许推断官网未出现的字段值
- 多个页面冲突时，优先保留更明确、更直接的页面证据
- 对截止时间、语言要求等易变化字段，必须保留原始证据文本

## 6. 数据校验与标准化

### 6.1 基础校验

抽取结果入库前至少校验：

- 必须能识别 `school_name` 和 `program_name`
- `field_name` 只能来自允许字段列表
- 长文本字段长度不能明显异常
- `source_url` 必须与已抓取页面一致

### 6.2 冲突处理

如果多个页面出现不同表述：

- 记录最直接、最新、最贴近官方要求的值
- 证据文本保留最关键片段
- 冲突严重时可在日志中标记人工复核

### 6.3 空值策略

第一版必须允许字段为空，不能因为抽不到某个字段就阻塞整个项目入库。

例如：

- 某些学校不公开学费
- 某些页面不写明确截止时间

此时应写入 `NULL`，并在问答阶段明确提示“未在已收录官网信息中找到明确答案”。

## 7. 脚本设计

建议主脚本：

```text
scripts/extract_projects.py
```

建议支持参数：

- `--school imperial`
- `--program msc-artificial-intelligence`
- `--all`
- `--force`

建议处理逻辑：

- 从 `data/raw/` 读取输入
- 从 `source_catalog` 获取项目基本标识
- 抽取完成后写入 SQLite
- 同步保存一份 `projects.json` 作为中间产物，便于调试

## 8. 对问答模块的输出契约

结构化问答模块应能直接依赖以下查询能力：

- 根据学校和项目查询完整项目记录
- 根据 `field_name` 查询指定字段和证据
- 根据项目获取全部来源页面

因此本子任务必须保证 SQLite 层具备清晰、稳定、可预测的查询接口。

## 9. 风险与处理

### 9.1 风险一：字段定义过多导致抽取不稳

处理：

- 第一版只保留高频字段
- 先保证字段型问答稳定，再考虑增量扩展

### 9.2 风险二：证据与字段脱节

处理：

- 每个高频字段都要求保留 `evidence_text`
- 入库时要求 `field_name` 和 `source_page_id` 可追溯

### 9.3 风险三：多页面信息冲突

处理：

- 明确冲突优先级
- 对高风险字段保留日志和人工复核点

## 10. 验收标准

- SQLite 中成功生成 `projects`、`source_pages`、`field_evidences` 三类核心表
- 至少一个项目可完整写入并被查询
- 学费、语言要求、截止时间等字段具备证据片段
- 字段缺失时系统不会报错，而是返回空值
- 支持对单个项目重复抽取并覆盖更新

## 11. 本子任务交付结果

完成本子任务后，系统将具备稳定回答字段型问题的核心基础。后续 LangGraph 在处理“学费是多少”“申请截止时间是什么时候”这类问题时，应优先消费这里产出的结构化数据和字段证据。
