# 多Agent协作系统技术摘要

## 1. 系统概述

本系统设计一种多Agent协作模式，实现任务的智能分解、并行执行与统一汇总。系统采用**Leader-SubAgent**架构，通过类似HTTP的通信协议实现Agent间交互，支持任务隔离、状态追踪与结果校验。

## 2. 核心技术栈

- **语言**: Python 3.13+
- **Agent框架**: LangChain (LCEL表达式、ChatModel)
- **数据库**: PostgreSQL + pgvector (向量存储 + 状态存储)
- **通信协议**: 自定义Agent HTTP-like Protocol (AHP)

## 3. 核心设计理念

### 3.1 Leader Agent (主Agent)
- **职责**: 任务统筹、分解、汇总
- **特点**: 
  - 持有全局上下文 (Global Context)
  - 维护任务表 (Task Registry)
  - 少量Token指令派发给Sub-Agent
  - 结果聚合与校验

### 3.2 Sub Agent (子Agent)
- **职责**: 执行具体子任务
- **特点**:
  - 独立工具集 (Tools)
  - 独立数据源 (Data Sources)
  - 独立上下文 (Private Context)
  - 独立存储资源 (Storage)
  - 定时反馈进度

### 3.3 任务隔离机制
- 每个任务唯一ID (UUID)
- 任务状态: `pending` | `in_progress` | `completed` | `failed`
- 任务锁定: 抢单模式防止重复执行

### 3.4 Agent通信协议 (AHP)
```
Request:
  {
    "method": "POST",        # GET/POST/TASK/RESULT
    "agent_id": "sub_01",
    "task_id": "uuid",
    "payload": {...},
    "token_limit": 500
  }

Response:
  {
    "status": 200,
    "task_id": "uuid",
    "result": {...},
    "progress": "50%"
  }
```

### 3.5 数据存储策略

| 数据类型 | 存储方式 | 用途 |
|---------|---------|------|
| 语义向量 | pgvector (PostgreSQL) | 语义检索、相似度匹配 |
| 对话摘要 | PostgreSQL | 上下文恢复、审计追溯 |
| 任务状态 | PostgreSQL | 任务追踪、进度监控 |
| Agent内存 | 各Agent私有存储 | 独立上下文 |

## 4. 工作流程

```
User Input
    ↓
Leader Agent (意图理解 + 任务分解)
    ↓
[Task 1] [Task 2] [Task 3] ... (并行/串行)
    ↓ (AHP Protocol)
Sub-Agent 1 → Sub-Agent 2 → Sub-Agent N
    ↓
Result Collection → Validation → Aggregation
    ↓
Final Output + Storage
```

## 5. 关键特性

- **Token优化**: Leader仅传递必要指令，避免上下文泄露
- **隔离执行**: 任务间无共享状态，互不干扰
- **可扩展性**: 易于添加新Agent类型
- **可观测性**: 完整任务链路追踪
- **容错机制**: 失败重试、降级处理

## 6. 依赖服务

- PostgreSQL 15+ (需启用 pgvector 扩展)
- 可选: LangChain 支持的 LLM (OpenAI/Anthropic/本地模型)

## 7. 后续章节

- [架构设计文档](./architecture_design.md): 详细模块设计与数据流
- [实现代码](./src/): 完整Python实现