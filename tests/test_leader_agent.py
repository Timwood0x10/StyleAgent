"""
Tests for Leader Agent
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.agents.leader_agent import LeaderAgent, AsyncLeaderAgent
from src.core.models import UserProfile, OutfitTask, Gender
from src.utils.llm import LocalLLM


# Mock StorageLayer before importing LeaderAgent
with patch("src.agents.leader_agent.StorageLayer"):
    with patch("src.agents.leader_agent.get_task_registry"):
        with patch("src.agents.leader_agent.get_message_queue"):
            from src.agents.leader_agent import LeaderAgent, AsyncLeaderAgent


class MockLocalLLM:
    """Mock LocalLLM for testing"""

    def __init__(self, mock_response: str = ""):
        self.available = True
        self._mock_response = mock_response

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        return self._mock_response

    async def ainvoke(self, prompt: str, system_prompt: str = "") -> str:
        return self._mock_response


class TestLeaderAgent:
    """Test LeaderAgent"""

    def test_leader_agent_creation(self):
        """Test LeaderAgent can be created"""
        mock_llm = MockLocalLLM()
        with patch("src.agents.leader_agent.StorageLayer"):
            with patch("src.agents.leader_agent.get_task_registry") as mock_reg:
                mock_reg.return_value = Mock()
                with patch("src.agents.leader_agent.get_message_queue"):
                    agent = LeaderAgent(mock_llm)
        assert agent.llm is not None
        assert agent.tasks == []
        assert agent.session_id == ""

    def test_parse_user_profile_valid_input(self):
        """Test parsing valid user profile input"""
        mock_llm = MockLocalLLM(
            mock_response='{"name": "John", "age": 25, "gender": "male", "occupation": "engineer", "hobbies": ["reading"], "mood": "happy"}'
        )
        with patch("src.agents.leader_agent.StorageLayer"):
            with patch("src.agents.leader_agent.get_task_registry") as mock_reg:
                mock_reg.return_value = Mock()
                with patch("src.agents.leader_agent.get_message_queue"):
                    agent = LeaderAgent(mock_llm)

        user_input = "I am John, 25 years old, male, an engineer, I like reading, feeling happy today"
        profile = agent.parse_user_profile(user_input)

        assert profile.name == "John"
        assert profile.age == 25
        assert profile.gender == Gender.MALE
        assert profile.occupation == "engineer"

    def test_fallback_parse_returns_default_profile(self):
        """Test fallback parsing returns default profile"""
        mock_llm = MockLocalLLM()

        with patch("src.agents.leader_agent.StorageLayer"):
            with patch("src.agents.leader_agent.get_task_registry") as mock_reg:
                mock_reg.return_value = Mock()
                with patch("src.agents.leader_agent.get_message_queue"):
                    agent = LeaderAgent(mock_llm)

        user_input = "test input"
        profile = agent._fallback_parse(user_input)

        # Default values from _fallback_parse
        assert profile.name == "User"
        assert profile.age == 25
        assert profile.gender == Gender.MALE

    def test_create_tasks_uses_config(self):
        """Test that create_tasks uses config for categories"""
        from src.utils.config import config

        mock_llm = MockLocalLLM()
        with patch("src.agents.leader_agent.StorageLayer"):
            with patch("src.agents.leader_agent.get_task_registry") as mock_reg:
                mock_reg.return_value = Mock()
                with patch("src.agents.leader_agent.get_message_queue"):
                    agent = LeaderAgent(mock_llm)

                    # Mock _analyze_required_categories to return empty (triggering default)
                    agent._analyze_required_categories = Mock(return_value=[])

        profile = UserProfile(
            name="Test",
            age=25,
            gender=Gender.MALE,
            occupation="engineer",
            hobbies=["reading"],
            mood="happy",
        )

        tasks = agent.create_tasks(profile)

        # Should use default categories from config
        assert len(tasks) > 0
        assert len(tasks) == len(config.SUB_AGENT_CATEGORIES)

        # Check task has correct category and agent_id
        for task in tasks:
            assert task.category in config.SUB_AGENT_CATEGORIES
            assert task.assignee_agent_id.startswith(config.SUB_AGENT_PREFIX)


class TestAsyncLeaderAgent:
    """Test AsyncLeaderAgent"""

    @pytest.mark.asyncio
    async def test_async_leader_agent_creation(self):
        """Test AsyncLeaderAgent can be created"""
        mock_llm = MockLocalLLM()
        with patch("src.agents.leader_agent.StorageLayer"):
            with patch("src.agents.leader_agent.get_task_registry") as mock_reg:
                mock_reg.return_value = Mock()
                with patch("src.agents.leader_agent.get_message_queue"):
                    agent = AsyncLeaderAgent(mock_llm)
        assert agent.llm is not None
        assert agent.tasks == []

    @pytest.mark.asyncio
    async def test_create_tasks_async(self):
        """Test async create_tasks method"""
        from src.utils.config import config

        mock_llm = MockLocalLLM()
        with patch("src.agents.leader_agent.StorageLayer"):
            with patch("src.agents.leader_agent.get_task_registry") as mock_reg:
                mock_reg.return_value = Mock()
                with patch("src.agents.leader_agent.get_message_queue"):
                    agent = AsyncLeaderAgent(mock_llm)

                    # Mock to return empty categories (trigger default) - must be async
                    async def mock_analyze(user_profile):
                        return []
                    agent._analyze_required_categories = mock_analyze

        profile = UserProfile(
            name="Test",
            age=25,
            gender=Gender.MALE,
            occupation="engineer",
            hobbies=["reading"],
            mood="happy",
        )

        tasks = await agent.create_tasks(profile)

        # Should use default categories from config
        assert len(tasks) > 0
        assert len(tasks) == len(config.SUB_AGENT_CATEGORIES)
