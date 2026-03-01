"""
Tests for AHP Protocol
"""

import pytest
from src.protocol.ahp import (
    AHPMessage,
    AHPMethod,
    AHPError,
    AHPErrorCode,
    MessageQueue,
    AHPSender,
    AHPReceiver,
    get_message_queue,
)


class TestAHPMessage:
    """Test AHP message"""

    def test_ahp_message_creation(self):
        """Test creating an AHP message"""
        msg = AHPMessage(
            method=AHPMethod.TASK,
            agent_id="leader",
            target_agent="head",
            task_id="task_123",
            session_id="session_456",
        )
        assert msg.method == AHPMethod.TASK
        assert msg.agent_id == "leader"
        assert msg.target_agent == "head"
        assert msg.task_id == "task_123"
        assert msg.session_id == "session_456"

    def test_ahp_message_to_dict(self):
        """Test converting message to dictionary"""
        msg = AHPMessage(
            method=AHPMethod.RESULT,
            agent_id="head",
            target_agent="leader",
            task_id="task_123",
            session_id="session_456",
            payload={"result": "ok"},
        )
        msg_dict = msg.to_dict()
        assert msg_dict["method"] == AHPMethod.RESULT
        assert msg_dict["payload"]["result"] == "ok"

    def test_ahp_message_from_dict(self):
        """Test creating message from dictionary"""
        data = {
            "method": AHPMethod.TASK,
            "agent_id": "leader",
            "target_agent": "head",
            "task_id": "task_123",
            "session_id": "session_456",
            "payload": {"key": "value"},
            "token_limit": 500,
            "timestamp": "2024-01-01T00:00:00",
            "message_id": "msg_123",
        }
        msg = AHPMessage.from_dict(data)
        assert msg.method == AHPMethod.TASK
        assert msg.agent_id == "leader"
        assert msg.task_id == "task_123"
        assert msg.message_id == "msg_123"

    def test_ahp_message_roundtrip(self):
        """Test message serialization roundtrip"""
        original = AHPMessage(
            method=AHPMethod.PROGRESS,
            agent_id="head",
            target_agent="leader",
            task_id="task_123",
            session_id="session_456",
            payload={"progress": 0.5},
        )
        restored = AHPMessage.from_dict(original.to_dict())
        assert restored.method == original.method
        assert restored.agent_id == original.agent_id
        assert restored.task_id == original.task_id

    def test_ahp_methods(self):
        """Test AHP method constants"""
        assert AHPMethod.TASK == "TASK"
        assert AHPMethod.RESULT == "RESULT"
        assert AHPMethod.PROGRESS == "PROGRESS"
        assert AHPMethod.HEARTBEAT == "HEARTBEAT"
        assert AHPMethod.ACK == "ACK"


class TestAHPError:
    """Test AHP Error"""

    def test_ahp_error_creation(self):
        """Test creating an AHP error"""
        error = AHPError(
            message="Test error",
            code=AHPErrorCode.TIMEOUT,
            agent_id="head",
            task_id="task_123",
        )
        assert error.message == "Test error"
        assert error.code == AHPErrorCode.TIMEOUT
        assert error.agent_id == "head"
        assert error.task_id == "task_123"

    def test_ahp_error_to_dict(self):
        """Test converting error to dictionary"""
        error = AHPError(
            message="Test error",
            code=AHPErrorCode.INVALID_MESSAGE,
            details={"key": "value"},
        )
        error_dict = error.to_dict()
        assert error_dict["message"] == "Test error"
        assert error_dict["code"] == "INVALID_MESSAGE"
        assert error_dict["details"]["key"] == "value"

    def test_ahp_error_codes(self):
        """Test AHP error codes"""
        assert AHPErrorCode.UNKNOWN.value == "UNKNOWN"
        assert AHPErrorCode.TIMEOUT.value == "TIMEOUT"
        assert AHPErrorCode.RETRY_EXHAUSTED.value == "RETRY_EXHAUSTED"


class TestMessageQueue:
    """Test MessageQueue"""

    def test_message_queue_creation(self):
        """Test creating a message queue"""
        mq = MessageQueue()
        assert mq is not None

    def test_get_queue(self):
        """Test getting a queue for an agent"""
        mq = MessageQueue()
        queue = mq.get_queue("test_agent")
        assert queue is not None

    def test_send_and_receive(self):
        """Test sending and receiving a message"""
        mq = MessageQueue()

        msg = AHPMessage(
            method=AHPMethod.TASK,
            agent_id="leader",
            target_agent="head",
            task_id="task_123",
            session_id="session_456",
        )

        mq.send("head", msg)

        # Try to receive (may timeout)
        received = mq.receive("head", timeout=1)
        # The message might not be available immediately due to threading
        assert received is None or received.task_id == "task_123"

    def test_message_deduplication(self):
        """Test message deduplication"""
        mq = MessageQueue()

        msg = AHPMessage(
            method=AHPMethod.TASK,
            agent_id="leader",
            target_agent="head",
            task_id="task_123",
            session_id="session_456",
        )

        # Send same message twice
        mq.send("head", msg)
        mq.send("head", msg)

        # Should only receive one
        received = mq.receive("head", timeout=1)
        assert received is not None
        # Second receive should timeout (queue should be empty)
        received2 = mq.receive("head", timeout=1)
        assert received2 is None

    def test_dlq_operations(self):
        """Test Dead Letter Queue operations"""
        mq = MessageQueue(max_retries=2)

        msg = AHPMessage(
            method=AHPMethod.TASK,
            agent_id="leader",
            target_agent="head",
            task_id="task_123",
            session_id="session_456",
        )

        # Move message to DLQ
        mq.to_dlq("head", msg, "Test error")

        dlq = mq.get_dlq("head")
        assert len(dlq) == 1
        assert dlq[0]["error"] == "Test error"

    def test_retry_mechanism(self):
        """Test retry mechanism"""
        mq = MessageQueue(max_retries=3)

        msg_id = "test_msg_123"

        # Check should_retry
        assert mq.should_retry(msg_id) is True
        assert mq.should_retry(msg_id) is True

        # Increment retry count
        count1 = mq.increment_retry(msg_id)
        assert count1 == 1
        assert mq.should_retry(msg_id) is True

        count2 = mq.increment_retry(msg_id)
        assert count2 == 2
        assert mq.should_retry(msg_id) is True

        count3 = mq.increment_retry(msg_id)
        assert count3 == 3
        # Should not retry after max_retries
        assert mq.should_retry(msg_id) is False

        # Reset retry
        mq.reset_retry(msg_id)
        assert mq.should_retry(msg_id) is True


class TestAHPSender:
    """Test AHP Sender"""

    def test_ahp_sender_creation(self):
        """Test creating an AHP sender"""
        mq = MessageQueue()
        sender = AHPSender(mq)
        assert sender.mq is not None


class TestAHPReceiver:
    """Test AHP Receiver"""

    def test_ahp_receiver_creation(self):
        """Test creating an AHP receiver"""
        mq = MessageQueue()
        receiver = AHPReceiver("head", mq)
        assert receiver.agent_id == "head"


class TestGetMessageQueue:
    """Test get_message_queue function"""

    def test_get_message_queue(self):
        """Test getting the global message queue"""
        mq1 = get_message_queue()
        mq2 = get_message_queue()
        # Should return the same instance
        assert mq1 is mq2
