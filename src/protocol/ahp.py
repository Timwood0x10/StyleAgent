"""
AHP (Agent HTTP-like Protocol) Communication Protocol

Supported methods:
- TASK: Dispatch task (Leader -> Sub)
- RESULT: Return result (Sub -> Leader)
- PROGRESS: Progress report (Sub -> Leader)
- HEARTBEAT: Heartbeat check (bidirectional)
- TOKEN_REQUEST: Token request
- TOKEN_RESPONSE: Token response
"""

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
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


class MessageQueue:
    """Agent message queue with timeout and heartbeat support"""

    def __init__(self):
        self._queues: Dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._heartbeats: Dict[str, datetime] = {}  # Agent heartbeats

    def get_queue(self, agent_id: str) -> queue.Queue:
        """Get queue for agent"""
        with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = queue.Queue()
            return self._queues[agent_id]

    def send(self, agent_id: str, message: AHPMessage):
        """Send message"""
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
        logger.debug(f"SEND [->{target_agent}] TASK: {payload.get('category', 'unknown')} (token_limit: {token_limit})")
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


class AHPReceiver:
    """AHP Receiver"""

    def __init__(self, agent_id: str, message_queue: MessageQueue):
        self.agent_id = agent_id
        self.mq = message_queue

    def receive(self, timeout: float = 30) -> Optional[AHPMessage]:
        """Receive message"""
        msg = self.mq.receive(self.agent_id, timeout)
        if msg:
            logger.debug(f"RECV [<-{self.agent_id}] {msg.method}")
            self.mq.update_heartbeat(self.agent_id)
        return msg

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
