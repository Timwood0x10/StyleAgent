"""
Tests for Memory Distillation Module

Tests for Message, StructuredMemory, MemoryDistiller, and SessionMemory classes.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.utils.context import (
    Message,
    StructuredMemory,
    MemoryDistiller,
    SessionMemory,
    CHARS_PER_TOKEN,
)


class MockLLM:
    """Mock LLM for testing."""

    def __init__(self, mock_response: str = "", fail: bool = False):
        self.available = True
        self._mock_response = mock_response
        self._fail = fail
        self.invoke_count = 0
        self.embed_count = 0

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        self.invoke_count += 1
        if self._fail:
            raise Exception("Mock LLM error")
        return self._mock_response

    async def ainvoke(self, prompt: str, system_prompt: str = "") -> str:
        self.invoke_count += 1
        if self._fail:
            raise Exception("Mock LLM error")
        return self._mock_response

    def embed(self, text: str):
        self.embed_count += 1
        return [0.1] * 1536


class MockStorage:
    """Mock StorageLayer for testing."""

    def __init__(self):
        self.saved_memories = []
        self.search_results = []

    def save_distilled_memory(
        self,
        session_id: str,
        agent_id: str,
        summary: str,
        original_token_count: int,
        compressed_token_count: int,
        memory_type: str = "user_memory",
        distill_level: int = 1,
        embedding=None,
        metadata: dict = None,
    ):
        self.saved_memories.append(
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "summary": summary,
                "original_token_count": original_token_count,
                "compressed_token_count": compressed_token_count,
                "memory_type": memory_type,
                "distill_level": distill_level,
                "embedding": embedding,
                "metadata": metadata,
            }
        )

    def get_distilled_memories(
        self, session_id: str, agent_id: str, memory_type: str = None, limit: int = 5
    ):
        return self.search_results

    def search_similar_memories(
        self, embedding, agent_id: str, memory_type: str = None, limit: int = 3
    ):
        return self.search_results


class TestMessage:
    """Test Message class."""

    def test_message_creation(self):
        msg = Message(role="user", content="Hello", timestamp="2024-01-01")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp == "2024-01-01"

    def test_message_default_timestamp(self):
        msg = Message(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
        assert msg.timestamp == ""


class TestStructuredMemory:
    """Test StructuredMemory class."""

    def test_creation_with_defaults(self):
        mem = StructuredMemory()
        assert mem.user_profile == {}
        assert mem.decisions_made == []
        assert mem.pending_tasks == []
        assert mem.important_facts == []
        assert mem.metadata == {}

    def test_creation_with_values(self):
        mem = StructuredMemory(
            user_profile={"age": 25, "gender": "male"},
            decisions_made=[{"key": "buy_shoes", "description": "Buy Nike shoes"}],
            pending_tasks=[{"task_id": "task1", "description": "Return item"}],
            important_facts=["Likes blue color"],
            metadata={"source": "distillation"},
        )
        assert mem.user_profile == {"age": 25, "gender": "male"}
        assert len(mem.decisions_made) == 1
        assert len(mem.pending_tasks) == 1
        assert "Likes blue color" in mem.important_facts

    def test_to_dict(self):
        mem = StructuredMemory(
            user_profile={"name": "Tom"},
            decisions_made=[{"key": "d1", "description": "Decision 1"}],
        )
        d = mem.to_dict()
        assert d["user_profile"] == {"name": "Tom"}
        assert len(d["decisions_made"]) == 1

    def test_to_json(self):
        mem = StructuredMemory(user_profile={"city": "Beijing"})
        json_str = mem.to_json()
        assert "Beijing" in json_str
        assert json.loads(json_str)["user_profile"]["city"] == "Beijing"

    def test_from_dict(self):
        data = {
            "user_profile": {"hobby": "reading"},
            "decisions_made": [{"key": "d1", "description": "Test"}],
            "pending_tasks": [],
            "important_facts": ["Fact1"],
            "metadata": {},
        }
        mem = StructuredMemory.from_dict(data)
        assert mem.user_profile == {"hobby": "reading"}
        assert len(mem.decisions_made) == 1

    def test_from_json(self):
        json_str = '{"user_profile": {"color": "red"}}'
        mem = StructuredMemory.from_json(json_str)
        assert mem.user_profile == {"color": "red"}

    def test_from_json_invalid(self):
        json_str = "not valid json"
        mem = StructuredMemory.from_json(json_str)
        assert mem.user_profile == {}

    def test_merge(self):
        mem1 = StructuredMemory(
            user_profile={"age": 20, "city": "Beijing"},
            decisions_made=[{"key": "d1", "description": "Decision 1"}],
            important_facts=["Fact A"],
        )
        mem2 = StructuredMemory(
            user_profile={"age": 25, "gender": "male"},  # age should override
            decisions_made=[
                {"key": "d1", "description": "Decision 1"},  # duplicate, should skip
                {"key": "d2", "description": "Decision 2"},
            ],
            important_facts=["Fact A", "Fact B"],  # Fact A duplicate
        )
        merged = mem1.merge(mem2)
        assert merged.user_profile == {"age": 25, "city": "Beijing", "gender": "male"}
        assert len(merged.decisions_made) == 2
        assert "Fact A" in merged.important_facts
        assert "Fact B" in merged.important_facts


class TestMemoryDistiller:
    """Test MemoryDistiller class."""

    def test_creation(self):
        distiller = MemoryDistiller(agent_id="test_agent")
        assert distiller.agent_id == "test_agent"
        assert distiller.max_tokens == 4000
        assert distiller.distill_threshold == 0.8
        assert distiller.keep_recent == 4
        assert len(distiller._history) == 0

    def test_add_message(self):
        distiller = MemoryDistiller()
        distiller.add_message("user", "Hello")
        distiller.add_message("assistant", "Hi there")
        assert len(distiller._history) == 2
        assert distiller._history[0].role == "user"

    def test_add_user_and_assistant(self):
        distiller = MemoryDistiller()
        distiller.add_user("What's the weather?")
        distiller.add_assistant("It's sunny.")
        assert len(distiller._history) == 2

    def test_estimate_tokens(self):
        distiller = MemoryDistiller()
        # 100 characters / 4 = 25 tokens
        text = "a" * 100
        assert distiller.estimate_tokens(text) == 25

    def test_get_current_tokens_empty(self):
        distiller = MemoryDistiller()
        assert distiller.get_current_tokens() == 0

    def test_get_current_tokens_with_history(self):
        distiller = MemoryDistiller()
        distiller.add_user("Hello world")  # 11 chars
        distiller.add_assistant("Hi there")  # 9 chars
        # 20 chars / 4 = 5 tokens for role + content
        tokens = distiller.get_current_tokens()
        assert tokens >= 5

    def test_set_session(self):
        distiller = MemoryDistiller()
        distiller.set_session("session-123")
        assert distiller._session_id == "session-123"

    def test_set_memory_type(self):
        distiller = MemoryDistiller()
        distiller.set_memory_type("task_memory")
        assert distiller._memory_type == "task_memory"

    def test_set_memory_type_invalid(self):
        distiller = MemoryDistiller()
        distiller.set_memory_type("invalid_type")
        assert distiller._memory_type == "user_memory"  # unchanged

    def test_should_distill_not_needed(self):
        distiller = MemoryDistiller(max_tokens=4000, distill_threshold=0.8)
        # Add small content, should not trigger
        for _ in range(3):
            distiller.add_user("Short message")
        assert not distiller.should_distill()

    def test_should_distill_at_max_level(self):
        distiller = MemoryDistiller()
        distiller._distill_level = 3  # Max level
        distiller._history = [Message("user", "x" * 10000)]  # Large content
        assert not distiller.should_distill()

    def test_get_context_no_memory(self):
        distiller = MemoryDistiller()
        distiller.add_user("Hello")
        distiller.add_assistant("Hi")
        ctx = distiller.get_context()
        assert "Hello" in ctx
        assert "Hi" in ctx

    def test_get_context_with_distilled_memory(self):
        distiller = MemoryDistiller()
        distiller._distilled_memory = StructuredMemory(
            user_profile={"name": "Tom"}
        )
        distiller.add_user("Recent message")
        ctx = distiller.get_context()
        assert "Tom" in ctx
        assert "Recent message" in ctx

    def test_get_structured_memory(self):
        distiller = MemoryDistiller()
        mem = StructuredMemory(user_profile={"x": 1})
        distiller._distilled_memory = mem
        assert distiller.get_structured_memory() == mem

    def test_get_full_history(self):
        distiller = MemoryDistiller()
        distiller.add_user("Hello")
        distiller.add_assistant("Hi")
        history = distiller.get_full_history()
        assert len(history) == 2

    def test_clear(self):
        distiller = MemoryDistiller()
        distiller.add_user("Hello")
        distiller._distilled_memory = StructuredMemory(user_profile={"x": 1})
        distiller._distill_level = 2
        distiller.clear()
        assert len(distiller._history) == 0
        assert distiller._distilled_memory is None
        assert distiller._distill_level == 1

    def test_distill_no_llm(self):
        distiller = MemoryDistiller(llm=None)
        distiller.add_user("Hello world" * 100)
        result = distiller.distill()
        assert result is False

    def test_distill_no_llm_async(self):
        distiller = MemoryDistiller(llm=None)
        distiller.add_user("Hello world" * 100)

        import asyncio

        result = asyncio.run(distiller.adistill())
        assert result is False

    def test_distill_not_needed_with_existing_memory(self):
        mock_llm = MockLLM(mock_response='{"user_profile":{}}')
        distiller = MemoryDistiller(llm=mock_llm)
        distiller._distilled_memory = StructuredMemory(
            user_profile={"name": "Tom"}
        )
        # Small content, should not trigger
        distiller.add_user("Hi")
        result = distiller.distill()
        assert result is False

    def test_distill_success(self):
        mock_response = json.dumps(
            {
                "user_profile": {"age": 30},
                "decisions_made": [{"key": "d1", "description": "Buy item"}],
                "pending_tasks": [],
                "important_facts": [],
            }
        )
        mock_llm = MockLLM(mock_response=mock_response)
        mock_storage = MockStorage()

        distiller = MemoryDistiller(
            llm=mock_llm,
            storage=mock_storage,
            agent_id="test",
            max_tokens=100,  # Low threshold to trigger
            distill_threshold=0.5,
            enable_importance_filter=False,  # Disable for test
        )
        distiller.set_session("session-1")

        # Add enough content to trigger distillation
        for i in range(10):
            distiller.add_user(f"Message number {i} with some content here")

        result = distiller.distill()
        assert result is True
        assert distiller._distilled_memory is not None
        assert distiller._distilled_memory.user_profile.get("age") == 30

    def test_distill_saves_to_storage(self):
        mock_response = json.dumps(
            {"user_profile": {"city": "Beijing"}, "decisions_made": [], "pending_tasks": [], "important_facts": []}
        )
        mock_llm = MockLLM(mock_response=mock_response)
        mock_storage = MockStorage()

        distiller = MemoryDistiller(
            llm=mock_llm,
            storage=mock_storage,
            agent_id="test",
            max_tokens=100,
            enable_importance_filter=False,
        )
        distiller.set_session("session-123")

        for i in range(10):
            distiller.add_user(f"Content {i} " * 50)

        distiller.distill()

        # Check storage was called
        assert len(mock_storage.saved_memories) == 1
        saved = mock_storage.saved_memories[0]
        assert saved["session_id"] == "session-123"
        assert saved["agent_id"] == "test"
        assert saved["memory_type"] == "user_memory"

    def test_distill_increments_level(self):
        mock_response = json.dumps(
            {"user_profile": {}, "decisions_made": [], "pending_tasks": [], "important_facts": []}
        )
        mock_llm = MockLLM(mock_response=mock_response)

        distiller = MemoryDistiller(
            llm=mock_llm,
            max_tokens=100,
            enable_importance_filter=False,
        )
        distiller.set_session("session-1")

        for i in range(10):
            distiller.add_user(f"Message {i} " * 50)

        assert distiller._distill_level == 1
        distiller.distill()
        assert distiller._distill_level == 2

    def test_load_from_storage(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        # Setup mock search results
        mock_storage.search_results = [
            {
                "summary": json.dumps(
                    {"user_profile": {"name": "Tom"}, "decisions_made": [], "pending_tasks": [], "important_facts": []}
                )
            }
        ]

        distiller = MemoryDistiller(llm=mock_llm, storage=mock_storage, agent_id="test")
        distiller.set_session("session-1")

        memories = distiller.load_from_storage("session-1", memory_type="user_memory")
        assert len(memories) == 1
        assert memories[0].user_profile.get("name") == "Tom"

    def test_search_similar_memories(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        mock_storage.search_results = [{"summary": '{"user_profile": {"x": 1}}'}]

        distiller = MemoryDistiller(llm=mock_llm, storage=mock_storage, agent_id="test")
        results = distiller.search_similar_memories("query text")
        assert len(results) == 1
        assert mock_llm.embed_count == 1

    def test_len(self):
        distiller = MemoryDistiller()
        distiller.add_user("Hello")
        distiller.add_assistant("Hi")
        distiller.add_user("Bye")
        assert len(distiller) == 3


class TestSessionMemory:
    """Test SessionMemory class."""

    def test_creation(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(
            session_id="sess-1",
            llm=mock_llm,
            storage=mock_storage,
            agent_id="leader",
        )
        assert sm.session_id == "sess-1"
        assert sm.agent_id == "leader"
        assert sm.user_memory is not None
        assert sm.task_memory is not None

    def test_user_memory_type(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)
        assert sm.user_memory._memory_type == "user_memory"

    def test_task_memory_type(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)
        assert sm.task_memory._memory_type == "task_memory"

    def test_add_user_turn(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_user_turn("What's the weather?", "It's sunny.")
        assert len(sm.user_memory._history) == 2

    def test_add_task_context(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_task_context("Recommend shoes")
        assert len(sm.task_memory._history) == 1

    def test_add_system_turn(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_system_turn("Here are some recommendations")
        assert len(sm.user_memory._history) == 1

    def test_get_context(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_user_turn("Hello", "Hi")
        ctx = sm.get_context()
        assert "User Memory" in ctx
        assert "Task Memory" in ctx

    def test_get_user_context(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_user_turn("Hello", "Hi")
        ctx = sm.get_user_context()
        assert "Hello" in ctx
        assert "Task Memory" not in ctx

    def test_get_task_context(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_task_context("Task info")
        ctx = sm.get_task_context()
        assert "Task info" in ctx

    def test_get_user_profile(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        # Set profile directly
        sm.user_memory._distilled_memory = StructuredMemory(
            user_profile={"age": 25, "gender": "male"}
        )
        profile = sm.get_user_profile()
        assert profile == {"age": 25, "gender": "male"}

    def test_get_pending_tasks(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        # Set tasks directly
        sm.task_memory._distilled_memory = StructuredMemory(
            pending_tasks=[{"task_id": "t1", "description": "Buy milk"}]
        )
        tasks = sm.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "t1"

    def test_clear(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_user_turn("Hello", "Hi")
        sm.add_task_context("Task")
        sm.clear()

        assert len(sm.user_memory._history) == 0
        assert len(sm.task_memory._history) == 0


class TestMemoryDistillerAsync:
    """Test async distillation methods."""

    def test_adistill_success(self):
        mock_response = json.dumps(
            {
                "user_profile": {"city": "Shanghai"},
                "decisions_made": [],
                "pending_tasks": [],
                "important_facts": [],
            }
        )
        mock_llm = MockLLM(mock_response=mock_response)
        mock_storage = MockStorage()

        distiller = MemoryDistiller(
            llm=mock_llm,
            storage=mock_storage,
            max_tokens=100,
            enable_importance_filter=False,
        )
        distiller.set_session("session-async")

        for i in range(10):
            distiller.add_user(f"Content {i} " * 50)

        import asyncio

        result = asyncio.run(distiller.adistill())
        assert result is True
        assert distiller._distilled_memory is not None
        assert mock_llm.invoke_count > 0


class TestSessionMemoryAsync:
    """Test async context retrieval."""

    def test_aget_context(self):
        mock_llm = MockLLM()
        mock_storage = MockStorage()
        sm = SessionMemory(session_id="sess-1", llm=mock_llm, storage=mock_storage)

        sm.add_user_turn("Hello", "Hi")

        import asyncio

        ctx = asyncio.run(sm.aget_context())
        assert "User Memory" in ctx
        assert "Task Memory" in ctx


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
