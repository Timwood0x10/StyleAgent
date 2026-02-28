"""
Core Data Model - Outfit Recommendation System
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


@dataclass
class UserProfile:
    """user profile"""

    name: str
    gender: Gender
    age: int
    occupation: str
    hobbies: List[str] = field(default_factory=list)
    mood: str = "normal"  #: happy/normal/depressed/excited
    style_preference: str = ""
    budget: str = "medium"  #  low/medium/high
    season: str = "spring"
    occasion: str = "daily"

    def to_prompt_context(self) -> str:
        """transform user profile to prompt context"""
        hobbies_str = "、".join(self.hobbies) if self.hobbies else "无"
        mood_desc = {
            "happy": "心情愉悦",
            "normal": "心情一般",
            "depressed": "心情压抑",
            "excited": "心情激动",
        }.get(self.mood, "心情一般")

        return f"""用户信息:
- 姓名: {self.name}
- 性别: {"男" if self.gender == Gender.MALE else "女"}
- 年龄: {self.age}岁
- 职业: {self.occupation}
- 爱好: {hobbies_str}
- 今日心情: {mood_desc}
- 风格偏好: {self.style_preference or "无特定偏好"}
- 预算: {self.budget}
- 季节: {self.season}
- 场合: {self.occasion}"""


@dataclass
class OutfitTask:
    """outfit recommendation task"""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    category: str = ""  # head/top/bottom/shoes
    user_profile: Optional[UserProfile] = None
    status: TaskStatus = TaskStatus.PENDING
    assignee_agent_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class OutfitRecommendation:
    """outfit recommendation result"""

    category: str  # head/top/bottom/shoes
    items: List[str] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    styles: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    price_range: str = ""

    def to_display(self) -> str:
        """display"""
        lines = [f"【{self.category}】"]
        if self.items:
            lines.append(f"  推荐: {', '.join(self.items)}")
        if self.colors:
            lines.append(f"  颜色: {', '.join(self.colors)}")
        if self.styles:
            lines.append(f"  风格: {', '.join(self.styles)}")
        if self.reasons:
            lines.append(f"  理由: {'; '.join(self.reasons)}")
        return "\n".join(lines)


@dataclass
class OutfitResult:
    """final outfit recommendation result"""

    session_id: str
    user_profile: UserProfile
    head: Optional[OutfitRecommendation] = None
    top: Optional[OutfitRecommendation] = None
    bottom: Optional[OutfitRecommendation] = None
    shoes: Optional[OutfitRecommendation] = None
    overall_style: str = ""
    summary: str = ""

    def to_display(self) -> str:
        """final display format"""
        lines = [
            "=" * 50,
            f"👤 user: {self.user_profile.name} ({self.user_profile.age} age  {self.user_profile.occupation})",
            f"📝 Today's mood: {self.user_profile.mood} | Hobby: {', '.join(self.user_profile.hobbies)}",
            "=" * 50,
            "",
        ]

        for part in [self.head, self.top, self.bottom, self.shoes]:
            if part:
                lines.append(part.to_display())
                lines.append("")

        if self.overall_style:
            lines.append(f"🎯 Overall Style: {self.overall_style}")
        if self.summary:
            lines.append(f"📝 Summary: {self.summary}")

        lines.append("=" * 50)
        return "\n".join(lines)
