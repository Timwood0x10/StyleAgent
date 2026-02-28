"""
Core Module - Core Components
"""

from .models import (
    UserProfile,
    Gender,
    OutfitTask,
    OutfitRecommendation,
    OutfitResult,
    TaskStatus,
)
from .registry import TaskRegistry, get_task_registry, get_registry
from .validator import ResultValidator, get_validator, ValidationLevel

__all__ = [
    "UserProfile",
    "Gender",
    "OutfitTask",
    "OutfitRecommendation",
    "OutfitResult",
    "TaskStatus",
    "TaskRegistry",
    "get_task_registry",
    "get_registry",
    "ResultValidator",
    "get_validator",
    "ValidationLevel",
]
