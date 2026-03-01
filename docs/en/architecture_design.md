# iFlow Multi-Agent Outfit Recommendation System Architecture

## 1. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                     │
│              examples/demo_interactive.py                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Leader Agent (Main Agent)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐│
│  │ User Profile│  │   Task      │  │   Result Aggregator     ││
│  │   Parser    │  │ Decomposer  │  │   + RAG Storage         ││
│  │ Context Enh.│  │  Category   │  │                         ││
│  └─────────────┘  └─────────────┘  └─────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │        Error Handling: Retry Handler + Circuit Breaker     ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   AHP Protocol    │
                    │  (Message Queue   │
                    │   + Token Ctrl)  │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Sub Agent 1  │   │  Sub Agent 2  │   │  Sub Agent N  │
│  (head acc.)  │   │  (top)        │   │  (more...)    │
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
│                    Result Validator                             │
│        Field Check │ Type Validation │ Reasonableness │ Auto-fix│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Storage Layer (PostgreSQL + pgvector)           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Semantic       │  │   Task          │  │   Session        │ │
│  │  Vectors (RAG)  │  │   Registry      │  │   Store          │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  Tables: user_profiles | outfit_recommendations | semantic_vectors│
│         tasks | sessions | agent_contexts | task_progress       │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Core Module Design

### 2.1 Leader Agent Module

```python
class LeaderAgent:
    """Main Agent: Task Coordination and Result Aggregation"""
    
    def __init__(self, llm: ChatModel):
        self.llm = llm
        self.validator = ResultValidator()
        self.registry = TaskRegistry()
        self.circuit_breaker = CircuitBreaker()
        self.retry_handler = RetryHandler()
    
    def process(self, user_input: str) -> OutfitResult:
        # 1. Parse user profile
        # 2. Analyze task categories
        # 3. Create and dispatch tasks
        # 4. Collect and validate results
        # 5. Aggregate output
        pass
    
    def parse_user_profile(self, user_input: str) -> UserProfile:
        """Parse user input to extract user profile"""
        pass
    
    def create_tasks(self, user_profile: UserProfile) -> List[OutfitTask]:
        """Task decomposition, determine recommendation categories"""
        pass
    
    def aggregate_results(self, ...) -> OutfitResult:
        """Result aggregation and validation"""
        pass
```

### 2.2 Sub Agent Module

```python
class OutfitSubAgent:
    """Sub Agent: Independent category recommendation execution"""
    
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
        """Execute recommendation: Tools + RAG + LLM"""
        pass
    
    def _get_rag_context(self, profile: UserProfile) -> str:
        """Get historical similar recommendations as context"""
        pass
```

### 2.3 AHP Communication Protocol

```python
class AHPProtocol:
    """Agent HTTP-like Protocol - Agent Communication Protocol"""
    
    # Message Methods
    METHOD_TASK = "TASK"         # Dispatch task
    METHOD_RESULT = "RESULT"     # Return result
    METHOD_PROGRESS = "PROGRESS" # Progress report
    METHOD_HEARTBEAT = "HEARTBEAT"  # Heartbeat
    METHOD_ACK = "ACK"           # Acknowledgment
    
    # Features
    - MessageQueue
    - Token Controller
    - DLQ (Dead Letter Queue)
    - Deduplication
```

### 2.4 Task Registry

```python
class TaskRegistry:
    """Task Registration and Status Management"""
    
    def register_task(self, session_id, title, description, category) -> str:
        """Register new task"""
        pass
    
    def claim_task(self, agent_id, task_id) -> bool:
        """Claim task (ensure unique execution)"""
        pass
    
    def update_status(self, task_id, status, result):
        """Update task status"""
        pass
```

### 2.5 Data Storage Layer

```sql
-- PostgreSQL Table Design

-- 1. User Profiles Table
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

-- 2. Outfit Recommendations Table
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

-- 3. Semantic Vectors Table (RAG)
CREATE TABLE semantic_vectors (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50),
    content TEXT NOT NULL,
    embedding vector(1536),  -- pgvector
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. Tasks Table
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

-- 5. Sessions Table
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY,
    user_input TEXT NOT NULL,
    final_output TEXT,
    summary TEXT,
    status VARCHAR(20) DEFAULT 'running',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 6. Agent Contexts Table
CREATE TABLE agent_contexts (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    context_data JSONB,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, agent_id)
);

-- Indexes
CREATE INDEX idx_vectors_session ON semantic_vectors(session_id);
CREATE INDEX idx_vectors_embedding ON semantic_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_contexts_session_agent ON agent_contexts(session_id, agent_id);
```

## 3. Subsystem Details

### 3.1 Tools

Each Sub Agent is equipped with the following tools:

| Tool | Function |
|------|----------|
| FashionSearchTool | Search fashion suggestions based on mood/occupation/season |
| WeatherCheckTool | Get weather information and suggestions |
| StyleRecommendTool | Get style recommendations and pairing suggestions |

### 3.2 Data Sources

| Data Source | Function |
|-------------|----------|
| FashionDatabase | Fashion database (trending colors, styles, age groups) |
| UserHistoryDB | User historical recommendation records |

### 3.3 Private Context

- Independent memory storage for each Agent
- Session-level data isolation
- Can persist to database

### 3.4 RAG Context Enhancement

- Generate query vector based on user profile
- Search similar historical recommendations in vector DB
- Provide historical recommendations as context to LLM

## 4. Error Handling and Fault Tolerance

### 4.1 Retry Mechanism (RetryHandler)

- Exponential backoff algorithm
- Configurable max retry count
- Specifiable retryable error types

### 4.2 Circuit Breaker (CircuitBreaker)

```
Closed (Normal) ──5 failures──> Open (Tripped)
                                      │
                                      ▼ (60s timeout)
                                 Half-Open (Testing)
                                      │
                                      ▼ (success)
                                 Closed (Recovered)
```

### 4.3 Dead Letter Queue (DLQ)

- Failed messages enter DLQ
- Can query and analyze failure reasons
- Support manual retry

## 5. Configuration and Extension

### 5.1 Agent Configuration Example

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

### 5.2 Extending New Agent Types

1. Add Agent definition in configuration
2. Inherit `OutfitSubAgent` to implement subclass
3. Register with Agent Factory
4. Define private toolset and data sources

## 6. Core Features Summary

| Feature | Description |
|---------|-------------|
| Parallel Processing | 4 Sub Agents process different categories simultaneously |
| Token Control | Compress instructions, reduce LLM token consumption |
| Circuit Breaker | Auto trip after 5 LLM failures |
| Retry Mechanism | Exponential backoff, max 3 retries |
| RAG | Generate context from historical recommendations |
| Private Context | Each Agent has independent memory isolation |
| DLQ | Failed messages enter dead letter queue |
| Multi-turn | Support user feedback for recommendation adjustment |
| Result Validation | Field completeness + type + reasonableness check |
