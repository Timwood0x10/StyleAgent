# AHP Protocol Specification

## Overview

The AHP (Agent HTTP-like Protocol) is a lightweight inter-agent communication protocol designed for the  multi-agent system. It provides reliable message delivery, task distribution, and result collection between the Leader Agent and multiple Sub Agents.

## Architecture

```
┌─────────────┐         AHP Protocol         ┌─────────────┐
│             │  ┌─────────────────────┐    │             │
│   Leader    │──│  Message Queue       │───▶│   Sub Agent │
│   Agent     │  │  (with ACK/DLQ)     │    │   (head)    │
│             │  └─────────────────────┘    │             │
└─────────────┘                              └─────────────┘
       │                                           │
       │              AHP Protocol                 │
       │  ┌─────────────────────┐                  │
       │  │  Task: recommend    │◀──────────────────┤
       │  │  ACK: received     │───────────────────▶│
       │  │  RESULT: items     │◀───────────────────│
       │  └─────────────────────┘                  │
       │                                           │
       ▼                                           ▼
┌─────────────────────────────────────────────────────┐
│              Message Flow                           │
│  1. TASK (Leader → Sub)                             │
│  2. ACK (Sub → Leader)                              │
│  3. PROGRESS (Sub → Leader)                        │
│  4. RESULT (Sub → Leader)                          │
└─────────────────────────────────────────────────────┘
```

## Message Types

| Method             | Direction     | Description                |
| ------------------ | ------------- | -------------------------- |
| `TASK`           | Leader → Sub | Dispatch task to sub-agent |
| `ACK`            | Bidirectional | Message acknowledgment     |
| `RESULT`         | Sub → Leader | Return task result         |
| `PROGRESS`       | Sub → Leader | Progress report            |
| `HEARTBEAT`      | Bidirectional | Health check               |
| `TOKEN_REQUEST`  | Sub → Leader | Token quota request        |
| `TOKEN_RESPONSE` | Leader → Sub | Token quota response       |

## Message Format

```python
@dataclass
class AHPMessage:
    method: str           # TASK / RESULT / PROGRESS / HEARTBEAT / ACK
    agent_id: str         # Source Agent ID
    target_agent: str     # Target Agent ID
    task_id: str          # Task ID
    session_id: str       # Session ID
    payload: Dict         # Message payload
    token_limit: int      # Token limit for LLM
    timestamp: datetime   # Message timestamp
    message_id: str       # Unique message ID (auto-generated)
```

## Error Handling

### Error Codes

| Code                      | Description              |
| ------------------------- | ------------------------ |
| `UNKNOWN`               | Unknown error            |
| `INVALID_MESSAGE`       | Invalid message format   |
| `TIMEOUT`               | Operation timeout        |
| `AGENT_NOT_FOUND`       | Target agent not found   |
| `QUEUE_FULL`            | Message queue is full    |
| `SERIALIZATION_ERROR`   | Serialization failed     |
| `DESERIALIZATION_ERROR` | Deserialization failed   |
| `RETRY_EXHAUSTED`       | Maximum retries exceeded |

### AHPError Class

```python
class AHPError(Exception):
    def __init__(
        self,
        message: str,
        code: AHPErrorCode = AHPErrorCode.UNKNOWN,
        agent_id: str = "",
        task_id: str = "",
        details: Dict[str, Any] = None,
    ):
        # Contains: message, code, agent_id, task_id, details
```

## Advanced Features

### 1. Message Acknowledgment (ACK)

The protocol ensures reliable message delivery through ACK messages:

- **Auto-ACK**: `AHPReceiver` automatically sends ACK for TASK/RESULT/PROGRESS messages
- **ACK Payload**: Contains `original_message_id` and `ack_status`
- **Timeout**: Configurable receive timeout

```python
# Send ACK
sender.send_ack(
    target_agent="head",
    session_id="session_123",
    original_message_id="msg_456",
    status="received"
)
```

### 2. Dead Letter Queue (DLQ)

Failed messages are moved to DLQ for investigation:

```python
# Move to DLQ
mq.to_dlq(agent_id, message, error_message)

# Get DLQ contents
dlq = mq.get_dlq(agent_id="head")

# Clear DLQ
mq.clear_dlq(agent_id="head")
```

### 3. Message Deduplication

Messages are deduplicated using `message_id`:

```python
# Duplicate messages are automatically filtered
mq.send(agent_id, message)  # First send - succeeds
mq.send(agent_id, message)  # Duplicate - filtered out
```

### 4. Retry Mechanism

Configurable retry for failed messages:

```python
mq = MessageQueue(max_retries=3, retry_delay=1.0)

# Check if should retry
if mq.should_retry(message_id):
    mq.increment_retry(message_id)

# Reset retry count
mq.reset_retry(message_id)
```

### 5. Token Control

The `TokenController` manages token limits for sub-agents:

```python
tc = TokenController(default_limit=500)
tc.set_limit("head", 300)

# Create compact instruction
instruction = tc.create_compact_instruction(
    user_profile={"name": "User", "age": 25},
    task={"category": "head", "instruction": "recommend hat"},
    max_tokens=300
)
```

## Integration with Agents

### Leader Agent

```python
from src.protocol import AHPSender, AHPError, AHPErrorCode

# Send task with error handling
try:
    sender.send_task(
        target_agent="head",
        task_id="task_123",
        session_id="session_456",
        payload={"category": "head", "user_info": {...}},
        token_limit=500
    )
except AHPError as e:
    mq.to_dlq(target_agent, None, str(e))
```

### Sub Agent

```python
from src.protocol import AHPReceiver, AHPError

# Receive with auto-ACK
msg = receiver.receive(timeout=30, auto_ack=True)

# Handle errors
try:
    result = process_task(msg)
    sender.send_result("leader", task_id, session_id, result)
except Exception as e:
    mq.to_dlq(agent_id, msg, str(e))
```

## Configuration

AHP configuration is managed via `config.yaml`:

```yaml
ahp:
  token_limit: 500
  task_timeout: 60
  heartbeat_interval: 30
  max_retries: 3
```

## Testing

Run AHP protocol tests:

```bash
pytest tests/test_ahp.py -v
```

Test coverage includes:

- Message serialization/deserialization
- ACK message handling
- DLQ operations
- Retry mechanism
- Error handling

## Best Practices

1. **Always handle ACKs**: Wait for acknowledgment before considering a task complete
2. **Use DLQ monitoring**: Regularly check DLQ for failed messages
3. **Configure timeouts appropriately**: Balance between responsiveness and reliability
4. **Implement retry logic**: Use the retry mechanism for transient failures
5. **Log errors comprehensively**: Include context (agent_id, task_id) in error logs
