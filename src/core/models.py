"""
核心数据模型 - 穿搭推荐系统
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
    """用户画像"""
    name: str
    gender: Gender
    age: int
    occupation: str  # 职业
    hobbies: List[str] = field(default_factory=list)  # 爱好
    mood: str = "normal"  # 心情: happy/normal/depressed/excited
    style_preference: str = ""  # 风格偏好
    budget: str = "medium"  # 预算: low/medium/high
    season: str = "spring"  # 季节
    occasion: str = "daily"  # 场合
    
    def to_prompt_context(self) -> str:
        """转换为提示词上下文"""
        hobbies_str = "、".join(self.hobbies) if self.hobbies else "无"
        mood_desc = {
            "happy": "心情愉悦",
            "normal": "心情一般",
            "depressed": "心情压抑",
            "excited": "心情激动"
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
    """穿搭任务"""
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
    """穿搭推荐结果"""
    category: str  # head/top/bottom/shoes
    items: List[str] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    styles: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    price_range: str = ""
    
    def to_display(self) -> str:
        """格式化显示"""
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
    """完整穿搭结果"""
    session_id: str
    user_profile: UserProfile
    head: Optional[OutfitRecommendation] = None
    top: Optional[OutfitRecommendation] = None
    bottom: Optional[OutfitRecommendation] = None
    shoes: Optional[OutfitRecommendation] = None
    overall_style: str = ""
    summary: str = ""
    
    def to_display(self) -> str:
        """完整展示"""
        lines = [
            "=" * 50,
            f"👤 用户: {self.user_profile.name} ({self.user_profile.age}岁 {self.user_profile.occupation})",
            f"📝 今日心情: {self.user_profile.mood} | 爱好: {', '.join(self.user_profile.hobbies)}",
            "=" * 50,
            ""
        ]
        
        for part in [self.head, self.top, self.bottom, self.shoes]:
            if part:
                lines.append(part.to_display())
                lines.append("")
        
        if self.overall_style:
            lines.append(f"🎯 整体风格: {self.overall_style}")
        if self.summary:
            lines.append(f"📝 总结: {self.summary}")
        
        lines.append("=" * 50)
        return "\n".join(lines)
