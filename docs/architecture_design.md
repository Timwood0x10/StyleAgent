# Multi-Agent Collaboration System Architecture Design

## 1. System Architecture Diagram

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

## 2. Core Module Design

### 2.1 Leader Agent Module

```python
class LeaderAgent:
    """Main Agent: Task Coordination and Aggregation"""
    
    def __init__(self, llm: ChatModel, task_registry: TaskRegistry):
        self.llm = llm
        self.task_registry = task_registry
        self.global_context = GlobalContext()
    
    def process(self, user_input: str) -> str:
        # 1. Understand user intent
        # 2. Decompose task into subtasks
        # 3. Dispatch to Sub-Agent
        # 4. Collect and validate results
        # 5. Aggregate output
        pass
    
    def decompose_task(self, task: str) -> List[Task]:
        """Task decomposition"""
        pass
    
    def aggregate_results(self, results: List[TaskResult]) -> str:
        """Result aggregation"""
        pass
```

### 2.2 Sub Agent Module

```python
class SubAgent:
    """Sub Agent: Independent subtask execution"""
    
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
        """Execute task"""
        pass
    
    def report_progress(self, progress: Progress):
        """Report progress"""
        pass
```

### 2.3 Task Registry

```python
class TaskRegistry:
    """Task registration and status management"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def register_task(self, task: Task) -> str:
        """Register new task, return task_id"""
        pass
    
    def claim_task(self, agent_id: str, task_id: str) -> bool:
        """Claim task (ensure unique execution)"""
        pass
    
    def update_status(self, task_id: str, status: TaskStatus):
        """Update task status"""
        pass
    
    def get_task_status(self, task_id: str) -> TaskStatus:
        """Get task status"""
        pass
```

### 2.4 AHP Communication Protocol

```python
class AHPProtocol:
    """Agent HTTP-like Protocol"""
    
    # Request methods
    METHOD_TASK = "TASK"      # Dispatch task
    METHOD_RESULT = "RESULT"  # Return result
    METHOD_PROGRESS = "PROGRESS"  # Progress report
    METHOD_HEARTBEAT = "HEARTBEAT"  # Heartbeat
    
    def __init__(self, message_queue: MessageQueue):
        self.mq = message_queue
    
    def send_task(self, target_agent: str, task: Task, token_limit: int):
        """Send task to Agent"""
        pass
    
    def receive_result(self, timeout: int = 30) -> TaskResult:
        """Receive result"""
        pass
```

### 2.5 Data Storage Layer

```sql
-- PostgreSQL table design

-- 1. Vector storage table (semantic data)
CREATE TABLE semantic_vectors (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50),
    content TEXT NOT NULL,
    embedding vector(1536),  -- pgvector
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Task status table
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

-- 3. Session/dialogue history table
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY,
    user_input TEXT NOT NULL,
    final_output TEXT,
    summary TEXT,  -- Dialogue summary
    status VARCHAR(20) DEFAULT 'running',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 4. Agent context table
CREATE TABLE agent_contexts (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    context_data JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_vectors_session ON semantic_vectors(session_id);
CREATE INDEX idx_vectors_embedding ON semantic_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_contexts_session_agent ON agent_contexts(session_id, agent_id);
```

## 3. Data Flow Design

### 3.1 Complete Workflow Sequence Diagram

```
User
  │
  ▼
LeaderAgent.analyze()
  │ Extract user intent
  ▼
LeaderAgent.decompose()
  │ Decompose into Task List
  ▼
For each task in tasks:
  │
  ├── TaskRegistry.register(task)
  │   └── Write pending status
  │
  ├── AHPProtocol.send_task(sub_agent, task, token_limit)
  │   │
  │   ▼
  │   SubAgent.execute()
  │   │ 1. Claim task()
  │   │ 2. Update to in_progress
  │   │ 3. Execute tools/data sources
  │   │ 4. Periodically report_progress()
  │   │ 5. Complete write result
  │   │
  │   ▼
  │   AHPProtocol.receive_result()
  │
  └── TaskRegistry.update_status(completed)
  │
  ▼
ResultValidator.validate()
  │ Validate all results
  ▼
LeaderAgent.aggregate()
  │ Aggregate output
  ▼
StorageLayer.store()
  │ 1. Store semantic vectors to pgvector
  │ 2. Update task status
  │ 3. Write dialogue summary
  │
  ▼
Final Output
```

### 3.2 Token Control Flow

```
Leader generates instruction:
┌────────────────────────────────────┐
│  Original task: "Analyze XX company"│
├────────────────────────────────────┤
│  Compact instruction (Token Limit 500): │
│  "Task: Financial analysis | Target: XX │
│   Metrics: Revenue/Profit/Debt | Format: JSON│
│   Context: {context_hash}"            │
└────────────────────────────────────┘
              │
              ▼
After Sub Agent receives:
1. Restore complete context from Private Context
2. Execute task with compact instruction
3. Return only structured results (not full dialogue)
```

## 4. Error Handling and Fault Tolerance

### 4.1 Task Failure Handling

| Failure Scenario | Handling Strategy |
|---------|---------|
| Sub Agent not responding | Re-dispatch after timeout (max 3 times) |
| Tool execution failed | Log error, try alternative tool |
| Result validation failed | Mark as failed, return to Leader for retry |
| Database connection failed | Degrade to memory cache, retry write |

### 4.2 Task State Machine

```
   ┌─────────┐
   │ pending │  (created)
   └────┬────┘
        │ claim
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

## 5. Configuration and Extension

### 5.1 Agent Configuration Example

```python
# sub_agent_config.yaml
agents:
  - id: "researcher"
    name: "Research Agent"
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
    name: "Coding Agent"
    tools:
      - read_codebase
      - write_code
      - run_tests
    data_sources:
      - type: "git"
    token_limit: 800
    timeout: 600
```

### 5.2 Extending New Agent Types

1. Add Agent definition in configuration
2. Implement `SubAgent` subclass
3. Register with Agent Factory
4. Define private toolset and data sources