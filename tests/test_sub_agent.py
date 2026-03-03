"""
Tests for Sub Agent - including style coordination
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.agents.sub_agent import OutfitSubAgent, AsyncOutfitSubAgent
from src.core.models import UserProfile, OutfitRecommendation, Gender
from src.utils.llm import LocalLLM


# Mock StorageLayer and other dependencies
with patch("src.agents.sub_agent.get_message_queue"):
    with patch("src.agents.sub_agent.StorageLayer"):
        from src.agents.sub_agent import OutfitSubAgent, AsyncOutfitSubAgent


class MockLocalLLM:
    """Mock LocalLLM for testing"""

    def __init__(self, mock_response: str = ""):
        self.available = True
        self._mock_response = mock_response

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        return self._mock_response

    async def ainvoke(self, prompt: str, system_prompt: str = "") -> str:
        return self._mock_response

    def embed(self, text: str):
        """Mock embed returns dummy vector"""
        return [0.1] * 1536


class TestOutfitSubAgent:
    """Test OutfitSubAgent"""

    def test_sub_agent_creation(self):
        """Test OutfitSubAgent can be created"""
        mock_llm = MockLocalLLM()
        with patch("src.agents.sub_agent.get_message_queue"):
            with patch("src.agents.sub_agent.StorageLayer"):
                agent = OutfitSubAgent("agent_shoes", "shoes", mock_llm)

        assert agent.agent_id == "agent_shoes"
        assert agent.category == "shoes"
        assert agent.llm is not None

    def test_recommend_accepts_coordination_context(self):
        """Test _recommend method accepts coordination_context parameter"""
        mock_llm = MockLocalLLM(
            mock_response='{"items": ["sneakers"], "colors": ["white"], "styles": ["casual"], "reasons": ["match"]}'
        )
        with patch("src.agents.sub_agent.get_message_queue"):
            with patch("src.agents.sub_agent.StorageLayer"):
                agent = OutfitSubAgent("agent_shoes", "shoes", mock_llm)

        profile = UserProfile(
            name="Test",
            age=25,
            gender=Gender.MALE,
            occupation="engineer",
            hobbies=[],
            mood="happy",
        )

        coordination_context = {
            "top": {
                "items": ["T-shirt"],
                "colors": ["navy blue"],
                "styles": ["casual"],
            },
            "bottom": {
                "items": ["jeans"],
                "colors": ["blue"],
                "styles": ["casual"],
            },
        }

        # This should not raise any error
        result = agent._recommend(profile, "", coordination_context)

        assert result is not None
        assert result.category == "shoes"

    def test_build_prompt_includes_coordination_context(self):
        """Test _build_prompt includes coordination_context in prompt"""
        mock_llm = MockLocalLLM()
        with patch("src.agents.sub_agent.get_message_queue"):
            with patch("src.agents.sub_agent.StorageLayer"):
                agent = OutfitSubAgent("agent_shoes", "shoes", mock_llm)

        profile = UserProfile(
            name="Test",
            age=25,
            gender=Gender.MALE,
            occupation="engineer",
            hobbies=["reading"],
            mood="happy",
        )

        coordination_context = {
            "top": {
                "items": ["cotton T-shirt", "denim jacket"],
                "colors": ["navy blue", "white"],
                "styles": ["casual", "modern"],
            },
            "bottom": {
                "items": ["slim-fit chinos"],
                "colors": ["black"],
                "styles": ["formal"],
            },
        }

        prompt = agent._build_prompt(
            user_profile=profile,
            fashion_info={},
            weather_info={},
            style_info={},
            compact_instruction="",
            rag_context="",
            coordination_context=coordination_context,
        )

        # Verify coordination context is in prompt
        assert "Already Recommended Categories" in prompt
        assert "top" in prompt
        assert "cotton T-shirt" in prompt
        assert "navy blue" in prompt
        assert "bottom" in prompt
        assert "slim-fit chinos" in prompt

    def test_build_prompt_works_without_coordination_context(self):
        """Test _build_prompt works when coordination_context is None"""
        mock_llm = MockLocalLLM()
        with patch("src.agents.sub_agent.get_message_queue"):
            with patch("src.agents.sub_agent.StorageLayer"):
                agent = OutfitSubAgent("agent_top", "top", mock_llm)

        profile = UserProfile(
            name="Test",
            age=25,
            gender=Gender.MALE,
            occupation="engineer",
            hobbies=[],
            mood="normal",
        )

        # Should work with None
        prompt = agent._build_prompt(
            user_profile=profile,
            fashion_info={},
            weather_info={},
            style_info={},
            compact_instruction="",
            rag_context="",
            coordination_context=None,
        )

        assert prompt is not None
        assert "top" in prompt.lower()

    def test_build_prompt_empty_coordination_context(self):
        """Test _build_prompt works with empty coordination_context"""
        mock_llm = MockLocalLLM()
        with patch("src.agents.sub_agent.get_message_queue"):
            with patch("src.agents.sub_agent.StorageLayer"):
                agent = OutfitSubAgent("agent_head", "head", mock_llm)

        profile = UserProfile(
            name="Test",
            age=30,
            gender=Gender.FEMALE,
            occupation="designer",
            hobbies=[],
            mood="happy",
        )

        # Should work with empty dict
        prompt = agent._build_prompt(
            user_profile=profile,
            fashion_info={},
            weather_info={},
            style_info={},
            compact_instruction="",
            rag_context="",
            coordination_context={},
        )

        assert prompt is not None

    def test_handle_task_extracts_coordination_context(self):
        """Test _handle_task extracts coordination_context from payload"""
        from src.protocol.ahp import AHPMessage, AHPMethod

        mock_llm = MockLocalLLM(
            mock_response='{"items": ["hat"], "colors": ["black"], "styles": ["casual"], "reasons": ["test"]}'
        )

        mock_mq = Mock()
        mock_sender = Mock()

        with patch("src.agents.sub_agent.get_message_queue", return_value=mock_mq):
            with patch("src.agents.sub_agent.StorageLayer"):
                with patch("src.agents.resources.AgentResourceFactory") as mock_factory:
                    # Mock factory returns mock resources
                    mock_resources = Mock()
                    mock_resources.use_tool = Mock(return_value={})
                    mock_factory.create_for_category = Mock(return_value=mock_resources)

                    agent = OutfitSubAgent("agent_head", "head", mock_llm)
                    agent.sender = mock_sender

                    # Create mock message with coordination_context
                    payload = {
                        "category": "head",
                        "user_info": {
                            "name": "TestUser",
                            "gender": "male",
                            "age": 25,
                            "occupation": "engineer",
                            "hobbies": [],
                            "mood": "happy",
                            "season": "spring",
                            "occasion": "daily",
                        },
                        "coordination_context": {
                            "top": {
                                "items": ["T-shirt"],
                                "colors": ["white"],
                                "styles": ["casual"],
                            }
                        },
                    }

                    msg = AHPMessage(
                        method=AHPMethod.TASK,
                        agent_id="leader",
                        target_agent="agent_head",
                        task_id="task-123",
                        session_id="session-123",
                        payload=payload,
                    )

                    # Execute handle_task - should not raise exception
                    agent._handle_task(msg)

                    # Verify result was sent (task completed successfully)
                    assert mock_sender.send_result.called

                    # Verify the call was successful (no error status)
                    call_args = mock_sender.send_result.call_args
                    # Check if status is "success"
                    status = call_args.kwargs.get("status") or (
                        call_args[0][3] if len(call_args[0]) > 3 else None
                    )
                    assert (
                        status == "success" or call_args[1].get("status") == "success"
                    )


class TestAsyncOutfitSubAgent:
    """Test AsyncOutfitSubAgent"""

    def test_async_sub_agent_creation(self):
        """Test AsyncOutfitSubAgent can be created"""
        mock_llm = MockLocalLLM()
        agent = AsyncOutfitSubAgent("agent_shoes", "shoes", mock_llm)

        assert agent.agent_id == "agent_shoes"
        assert agent.category == "shoes"

    def test_async_build_prompt_includes_coordination_context(self):
        """Test async _build_prompt includes coordination_context"""
        mock_llm = MockLocalLLM()
        with patch("src.protocol.ahp.get_async_message_queue"):
            agent = AsyncOutfitSubAgent("agent_shoes", "shoes", mock_llm)

        profile = UserProfile(
            name="Test",
            age=25,
            gender=Gender.MALE,
            occupation="engineer",
            hobbies=[],
            mood="happy",
        )

        coordination_context = {
            "top": {
                "items": ["jacket"],
                "colors": ["black"],
                "styles": ["formal"],
            }
        }

        prompt = agent._build_prompt(
            user_profile=profile,
            fashion_info={},
            weather_info={},
            style_info={},
            compact_instruction="",
            rag_context="",
            coordination_context=coordination_context,
        )

        assert "Already Recommended Categories" in prompt
        assert "jacket" in prompt


class TestStyleCoordinationIntegration:
    """Integration tests for style coordination between agents"""

    def test_full_coordination_flow(self):
        """Test complete coordination flow from Leader to SubAgent"""
        # Simulate Leader building coordination context
        phase1_results = {
            "top": OutfitRecommendation(
                category="top",
                items=["fitted cotton T-shirt"],
                colors=["navy blue", "white"],
                styles=["casual", "modern"],
                reasons=["matches mood"],
                price_range="¥200-500",
            ),
            "bottom": OutfitRecommendation(
                category="bottom",
                items=["slim-fit chinos"],
                colors=["dark gray"],
                styles=["smart casual"],
                reasons=["coordinates with top"],
                price_range="¥300-600",
            ),
        }

        # Build coordination context (as LeaderAgent does)
        coordination_context = {
            cat: {"items": r.items, "colors": r.colors, "styles": r.styles}
            for cat, r in phase1_results.items()
        }

        # Verify coordination context format
        assert "top" in coordination_context
        assert "bottom" in coordination_context
        assert "fitted cotton T-shirt" in coordination_context["top"]["items"]
        assert "slim-fit chinos" in coordination_context["bottom"]["items"]

        # Now simulate SubAgent using this context
        mock_llm = MockLocalLLM(
            mock_response='{"items": ["white sneakers"], "colors": ["white"], "styles": ["casual"], "reasons": ["match"]}'
        )

        with patch("src.agents.sub_agent.get_message_queue"):
            with patch("src.agents.sub_agent.StorageLayer"):
                with patch("src.agents.resources.AgentResourceFactory") as mock_factory:
                    # Mock factory returns mock resources
                    mock_resources = Mock()
                    mock_resources.use_tool = Mock(return_value={})
                    mock_factory.create_for_category = Mock(return_value=mock_resources)

                    agent = OutfitSubAgent("agent_shoes", "shoes", mock_llm)

                    profile = UserProfile(
                        name="Test",
                        age=25,
                        gender=Gender.MALE,
                        occupation="engineer",
                        hobbies=[],
                        mood="happy",
                    )

                    # Call _recommend with coordination context
                    result = agent._recommend(profile, "", coordination_context)

                    # The result should be generated (LLM was called)
                    assert result is not None
                    assert result.category == "shoes"

    def test_coordination_context_format(self):
        """Test coordination_context has correct format for all categories"""
        from src.utils.config import config

        # Test that all possible category combinations work
        categories = config.SUB_AGENT_CATEGORIES

        for primary_cat in categories:
            other_cats = [c for c in categories if c != primary_cat]

            # Build context excluding primary category
            context = {}
            for cat in other_cats:
                context[cat] = {
                    "items": [f"item_{cat}_1", f"item_{cat}_2"],
                    "colors": ["color1", "color2"],
                    "styles": ["style1"],
                }

            # Verify context structure
            for cat, info in context.items():
                assert "items" in info
                assert "colors" in info
                assert "styles" in info
                assert len(info["items"]) == 2
