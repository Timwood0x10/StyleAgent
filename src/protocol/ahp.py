"""
AHP (Agent HTTP-like Protocol) 通信协议
"""
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class AHPMessage:
    """AHP 消息格式"""
    method: str          # TASK / RESULT / PROGRESS / HEARTBEAT
    agent_id: str        # 目标 Agent ID
    task_id: str         # 任务 ID
    session_id: str      # 会话 ID
    payload: Dict[str, Any] = field(default_factory=dict)
    token_limit: int = 500
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "token_limit": self.token_limit,
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id
        }


class MessageQueue:
    """Agent 消息队列"""
    
    def __init__(self):
        self._queues: Dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
    
    def get_queue(self, agent_id: str) -> queue.Queue:
        with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = queue.Queue()
            return self._queues[agent_id]
    
    def send(self, agent_id: str, message: AHPMessage):
        """发送消息"""
        self.get_queue(agent_id).put(message)
    
    def receive(self, agent_id: str, timeout: float = 30) -> Optional[AHPMessage]:
        """接收消息"""
        try:
            return self.get_queue(agent_id).get(timeout=timeout)
        except queue.Empty:
            return None
    
    def broadcast(self, agent_ids: list, message: AHPMessage):
        """广播消息"""
        for agent_id in agent_ids:
            self.send(agent_id, message)


class AHPSender:
    """AHP 发送器"""
    
    def __init__(self, message_queue: MessageQueue):
        self.mq = message_queue
    
    def send_task(self, target_agent: str, task_id: str, session_id: str, 
                  payload: Dict[str, Any], token_limit: int = 500) -> AHPMessage:
        """发送任务给 Agent"""
        msg = AHPMessage(
            method="TASK",
            agent_id=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload=payload,
            token_limit=token_limit
        )
        self.mq.send(target_agent, msg)
        print(f"   📤 [→{target_agent}] TASK: {payload.get('category', 'unknown')}")
        return msg
    
    def send_result(self, target_agent: str, task_id: str, session_id: str,
                   result: Dict[str, Any], status: str = "success") -> AHPMessage:
        """发送结果"""
        msg = AHPMessage(
            method="RESULT",
            agent_id=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload={"result": result, "status": status}
        )
        self.mq.send(target_agent, msg)
        return msg
    
    def send_progress(self, target_agent: str, task_id: str, session_id: str,
                     progress: float, message: str = "") -> AHPMessage:
        """发送进度"""
        msg = AHPMessage(
            method="PROGRESS",
            agent_id=target_agent,
            task_id=task_id,
            session_id=session_id,
            payload={"progress": progress, "message": message}
        )
        self.mq.send(target_agent, msg)
        return msg


class AHPReceiver:
    """AHP 接收器"""
    
    def __init__(self, agent_id: str, message_queue: MessageQueue):
        self.agent_id = agent_id
        self.mq = message_queue
    
    def receive(self, timeout: float = 30) -> Optional[AHPMessage]:
        """接收消息"""
        msg = self.mq.receive(self.agent_id, timeout)
        if msg:
            print(f"   📥 [←{self.agent_id}] {msg.method}")
        return msg
    
    def wait_for_task(self, timeout: float = 60) -> Optional[AHPMessage]:
        """等待任务"""
        msg = self.receive(timeout)
        if msg and msg.method == "TASK":
            return msg
        return None


# 全局消息队列实例
_global_mq: Optional[MessageQueue] = None

def get_message_queue() -> MessageQueue:
    """获取全局消息队列"""
    global _global_mq
    if _global_mq is None:
        _global_mq = MessageQueue()
    return _global_mq
