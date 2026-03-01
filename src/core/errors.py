"""
Error Handling and Retry Mechanism

Features:
- Automatic retry on task failure
- Fallback processing
- Timeout handling
- Agent failover
"""

import time
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..utils import get_logger

logger = get_logger(__name__)


class ErrorType(str, Enum):
    """Error types"""

    TIMEOUT = "timeout"  # Request timeout
    TOOL_FAILED = "tool_failed"  # Tool execution failed
    LLM_FAILED = "llm_failed"  # LLM call failed
    NETWORK = "network"  # Network error
    VALIDATION = "validation"  # Validation failed
    UNKNOWN = "unknown"  # Unknown error


@dataclass
class ErrorInfo:
    """Error information"""

    error_type: ErrorType
    message: str
    task_id: str = ""
    agent_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    traceback: str = ""

    @classmethod
    def from_exception(cls, e: Exception, task_id: str = "", agent_id: str = ""):
        """Create from exception"""
        error_type = ErrorType.UNKNOWN
        msg = str(e)

        if "timeout" in msg.lower():
            error_type = ErrorType.TIMEOUT
        elif "tool" in msg.lower():
            error_type = ErrorType.TOOL_FAILED
        elif "llm" in msg.lower() or "model" in msg.lower():
            error_type = ErrorType.LLM_FAILED
        elif "network" in msg.lower() or "connection" in msg.lower():
            error_type = ErrorType.NETWORK
        elif "validation" in msg.lower():
            error_type = ErrorType.VALIDATION

        return cls(
            error_type=error_type,
            message=msg,
            task_id=task_id,
            agent_id=agent_id,
            traceback=traceback.format_exc(),
        )


@dataclass
class RetryConfig:
    """Retry configuration"""

    max_retries: int = 3  # Maximum retry attempts
    initial_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    backoff_factor: float = 2.0  # Exponential backoff factor
    retry_on: Optional[List[ErrorType]] = None  # Error types to retry

    def __post_init__(self):
        if self.retry_on is None:
            self.retry_on = [
                ErrorType.TIMEOUT,
                ErrorType.NETWORK,
                ErrorType.TOOL_FAILED,
                ErrorType.LLM_FAILED,
            ]


class RetryHandler:
    """
    Retry handler with exponential backoff

    Uses exponential backoff algorithm for retry logic
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._attempts: Dict[str, int] = {}  # task_id -> attempt_count

    def should_retry(self, error: ErrorInfo) -> bool:
        """Check if should retry"""
        if error.task_id not in self._attempts:
            self._attempts[error.task_id] = 0

        # Check retry count limit
        if self._attempts[error.task_id] >= self.config.max_retries:
            return False

        # Check error type allowlist
        if self.config.retry_on is None or error.error_type not in self.config.retry_on:
            return False

        return True

    def get_delay(self, task_id: str) -> float:
        """Calculate delay with exponential backoff"""
        attempt = self._attempts.get(task_id, 0)
        delay = min(
            self.config.initial_delay * (self.config.backoff_factor**attempt),
            self.config.max_delay,
        )
        return delay

    def record_attempt(self, task_id: str):
        """Record attempt count"""
        self._attempts[task_id] = self._attempts.get(task_id, 0) + 1

    def reset(self, task_id: Optional[str] = None):
        """Reset counter"""
        if task_id:
            self._attempts.pop(task_id, None)
        else:
            self._attempts.clear()

    def execute_with_retry(
        self, func: Callable, task_id: str = "", *args, **kwargs
    ) -> Any:
        """
        Execute function with retry logic

        Args:
            func: Function to execute
            task_id: Task ID for tracking
            *args, **kwargs: Function arguments

        Returns:
            Function return value

        Raises:
            Last exception if all retries exhausted
        """
        last_error = None

        while True:
            try:
                result = func(*args, **kwargs)
                self.reset(task_id)  # Reset on success
                return result

            except Exception as e:
                error = ErrorInfo.from_exception(e, task_id=task_id)

                if not self.should_retry(error):
                    raise last_error or e

                # Record and wait
                self.record_attempt(task_id)
                delay = self.get_delay(task_id)

                logger.warning(f"{error.error_type.value}: {error.message}")
                logger.warning(f"Retry: {task_id} attempt {self._attempts[task_id]}/{self.config.max_retries}, waiting {delay:.1f}s")

                time.sleep(delay)
                last_error = e


class FallbackHandler:
    """
    Fallback handler

    Provides alternative when primary method fails
    """

    def __init__(self):
        self._fallbacks: Dict[str, Callable] = {}

    def register(self, name: str, handler: Callable):
        """Register fallback handler"""
        self._fallbacks[name] = handler

    def execute(
        self, primary: Callable, fallback_name: str = "default", *args, **kwargs
    ) -> Any:
        """Execute primary, fallback on failure"""
        try:
            return primary(*args, **kwargs)
        except Exception:
            fallback = self._fallbacks.get(fallback_name)
            if fallback:
                logger.info(f"Fallback: using {fallback_name}")
                return fallback(*args, **kwargs)
            raise


class TimeoutHandler:
    """
    Timeout handler
    """

    @staticmethod
    def execute_with_timeout(
        func: Callable, timeout: float = 30, default: Any = None, *args, **kwargs
    ) -> Any:
        """Execute with timeout protection"""
        result = [default]
        exception = [None]

        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")

        if exception[0]:
            raise exception[0]

        return result[0]


class CircuitBreaker:
    """
    Circuit breaker - prevents cascading failures

    States: closed(normal) -> open(breaker) -> half_open(testing)
    """

    def __init__(self, failure_threshold: int = 5, timeout: float = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "closed"  # closed / open / half_open
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """Get current state"""
        with self._lock:
            if self._state == "open":
                # Check if should transition to half_open
                if self._last_failure_time:
                    elapsed = (datetime.now() - self._last_failure_time).seconds
                    if elapsed >= self.timeout:
                        self._state = "half_open"
            return self._state

    def record_success(self):
        """Record successful execution"""
        with self._lock:
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self):
        """Record failed execution"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._failure_count >= self.failure_threshold:
                self._state = "open"
                logger.warning(f"Circuit OPEN: {self._failure_count} consecutive failures")

    def can_execute(self) -> bool:
        """Check if execution allowed"""
        return self.state != "open"

    def reset(self):
        """Reset circuit breaker"""
        with self._lock:
            self._failure_count = 0
            self._state = "closed"
            self._last_failure_time = None


# Global retry handler instance
_global_retry_handler: Optional[RetryHandler] = None


def get_retry_handler(config: Optional[RetryConfig] = None) -> RetryHandler:
    """Get retry handler instance"""
    global _global_retry_handler
    if _global_retry_handler is None:
        _global_retry_handler = RetryHandler(config)
    return _global_retry_handler
