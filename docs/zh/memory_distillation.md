# 记忆蒸馏 (Memory Distillation)

## 概述

记忆蒸馏模块将对话历史转换为结构化记忆，持久化存储到 pgvector 支持跨会话检索，并支持记忆类型分离。

## 核心概念

### 1. 结构化记忆格式

蒸馏输出现在采用结构化 JSON 格式：

```json
{
    "user_profile": {"key": "value"},
    "decisions_made": [{"key": "唯一标识", "description": "描述"}],
    "pending_tasks": [{"task_id": "唯一标识", "description": "描述"}],
    "important_facts": ["事实1", "事实2"]
}
```

- **user_profile**: 长期有效的用户属性（风格偏好、预算等）
- **decisions_made**: 已做出的决定，包含唯一标识避免重复
- **pending_tasks**: 未完成的重要任务
- **important_facts**: 不适合上述类别的其他重要事实

### 2. 蒸馏层级（防止递归劣化）

为防止多次蒸馏导致信息丢失：

- 每条记忆有 `distill_level` 字段（1, 2, 3）
- 最高 3 级 - 超过此级别不再蒸馏
- 确保信息质量不会随时间下降

### 3. 重要性过滤

蒸馏前会评估对话的重要性：

- 仅包含长期有效信息的对话才会被蒸馏
- 长期信息包括：用户偏好、身份信息、关键决策
- 减少长期记忆中的噪声

### 4. 记忆类型分离

两种类型的记忆分开管理：

| 类型 | 说明 | 跨会话 |
|------|------|--------|
| user_memory | 用户偏好、预算、风格 | ✅ 是 |
| task_memory | 当前任务进度 | ❌ 否 |

## 使用方法

### 基础用法

```python
from src.utils import SessionMemory, LocalLLM
from src.storage import get_storage

# 初始化
session_memory = SessionMemory(
    session_id="uuid",
    llm=your_llm,
    storage=get_storage(),
    agent_id="leader"
)

# 添加对话
session_memory.add_user_turn("我想买一件外套", "您的预算是多少？")
session_memory.add_user_turn("500左右", "推荐这款...")

# 获取蒸馏后的上下文（超过阈值自动蒸馏）
context = session_memory.get_context()

# 获取用户画像
profile = session_memory.get_user_profile()
# {"style_preference": "casual", "budget": "500"}

# 获取待办任务
tasks = session_memory.get_pending_tasks()
```

### 分离用户/任务记忆

```python
# 添加用户对话
session_memory.add_user_turn("用户输入", "助手回复")

# 添加任务上下文
session_memory.add_task_context("任务: 推荐穿搭 - 状态: 80%完成")

# 获取特定类型的记忆
user_context = session_memory.get_user_context()  # 仅用户记忆
task_context = session_memory.get_task_context()  # 仅任务记忆
```

### 搜索相似记忆

```python
# 在 user_memory 中搜索
results = session_memory.search_memory("用户偏好", memory_type="user_memory")

# 在 task_memory 中搜索
results = session_memory.search_memory("穿搭推荐", memory_type="task_memory")

# 搜索两种类型
results = session_memory.search_memory("预算")
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_tokens | 4000 | 蒸馏前的最大 token 数 |
| distill_threshold | 0.8 | 触发蒸馏的阈值 (0.0-1.0) |
| keep_recent | 4 | 保留最近 N 轮完整对话 |
| enable_importance_filter | True | 是否启用重要性过滤 |

```python
session_memory = SessionMemory(
    session_id="uuid",
    llm=llm,
    storage=storage,
    max_tokens=2000,  # 更小的阈值
    enable_importance_filter=False  # 禁用过滤
)
```

## 数据库表结构

```sql
CREATE TABLE memory_summaries (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    summary JSONB NOT NULL,  -- 结构化JSON
    original_token_count INT,
    compressed_token_count INT,
    memory_type VARCHAR(20) DEFAULT 'user_memory',
    distill_level INT DEFAULT 1,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## API 参考

### SessionMemory

| 方法 | 说明 |
|------|------|
| `add_user_turn(user_input, assistant_response)` | 添加对话轮次 |
| `add_task_context(task_info)` | 添加任务上下文 |
| `get_context()` | 获取组合上下文 |
| `get_user_context()` | 仅获取用户记忆 |
| `get_task_context()` | 仅获取任务记忆 |
| `get_user_profile()` | 从记忆中获取用户画像 |
| `get_pending_tasks()` | 获取待办任务 |
| `search_memory(query, memory_type, limit)` | 搜索相似记忆 |
| `clear()` | 清空所有记忆 |

### MemoryDistiller

| 方法 | 说明 |
|------|------|
| `set_session(session_id)` | 设置会话 ID |
| `set_memory_type(type)` | 设置记忆类型 (user_memory/task_memory) |
| `add_user(content)` | 添加用户消息 |
| `add_assistant(content)` | 添加助手消息 |
| `should_distill()` | 检查是否需要蒸馏 |
| `distill()` | 触发蒸馏 |
| `get_context()` | 获取蒸馏后的上下文 |
| `search_similar_memories(query, limit)` | 搜索相似记忆 |

### StructuredMemory

| 方法 | 说明 |
|------|------|
| `to_dict()` | 转换为字典 |
| `to_json()` | 转换为 JSON 字符串 |
| `from_dict(data)` | 从字典创建 |
| `from_json(json_str)` | 从 JSON 字符串创建 |
| `merge(other)` | 合并另一个记忆 |