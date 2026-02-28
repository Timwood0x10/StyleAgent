"""
Core Data Models - Outfit Recommendation System
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


class TaskStatus(str, Enum):
    """Task status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Gender(str, Enum):
    """Gender enum"""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


@dataclass
class UserProfile:
    """User profile"""
    name: str
    gender: Gender
    age: int
    occupation: str  # Profession
    hobbies: List[str] = field(default_factory=list)  # Hobbies
    mood: str = "normal"  # Mood: happy/normal/depressed/excited
    style_preference: str = ""  # Style preference
    budget: str = "medium"  # Budget: low/medium/high
    season: str = "spring"  # Season
    occasion: str = "daily"  # Occasion
    
    def to_prompt_context(self) -> str:
        """Convert to prompt context"""
        hobbies_str = ", ".join(self.hobbies) if self.hobbies else "none"
        mood_desc = {
            "happy": "happy",
            "normal": "neutral",
            "depressed": "depressed",
            "excited": "excited"
        }.get(self.mood, "neutral")
        
        gender_str = "Male" if self.gender == Gender.MALE else "Female"
        
        return f"""User Info:
- Name: {self.name}
- Gender: {gender_str}
- Age: {self.age}
- Occupation: {self.occupation}
- Hobbies: {hobbies_str}
- Today's Mood: {mood_desc}
- Style Preference: {self.style_preference or "no specific preference"}
- Budget: {self.budget}
- Season: {self.season}
- Occasion: {self.occasion}"""


@dataclass
class OutfitTask:
    """Outfit task"""
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
    """Outfit recommendation result"""
    category: str  # head/top/bottom/shoes
    items: List[str] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    styles: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    price_range: str = ""
    
    def to_display(self) -> str:
        """Format for display"""
        lines = [f"[{self.category.upper()}]"]
        if self.items:
            lines.append(f"  Items: {', '.join(self.items)}")
        if self.colors:
            lines.append(f"  Colors: {', '.join(self.colors)}")
        if self.styles:
            lines.append(f"  Styles: {', '.join(self.styles)}")
        if self.reasons:
            lines.append(f"  Reasons: {'; '.join(self.reasons)}")
        return "\n".join(lines)


@dataclass
class OutfitResult:
    """Complete outfit result"""
    session_id: str
    user_profile: UserProfile
    head: Optional[OutfitRecommendation] = None
    top: Optional[OutfitRecommendation] = None
    bottom: Optional[OutfitRecommendation] = None
    shoes: Optional[OutfitRecommendation] = None
    overall_style: str = ""
    summary: str = ""
    
    def to_display(self) -> str:
        """Complete display"""
        lines = [
            "=" * 50,
            f"User: {self.user_profile.name} ({self.user_profile.age} {self.user_profile.occupation})",
            f"Mood: {self.user_profile.mood} | Hobbies: {', '.join(self.user_profile.hobbies)}",
            "=" * 50,
            ""
        ]
        
        for part in [self.head, self.top, self.bottom, self.shoes]:
            if part:
                lines.append(part.to_display())
                lines.append("")
        
        if self.overall_style:
            lines.append(f"Overall Style: {self.overall_style}")
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        
        lines.append("=" * 50)
        return "\n".join(lines)