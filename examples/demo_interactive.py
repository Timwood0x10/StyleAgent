#!/usr/bin/env python3
"""
Interactive Outfit Recommendation Demo
Multi-turn conversation with LeaderAgent + SubAgent system
Supports user feedback, context awareness, and continuous improvement
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.utils.llm import LocalLLM, MockLLM
from src.agents.leader_agent import LeaderAgent
from src.agents.sub_agent import OutfitSubAgent
from src.protocol import get_message_queue
from src.core.models import UserProfile, Gender, OutfitResult
from src.storage.postgres import StorageLayer


class FeedbackType(Enum):
    """User feedback types"""
    LIKE = "like"           # 喜欢推荐
    DISLIKE = "dislike"     # 不喜欢
    TOO_EXPENSIVE = "too_expensive"  # 太贵
    TOO_CHEAP = "too_cheap"  # 太便宜
    TOO_FORMAL = "too_formal"  # 太正式
    TOO_CASUAL = "too_casual"  # 太随意
    CHANGE_COLOR = "change_color"  # 换颜色
    CHANGE_STYLE = "change_style"  # 换风格
    CHANGE_ITEM = "change_item"  # 换单品
    OTHER = "other"         # 其他


class SessionManager:
    """Manage conversation sessions and user profiles"""

    def __init__(self):
        self.current_session_id: Optional[str] = None
        self.current_user_profile: Optional[UserProfile] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.last_recommendation: Optional[OutfitResult] = None

    def start_new_session(self):
        """Start a new conversation session"""
        self.current_session_id = str(uuid.uuid4())
        self.conversation_history = []
        self.last_recommendation = None
        print("\n🆕 开始新的对话会话")

    def update_user_profile(self, profile: UserProfile):
        """Update user profile"""
        self.current_user_profile = profile

    def add_to_history(self, role: str, content: str):
        """Add message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_context_summary(self) -> str:
        """Get summary of conversation context"""
        if not self.conversation_history:
            return "暂无对话历史"

        recent = self.conversation_history[-3:]
        summary_parts = []
        for msg in recent:
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            summary_parts.append(f"{role_emoji} {msg['content'][:50]}...")

        return "\n".join(summary_parts)


class InteractiveDemo:
    """Interactive outfit recommendation demo with feedback support"""

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self.llm = None
        self.leader = None
        self.sub_agents = []
        self.session_manager = SessionManager()
        self._running = False
        self.storage = None

    def setup(self):
        """Initialize the system"""
        print("\n" + "=" * 60)
        print("🧥 穿搭推荐系统 - 交互式对话")
        print("=" * 60)

        # Initialize LLM
        if self.use_mock:
            print("\n📦 使用 Mock LLM")
            self.llm = MockLLM(response=self._get_mock_response())
        else:
            print("\n🔗 连接 LLM...")
            self.llm = LocalLLM()
            if not self.llm.available:
                print("⚠️  LLM 不可用，自动切换到 Mock 模式")
                self.llm = MockLLM(response=self._get_mock_response())
                self.use_mock = True
            else:
                print(f"✅ LLM 已连接: {self.llm.model_name}")

        # Initialize Leader Agent
        print("\n🔧 初始化 Leader Agent...")
        self.leader = LeaderAgent(self.llm)
        print("✅ Leader Agent 已就绪")

        # Initialize Sub Agents
        print("\n🔧 初始化 Sub Agents...")
        categories = ["head", "top", "bottom", "shoes"]
        for cat in categories:
            agent = OutfitSubAgent(f"agent_{cat}", cat, self.llm)
            agent.start()
            self.sub_agents.append(agent)
        print(f"✅ {len(self.sub_agents)} 个 Sub Agent 已启动")

        # Initialize storage
        print("\n💾 初始化存储...")
        try:
            self.storage = StorageLayer()
            print("✅ 存储已就绪")
        except Exception as e:
            print(f"⚠️  存储初始化失败: {e}")
            self.storage = None

        # Start new session
        self.session_manager.start_new_session()

        print("\n" + "=" * 60)
        print("🎉 系统初始化完成！")
        print("=" * 60)

    def _get_mock_response(self) -> str:
        """Get mock LLM response for demo"""
        return json.dumps({
            "items": ["T-shirt", "Casual shirt"],
            "colors": ["blue", "white"],
            "styles": ["casual", "comfortable"],
            "reasons": ["适合你的年龄和气质", "百搭易搭配"],
            "price_range": "medium"
        })

    def cleanup(self):
        """Cleanup resources"""
        print("\n🧹 清理资源...")
        for agent in self.sub_agents:
            agent.stop()
        print("✅ 已清理")

    def parse_feedback(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Parse user feedback from input"""
        user_input_lower = user_input.lower()

        # 正面反馈
        positive_keywords = ["喜欢", "不错", "可以", "好", "满意", "yes", "good", "ok", "like"]
        if any(kw in user_input_lower for kw in positive_keywords):
            return {"type": FeedbackType.LIKE.value, "content": user_input}

        # 不喜欢
        if "不喜欢" in user_input or "不要" in user_input or "dislike" in user_input_lower:
            return {"type": FeedbackType.DISLIKE.value, "content": user_input}

        # 太贵
        if "太贵" in user_input or "贵了" in user_input or "expensive" in user_input_lower:
            return {"type": FeedbackType.TOO_EXPENSIVE.value, "content": user_input}

        # 太便宜
        if "太便宜" in user_input or "cheap" in user_input_lower:
            return {"type": FeedbackType.TOO_CHEAP.value, "content": user_input}

        # 太正式
        if "太正式" in user_input or "formal" in user_input_lower:
            return {"type": FeedbackType.TOO_FORMAL.value, "content": user_input}

        # 太随意
        if "太随意" in user_input or "casual" in user_input_lower:
            return {"type": FeedbackType.TOO_CASUAL.value, "content": user_input}

        # 换颜色
        if "换颜色" in user_input or "change color" in user_input_lower:
            return {"type": FeedbackType.CHANGE_COLOR.value, "content": user_input}

        # 换风格
        if "换风格" in user_input or "change style" in user_input_lower:
            return {"type": FeedbackType.CHANGE_STYLE.value, "content": user_input}

        # 换单品
        if "换" in user_input or "change" in user_input_lower:
            return {"type": FeedbackType.CHANGE_ITEM.value, "content": user_input}

        return None

    def build_refined_prompt(self, original_input: str, feedback: Dict[str, Any]) -> str:
        """Build refined prompt based on user feedback"""
        feedback_type = feedback["type"]
        content = feedback["content"]

        refinement_context = f"""
基于用户反馈调整推荐:
- 原始需求: {original_input}
- 反馈类型: {feedback_type}
- 反馈内容: {content}

请根据反馈重新调整推荐方案。
"""

        # Add specific guidance based on feedback type
        if feedback_type == FeedbackType.DISLIKE.value:
            refinement_context += "\n用户不喜欢当前推荐，请提供完全不同的风格或单品。"
        elif feedback_type == FeedbackType.TOO_EXPENSIVE.value:
            refinement_context += "\n用户认为价格太高，请推荐更实惠的选项。"
        elif feedback_type == FeedbackType.TOO_CHEAP.value:
            refinement_context += "\n用户希望更高端的推荐，请推荐更高品质的单品。"
        elif feedback_type == FeedbackType.TOO_FORMAL.value:
            refinement_context += "\n用户认为太正式了，请推荐更轻松休闲的风格。"
        elif feedback_type == FeedbackType.TOO_CASUAL.value:
            refinement_context += "\n用户希望更正式一些，请推荐更专业的风格。"
        elif feedback_type == FeedbackType.CHANGE_COLOR.value:
            refinement_context += "\n用户想换一种颜色，请提供其他颜色选择。"
        elif feedback_type == FeedbackType.CHANGE_STYLE.value:
            refinement_context += "\n用户想换一种风格，请提供不同的风格选择。"
        elif feedback_type == FeedbackType.CHANGE_ITEM.value:
            refinement_context += "\n用户想换一些单品，请提供其他选择。"

        return refinement_context

    def process_input(self, user_input: str) -> dict:
        """Process user input and return recommendation"""
        print(f"\n🔄 处理输入: {user_input}")

        # Check if this is feedback on previous recommendation
        feedback = self.parse_feedback(user_input)

        if feedback and self.session_manager.last_recommendation:
            # This is feedback - refine the recommendation
            print(f"\n📝 检测到反馈: {feedback['type']}")
            return self._process_feedback(user_input, feedback)

        # New recommendation request
        try:
            # Build enhanced prompt with context
            context = self._build_context_prompt(user_input)

            # Use LeaderAgent to process
            result = self.leader.process(context)

            if result:
                # Update session
                self.session_manager.update_user_profile(result.user_profile)
                self.session_manager.last_recommendation = result
                self.session_manager.add_to_history("user", user_input)
                self.session_manager.add_to_history("assistant", "推荐完成")

                return {
                    "success": True,
                    "result": result,
                    "is_new": True
                }
            else:
                return {
                    "success": False,
                    "error": "No result returned"
                }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

    def _build_context_prompt(self, user_input: str) -> str:
        """Build prompt with conversation context"""
        prompt = user_input

        # Add user profile context if available
        profile = self.session_manager.current_user_profile
        if profile:
            context_parts = []
            if profile.name and profile.name != "User":
                context_parts.append(f"用户名为 {profile.name}")
            if profile.occupation:
                context_parts.append(f"职业是 {profile.occupation}")
            if profile.style_preference:
                context_parts.append(f"偏好风格是 {profile.style_preference}")

            if context_parts:
                prompt = f"{'，'.join(context_parts)}，{user_input}"

        # Add conversation history context
        history = self.session_manager.conversation_history
        if history:
            recent_context = "之前的对话："
            for msg in history[-2:]:
                role = "用户" if msg["role"] == "user" else "系统"
                recent_context += f"\n{role}: {msg['content'][:100]}"
            prompt = f"{recent_context}\n\n当前需求: {user_input}"

        return prompt

    def _process_feedback(self, original_input: str, feedback: Dict[str, Any]) -> dict:
        """Process user feedback and refine recommendation"""
        try:
            # Build refined prompt
            refined_prompt = self.build_refined_prompt(original_input, feedback)

            # Get previous recommendation for context
            prev_result = self.session_manager.last_recommendation
            if prev_result:
                prev_profile = prev_result.user_profile

                # Update profile with feedback
                if feedback["type"] == FeedbackType.TOO_EXPENSIVE.value:
                    prev_profile.budget = "low"
                elif feedback["type"] == FeedbackType.TOO_CHEAP.value:
                    prev_profile.budget = "high"
                elif feedback["type"] == FeedbackType.TOO_FORMAL.value:
                    prev_profile.style_preference = "casual"
                elif feedback["type"] == FeedbackType.TOO_CASUAL.value:
                    prev_profile.style_preference = "formal"

                # Record rejected items
                if prev_result.head and prev_result.head.items:
                    prev_profile.rejected_items.extend(prev_result.head.items)
                if prev_result.top and prev_result.top.items:
                    prev_profile.rejected_items.extend(prev_result.top.items)
                if prev_result.bottom and prev_result.bottom.items:
                    prev_profile.rejected_items.extend(prev_result.bottom.items)
                if prev_result.shoes and prev_result.shoes.items:
                    prev_profile.rejected_items.extend(prev_result.shoes.items)

            # Process refined request
            result = self.leader.process(refined_prompt)

            if result:
                # Update session
                self.session_manager.last_recommendation = result
                self.session_manager.add_to_history("user", f"反馈: {feedback['content']}")
                self.session_manager.add_to_history("assistant", "根据反馈调整推荐")

                return {
                    "success": True,
                    "result": result,
                    "is_new": False,
                    "feedback_applied": feedback["type"]
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to process feedback"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def display_result(self, result: dict):
        """Display recommendation result"""
        if not result.get("success"):
            print(f"\n❌ 错误: {result.get('error', 'Unknown error')}")
            return

        outfit = result.get("result")
        if not outfit:
            print("\n❌ 没有返回结果")
            return

        # Display header
        print("\n" + "=" * 60)
        if result.get("is_new", True):
            print("👔 穿搭推荐")
        else:
            print("🔄 根据反馈调整后的推荐")
        print("=" * 60)

        profile = outfit.user_profile
        print(f"\n👤 用户信息")
        print("-" * 40)
        gender_str = "女" if profile.gender == Gender.FEMALE else "男"
        print(f"  姓名: {profile.name}")
        print(f"  性别: {gender_str}")
        print(f"  年龄: {profile.age}")
        if profile.occupation:
            print(f"  职业: {profile.occupation}")
        if profile.mood:
            print(f"  心情: {profile.mood}")
        if profile.occasion:
            print(f"  场合: {profile.occasion}")
        if profile.budget:
            print(f"  预算: {profile.budget}")
        if profile.season:
            print(f"  季节: {profile.season}")

        print(f"\n👔 推荐穿搭")
        print("-" * 40)

        categories = {
            "head": "🎩 头部配饰",
            "top": "👕 上装",
            "bottom": "👖 下装",
            "shoes": "👟 鞋子",
        }

        for cat, title in categories.items():
            item = getattr(outfit, cat, None)
            if item and item.items:
                print(f"\n{title}")
                print(f"  推荐: {', '.join(item.items)}")
                if item.colors:
                    print(f"  颜色: {', '.join(item.colors)}")
                if item.styles:
                    print(f"  风格: {', '.join(item.styles)}")
                if item.reasons:
                    print(f"  理由: {', '.join(item.reasons)}")

        if outfit.overall_style:
            print(f"\n🎯 整体风格: {outfit.overall_style}")

        if outfit.summary:
            print(f"\n📝 总结: {outfit.summary}")

        print("\n" + "=" * 60)

        # Display feedback hint
        print("\n💡 您可以:")
        print("   - 输入反馈：'太贵了'、'不喜欢'、'太正式'、'太随意'")
        print("   - 输入'换颜色'或'换风格'来调整")
        print("   - 输入新的需求开始新的推荐")
        print("   - 输入'history'查看对话历史")
        print("   - 输入'profile'查看/更新用户信息")
        print("=" * 60)

    def display_help(self):
        """Display help information"""
        print("""
🧥 穿搭推荐系统 - 命令帮助
══════════════════════════════════════════════════════════

📝 基本命令:
   <直接输入需求>     例如: "我需要一套商务正装"
   
💬 反馈命令:
   喜欢/不错/好      确认当前推荐
   不喜欢/不要       不喜欢当前推荐
   太贵了/贵了       预算太高
   太便宜            想要更高端
   太正式            想要更休闲
   太随意            想要更正式
   换颜色            想换颜色
   换风格            想换风格
   换xxx             想换某个单品

🔧 系统命令:
   history / 历史    查看对话历史
   profile / 用户    查看当前用户信息
   clear / 清屏      清空屏幕
   help / 帮助       显示帮助信息
   new / 新会话      开始新的对话会话
   quit / exit / 退出  退出程序

💡 示例:
   - "我是小明，男，25岁，程序员"  (设置用户信息)
   - "给我推荐一套去约会穿的"      (获取推荐)
   - "太贵了"                       (反馈调整)
   - "换颜色"                       (调整推荐)

══════════════════════════════════════════════════════════
""")

    def display_history(self):
        """Display conversation history"""
        history = self.session_manager.conversation_history
        if not history:
            print("\n📜 暂无对话历史")
            return

        print("\n📜 对话历史")
        print("-" * 40)
        for i, msg in enumerate(history, 1):
            role = "👤 用户" if msg["role"] == "user" else "🤖 系统"
            print(f"{i}. {role}: {msg['content'][:80]}")
        print("-" * 40)

    def display_profile(self):
        """Display current user profile"""
        profile = self.session_manager.current_user_profile
        if not profile:
            print("\n👤 暂无用户信息，请先输入您的基本信息")
            return

        print("\n👤 当前用户信息")
        print("-" * 40)
        print(f"  姓名: {profile.name}")
        print(f"  性别: {'女' if profile.gender == Gender.FEMALE else '男'}")
        print(f"  年龄: {profile.age}")
        print(f"  职业: {profile.occupation or '未设置'}")
        print(f"  心情: {profile.mood}")
        print(f"  场合: {profile.occasion}")
        print(f"  预算: {profile.budget}")
        print(f"  季节: {profile.season}")
        if profile.style_preference:
            print(f"  风格偏好: {profile.style_preference}")
        if profile.hobbies:
            print(f"  爱好: {', '.join(profile.hobbies)}")
        print("-" * 40)
        print("💡 如需更新信息，请直接输入新的信息，如：")
        print("   '我今年30岁了' 或 '我的预算是高'")

    def run(self):
        """Run interactive demo"""
        self.setup()

        print("\n" + "-" * 60)
        print("💬 欢迎使用穿搭推荐系统！")
        print("   输入 'help' 查看帮助信息")
        print("-" * 60)

        while True:
            try:
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ["quit", "exit", "q", "退出"]:
                    print("\n👋 再见！感谢使用穿搭推荐系统")
                    break

                if user_input.lower() in ["help", "帮助", "h"]:
                    self.display_help()
                    continue

                if user_input.lower() in ["clear", "清屏", "cls"]:
                    print("\033[2J\033[H")
                    print("🧥 穿搭推荐系统 - 交互式对话")
                    continue

                if user_input.lower() in ["history", "历史", "记录"]:
                    self.display_history()
                    continue

                if user_input.lower() in ["profile", "用户", "用户信息"]:
                    self.display_profile()
                    continue

                if user_input.lower() in ["new", "新会话", "新对话"]:
                    self.session_manager.start_new_session()
                    print("\n🆕 已开始新的对话会话")
                    continue

                # Process input
                result = self.process_input(user_input)

                # Display result
                self.display_result(result)

            except KeyboardInterrupt:
                print("\n\n👋 已退出")
                break
            except Exception as e:
                print(f"\n❌ 错误: {e}")
                import traceback
                traceback.print_exc()

        self.cleanup()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="交互式穿搭推荐系统")
    parser.add_argument(
        "--mock", "-m",
        action="store_true",
        help="使用 Mock LLM (不需要真实 LLM 服务)"
    )
    args = parser.parse_args()

    demo = InteractiveDemo(use_mock=args.mock)
    demo.run()


if __name__ == "__main__":
    main()