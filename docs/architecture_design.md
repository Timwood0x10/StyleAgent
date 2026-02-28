# 多Agent协作系统架构设计

## 1. 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Leader Agent                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Task Planner │  │Context Mgr  │  │ Result Aggregator       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   AHP Protocol    │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Sub Agent 1  │   │  Sub Agent 2  │   │  Sub Agent N  │
│ ┌───────────┐ │   │ ┌───────────┐ │   │ ┌───────────┐ │
│ │ Tools     │ │   │ │ Tools     │ │   │ │ Tools     │ │
│ │ Data Src  │ │   │ │ Data Src  │ │   │ │ Data Src  │ │
│ │ Context   │ │   │ │ Context   │ │   │ │ Context   │ │
│ │ Storage   │ │   │ │ Storage   │ │   │ │ Storage   │ │
│ └───────────┘ │   │ └───────────┘ │   │ └───────────┘ │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                     │
        └───────────────────┴─────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Result Validator                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Storage Layer (PostgreSQL)                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │  Vector Store   │  │   Task State   │  │  Session Store │   │
│  │  (pgvector)     │  │    (SQL)       │  │    (SQL)       │   │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 核心模块设计

### 2.1 Leader Agent 模块

```python
class LeaderAgent:
    """主Agent: 任务统筹与汇总"""
    
    def __init__(self, llm: ChatModel, task_registry: TaskRegistry):
        self.llm = llm
        self.task_registry = task_registry
        self.global_context = GlobalContext()
    
    def process(self, user_input: str) -> str:
        # 1. 理解用户意图
        # 2. 分解任务为子任务
        # 3. 分发给 Sub-Agent
        # 4. 收集结果并校验
        # 5. 汇总输出
        pass
    
    def decompose_task(self, task: str) -> List[Task]:
        """任务分解"""
        pass
    
    def aggregate_results(self, results: List[TaskResult]) -> str:
        """结果聚合"""
        pass
```

### 2.2 Sub Agent 模块

```python
class SubAgent:
    """子Agent: 独立执行子任务"""
    
    def __init__(
        self, 
        agent_id: str,
        llm: ChatModel,
        tools: List[BaseTool],
        data_sources: List[DataSource],
        private_context: PrivateContext,
        storage: AgentStorage
    ):
        self.agent_id = agent_id
        self.llm = llm
        self.tools = tools
        self.data_sources = data_sources
        self.private_context = private_context
        self.storage = storage
    
    def execute_task(self, task: Task) -> TaskResult:
        """执行任务"""
        pass
    
    def report_progress(self, progress: Progress):
        """报告进度"""
        pass
```

### 2.3 任务注册表 (Task Registry)

```python
class TaskRegistry:
    """任务注册与状态管理"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def register_task(self, task: Task) -> str:
        """注册新任务,返回task_id"""
        pass
    
    def claim_task(self, agent_id: str, task_id: str) -> bool:
        """抢单任务(确保唯一执行)"""
        pass
    
    def update_status(self, task_id: str, status: TaskStatus):
        """更新任务状态"""
        pass
    
    def get_task_status(self, task_id: str) -> TaskStatus:
        """获取任务状态"""
        pass
```

### 2.4 AHP 通信协议

```python
class AHPProtocol:
    """Agent HTTP-like Protocol"""
    
    # 请求方法
    METHOD_TASK = "TASK"      # 分发任务
    METHOD_RESULT = "RESULT"  # 返回结果
    METHOD_PROGRESS = "PROGRESS"  # 进度汇报
    METHOD_HEARTBEAT = "HEARTBEAT"  # 心跳
    
    def __init__(self, message_queue: MessageQueue):
        self.mq = message_queue
    
    def send_task(self, target_agent: str, task: Task, token_limit: int):
        """发送任务给Agent"""
        pass
    
    def receive_result(self, timeout: int = 30) -> TaskResult:
        """接收结果"""
        pass
```

### 2.5 数据存储层

```sql
-- PostgreSQL 表结构设计

-- 1. 向量存储表 (语义数据)
CREATE TABLE semantic_vectors (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50),
    content TEXT NOT NULL,
    embedding vector(1536),  -- pgvector
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. 任务状态表
CREATE TABLE tasks (
    task_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    parent_task_id UUID,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL,  -- pending/in_progress/completed/failed
    assignee_agent_id VARCHAR(50),
    result JSONB,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 3. 会话/对话历史表
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY,
    user_input TEXT NOT NULL,
    final_output TEXT,
    summary TEXT,  -- 对话摘要
    status VARCHAR(20) DEFAULT 'running',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 4. Agent 上下文表
CREATE TABLE agent_contexts (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    context_data JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_vectors_session ON semantic_vectors(session_id);
CREATE INDEX idx_vectors_embedding ON semantic_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_contexts_session_agent ON agent_contexts(session_id, agent_id);
```

## 3. 数据流设计

### 3.1 完整工作流时序图

```
User
  │
  ▼
LeaderAgent.analyze()
  │ 提取用户意图
  ▼
LeaderAgent.decompose()
  │ 拆分为 Task List
  ▼
For each task in tasks:
  │
  ├── TaskRegistry.register(task)
  │   └── 写入 pending 状态
  │
  ├── AHPProtocol.send_task(sub_agent, task, token_limit)
  │   │
  │   ▼
  │   SubAgent.execute()
  │   │ 1. 抢单 claim_task()
  │   │ 2. 更新为 in_progress
  │   │ 3. 执行工具/数据源
  │   │ 4. 定期 report_progress()
  │   │ 5. 完成写入 result
  │   │
  │   ▼
  │   AHPProtocol.receive_result()
  │
  └── TaskRegistry.update_status(completed)
  │
  ▼
ResultValidator.validate()
  │ 校验所有结果
  ▼
LeaderAgent.aggregate()
  │ 汇总输出
  ▼
StorageLayer.store()
  │ 1. 语义向量存入 pgvector
  │ 2. 任务状态更新
  │ 3. 对话摘要写入
  │
  ▼
Final Output
```

### 3.2 Token 控制流程

```
Leader 生成指令:
┌────────────────────────────────────┐
│  原始任务: "分析XX公司财务数据"    │
├────────────────────────────────────┤
│  精简指令 (Token Limit 500):       │
│  "任务: 财务分析 | 目标: XX公司    │
│   指标: 营收/利润/负债 | 格式: JSON│
│   上文: {context_hash}"            │
└────────────────────────────────────┘
              │
              ▼
Sub Agent 接收后:
1. 从 Private Context 恢复完整上下文
2. 结合精简指令执行任务
3. 仅返回结构化结果 (非完整对话)
```

## 4. 错误处理与容错

### 4.1 任务失败处理

| 失败场景 | 处理策略 |
|---------|---------|
| Sub Agent 无响应 | 超时后重新派发 (最多3次) |
| 工具执行失败 | 记录错误，尝试备选工具 |
| 结果校验失败 | 标记为 failed，返回 Leader 重试 |
| 数据库连接失败 | 降级到内存缓存，重试写入 |

### 4.2 任务状态机

```
   ┌─────────┐
   │ pending │  (创建)
   └────┬────┘
        │ claim (抢单)
        ▼
   ┌─────────┐
   │in_progress│
   └────┬────┘
        │ complete
        ▼        │ fail
   ┌─────────┐  │
   │completed│◄─┘
   └─────────┘
```

## 5. 配置与扩展

### 5.1 Agent 配置示例

```python
# sub_agent_config.yaml
agents:
  - id: "researcher"
    name: "研究Agent"
    tools:
      - search_web
      - read_file
      - write_summary
    data_sources:
      - type: "web"
      - type: "local_db"
    token_limit: 500
    timeout: 300
    
  - id: "coder"
    name: "编码Agent"
    tools:
      - read_codebase
      - write_code
      - run_tests
    data_sources:
      - type: "git"
    token_limit: 800
    timeout: 600
```

### 5.2 扩展新 Agent 类型

1. 在配置中添加 Agent 定义
2. 实现 `SubAgent` 子类
3. 注册到 Agent Factory
4. 定义私有工具集和数据源
