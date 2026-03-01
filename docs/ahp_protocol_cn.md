# AHP 协议规范

## 概述

AHP（Agent HTTP-like Protocol）是一种轻量级的多智能体通信协议，专为本项 多智能体系统设计。它在 Leader Agent 和多个 Sub Agent 之间提供可靠的消息传递、任务分发和结果收集功能。

## 架构

```
┌─────────────┐         AHP 协议              ┌─────────────┐
│             │  ┌─────────────────────┐    │             │
│   Leader    │──│  消息队列            │───▶│   Sub Agent │
│   Agent     │  │  (含 ACK/DLQ)       │    │   (head)    │
│             │  └─────────────────────┘    │             │
└─────────────┘                              └─────────────┘
       │                                           │
       │              AHP 协议                      │
       │  ┌─────────────────────┐                  │
       │  │  TASK: 推荐任务      │◀─────────────────┤
       │  │  ACK: 已收到确认     │─────────────────▶│
       │  │  PROGRESS: 进度     │◀─────────────────┤
       │  │  RESULT: 推荐结果    │◀─────────────────┤
       │  └─────────────────────┘                  │
       │                                           │
       ▼                                           ▼
┌─────────────────────────────────────────────────────┐
│              消息流程                                │
│  1. TASK (Leader → Sub) 分发任务                    │
│  2. ACK (Sub → Leader) 消息确认                     │
│  3. PROGRESS (Sub → Leader) 进度报告               │
│  4. RESULT (Sub → Leader) 返回结果                  │
└─────────────────────────────────────────────────────┘
```

## 消息类型

| 方法               | 方向          | 说明               |
| ------------------ | ------------- | ------------------ |
| `TASK`           | Leader → Sub | 向子智能体分发任务 |
| `ACK`            | 双向          | 消息确认回执       |
| `RESULT`         | Sub → Leader | 返回任务结果       |
| `PROGRESS`       | Sub → Leader | 进度报告           |
| `HEARTBEAT`      | 双向          | 心跳检测           |
| `TOKEN_REQUEST`  | Sub → Leader | Token 配额请求     |
| `TOKEN_RESPONSE` | Leader → Sub | Token 配额响应     |

## 消息格式

```python
@dataclass
class AHPMessage:
    method: str           # TASK / RESULT / PROGRESS / HEARTBEAT / ACK
    agent_id: str         # 源智能体 ID
    target_agent: str     # 目标智能体 ID
    task_id: str          # 任务 ID
    session_id: str       # 会话 ID
    payload: Dict         # 消息载荷
    token_limit: int      # LLM Token 限制
    timestamp: datetime   # 时间戳
    message_id: str       # 唯一消息 ID（自动生成）
```

## 错误处理

### 错误码

| 错误码                    | 说明             |
| ------------------------- | ---------------- |
| `UNKNOWN`               | 未知错误         |
| `INVALID_MESSAGE`       | 无效消息格式     |
| `TIMEOUT`               | 操作超时         |
| `AGENT_NOT_FOUND`       | 目标智能体不存在 |
| `QUEUE_FULL`            | 消息队列已满     |
| `SERIALIZATION_ERROR`   | 序列化失败       |
| `DESERIALIZATION_ERROR` | 反序列化失败     |
| `RETRY_EXHAUSTED`       | 超过最大重试次数 |

### AHPError 类

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
        # 包含: message, code, agent_id, task_id, details
```

## 高级特性

### 1. 消息确认 (ACK)

协议通过 ACK 消息确保可靠的消息传递：

- **自动 ACK**：`AHPReceiver` 自动为 TASK/RESULT/PROGRESS 消息发送 ACK
- **ACK 载荷**：包含 `original_message_id` 和 `ack_status`
- **超时**：可配置接收超时时间

```python
# 发送 ACK
sender.send_ack(
    target_agent="head",
    session_id="session_123",
    original_message_id="msg_456",
    status="received"
)
```

### 2. 死信队列 (DLQ)

失败的消息会被移入 DLQ 供后续调查：

```python
# 移入 DLQ
mq.to_dlq(agent_id, message, error_message)

# 获取 DLQ 内容
dlq = mq.get_dlq(agent_id="head")

# 清空 DLQ
mq.clear_dlq(agent_id="head")
```

### 3. 消息去重

使用 `message_id` 对消息进行去重：

```python
# 重复消息会被自动过滤
mq.send(agent_id, message)  # 首次发送 - 成功
mq.send(agent_id, message)  # 重复 - 被过滤
```

### 4. 重试机制

为失败消息提供可配置的重试功能：

```python
mq = MessageQueue(max_retries=3, retry_delay=1.0)

# 检查是否应该重试
if mq.should_retry(message_id):
    mq.increment_retry(message_id)

# 重置重试计数
mq.reset_retry(message_id)
```

### 5. Token 控制

`TokenController` 管理子智能体的 Token 限制：

```python
tc = TokenController(default_limit=500)
tc.set_limit("head", 300)

# 创建紧凑指令
instruction = tc.create_compact_instruction(
    user_profile={"name": "用户", "age": 25},
    task={"category": "head", "instruction": "推荐帽子"},
    max_tokens=300
)
```

## 智能体集成

### Leader Agent

```python
from src.protocol import AHPSender, AHPError, AHPErrorCode

# 发送任务（含错误处理）
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

# 接收消息（自动 ACK）
msg = receiver.receive(timeout=30, auto_ack=True)

# 处理错误
try:
    result = process_task(msg)
    sender.send_result("leader", task_id, session_id, result)
except Exception as e:
    mq.to_dlq(agent_id, msg, str(e))
```

## 配置

AHP 配置通过 `config.yaml` 管理：

```yaml
ahp:
  token_limit: 500
  task_timeout: 60
  heartbeat_interval: 30
  max_retries: 3
```

## 测试

运行 AHP 协议测试：

```bash
pytest tests/test_ahp.py -v
```

测试覆盖：

- 消息序列化/反序列化
- ACK 消息处理
- DLQ 操作
- 重试机制
- 错误处理

## 最佳实践

1. **始终处理 ACK**：在任务完成前等待确认回执
2. **监控 DLQ**：定期检查 DLQ 中的失败消息
3. **合理配置超时**：在响应性和可靠性之间取得平衡
4. **实现重试逻辑**：对临时性故障使用重试机制
5. **全面记录错误**：在错误日志中包含上下文信息（agent_id、task_id）
