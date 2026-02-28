"""
Agents Module - Leader + Sub Agents (AHP Protocol)
"""

from .leader_agent import LeaderAgent
from .sub_agent import OutfitSubAgent, OutfitAgentFactory
from .resources import AgentResources, AgentResourceFactory, PrivateContext
from ..core.models import UserProfile, Gender, OutfitRecommendation, OutfitResult
from ..utils.llm import create_llm, LocalLLM

__all__ = [
    "LeaderAgent",
    "OutfitSubAgent",
    "OutfitAgentFactory",
    "AgentResources",
    "AgentResourceFactory",
    "PrivateContext",
    "UserProfile",
    "Gender",
    "OutfitRecommendation",
    "OutfitResult",
    "create_llm",
    "LocalLLM",
]
