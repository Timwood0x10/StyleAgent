# Multi-Agent Collaboration System Technical Summary

## 1. System Overview

This system designs a multi-Agent collaboration pattern, implementing intelligent task decomposition, parallel execution, and unified aggregation. The system adopts a **Leader-SubAgent** architecture, using an HTTP-like protocol for Agent interaction, supporting task isolation, status tracking, and result validation.

## 2. Core Technology Stack

- **Language**: Python 3.13+
- **Agent Framework**: LangChain (LCEL expressions, ChatModel)
- **Database**: PostgreSQL + pgvector (Vector storage + State storage)
- **Communication Protocol**: Custom Agent HTTP-like Protocol (AHP)

## 3. Core Design Concepts

### 3.1 Leader Agent
- **Responsibility**: Task coordination, decomposition, aggregation
- **Features**:
  - Holds global context (Global Context)
  - Maintains task table (Task Registry)
  - Sends compact token instructions to Sub-Agent
  - Result aggregation and validation

### 3.2 Sub Agent
- **Responsibility**: Execute specific subtasks
- **Features**:
  - Independent toolset (Tools)
  - Independent data sources (Data Sources)
  - Independent context (Private Context)
  - Independent storage resources (Storage)
  - Regular progress feedback

### 3.3 Task Isolation Mechanism
- Each task has a unique ID (UUID)
- Task status: `pending` | `in_progress` | `completed` | `failed`
- Task locking: Claim mechanism prevents duplicate execution

### 3.4 Agent Communication Protocol (AHP)

| Method | Direction | Description |
|--------|-----------|-------------|
| `TASK` | Leader → Sub | Dispatch task |
| `RESULT` | Sub → Leader | Return result |
| `PROGRESS` | Sub → Leader | Progress report |
| `HEARTBEAT` | Bidirectional | Heartbeat detection |

### 3.5 Data Storage Strategy

| Data Type | Storage Method | Purpose |
|-----------|----------------|---------|
| Semantic Vectors | pgvector (PostgreSQL) | Semantic retrieval, similarity matching |
| Dialogue Summaries | PostgreSQL | Context recovery, audit tracing |
| Task Status | PostgreSQL | Task tracking, progress monitoring |
| Agent Memory | Each Agent's private storage | Independent context |

## 4. Workflow

```
User Input
  │
  ▼
Leader Agent (Intent understanding + Task decomposition)
  │
  ▼
[Task 1] [Task 2] [Task 3] ... (Parallel/Serial)
  │
  ▼
Sub Agents execute in parallel (via AHP protocol)
  │
  ▼
Result Validator (Validate all results)
  │
  ▼
Leader Agent (Aggregate output)
  │
  ▼
Storage Layer (Store to pgvector + Update status)
```

## 5. Key Features

- **Token Optimization**: Leader passes only necessary instructions, avoids context leakage
- **Isolated Execution**: No shared state between tasks, no interference
- **Scalability**: Easy to add new Agent types
- **Observability**: Complete task chain tracking
- **Fault Tolerance**: Retry on failure, degradation handling

## 6. Dependent Services

- PostgreSQL 15+ (requires pgvector extension enabled)
- Optional: LangChain supported LLM (OpenAI/Anthropic/Local models)

## 7. Subsequent Chapters

- [Architecture Design Document](./architecture_design.md): Detailed module design and data flow
- [Implementation Code](./src/): Complete Python implementation
