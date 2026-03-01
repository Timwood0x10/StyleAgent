# 错误处理机制

## 1. 概述

本系统的错误处理机制建立在三个核心组件之上：

1. **RetryHandler** - 带指数退避的自动重试
2. **CircuitBreaker** - 防止级联故障
3. **Fallback** - 服务不可用时的降级处理

这些组件协同工作，为 LeaderAgent 和 SubAgent 中的 LLM 调用提供容错能力。

## 2. 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent 调用                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     熔断器 (Circuit Breaker)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Closed    │──▶│    Open     │──▶│ Half-Open  │        │
│  │  (正常)     │   │  (阻断)     │   │  (测试中)   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     重试处理器 (Retry Handler)               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  尝试 1 → 失败 → 等待 (delay) → 尝试 2            │    │
│  │  → 失败 → 等待 (delay*2) → 尝试 3 → 成功         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     降级处理 (Fallback)                      │
│  重试耗尽时返回默认响应                                      │
└─────────────────────────────────────────────────────────────┘
```

## 3. 核心组件

### 3.1 ErrorType 枚举

位于 `src/core/errors.py`:

```python
class ErrorType(str, Enum):
    """错误类型"""
    TIMEOUT = "timeout"          # 请求超时
    TOOL_FAILED = "tool_failed"  # 工具执行失败
    LLM_FAILED = "llm_failed"    # LLM 调用失败
    NETWORK = "network"          # 网络错误
    VALIDATION = "validation"     # 验证失败
    UNKNOWN = "unknown"          # 未知错误
```

### 3.2 RetryConfig

```python
@dataclass
class RetryConfig:
    max_retries: int = 3           # 最大重试次数
    initial_delay: float = 1.0      # 初始延迟（秒）
    max_delay: float = 60.0         # 最大延迟（秒）
    backoff_factor: float = 2.0     # 指数退避因子
    retry_on: Optional[List[ErrorType]] = None  # 需要重试的错误类型
```

### 3.3 RetryHandler

带指数退避的核心重试逻辑：

```python
class RetryHandler:
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._attempts: Dict[str, int] = {}

    def should_retry(self, error: ErrorInfo) -> bool:
        """根据重试次数和错误类型判断是否应该重试"""
        if error.task_id not in self._attempts:
            self._attempts[error.task_id] = 0
        
        # 检查重试次数限制
        if self._attempts[error.task_id] >= self.config.max_retries:
            return False
        
        # 检查错误类型是否在允许重试列表中
        if error.error_type not in self.config.retry_on:
            return False
        
        return True

    def get_delay(self, task_id: str) -> float:
        """计算指数退避延迟"""
        attempt = self._attempts.get(task_id, 0)
        delay = min(
            self.config.initial_delay * (self.config.backoff_factor ** attempt),
            self.config.max_delay,
        )
        return delay
```

### 3.4 CircuitBreaker

通过在服务不健康时停止请求来防止级联故障：

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: float = 60):
        self.failure_threshold = failure_threshold  # 打开熔断的失败次数阈值
        self.timeout = timeout                      # 熔断持续时间（秒）
        self._failure_count = 0
        self._state = "closed"  # closed / open / half_open

    @property
    def state(self) -> str:
        """获取当前状态，自动从 open 转换到 half_open"""
        if self._state == "open":
            elapsed = (datetime.now() - self._last_failure_time).total_seconds()
            if elapsed >= self.timeout:
                self._state = "half_open"
        return self._state

    def can_execute(self) -> bool:
        """检查是否允许执行"""
        return self.state != "open"

    def record_success(self):
        """成功时重置"""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        """失败次数达到阈值时打开熔断"""
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
```

## 4. Agent 中的集成

### 4.1 LeaderAgent

```python
class LeaderAgent:
    def __init__(self, llm: LocalLLM):
        # ... 其他初始化 ...
        
        # 重试配置
        retry_config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
            retry_on=[
                ErrorType.LLM_FAILED,
                ErrorType.NETWORK,
                ErrorType.TIMEOUT,
            ],
        )
        self.retry_handler = RetryHandler(retry_config)
        
        # 熔断器配置
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,  # 连续5次失败后打开
            timeout=60             # 60秒后尝试恢复
        )

    def _llm_call_with_circuit_breaker(self, func_name, func, *args, **kwargs):
        """带熔断器和重试的 LLM 调用"""
        
        # 首先检查熔断器状态
        if not self.circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {func_name}")
            return self._get_fallback_result(func_name)
        
        try:
            # 执行带重试的调用
            result = self.retry_handler.execute_with_retry(
                func,
                task_id=f"leader_{func_name}",
                *args,
                **kwargs
            )
            self.circuit_breaker.record_success()
            return result
        except Exception as e:
            self.circuit_breaker.record_failure()
            return self._get_fallback_result(func_name)

    def _get_fallback_result(self, func_name: str) -> Any:
        """熔断打开或重试耗尽时的降级处理"""
        if func_name == "parse_user_profile":
            return UserProfile(
                name="User",
                gender=Gender.MALE,
                age=25,
                occupation="",
                hobbies=[],
                mood="normal",
                budget="medium",
                season="spring",
                occasion="daily",
            )
        elif func_name == "aggregate_results":
            return None
        return None
```

### 4.2 SubAgent

SubAgent 有类似的集成，降级时返回基本推荐：

```python
def _get_fallback_result(self, func_name: str) -> Any:
    if "recommend" in func_name:
        return json.dumps({
            "category": self.category,
            "items": ["基础单品"],
            "colors": ["中性色"],
            "styles": ["休闲"],
            "reasons": ["服务不可用，返回默认推荐"],
            "price_range": "中等"
        })
    return None
```

## 5. 流程图

```
LLM 调用请求
        │
        ▼
┌───────────────────┐
│ 熔断器检查状态     │──── 打开? ────▶ 返回降级响应
└────────┬──────────┘
         │ 关闭/半开
         ▼
┌───────────────────┐
│  执行重试处理器    │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
 成功       失败
    │         │
    ▼         ▼
记录成功   检查重试
    │        次数
    │    ┌────┴────┐
    │    │         │
    │  重试     已耗尽
    │    │         │
    │    ▼         ▼
    │ 等待     记录
    │ 退避     失败
    │    │         │
    └────┴─────────┘
         │
         ▼
   返回结果
```

## 6. 配置参数

| 参数 | 默认值 | 描述 |
|--------|--------|------|
| `max_retries` | 3 | 最大重试次数 |
| `initial_delay` | 1.0秒 | 初始重试延迟 |
| `max_delay` | 30.0秒 | 最大重试延迟 |
| `backoff_factor` | 2.0 | 指数退避倍数 |
| `failure_threshold` | 5 | 打开熔断的失败次数 |
| `circuit_timeout` | 60秒 | 熔断持续时间 |

## 7. 重试的错误类型

系统配置为对以下错误类型进行重试：

- `LLM_FAILED` - LLM 调用失败
- `NETWORK` - 网络错误
- `TIMEOUT` - 请求超时

以下错误类型不触发重试：

- `VALIDATION` - 验证失败（应修复输入）
- `UNKNOWN` - 未知错误

## 8. 注意事项

1. **熔断器状态转换**:
   - `closed` → `open`: 连续5次失败后
   - `open` → `half_open`: 60秒后
   - `half_open` → `closed`: 首次调用成功后
   - `half_open` → `open`: 测试调用失败后

2. **降级行为**:
   - LeaderAgent: 返回默认 UserProfile 或 None
   - SubAgent: 返回基础 JSON 推荐

3. **日志记录**: 所有重试尝试和熔断器状态变化都会记录以便调试。

4. **线程安全**: CircuitBreaker 使用锁来确保状态管理的线程安全。
