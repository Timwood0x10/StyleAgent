# Error Handling Mechanism

## 1. Overview

The error handling mechanism in this system is built on three core components:

1. **RetryHandler** - Automatic retry with exponential backoff
2. **CircuitBreaker** - Prevent cascading failures
3. **Fallback** - Degrade gracefully when service is unavailable

These components work together to provide resilience for LLM calls in both LeaderAgent and SubAgent.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Call                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Circuit Breaker                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Closed    │──▶│    Open     │──▶│ Half-Open  │        │
│  │  (Normal)   │   │  (Blocked)  │   │  (Testing) │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Retry Handler                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Attempt 1 → Failed → Wait (delay) → Attempt 2      │   │
│  │  → Failed → Wait (delay*2) → Attempt 3 → Success   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Fallback                              │
│  Return default response when retry exhausted               │
└─────────────────────────────────────────────────────────────┘
```

## 3. Key Components

### 3.1 ErrorType Enum

Located in `src/core/errors.py`:

```python
class ErrorType(str, Enum):
    """Error types"""
    TIMEOUT = "timeout"          # Request timeout
    TOOL_FAILED = "tool_failed"  # Tool execution failed
    LLM_FAILED = "llm_failed"    # LLM call failed
    NETWORK = "network"          # Network error
    VALIDATION = "validation"    # Validation failed
    UNKNOWN = "unknown"          # Unknown error
```

### 3.2 RetryConfig

```python
@dataclass
class RetryConfig:
    max_retries: int = 3           # Maximum retry attempts
    initial_delay: float = 1.0      # Initial delay in seconds
    max_delay: float = 60.0        # Maximum delay in seconds
    backoff_factor: float = 2.0    # Exponential backoff factor
    retry_on: Optional[List[ErrorType]] = None  # Error types to retry
```

### 3.3 RetryHandler

Core retry logic with exponential backoff:

```python
class RetryHandler:
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._attempts: Dict[str, int] = {}

    def should_retry(self, error: ErrorInfo) -> bool:
        """Check if should retry based on attempt count and error type"""
        if error.task_id not in self._attempts:
            self._attempts[error.task_id] = 0
        
        if self._attempts[error.task_id] >= self.config.max_retries:
            return False
        
        if error.error_type not in self.config.retry_on:
            return False
        
        return True

    def get_delay(self, task_id: str) -> float:
        """Calculate delay with exponential backoff"""
        attempt = self._attempts.get(task_id, 0)
        delay = min(
            self.config.initial_delay * (self.config.backoff_factor ** attempt),
            self.config.max_delay,
        )
        return delay
```

### 3.4 CircuitBreaker

Prevents cascading failures by stopping requests when service is unhealthy:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: float = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self._failure_count = 0
        self._state = "closed"  # closed / open / half_open

    @property
    def state(self) -> str:
        """Get current state, auto-transition from open to half_open"""
        if self._state == "open":
            elapsed = (datetime.now() - self._last_failure_time).total_seconds()
            if elapsed >= self.timeout:
                self._state = "half_open"
        return self._state

    def can_execute(self) -> bool:
        """Check if execution allowed"""
        return self.state != "open"

    def record_success(self):
        """Reset on success"""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        """Open circuit after threshold failures"""
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
```

## 4. Integration in Agents

### 4.1 LeaderAgent

```python
class LeaderAgent:
    def __init__(self, llm: LocalLLM):
        # ... other initialization ...
        
        # Retry configuration
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
        
        # Circuit breaker configuration
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60
        )

    def _llm_call_with_circuit_breaker(self, func_name, func, *args, **kwargs):
        """Execute LLM call with circuit breaker and retry"""
        
        # Check circuit breaker first
        if not self.circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {func_name}")
            return self._get_fallback_result(func_name)
        
        try:
            # Execute with retry
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
        """Fallback when circuit is open or retry exhausted"""
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

SubAgent has similar integration, with fallback returning a basic recommendation:

```python
def _get_fallback_result(self, func_name: str) -> Any:
    if "recommend" in func_name:
        return json.dumps({
            "category": self.category,
            "items": ["basic item"],
            "colors": ["neutral color"],
            "styles": ["casual"],
            "reasons": ["default recommendation due to service unavailable"],
            "price_range": "medium"
        })
    return None
```

## 5. Flow Diagram

```
LLM Call Request
        │
        ▼
┌───────────────────┐
│ Circuit Breaker   │──── Open? ───▶ Return Fallback
│   Check State     │
└────────┬──────────┘
         │ Closed/Half-Open
         ▼
┌───────────────────┐
│  Execute with     │
│  Retry Handler    │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
 Success    Failed
    │         │
    ▼         ▼
Record    Check Retry
Success   Count
    │         │
    │    ┌────┴────┐
    │    │         │
    │  Retry    Exhausted
    │    │         │
    │    ▼         ▼
    │ Wait     Record
    │ Backoff  Failure
    │    │         │
    └────┴─────────┘
         │
         ▼
   Return Result
```

## 6. Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts |
| `initial_delay` | 1.0s | Initial retry delay |
| `max_delay` | 30.0s | Maximum retry delay |
| `backoff_factor` | 2.0 | Exponential backoff multiplier |
| `failure_threshold` | 5 | Failures before opening circuit |
| `circuit_timeout` | 60s | Time before trying again |

## 7. Error Types to Retry

The system is configured to retry on these error types:

- `LLM_FAILED` - LLM call failed
- `NETWORK` - Network error
- `TIMEOUT` - Request timeout

The following error types do NOT trigger retry:

- `VALIDATION` - Validation failed (should fix input)
- `UNKNOWN` - Unknown error

## 8. Notes

1. **Circuit Breaker State Transitions**:
   - `closed` → `open`: After 5 consecutive failures
   - `open` → `half_open`: After 60 seconds
   - `half_open` → `closed`: After first successful call
   - `half_open` → `open`: If test call fails

2. **Fallback Behavior**:
   - LeaderAgent: Returns default UserProfile or None
   - SubAgent: Returns basic JSON recommendation

3. **Logging**: All retry attempts and circuit breaker state changes are logged for debugging.

4. **Thread Safety**: CircuitBreaker uses locks to ensure thread-safe state management.
