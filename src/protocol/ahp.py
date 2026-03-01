"""
AHP (Agent HTTP-like Protocol) Communication Protocol

Supported methods:
- TASK: Dispatch task (Leader -> Sub)
- RESULT: Return result (Sub -> Leader)
- PROGRESS: Progress report (Sub -> Leader)
- HEARTBEAT: Heartbeat check (bidirectional)
- TOKEN_REQUEST: Token request
- TOKEN_RESPONSE: Token response
- ACK: Message acknowledgment
"""

import asyncio
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from ..utils import get_logger

# Logger for this module
logger = get_logger(__name__)


# AHP Methods
class AHPMethod:
    TASK = "TASK"
    RESULT = "RESULT"
    PROGRESS = "PROGRESS"
    HEARTBEAT = "HEARTBEAT"
    TOKEN_REQUEST = "TOKEN_REQUEST"
    TOKEN_RESPONSE = "TOKEN_RESPONSE"
    ACK = "ACK"


# AHP Error Codes
class AHPErrorCode(Enum):
    """AHP protocol error codes"""

    UNKNOWN = "UNKNOWN"
    INVALID_MESSAGE = "INVALID_MESSAGE"
    TIMEOUT = "TIMEOUT"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    QUEUE_FULL = "QUEUE_FULL"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"
    DESERIALIZATION_ERROR = "DESERIALIZATION_ERROR"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class AHPError(Exception):
    """AHP protocol error with error code and context"""

    def __init__(
        self,
        message: str,
        code: AHPErrorCode = AHPErrorCode.UNKNOWN,
        agent_id: str = "",
        task_id: str = "",
        details: Dict[str, Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.agent_id = agent_id
        self.task_id = task_id
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code.value,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "details": self.details,
        }


@dataclass
class AHPMessage:
    """AHP message format"""

    method: str  # TASK / RESULT / PROGRESS / HEARTBEAT
    agent_id: str  # Source Agent ID
    target_agent: str  # Target Agent ID
    task_id: str  # Task ID
    session_id: str  # Session ID
    payload: Dict[str, Any] = field(default_factory=dict)
    token_limit: int = 500
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "agent_id": self.agent_id,
            "target_agent": self.target_agent,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "token_limit": self.token_limit,
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AHPMessage":
        """Create AHPMessage from dictionary"""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            method=data.get("method", ""),
            agent_id=data.get("agent_id", ""),
            target_agent=data.get("target_agent", ""),
            task_id=data.get("task_id", ""),
            session_id=data.get("session_id", ""),
            payload=data.get("payload", {}),
            token_limit=data.get("token_limit", 500),
            timestamp=timestamp,
            message_id=data.get("message_id", str(uuid.uuid4())),
        )


class MessageQueue:
    """Agent message queue with timeout, heartbeat, DLQ and retry support"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self._queues: Dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._heartbeats: Dict[str, datetime] = {}
        self._message_ids: Dict[str, set] = {}  # Track message IDs for deduplication
        # Dead Letter Queue: stores failed messages
        self._dlq: Dict[str, list] = {}  # agent_id -> list of failed messages
        # Retry tracking
        self._retry_count: Dict[str, int] = {}  # message_id -> retry count
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    def get_queue(self, agent_id: str) -> queue.Queue:
        """Get queue for agent"""
        with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = queue.Queue()
            return self._queues[agent_id]

    def send(self, agent_id: str, message: AHPMessage):
        """Send message with deduplication"""
        # Check for duplicate message
        with self._lock:
            if agent_id not in self._message_ids:
                self._message_ids[agent_id] = set()

            if message.message_id in self._message_ids[agent_id]:
                logger.warning(f"Duplicate message detected: {message.message_id}")
                return

            self._message_ids[agent_id].add(message.message_id)

        self.get_queue(agent_id).put(message)

    def receive(self, agent_id: str, timeout: float = 30) -> Optional[AHPMessage]:
        """Receive message"""
        try:
            return self.get_queue(agent_id).get(timeout=timeout)
        except queue.Empty:
            return None

    def broadcast(self, agent_ids: list, message: AHPMessage):
        """Broadcast message"""
        for agent_id in agent_ids:
            self.send(agent_id, message)

    def update_heartbeat(self, agent_id: str):
        """Update heartbeat"""
        with self._lock:
            self._heartbeats[agent_id] = datetime.now()

    def get_heartbeat(self, agent_id: str) -> Optional[datetime]:
        """Get heartbeat time"""
        with self._lock:
            return self._heartbeats.get(agent_id)

    def to_dlq(self, agent_id: str, message: AHPMessage, error: str = ""):
        """Move failed message to Dead Letter Queue"""
        with self._lock:
            if agent_id not in self._dlq:
                self._dlq[agent_id] = []

            dlq_entry = {
                "message": message.to_dict(),
                "error": error,
                "timestamp": datetime.now().isoformat(),
                "retry_count": self._retry_count.get(message.message_id, 0),
            }
            self._dlq[agent_id].append(dlq_entry)
            logger.error(f"Message {message.message_id} moved to DLQ: {error}")

    def get_dlq(self, agent_id: Optional[str] = None) -> Union[Dict[str, list], list]:
        """Get messages from Dead Letter Queue"""
        with self._lock:
            if agent_id:
                return self._dlq.get(agent_id, [])
            return dict(self._dlq)

    def clear_dlq(self, agent_id: str = None):
        """Clear Dead Letter Queue"""
        with self._lock:
            if agent_id:
                self._dlq[agent_id] = []
            else:
                self._dlq = {}

    def should_retry(self, message_id: str) -> bool:
        """Check if message should be retried"""
        retry_count = self._retry_count.get(message_id, 0)
        return retry_count < self._max_retries

    def increment_retry(self, message_id: str) -> int:
        """Increment retry count and return new count"""
        with self._lock:
            self._retry_count[message_id] = self._retry_count.get(message_id, 0) + 1
            return self._retry_count[message_id]

    def reset_retry(self, message_id: str):
        """Reset retry count for message"""
        with self._lock:
            self._retry_count.pop(message_id, None)

    def is_alive(self, agent_id: str, timeout: float = 60) -> bool:
        """Check if agent is alive"""
        last_heartbeat = self.get_heartbeat(agent_id)
        if not last_heartbeat:
            return True  # First record, assume alive
        return (datetime.now() - last_heartbeat).seconds < timeout


class TokenController:
    """Token controller - controls Sub Agent token usage"""

    def __init__(self, default_limit: int = 500):
        self.default_limit = default_limit
        self._quotas: Dict[str, int] = {}  # agent_id -> token_limit

    def get_limit(self, agent_id: str) -> int:
        """Get agent token limit"""
        return self._quotas.get(agent_id, self.default_limit)

    def set_limit(self, agent_id: str, limit: int):
        """Set agent token limit"""
        self._quotas[agent_id] = limit

    def create_compact_instruction(
        self, user_profile: Dict, task: Dict, context: str = "", max_tokens: int = None
    ) -> str:
        """Create compact instruction (Token control)"""
        limit = max_tokens or self.default_limit

        # Compact format
        instruction_parts = [
            f"Task: {task.get('category', 'unknown')}",
            f"Target: {user_profile.get('name', 'User')}",
        ]

        # Key information
        key_info = []
        if user_profile.get("gender"):
            key_info.append(f"Gender: {user_profile['gender']}")
        if user_profile.get("age"):
            key_info.append(f"Age: {user_profile['age']}")
        if user_profile.get("occupation"):
            key_info.append(f"Occupation: {user_profile['occupation']}")
        if user_profile.get("mood"):
            key_info.append(f"Mood: {user_profile['mood']}")
        if user_profile.get("hobbies"):
            key_info.append(f"Hobbies: {','.join(user_profile['hobbies'])}")

        if key_info:
            instruction_parts.append("User Info: " + "; ".join(key_info))

        # Task description
        if task.get("instruction"):
            instruction_parts.append(f"Requirement: {task['instruction']}")

        # Context summary (if provided)
        if context:
            # Estimate token, reserve space
            available = limit - sum(len(p) for p in instruction_parts) - 50
            if available > 100:
                instruction_parts.append(f"Context: {context[:available]}")

        return "\n".join(instruction_parts)


class AHPSender:
    """AHP Sender"""

    def __init__(
        self, message_queue: MessageQueue, token_controller: TokenController = None
    ):
        self.mq = message_queue
        self.token_controller = token_controller or TokenController()

    def send_task(
        self,
        target_agent: str,
        task_id: str,
        session_id: str,
        payload: Dict[str, Any],
        token_limit: int = 500,
        context: str = "",
    ) -> AHPMessage:
        """Send task to agent with compact instruction"""

        # Generate compact instruction
        compact_instruction = self.token_controller.create_compact_instruction(
            user_profile=payload.get("user_info", {}),
            task={
                "category": payload.get("category"),
                "instruction": payload.get("instruction"),
            },
            context=context,
            max_tokens=token_limit,
        )

        # Inject compact instruction
        payload["compact_instruction"] = compact_instruction

        msg = AHPMessage(
            method=AHPMethod.TASK,
            agent_id="leader",
            target_agent=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload=payload,
            token_limit=token_limit,
        )
        self.mq.send(target_agent, msg)
        logger.debug(
            f"SEND [->{target_agent}] TASK: {payload.get('category', 'unknown')} (token_limit: {token_limit})"
        )
        return msg

    def send_result(
        self,
        target_agent: str,
        task_id: str,
        session_id: str,
        result: Dict[str, Any],
        status: str = "success",
    ) -> AHPMessage:
        """Send result"""
        msg = AHPMessage(
            method=AHPMethod.RESULT,
            agent_id="leader",
            target_agent=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload={"result": result, "status": status},
        )
        self.mq.send(target_agent, msg)
        return msg

    def send_progress(
        self,
        target_agent: str,
        task_id: str,
        session_id: str,
        progress: float,
        message: str = "",
    ) -> AHPMessage:
        """Send progress"""
        msg = AHPMessage(
            method=AHPMethod.PROGRESS,
            agent_id="leader",
            target_agent=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload={"progress": progress, "message": message},
        )
        self.mq.send(target_agent, msg)
        return msg

    def send_heartbeat(self, target_agent: str, session_id: str) -> AHPMessage:
        """Send heartbeat"""
        msg = AHPMessage(
            method=AHPMethod.HEARTBEAT,
            agent_id="leader",
            target_agent=target_agent,
            task_id="",
            session_id=session_id,
            payload={"timestamp": datetime.now().isoformat()},
        )
        self.mq.send(target_agent, msg)
        return msg

    def send_ack(
        self,
        target_agent: str,
        session_id: str,
        original_message_id: str,
        status: str = "received",
    ) -> AHPMessage:
        """Send acknowledgment for a message"""
        msg = AHPMessage(
            method=AHPMethod.ACK,
            agent_id="leader",
            target_agent=target_agent,
            task_id="",
            session_id=session_id,
            payload={
                "original_message_id": original_message_id,
                "ack_status": status,
                "timestamp": datetime.now().isoformat(),
            },
        )
        self.mq.send(target_agent, msg)
        logger.debug(f"SEND [->{target_agent}] ACK for {original_message_id}: {status}")
        return msg


class AHPReceiver:
    """AHP Receiver"""

    def __init__(self, agent_id: str, message_queue: MessageQueue):
        self.agent_id = agent_id
        self.mq = message_queue

    def receive(
        self, timeout: float = 30, auto_ack: bool = True
    ) -> Optional[AHPMessage]:
        """Receive message"""
        msg = self.mq.receive(self.agent_id, timeout)
        if msg:
            logger.debug(f"RECV [<-{self.agent_id}] {msg.method}")
            self.mq.update_heartbeat(self.agent_id)

            # Auto send ACK for TASK/RESULT/PROGRESS messages
            if auto_ack and msg.method in [
                AHPMethod.TASK,
                AHPMethod.RESULT,
                AHPMethod.PROGRESS,
            ]:
                self._send_ack(msg)
        return msg

    def _send_ack(self, original_msg: AHPMessage):
        """Send acknowledgment for received message"""
        ack_msg = AHPMessage(
            method=AHPMethod.ACK,
            agent_id=self.agent_id,
            target_agent=original_msg.agent_id,
            task_id=original_msg.task_id,
            session_id=original_msg.session_id,
            payload={
                "original_message_id": original_msg.message_id,
                "ack_status": "received",
                "timestamp": datetime.now().isoformat(),
            },
        )
        self.mq.send(original_msg.agent_id, ack_msg)
        logger.debug(
            f"SEND [->{original_msg.agent_id}] ACK for {original_msg.message_id}"
        )

    def wait_for_task(self, timeout: float = 60) -> Optional[AHPMessage]:
        """Wait for task"""
        msg = self.receive(timeout)
        if msg and msg.method == AHPMethod.TASK:
            return msg
        return None

    def send_heartbeat(self, session_id: str):
        """Send heartbeat"""
        self.mq.update_heartbeat(self.agent_id)

    def send_progress(
        self, session_id: str, task_id: str, progress: float, message: str = ""
    ):
        """Send progress to leader"""
        msg = AHPMessage(
            method=AHPMethod.PROGRESS,
            agent_id=self.agent_id,
            target_agent="leader",
            task_id=task_id,
            session_id=session_id,
            payload={"progress": progress, "message": message},
        )
        self.mq.send("leader", msg)

    def send_result(
        self, session_id: str, task_id: str, result: Dict, status: str = "success"
    ):
        """Send result to leader"""
        msg = AHPMessage(
            method=AHPMethod.RESULT,
            agent_id=self.agent_id,
            target_agent="leader",
            task_id=task_id,
            session_id=session_id,
            payload={"result": result, "status": status},
        )
        self.mq.send("leader", msg)


# Global message queue instance
_global_mq: Optional[MessageQueue] = None


def get_message_queue() -> MessageQueue:
    """Get global message queue"""
    global _global_mq
    if _global_mq is None:
        _global_mq = MessageQueue()
    return _global_mq


def reset_message_queue():
    """Reset message queue"""
    global _global_mq
    _global_mq = None


# ========== Async Version ==========


class AsyncMessageQueue:
    """Async Agent message queue with asyncio.Queue"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._heartbeats: Dict[str, datetime] = {}
        self._message_ids: Dict[str, set] = {}
        self._dlq: Dict[str, list] = {}
        self._retry_count: Dict[str, int] = {}
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    async def get_queue(self, agent_id: str) -> asyncio.Queue:
        """Get async queue for agent"""
        async with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = asyncio.Queue()
            return self._queues[agent_id]

    async def send(self, agent_id: str, message: AHPMessage):
        """Send message with deduplication (async)"""
        async with self._lock:
            if agent_id not in self._message_ids:
                self._message_ids[agent_id] = set()

            if message.message_id in self._message_ids[agent_id]:
                logger.warning(f"Duplicate message detected: {message.message_id}")
                return

            self._message_ids[agent_id].add(message.message_id)

        queue = await self.get_queue(agent_id)
        await queue.put(message)

    async def receive(self, agent_id: str, timeout: float = 30) -> Optional[AHPMessage]:
        """Receive message (async)"""
        queue = await self.get_queue(agent_id)
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def broadcast(self, agent_ids: list, message: AHPMessage):
        """Broadcast message (async)"""
        for agent_id in agent_ids:
            await self.send(agent_id, message)

    async def update_heartbeat(self, agent_id: str):
        """Update heartbeat (async)"""
        async with self._lock:
            self._heartbeats[agent_id] = datetime.now()

    async def get_heartbeat(self, agent_id: str) -> Optional[datetime]:
        """Get heartbeat time (async)"""
        async with self._lock:
            return self._heartbeats.get(agent_id)

    async def to_dlq(self, agent_id: str, message: AHPMessage, error: str = ""):
        """Move failed message to Dead Letter Queue (async)"""
        async with self._lock:
            if agent_id not in self._dlq:
                self._dlq[agent_id] = []

            dlq_entry = {
                "message": message.to_dict(),
                "error": error,
                "timestamp": datetime.now().isoformat(),
                "retry_count": self._retry_count.get(message.message_id, 0),
            }
            self._dlq[agent_id].append(dlq_entry)
            logger.error(f"Message {message.message_id} moved to DLQ: {error}")

    async def get_dlq(self, agent_id: Optional[str] = None) -> Union[Dict[str, list], list]:
        """Get messages from Dead Letter Queue (async)"""
        async with self._lock:
            if agent_id:
                return self._dlq.get(agent_id, [])
            return dict(self._dlq)

    async def should_retry(self, message_id: str) -> bool:
        """Check if message should be retried (async)"""
        retry_count = self._retry_count.get(message_id, 0)
        return retry_count < self._max_retries

    async def increment_retry(self, message_id: str) -> int:
        """Increment retry count (async)"""
        async with self._lock:
            self._retry_count[message_id] = self._retry_count.get(message_id, 0) + 1
            return self._retry_count[message_id]

    async def is_alive(self, agent_id: str, timeout: float = 60) -> bool:
        """Check if agent is alive (async)"""
        last_heartbeat = await self.get_heartbeat(agent_id)
        if not last_heartbeat:
            return True
        return (datetime.now() - last_heartbeat).seconds < timeout


class AsyncAHPSender:
    """Async AHP Sender"""

    def __init__(
        self,
        message_queue: AsyncMessageQueue,
        agent_id: str = "leader",
        token_controller: "AsyncTokenController" = None,
    ):
        self.mq = message_queue
        self.agent_id = agent_id
        self.token_controller = token_controller or AsyncTokenController()

    async def send_task(
        self,
        target_agent: str,
        task_id: str,
        session_id: str,
        payload: Dict[str, Any],
        token_limit: int = 500,
        context: str = "",
    ) -> AHPMessage:
        """Send task to agent (async)"""
        compact_instruction = self.token_controller.create_compact_instruction(
            user_profile=payload.get("user_info", {}),
            task={
                "category": payload.get("category"),
                "instruction": payload.get("instruction"),
            },
            context=context,
            max_tokens=token_limit,
        )

        payload["compact_instruction"] = compact_instruction

        msg = AHPMessage(
            method=AHPMethod.TASK,
            agent_id=self.agent_id,
            target_agent=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload=payload,
            token_limit=token_limit,
        )
        await self.mq.send(target_agent, msg)
        logger.debug(
            f"ASYNC SEND [->{target_agent}] TASK: {payload.get('category', 'unknown')}"
        )
        return msg

    async def send_result(
        self,
        target_agent: str,
        task_id: str,
        session_id: str,
        result: Dict[str, Any],
        status: str = "success",
    ) -> AHPMessage:
        """Send result (async)"""
        msg = AHPMessage(
            method=AHPMethod.RESULT,
            agent_id=self.agent_id,
            target_agent=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload={"result": result, "status": status},
        )
        await self.mq.send(target_agent, msg)
        return msg

    async def send_progress(
        self,
        target_agent: str,
        task_id: str,
        session_id: str,
        progress: float,
        message: str = "",
    ) -> AHPMessage:
        """Send progress (async)"""
        msg = AHPMessage(
            method=AHPMethod.PROGRESS,
            agent_id=self.agent_id,
            target_agent=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload={"progress": progress, "message": message},
        )
        await self.mq.send(target_agent, msg)
        return msg


class AsyncAHPReceiver:
    """Async AHP Receiver"""

    def __init__(self, agent_id: str, message_queue: AsyncMessageQueue):
        self.agent_id = agent_id
        self.mq = message_queue

    async def receive(
        self, timeout: float = 30, auto_ack: bool = True
    ) -> Optional[AHPMessage]:
        """Receive message (async)"""
        msg = await self.mq.receive(self.agent_id, timeout)
        if msg:
            logger.debug(f"ASYNC RECV [<-{self.agent_id}] {msg.method}")
            await self.mq.update_heartbeat(self.agent_id)
        return msg

    async def wait_for_task(self, timeout: float = 60) -> Optional[AHPMessage]:
        """Wait for task (async)"""
        msg = await self.receive(timeout)
        if msg and msg.method == AHPMethod.TASK:
            return msg
        return None


class AsyncTokenController:
    """Async Token Controller"""

    def __init__(self, default_limit: int = 500):
        self.default_limit = default_limit
        self._quotas: Dict[str, int] = {}

    def get_limit(self, agent_id: str) -> int:
        return self._quotas.get(agent_id, self.default_limit)

    def set_limit(self, agent_id: str, limit: int):
        self._quotas[agent_id] = limit

    def create_compact_instruction(
        self, user_profile: Dict, task: Dict, context: str = "", max_tokens: int = None
    ) -> str:
        """Create compact instruction (same as sync version)"""
        limit = max_tokens or self.default_limit

        instruction_parts = [
            f"Task: {task.get('category', 'unknown')}",
            f"Target: {user_profile.get('name', 'User')}",
        ]

        key_info = []
        if user_profile.get("gender"):
            key_info.append(f"Gender: {user_profile['gender']}")
        if user_profile.get("age"):
            key_info.append(f"Age: {user_profile['age']}")
        if user_profile.get("occupation"):
            key_info.append(f"Occupation: {user_profile['occupation']}")
        if user_profile.get("mood"):
            key_info.append(f"Mood: {user_profile['mood']}")
        if user_profile.get("hobbies"):
            key_info.append(f"Hobbies: {','.join(user_profile['hobbies'])}")

        if key_info:
            instruction_parts.append("User Info: " + "; ".join(key_info))

        if task.get("instruction"):
            instruction_parts.append(f"Requirement: {task['instruction']}")

        if context:
            available = limit - sum(len(p) for p in instruction_parts) - 50
            if available > 100:
                instruction_parts.append(f"Context: {context[:available]}")

        return "\n".join(instruction_parts)


# Global async message queue instance
_async_global_mq: Optional[AsyncMessageQueue] = None


async def get_async_message_queue() -> AsyncMessageQueue:
    """Get global async message queue"""
    global _async_global_mq
    if _async_global_mq is None:
        _async_global_mq = AsyncMessageQueue()
    return _async_global_mq


async def reset_async_message_queue():
    """Reset async message queue"""
    global _async_global_mq
    _async_global_mq = None
