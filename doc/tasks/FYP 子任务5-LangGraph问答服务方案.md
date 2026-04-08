# GlobalStudy AI 子任务 5 技术方案

## 1. 子任务定位

### 1.1 子任务名称

LangGraph 问答服务方案

### 1.2 子任务目标

构建一个支持多轮上下文的问答服务，能够对用户问题进行理解、实体补全、问题路由、结构化查询、向量检索、证据组织和回答生成，并通过统一 API 向前端返回答案与引用。

### 1.3 完成标准

- 实现 `/api/chat` 主接口
- 能识别字段型、解释型、比较型问题
- 能利用最近若干轮对话补全实体
- 返回答案时附带规范化引用结构
- 证据不足时能安全降级

## 2. 负责范围

纳入范围：

- LangGraph 状态设计
- 问题理解与路由
- SQLite 查询与 ChromaDB 检索接入
- 回答生成提示词
- 统一响应结构

不纳入范围：

- 原始采集
- 字段抽取
- 向量建库
- 前端页面渲染

## 3. 接口设计

### 3.1 主接口

```text
POST /api/chat
```

请求体建议：

```json
{
  "messages": [
    { "role": "user", "content": "介绍一下帝国理工的 AI 硕士项目" },
    { "role": "assistant", "content": "..." },
    { "role": "user", "content": "那它的雅思要求呢" }
  ]
}
```

响应体建议：

```json
{
  "answer": "根据已收录的官网页面，该项目的语言要求为……",
  "citations": [
    {
      "school_name": "Imperial College London",
      "program_name": "MSc Artificial Intelligence",
      "page_title": "Entry requirements",
      "source_url": "https://...",
      "evidence_text": "Minimum IELTS score ...",
      "evidence_type": "structured_field"
    }
  ],
  "resolved_context": {
    "school_name": "Imperial College London",
    "program_name": "MSc Artificial Intelligence",
    "question_type": "field"
  }
}
```

## 4. LangGraph 状态设计

建议状态字段：

- `messages`
- `current_question`
- `resolved_school`
- `resolved_program`
- `question_type`
- `structured_result`
- `retrieved_chunks`
- `citations`
- `final_answer`

设计原则：

- 状态必须足够支撑节点间传递
- 但不要把底层数据库对象直接放进状态
- 状态里只保留与本轮问答相关的中间结果

## 5. 工作流设计

### 5.1 推荐节点

1. `load_context`
2. `understand_question`
3. `resolve_entities`
4. `route_question`
5. `query_structured_data`
6. `retrieve_vector_chunks`
7. `merge_evidences`
8. `generate_answer`

### 5.2 节点职责

#### `load_context`

从请求中的最近几轮消息提取可复用上下文，识别上一轮已经确定的学校和项目。

#### `understand_question`

判断当前问题是否为：

- 字段型
- 解释型
- 比较型
- 追问型

#### `resolve_entities`

目标：

- 识别学校名和项目名
- 若当前问题未明确出现实体，则尝试从历史消息继承

#### `route_question`

根据问题类型选择路径：

- 字段型优先查 SQLite
- 解释型优先查 ChromaDB
- 比较型优先走混合路径

#### `query_structured_data`

根据已识别的学校、项目和字段名查询 SQLite，并返回字段值和字段证据。

#### `retrieve_vector_chunks`

根据问题文本和实体过滤条件查询 ChromaDB，返回最相关的若干 chunk。

#### `merge_evidences`

统一整理结构化证据和 chunk 证据：

- 去重
- 控制数量
- 规范输出字段

#### `generate_answer`

要求模型：

- 只能依据提供证据回答
- 不足时明确说明找不到
- 回答简洁、准确、不要额外发散

## 6. 查询路由设计

### 6.1 字段型问题

典型问题：

- “学费是多少”
- “申请截止时间是什么时候”
- “雅思要求多少”

处理方式：

- 从问题中识别字段意图
- SQLite 直接查字段值和证据
- 如有必要，再用检索结果补充背景说明

### 6.2 解释型问题

典型问题：

- “这个项目主要学什么”
- “课程设置有什么特点”
- “官网怎么介绍这个项目”

处理方式：

- 向量检索优先
- 回答阶段整合多个相关 chunk

### 6.3 比较型问题

典型问题：

- “它和爱丁堡的 AI 硕士相比怎么样”
- “和刚才那个项目比申请要求有什么差别”

处理方式：

- 先解析对比对象
- 对两个项目分别做结构化查询和向量检索
- 统一组织证据后生成对比回答

第一版可以只支持有限比较场景，不必追求复杂表格化比较。

## 7. 多轮问答设计

### 7.1 上下文来源

不引入登录和持久化会话，直接由前端回传最近若干轮消息。

优点：

- 实现简单
- 本地 Demo 足够
- 不新增状态存储基础设施

### 7.2 上下文截断策略

建议只保留最近若干轮消息，避免：

- 提示词过长
- 模型关注点被早期无关内容稀释

### 7.3 追问解析

重点支持这类表达：

- “那它的雅思要求呢”
- “截止时间呢”
- “和上一个比怎么样”

要求：

- 如果上一轮项目上下文明确，应能补全
- 如果上下文不明确，应要求用户重新说明学校或项目

## 8. 回答生成约束

### 8.1 提示词原则

系统提示词必须强调：

- 你是留学项目信息问答助手
- 只能依据提供的官网证据作答
- 不允许补充未出现的信息
- 如果证据不足，要明确说明无法确认

### 8.2 输出风格

回答建议：

- 先直接回答问题
- 再补充必要说明
- 不要输出大段空泛套话

### 8.3 无答案场景

若没有足够证据，应返回类似表述：

`未在当前已收录的官网页面中找到明确答案，建议查看原始链接进一步确认。`

## 9. 后端服务设计

### 9.1 服务层划分

建议划分为：

- `services/chat_service.py`
- `services/entity_resolver.py`
- `services/structured_query_service.py`
- `services/vector_retrieval_service.py`
- `graph/chat_graph.py`

设计目的：

- 保持 LangGraph 节点职责清晰
- 便于单元测试
- 避免把全部逻辑堆进一个接口文件

### 9.2 模型与仓储层

建议将 SQLite 和 ChromaDB 的访问封装到仓储或客户端层，而不是直接在图节点中散写查询代码。

## 10. 风险与处理

### 10.1 风险一：多轮追问误绑定项目

处理：

- 只继承最近清晰确认的实体
- 如果上下文不明确，宁可请用户补充，也不要强行猜测

### 10.2 风险二：路由过度复杂

处理：

- 第一版只做三类问题路由
- 不做多 Agent 复杂编排

### 10.3 风险三：模型幻觉

处理：

- 所有回答都基于显式证据
- 缺失时明确拒答或说明证据不足
- 结构化字段优先于自由生成

## 11. 验收标准

- `/api/chat` 能处理单轮和多轮输入
- 字段型问题优先返回结构化字段和证据
- 解释型问题能返回向量检索证据
- 比较型问题至少支持基础的两项目对比
- 响应中始终带有可展示的 `citations`

## 12. 本子任务交付结果

完成本子任务后，系统的问答主链路将真正成立。它会把结构化库、向量库和 LLM 连接起来，形成毕业设计 Demo 最核心的智能能力。
