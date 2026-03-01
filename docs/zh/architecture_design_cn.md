# iFlow 多智能体穿搭推荐系统架构设计

## 1. 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层                                │
│              examples/demo_interactive.py                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Leader Agent (主智能体)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐│
│  │ 用户信息解析 │  │  任务分解器  │  │      结果聚合器          ││
│  │   上下文增强 │  │   类别分析   │  │   RAG 向量存储          ││
│  └─────────────┘  └─────────────┘  └─────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              错误处理: 重试器 + 断路器                       ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   AHP Protocol    │
                    │  (消息队列 + Token控制)│
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Sub Agent 1  │   │  Sub Agent 2  │   │  Sub Agent N  │
│  (head 配饰)  │   │  (top 上装)   │   │  (更多品类...) │
│ ┌───────────┐ │   │ ┌───────────┐ │   │ ┌───────────┐ │
│ │ Tools     │ │   │ │ Tools     │ │   │ │ Tools     │ │
│ │ Data Src  │ │   │ │ Data Src  │ │   │ │ Data Src  │ │
│ │ Context   │ │   │ │ Context   │ │   │ │ Context   │ │
│ │ RAG       │ │   │ │ RAG       │ │   │ │ RAG       │ │
│ └───────────┘ │   │ └───────────┘ │   │ └───────────┘ │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                     │
        └───────────────────┴─────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Result Validator (结果验证器)                  │
│         字段检查 │ 类型验证 │ 内容合理性 │ 自动修复              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Storage Layer (PostgreSQL + pgvector)           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Semantic       │  │   Task          │  │   Session       │ │
│  │  Vectors (RAG)  │  │   Registry      │  │   Store         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  表: user_profiles | outfit_recommendations | semantic_vectors  │
│      tasks | sessions | agent_contexts | task_progress           │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 核心模块设计

### 2.1 Leader Agent 模块

```python
class LeaderAgent:
    """主智能体: 任务协调与结果聚合"""
    
    def __init__(self, llm: ChatModel):
        self.llm = llm
        self.validator = ResultValidator()
        self.registry = TaskRegistry()
        self.circuit_breaker = CircuitBreaker()
        self.retry_handler = RetryHandler()
    
    def process(self, user_input: str) -> OutfitResult:
        # 1. 解析用户信息
        # 2. 分析任务类别
        # 3. 创建并分发任务
        # 4. 收集验证结果
        # 5. 聚合输出
        pass
    
    def parse_user_profile(self, user_input: str) -> UserProfile:
        """解析用户输入，提取用户画像"""
        pass
    
    def create_tasks(self, user_profile: UserProfile) -> List[OutfitTask]:
        """任务分解，确定推荐品类"""
        pass
    
    def aggregate_results(self, ...) -> OutfitResult:
        """结果聚合与验证"""
        pass
```

### 2.2 Sub Agent 模块

```python
class OutfitSubAgent:
    """子智能体: 独立执行品类推荐任务"""
    
    def __init__(
        self, 
        agent_id: str,
        category: str,
        llm: ChatModel,
    ):
        self.agent_id = agent_id
        self.category = category  # head/top/bottom/shoes
        self.llm = llm
        self.resources = AgentResources()
        self.retry_handler = RetryHandler()
        self.circuit_breaker = CircuitBreaker()
    
    def _recommend(self, profile: UserProfile) -> OutfitRecommendation:
        """执行推荐: 工具 + RAG + LLM"""
        pass
    
    def _get_rag_context(self, profile: UserProfile) -> str:
        """获取历史相似推荐作为上下文"""
        pass
```

### 2.3 AHP 通信协议

```python
class AHPProtocol:
    """Agent HTTP-like Protocol - 智能体通信协议"""
    
    # 消息方法
    METHOD_TASK = "TASK"       # 分发任务
    METHOD_RESULT = "RESULT"   # 返回结果
    METHOD_PROGRESS = "PROGRESS"  # 进度报告
    METHOD_HEARTBEAT = "HEARTBEAT"  # 心跳
    METHOD_ACK = "ACK"         # 确认
    
    # 特性
    - MessageQueue (消息队列)
    - Token Controller (Token控制)
    - DLQ (死信队列)
    - 去重机制
```

### 2.4 任务注册中心

```python
class TaskRegistry:
    """任务注册与状态管理"""
    
    def register_task(self, session_id, title, description, category) -> str:
        """注册新任务"""
        pass
    
    def claim_task(self, agent_id, task_id) -> bool:
        """认领任务（确保唯一执行）"""
        pass
    
    def update_status(self, task_id, status, result):
        """更新任务状态"""
        pass
```

### 2.5 数据存储层

```sql
-- PostgreSQL 表设计

-- 1. 用户画像表
CREATE TABLE user_profiles (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    name VARCHAR(100),
    gender VARCHAR(20),
    age INT,
    occupation VARCHAR(100),
    hobbies TEXT[],
    mood VARCHAR(50),
    style_preference VARCHAR(100),
    budget VARCHAR(20),
    season VARCHAR(20),
    occasion VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. 穿搭推荐表
CREATE TABLE outfit_recommendations (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    category VARCHAR(50),
    items TEXT[],
    colors TEXT[],
    styles TEXT[],
    reasons TEXT[],
    price_range VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. 向量存储表 (RAG)
CREATE TABLE semantic_vectors (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50),
    content TEXT NOT NULL,
    embedding vector(1536),  -- pgvector
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. 任务状态表
CREATE TABLE tasks (
    task_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    status VARCHAR(20) NOT NULL,
    assignee_agent_id VARCHAR(50),
    result JSONB,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 5. 会话历史表
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY,
    user_input TEXT NOT NULL,
    final_output TEXT,
    summary TEXT,
    status VARCHAR(20) DEFAULT 'running',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 6. Agent 私有上下文表
CREATE TABLE agent_contexts (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    context_data JSONB,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, agent_id)
);

-- 索引
CREATE INDEX idx_vectors_session ON semantic_vectors(session_id);
CREATE INDEX idx_vectors_embedding ON semantic_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_contexts_session_agent ON agent_contexts(session_id, agent_id);
```

## 3. 子系统详解

### 3.1 Tools (工具)

每个 Sub Agent 配备以下工具：

| 工具 | 功能 |
|------|------|
| FashionSearchTool | 根据心情/职业/季节搜索时尚建议 |
| WeatherCheckTool | 获取天气信息和建议 |
| StyleRecommendTool | 获取风格推荐和搭配建议 |

### 3.2 Data Sources (数据源)

| 数据源 | 功能 |
|--------|------|
| FashionDatabase | 时尚数据库（趋势颜色、风格、年龄段） |
| UserHistoryDB | 用户历史推荐记录 |

### 3.3 Private Context (私有上下文)

- 每个 Agent 独立的内存存储
- Session 级别的数据隔离
- 可持久化到数据库

### 3.4 RAG 上下文增强

- 基于用户画像生成查询向量
- 在向量数据库中搜索相似历史推荐
- 将历史推荐作为上下文提供给 LLM

## 4. 错误处理与容错

### 4.1 重试机制 (RetryHandler)

- 指数退避算法
- 可配置最大重试次数
- 指定可重试的错误类型

### 4.2 断路器 (CircuitBreaker)

```
Closed (正常) ──失败5次──> Open (熔断)
                              │
                              ▼ (60秒后)
                         Half-Open (测试)
                              │
                              ▼ (成功)
                         Closed (恢复)
```

### 4.3 死信队列 (DLQ)

- 失败消息进入 DLQ
- 可查询和分析失败原因
- 支持手动重试

## 5. 配置与扩展

### 5.1 Agent 配置示例

```yaml
agents:
  - id: "agent_head"
    category: "head"
    tools:
      - fashion_search
      - weather_check
      - style_recommend
    token_limit: 500
    timeout: 60
    
  - id: "agent_top"
    category: "top"
    # ...
```

### 5.2 扩展新 Agent 类型

1. 在配置中添加 Agent 定义
2. 继承 `OutfitSubAgent` 实现子类
3. 使用 Agent Factory 注册
4. 定义私有工具集和数据源

## 6. 核心特性总结

| 特性 | 说明 |
|------|------|
| 并行处理 | 4 个 Sub Agent 同时处理不同品类 |
| Token 控制 | 压缩指令，减少 LLM token 消耗 |
| 断路器 | LLM 失败 5 次后自动熔断 |
| 重试机制 | 指数退避策略，最多重试 3 次 |
| RAG | 基于历史推荐生成上下文 |
| 私有上下文 | 每个 Agent 独立内存隔离 |
| DLQ | 失败消息进入死信队列 |
| 多轮对话 | 支持用户反馈调整推荐 |
| 结果验证 | 字段完整性 + 类型 + 合理性检查 |
