# Memory Distillation

## Overview

Memory Distillation is a module that converts conversation history into structured memories, persists them to pgvector for cross-session retrieval, and supports memory type separation.

## Core Concepts

### 1. Structured Memory Format

The distillation output is now in structured JSON format:

```json
{
    "user_profile": {"key": "value"},
    "decisions_made": [{"key": "unique_id", "description": "description"}],
    "pending_tasks": [{"task_id": "unique_id", "description": "description"}],
    "important_facts": ["fact1", "fact2"]
}
```

- **user_profile**: Long-term user attributes (style preference, budget, etc.)
- **decisions_made**: Decisions already made with unique keys to avoid duplicates
- **pending_tasks**: Unfinished important tasks
- **important_facts**: Other important facts not suitable for above categories

### 2. Distill Level (Prevent Recursive Degradation)

To prevent information loss from multiple distillations:

- Each memory has a `distill_level` field (1, 2, 3)
- Maximum level is 3 - memories above this level won't be distilled again
- This ensures information quality doesn't degrade over time

### 3. Importance Filtering

Before distillation, conversations are evaluated for importance:

- Only conversations containing long-term valid information are distilled
- Long-term info includes: user preferences, identity info, key decisions
- Reduces noise in long-term memory

### 4. Memory Type Separation

Two types of memory are maintained separately:

| Type | Description | Cross-session |
|------|-------------|---------------|
| user_memory | User preferences, budget, style | ✅ Yes |
| task_memory | Current task progress | ❌ No |

## Usage

### Basic Usage

```python
from src.utils import SessionMemory, LocalLLM
from src.storage import get_storage

# Initialize
session_memory = SessionMemory(
    session_id="uuid",
    llm=your_llm,
    storage=get_storage(),
    agent_id="leader"
)

# Add conversation
session_memory.add_user_turn("I want to buy a coat", "What's your budget?")
session_memory.add_user_turn("Around 500", "推荐这款...")

# Get distilled context (auto-distills when threshold exceeded)
context = session_memory.get_context()

# Get user profile
profile = session_memory.get_user_profile()
# {"style_preference": "casual", "budget": "500"}

# Get pending tasks
tasks = session_memory.get_pending_tasks()
```

### Separate User/Task Memory

```python
# Add user conversation
session_memory.add_user_turn("user input", "assistant response")

# Add task context
session_memory.add_task_context("Task: Recommend outfit - Status: 80% complete")

# Get specific memory type
user_context = session_memory.get_user_context()
task_context = session_memory.get_task_context()
```

### Search Similar Memories

```python
# Search in user_memory
results = session_memory.search_memory("user preferences", memory_type="user_memory")

# Search in task_memory
results = session_memory.search_memory("outfit recommendation", memory_type="task_memory")

# Search both
results = session_memory.search_memory("budget")
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| max_tokens | 4000 | Maximum tokens before distillation |
| distill_threshold | 0.8 | Threshold (0.0-1.0) to trigger distillation |
| keep_recent | 4 | Number of recent turns to keep intact |
| enable_importance_filter | True | Whether to filter by importance |

```python
session_memory = SessionMemory(
    session_id="uuid",
    llm=llm,
    storage=storage,
    max_tokens=2000,  # Smaller threshold
    enable_importance_filter=False  # Disable filtering
)
```

## Database Schema

```sql
CREATE TABLE memory_summaries (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    summary JSONB NOT NULL,  -- Structured JSON
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

## API Reference

### SessionMemory

| Method | Description |
|--------|-------------|
| `add_user_turn(user_input, assistant_response)` | Add conversation turn |
| `add_task_context(task_info)` | Add task context |
| `get_context()` | Get combined context |
| `get_user_context()` | Get user memory only |
| `get_task_context()` | Get task memory only |
| `get_user_profile()` | Get user profile from memory |
| `get_pending_tasks()` | Get pending tasks |
| `search_memory(query, memory_type, limit)` | Search similar memories |
| `clear()` | Clear all memory |

### MemoryDistiller

| Method | Description |
|--------|-------------|
| `set_session(session_id)` | Set session ID |
| `set_memory_type(type)` | Set memory type (user_memory/task_memory) |
| `add_user(content)` | Add user message |
| `add_assistant(content)` | Add assistant message |
| `should_distill()` | Check if distillation needed |
| `distill()` | Trigger distillation |
| `get_context()` | Get distilled context |
| `search_similar_memories(query, limit)` | Search similar memories |

### StructuredMemory

| Method | Description |
|--------|-------------|
| `to_dict()` | Convert to dictionary |
| `to_json()` | Convert to JSON string |
| `from_dict(data)` | Create from dictionary |
| `from_json(json_str)` | Create from JSON string |
| `merge(other)` | Merge another memory |