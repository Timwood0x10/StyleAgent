# Style Agent Framework 架构设计

## 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Input                                    │
│                    "Xiao Ming, male, 22..."                            │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Leader Agent                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ Parse Profile│  │  Task Plan   │  │  Aggregate   │                │
│  │   (LLM)      │  │  (LLM)       │  │   Results    │                │
│  └──────────────┘  └──────────────┘  └──────────────┘                │
│         │                 │                 │                           │
│         └─────────────────┼─────────────────┘                           │
│                           │                                              │
│                    dispatch tasks (并行)                                 │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  agent_top      │ │ agent_bottom    │ │  agent_head     │
│  agent_shoes    │ │    ...          │ │    ...          │
│  (Worker Actors)│ │                 │ │                 │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                  │                  │
         └──────────────────┼──────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      AHP Protocol Layer                                 │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  Message Queue (In-Memory)                                     │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │    │
│  │  │ leader  │ │agent_top│ │agent_bt │ │agent_hd │   ...        │    │
│  │  │  queue  │ │  queue  │ │  queue  │ │  queue  │              │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Message Types: TASK | RESULT | PROGRESS | ACK | HEARTBEAT            │
└─────────────────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│     Tools       │ │     LLM         │ │    Storage      │
│                 │ │                  │ │                 │
│ • fashion_search│ │ • gpt-oss:20b   │ │  • PostgreSQL   │
│ • weather_check │ │ • llama3.2:3b   │ │  • pgvector     │
│ • style_recomm  │ │                  │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
         │                                    │
         │                                    ▼
         │                        ┌─────────────────────────┐
         │                        │     Vector DB            │
         │                        │  • Sessions             │
         │                        │  • Recommendations      │
         │                        │  • Memories (RAG)       │
         │                        └─────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Memory System                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│  │ SessionMemory│  │UserMemory   │  │TaskMemory   │                    │
│  │  (短期)      │  │ (长期)       │  │ (蒸馏)       │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 消息流转机制

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     消息生命周期 (Message Lifecycle)                     │
└─────────────────────────────────────────────────────────────────────────┘

   [发送]                    [队列]                     [接收/处理]
   
┌─────────┐              ┌─────────┐                ┌─────────┐
│ Leader  │  TASK       │  MQ     │                │ Sub     │
│         │ ─────────▶  │         │  ─────────▶    │  Agent  │
│         │              │         │                │         │
│         │ ◀─────────  │         │ ◀─────────     │         │
└─────────┘   RESULT    └─────────┘    ACK         └─────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  消息类型 (Message Types)                                                │
├─────────────────────────────────────────────────────────────────────────┤
│  TASK     │ 派发任务          │ Leader  → Sub Agent                    │
│ RESULT    │ 返回结果          │ Sub Agent → Leader                     │
│ PROGRESS  │ 进度汇报          │ Sub Agent → Leader                     │
│ ACK       │ 确认收到          │ Sub Agent → Leader                     │
│ HEARTBEAT │ 心跳保活          │ All Agents                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 任务生产消费流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     任务生产-消费模型                                     │
└─────────────────────────────────────────────────────────────────────────┘

                          Leader Agent (Producer)
                                 │
                                 │ 1. 解析用户输入
                                 ▼
                        ┌─────────────────┐
                        │  Parse Profile  │
                        │   (UserProfile) │
                        └────────┬────────┘
                                 │
                                 │ 2. LLM 决策需要哪些 agent
                                 ▼
                        ┌─────────────────┐
                        │ Determine Tasks │
                        │ [top, bottom]   │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
        ┌──────────┐       ┌──────────┐       ┌──────────┐
        │Task Queue│       │Task Queue│       │Task Queue│
        │ agent_top│       │agent_btm │       │   ...    │
        └────┬─────┘       └────┬─────┘       └────┬─────┘
             │                   │                  │
             │    ┌──────────────┴──────────────┐   │
             │    │     Phase 1: 并行派发        │   │
             │    │  ThreadPoolExecutor          │   │
             │    └─────────────────────────────┘   │
             │                                      │
             ▼                                      ▼
       ┌──────────┐                          ┌──────────┐
       │Sub Agent │                          │Sub Agent │
       │ (Consumer)                          │ (Consumer)│
       │             ┌──────────────────────┘          │
       │             │                                   │
       │             │ 3. 处理任务                        │
       │             ▼                                   │
       │    ┌─────────────────┐                         │
       │    │  Execute Task   │                         │
       │    │  ┌───────────┐  │                         │
       │    │  │  Tools    │  │                         │
       │    │  │  (RAG)   │  │                         │
       │    │  │  LLM     │  │                         │
       │    │  └───────────┘  │                         │
       │    └────────┬────────┘                         │
       │             │                                   │
       │             │ 4. 返回结果                       │
       │             ▼                                   │
       │    ┌─────────────────┐                         │
       │    │  Send RESULT    │ ◀───────────────────────┘
       │    │  to Leader     │
       │    └────────┬────────┘
       │             │
       │    ┌────────┴────────┐
       │    │  Phase 2:       │
       │    │  依赖感知的任务  │
       │    │  (top结果给shoes)│
       │    └────────┬────────┘
       │             │
       │             ▼
       │    ┌─────────────────┐
       │    │  Coordination   │
       │    │  Context        │
       │    └────────┬────────┘
       │             │
       └─────────────┘
       
                       
       Leader (Aggregator)
              │
              │ 5. 聚合所有结果
              ▼
       ┌─────────────────┐
       │ Aggregate       │
       │ [top+bottom+    │
       │  head+shoes]   │
       └────────┬────────┘
                │
                ▼
       ┌─────────────────┐
       │ Final Output    │
       │ + Save to DB   │
       └─────────────────┘
```

---

## Actor 模型对应关系

| Actor 模型概念 | iFlow 实现 |
|----------------|-----------|
| Actor | `LeaderAgent`, `OutfitSubAgent` |
| Mailbox | `MessageQueue` (In-Memory) |
| Message | `AHPMessage` (TASK/RESULT/PROGRESS/ACK) |
| Behavior | Agent 内部的 `_handle_task()`, `_recommend()` |
| Supervisor | `LeaderAgent` 协调多个 Sub Agent |
| Failure Handling | DLQ (Dead Letter Queue) |

---

## 关键设计点

| 特性 | 实现方式 |
|------|----------|
| **并发模型** | `ThreadPoolExecutor` 派发任务到多个 Sub Agent |
| **通信协议** | In-Memory Message Queue + AHP 自定义协议 |
| **状态管理** | `SessionMemory` 短期会话 + `TaskMemory` 蒸馏 |
| **容错机制** | DLQ 存储失败消息，支持重试 |
| **任务协调** | Phase 1 (并行) → Phase 2 (依赖感知) |
| **扩展性** | 可动态注册新的 Agent 类型 |

---

## 目录结构

```
src/
├── agents/
│   ├── leader_agent.py      # Coordinator Actor
│   ├── sub_agent.py         # Worker Actor
│   └── resources.py         # Tools (fashion_search, weather, style)
├── protocol/
│   └── ahp.py              # AHP Protocol (消息定义与队列)
├── core/
│   ├── models.py           # 数据模型
│   ├── errors.py            # 错误定义
│   └── registry.py          # Agent 注册表
├── storage/
│   └── postgres.py         # PostgreSQL + pgvector
└── utils/
    ├── llm.py              # LLM 封装 (支持 Ollama)
    ├── context.py           # Memory System
    └── config.py            # 配置管理
```

---

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 语言 | Python 3.13 |
| LLM | Ollama (gpt-oss:20b / llama3.2:3b) |
| 协议 | AHP (自定义) |
| 存储 | PostgreSQL + pgvector |
| 并发 | ThreadPoolExecutor |
| 消息队列 | In-Memory (asyncio.Queue) |

---

## 消息格式 (AHP Protocol)

```python
class AHPMessage:
    message_id: str
    method: AHPMethod        # TASK, RESULT, PROGRESS, ACK, HEARTBEAT
    agent_id: str            # 发送方
    target_agent: str        # 接收方
    task_id: str             # 任务ID
    session_id: str          # 会话ID
    payload: Dict             # 消息内容
    timestamp: datetime
```

---

