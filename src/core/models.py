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
    """user profile with context awareness"""

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
    
    # Context awareness fields
    previous_recommendations: List[str] = field(default_factory=list)  # History of recommended items
    preferred_colors: List[str] = field(default_factory=list)  # User's preferred colors
    rejected_items: List[str] = field(default_factory=list)  # Items user rejected
    body_type: str = ""  # Body type for better recommendations
    skin_tone: str = ""  # Skin tone for color matching
    
    def to_prompt_context(self) -> str:
        """transform user profile to prompt context"""
        hobbies_str = "、".join(self.hobbies) if self.hobbies else "无"
        mood_desc = {
            "happy": "心情愉悦",
            "normal": "心情一般",
            "depressed": "心情压抑",
            "excited": "心情激动",
        }.get(self.mood, "心情一般")
        
        # Build context sections
        context_parts = [
            f"- 姓名: {self.name}",
            f"- 性别: {"男" if self.gender == Gender.MALE else "女"}",
            f"- 年龄: {self.age}岁",
            f"- 职业: {self.occupation}",
            f"- 爱好: {hobbies_str}",
            f"- 今日心情: {mood_desc}",
            f"- 风格偏好: {self.style_preference or "无特定偏好"}",
            f"- 预算: {self.budget}",
            f"- 季节: {self.season}",
            f"- 场合: {self.occasion}",
        ]
        
        # Add context awareness fields if available
        if self.previous_recommendations:
            prev_str = "、".join(self.previous_recommendations[-5:])  # Last 5 items
            context_parts.append(f"- 历史推荐: {prev_str}")
        
        if self.preferred_colors:
            colors_str = "、".join(self.preferred_colors)
            context_parts.append(f"- 喜好的颜色: {colors_str}")
            
        if self.rejected_items:
            rejected_str = "、".join(self.rejected_items[-3:])  # Last 3 rejected
            context_parts.append(f"- 拒绝过的单品: {rejected_str}")
        
        if self.body_type:
            context_parts.append(f"- 体型: {self.body_type}")
            
        if self.skin_tone:
            context_parts.append(f"- 肤色: {self.skin_tone}")
        
        return "用户信息:\n" + "\n".join(context_parts)


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
