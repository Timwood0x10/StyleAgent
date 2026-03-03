# 记忆蒸馏 (Memory Distillation)

## 概述

记忆蒸馏是一种将长对话历史压缩为简洁关键信息摘要的技术。它通过以下方式解决 LLM 对话的 token 限制问题：

1. **检测蒸馏时机** - 监控 token 使用情况，达到阈值时触发蒸馏
2. **提取关键信息** - 使用 LLM 蒸馏重要细节（用户偏好、决策、上下文）
3. **持久化到向量数据库** - 将蒸馏后的记忆存储到 pgvector，支持跨会话检索
4. **检索相关记忆** - 通过向量语义搜索历史蒸馏记忆

## 为什么要用记忆蒸馏？

### 问题
- LLM 有上下文窗口限制（如 4K、8K、32K tokens）
- 长对话会超出这些限制
- 直接截断会丢失重要信息

### 解决方案：蒸馏
我们不丢失信息，而是：
1. 保留最近 N 轮完整对话
2. 将更早的对话压缩成简洁摘要（使用 LLM）
3. 将摘要存入向量数据库供检索

## 架构设计

### 组件

```
┌─────────────────────────────────────────────────────────┐
│                    SessionMemory                        │
│  (管理会话的蒸馏流程)                                   │
├─────────────────────────────────────────────────────────┤
│                  MemoryDistiller                        │
│  - 追踪对话历史                                         │
│  - 估算 token 使用量                                    │
│  - 触发 LLM 蒸馏                                        │
│  - 持久化到 StorageLayer                               │
├─────────────────────────────────────────────────────────┤
│                   StorageLayer                         │
│  - PostgreSQL + pgvector                               │
│  - save_distilled_memory()                             │
│  - get_distilled_memories()                            │
│  - search_similar_memories()                           │
└─────────────────────────────────────────────────────────┘
```

### 数据库表结构

```sql
CREATE TABLE memory_summaries (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    summary TEXT NOT NULL,
    original_token_count INT,
    compressed_token_count INT,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## 使用方法

### 基本用法

```python
from src.utils import SessionMemory, LocalLLM
from src.storage import get_storage

# 初始化
llm = LocalLLM()
storage = get_storage()
session_memory = SessionMemory(
    session_id="user-123",
    llm=llm,
    storage=storage,
    agent_id="leader",
    max_tokens=4000
)

# 添加对话轮次
session_memory.add_user_turn("我想买一件外套", "好的，请问您的预算是多少？")
session_memory.add_user_turn("500左右", "推荐这款...")
session_memory.add_user_turn("还有其他款式吗", "当然，这里有...")

# 获取蒸馏后的上下文（超过阈值自动蒸馏）
context = session_memory.get_context()
```

### 手动蒸馏

```python
# 手动触发
session_memory.distiller.distill()

# 异步版本
await session_memory.distiller.adistill()
```

### 搜索相似记忆

```python
# 搜索相关历史记忆
results = session_memory.search_memory("用户偏好")
for r in results:
    print(f"- {r['summary']} (相似度: {r['similarity']})")
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_tokens` | 4000 | 最大 token 数，超过则蒸馏 |
| `distill_threshold` | 0.8 | 触发蒸馏的阈值（0-1） |
| `keep_recent` | 4 | 保留最近 N 轮完整对话 |

### 调优

```python
# 更激进的蒸馏
session_memory = SessionMemory(
    max_tokens=2000,       # 更小的上下文窗口
    distill_threshold=0.6, # 更早触发蒸馏
    keep_recent=2          # 保留更少轮次
)
```

## 蒸馏流程详解

### 步骤流程

```
对话历史：
[用户1] → [助手1] → [用户2] → [助手2] → [用户3] → [助手3] → [用户4] → [助手4] → [用户5]

超过阈值（>80% max_tokens）
           │
           ▼
┌─────────────────────────────────────┐
│  1. 分割：                           │
│     - 待蒸馏：用户1-助手3            │
│     - 保留：用户4-助手4              │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  2. LLM 蒸馏提示：                   │
│  "总结以下关键信息：                 │
│   - 用户偏好                         │
│   - 重要决策                         │
│   - 未完成任务                       │
│   - 关键上下文                       │
│  请用中文总结。"                    │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  3. LLM 输出（摘要）：               │
│  "用户偏好休闲风格，预算500左右，    │
│   已推荐外套款式，正在挑选中..."      │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  4. 持久化到 pgvector：             │
│  - 保存摘要文本                     │
│  - 生成向量 embedding               │
│  - 存储元数据                       │
└─────────────────────────────────────┘
           │
           ▼
最终上下文：
┌─────────────────────────────────────┐
│ [蒸馏记忆]                           │
│ 用户偏好休闲风格，预算500左右...     │
├─────────────────────────────────────┤
│ [最近对话]                          │
│ 用户4: 还有其他款式吗                │
│ 助手: 当然，这里有...               │
└─────────────────────────────────────┘
```

## 优势

1. **Token 效率**：将 4000+ tokens 压缩成约 200 tokens 的摘要
2. **信息保留**：保留关键偏好和决策
3. **跨会话持久化**：记忆在重启后依然存在
4. **语义检索**：通过向量搜索找到相关历史上下文
5. **自动执行**：透明发生，无需手动干预

## 与 Agent 集成

### Leader Agent 集成示例

```python
from src.utils import SessionMemory

class LeaderAgent:
    def __init__(self, ...):
        self.session_memory = SessionMemory(
            session_id=session_id,
            llm=self.llm,
            storage=self.storage,
            agent_id="leader"
        )
    
    async def handle_user_input(self, user_input: str):
        # 添加到记忆
        self.session_memory.add_user_turn(user_input)
        
        # 获取蒸馏后的上下文
        context = await self.session_memory.aget_context()
        
        # 用于 LLM prompt
        response = await self.llm.ainvoke(
            prompt=f"上下文：{context}\n\n用户：{user_input}"
        )
        
        self.session_memory.add_system_turn(response)
        return response
```

## 错误处理

- **没有 LLM**：跳过蒸馏，使用现有上下文
- **没有 Storage**：仅内存存储，不持久化
- **LLM 失败**：记录错误，保留原始上下文
- **空历史**：不执行蒸馏

## 性能考虑

- 蒸馏增加延迟（每次 LLM 调用约 1-2 秒）
- 向量生成增加约 0.5 秒
- 向量搜索很快（<100 毫秒）
- 考虑异步蒸馏以获得更好的用户体验
