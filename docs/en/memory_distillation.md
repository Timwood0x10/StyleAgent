# Memory Distillation

## Overview

Memory Distillation is a technique for compressing long-term conversation history into concise, key information summaries. It addresses the token limit challenge in LLM conversations by:

1. **Detecting when distillation is needed** - Monitors token usage and triggers distillation when threshold is reached
2. **Extracting key information** - Uses LLM to distill important details (user preferences, decisions, context)
3. **Persisting to vector database** - Stores distilled memories in pgvector for cross-session retrieval
4. **Retrieving relevant memories** - Enables semantic search of historical distilled memories

## Why Memory Distillation?

### Problem
- LLMs have context window limits (e.g., 4K, 8K, 32K tokens)
- Long conversations exceed these limits
- Simply truncating loses important information

### Solution: Distillation
Instead of losing information, we:
1. Keep recent N turns as-is (full context)
2. Compress earlier turns into concise summaries using LLM
3. Store summaries in vector database for retrieval

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│                    SessionMemory                        │
│  (Manages distillation for a session)                  │
├─────────────────────────────────────────────────────────┤
│                  MemoryDistiller                        │
│  - Tracks conversation history                          │
│  - Estimates token usage                               │
│  - Triggers LLM-based distillation                     │
│  - Persists to StorageLayer                            │
├─────────────────────────────────────────────────────────┤
│                   StorageLayer                         │
│  - PostgreSQL + pgvector                               │
│  - save_distilled_memory()                             │
│  - get_distilled_memories()                            │
│  - search_similar_memories()                           │
└─────────────────────────────────────────────────────────┘
```

### Database Schema

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

## Usage

### Basic Usage

```python
from src.utils import SessionMemory, LocalLLM
from src.storage import get_storage

# Initialize
llm = LocalLLM()
storage = get_storage()
session_memory = SessionMemory(
    session_id="user-123",
    llm=llm,
    storage=storage,
    agent_id="leader",
    max_tokens=4000
)

# Add conversation turns
session_memory.add_user_turn("我想买一件外套", "好的，请问您的预算是多少？")
session_memory.add_user_turn("500左右", "推荐这款...")
session_memory.add_user_turn("还有其他款式吗", "当然，这里有...")

# Get distilled context (auto-distills if threshold exceeded)
context = session_memory.get_context()
```

### Manual Distillation

```python
# Manual trigger
session_memory.distiller.distill()

# Async version
await session_memory.distiller.adistill()
```

### Search Similar Memories

```python
# Search for relevant historical memories
results = session_memory.search_memory("用户偏好")
for r in results:
    print(f"- {r['summary']} (similarity: {r['similarity']})")
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_tokens` | 4000 | Maximum tokens before distillation |
| `distill_threshold` | 0.8 | Threshold (0-1) to trigger distillation |
| `keep_recent` | 4 | Number of recent turns to keep intact |

### Tuning

```python
# More aggressive distillation
session_memory = SessionMemory(
    max_tokens=2000,       # Smaller context window
    distill_threshold=0.6,  # Trigger earlier
    keep_recent=2          # Keep fewer recent turns
)
```

## How Distillation Works

### Step-by-Step Flow

```
Conversation History:
[User1] → [Assistant1] → [User2] → [Assistant2] → [User3] → [Assistant3] → [User4] → [Assistant4] → [User5]

Threshold exceeded (>80% of max_tokens)
           │
           ▼
┌─────────────────────────────────────┐
│  1. Split:                          │
│     - To Distill: User1-Assistant3  │
│     - Keep: User4-Assistant4       │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  2. LLM Distillation Prompt:        │
│  "Summarize key info:               │
│   - User preferences                │
│   - Important decisions             │
│   - Uncompleted tasks               │
│   - Critical context                │
│  Keep in Chinese."                  │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  3. LLM Output (Summary):           │
│  "用户偏好休闲风格，预算500左右，     │
│   已推荐外套款式，正在挑选中..."      │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  4. Persist to pgvector:            │
│  - Save summary text                │
│  - Generate embedding               │
│  - Store with metadata              │
└─────────────────────────────────────┘
           │
           ▼
Final Context:
┌─────────────────────────────────────┐
│ [Distilled Memory]                  │
│ 用户偏好休闲风格，预算500左右...     │
├─────────────────────────────────────┤
│ [Recent Turns]                      │
│ User4: 还有其他款式吗               │
│ Assistant: 当然，这里有...           │
└─────────────────────────────────────┘
```

## Benefits

1. **Token Efficiency**: Compresses 4000+ tokens into ~200 token summaries
2. **Information Retention**: Preserves key preferences and decisions
3. **Cross-Session Persistence**: Memories survive restarts
4. **Semantic Retrieval**: Find relevant historical context via vector search
5. **Automatic**: Happens transparently, no manual intervention needed

## Integration with Agents

### Leader Agent Integration

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
        # Add to memory
        self.session_memory.add_user_turn(user_input)
        
        # Get distilled context for LLM
        context = await self.session_memory.aget_context()
        
        # Use in LLM prompt
        response = await self.llm.ainvoke(
            prompt=f"Context: {context}\n\nUser: {user_input}"
        )
        
        self.session_memory.add_system_turn(response)
        return response
```

## Error Handling

- **No LLM**: Distillation skipped, continues with existing context
- **No Storage**: In-memory only, no persistence
- **LLM Failure**: Logs error, keeps original context
- **Empty History**: No distillation performed

## Performance Considerations

- Distillation adds latency (~1-2s per LLM call)
- Embedding generation adds ~0.5s
- Vector search is fast (<100ms)
- Consider async distillation for better UX
