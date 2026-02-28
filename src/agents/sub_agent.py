"""
Sub Agent - Outfit Recommendation Execution (using AHP Protocol)
"""

import json
import threading
from typing import Dict, Any, Optional
from ..core.models import UserProfile, OutfitRecommendation, OutfitTask, TaskStatus
from ..utils.llm import LocalLLM
from ..utils import get_logger
from ..protocol import get_message_queue, AHPReceiver, AHPSender

# Logger for this module
logger = get_logger(__name__)


# System prompts for each category
CATEGORY_PROMPTS = {
    "head": """You are an accessory expert, skilled at recommending head accessories like hats, glasses, necklaces, earrings.
Based on user characteristics and mood, recommend suitable accessories.
Note:
- When mood is depressed, choose accessories that bring vitality or comfort
- Consider user's occupation and daily activities
- Provide specific color and style suggestions""",
    "top": """You are a tops expert, skilled at recommending T-shirts, shirts, jackets, hoodies, etc.
Based on user characteristics and mood, recommend suitable tops.
Note:
- When mood is depressed, choose colors that improve mood (like bright colors)
- Consider season and occasion
- Provide specific style and color suggestions""",
    "bottom": """You are a bottoms expert, skilled at recommending jeans, casual pants, dress pants, etc.
Based on user characteristics and mood, recommend suitable bottoms.
Note:
- Consider coordination with tops
- Comfort and occasion requirements
- Provide specific style and color suggestions""",
    "shoes": """You are a footwear expert, skilled at recommending all kinds of shoes.
Based on user characteristics and mood, recommend suitable shoes.
Note:
- Consider coordination with overall outfit
- Comfort and practicality
- Provide specific style and color suggestions""",
}


class OutfitSubAgent:
    """Outfit Sub Agent (communicating via AHP Protocol)"""

    def __init__(self, agent_id: str, category: str, llm: LocalLLM):
        self.agent_id = agent_id
        self.category = category
        self.llm = llm
        self.system_prompt = CATEGORY_PROMPTS.get(
            category, "You are a fashion consultant"
        )
        self.mq = get_message_queue()
        self.receiver = AHPReceiver(agent_id, self.mq)
        self.sender = AHPSender(self.mq)
        self._running = False

    def start(self):
        """Start agent (listen to message queue)"""
        self._running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        logger.info(f"{self.agent_id} started (listening)")

    def stop(self):
        """Stop agent"""
        self._running = False

    def _run_loop(self):
        """Main loop - listen for messages"""
        while self._running:
            msg = self.receiver.wait_for_task(timeout=5)
            if msg:
                logger.info(f"[{self.agent_id}] received task: {msg.payload.get('category')}")
                self._handle_task(msg)

    def _handle_task(self, msg):
        """Handle task"""
        task_id = msg.task_id
        session_id = msg.session_id
        payload = msg.payload

        try:
            # 1. Send progress
            self.sender.send_progress("leader", task_id, session_id, 0.1, "Starting")

            # 2. Execute recommendation
            user_info = payload.get("user_info", {})
            profile = UserProfile(
                name=user_info.get("name", "User"),
                gender=user_info.get("gender", "male"),
                age=user_info.get("age", 25),
                occupation=user_info.get("occupation", ""),
                hobbies=user_info.get("hobbies", []),
                mood=user_info.get("mood", "normal"),
                season=user_info.get("season", "spring"),
                occasion=user_info.get("occasion", "daily"),
            )

            self.sender.send_progress(
                "leader", task_id, session_id, 0.5, "Recommending..."
            )
            result = self._recommend(profile)

            self.sender.send_progress("leader", task_id, session_id, 0.9, "Completed")

            # 3. Return result
            self.sender.send_result(
                "leader",
                task_id,
                session_id,
                {
                    "category": self.category,
                    "items": result.items,
                    "colors": result.colors,
                    "styles": result.styles,
                    "reasons": result.reasons,
                    "price_range": result.price_range,
                },
                status="success",
            )

            logger.info(f"[{self.agent_id}] task completed")

        except Exception as e:
            self.sender.send_result(
                "leader", task_id, session_id, {"error": str(e)}, status="failed"
            )
            logger.error(f"[{self.agent_id}] task failed: {e}")

    def _recommend(self, user_profile: UserProfile) -> OutfitRecommendation:
        """Execute recommendation"""

        prompt = self._build_prompt(user_profile)
        response = self.llm.invoke(prompt, self.system_prompt)

        return self._parse_response(response)

    def _build_prompt(self, user_profile: UserProfile) -> str:
        """Build prompt"""

        category_names = {
            "head": "head accessories (hats, glasses, necklaces, earrings, etc.)",
            "top": "tops (T-shirts, shirts, jackets, hoodies, etc.)",
            "bottom": "bottoms (jeans, casual pants, dress pants, etc.)",
            "shoes": "shoes (sneakers, dress shoes, casual shoes, etc.)",
        }

        mood_adjustments = {
            "depressed": "User is feeling depressed today, recommend styles that bring vitality or comfort, consider adding some bright colors",
            "happy": "User is happy today, can choose more vibrant and lively styles",
            "excited": "User is excited, recommend elegant and appropriate styles",
            "normal": "User's mood is normal, choose comfortable and natural styles",
        }

        prompt = f"""User Info:
{user_profile.to_prompt_context()}

Please recommend {category_names.get(self.category, self.category)} for the user.

{mood_adjustments.get(user_profile.mood, "")}

Requirements:
1. Choose appropriate styles based on user's age ({user_profile.age}) and occupation ({user_profile.occupation})
2. Consider season ({user_profile.season}) and occasion ({user_profile.occasion})
3. Budget: {user_profile.budget}
4. If user has hobbies: {', '.join(user_profile.hobbies)}, consider how these hobbies affect outfit choices

Please return JSON format:
{{
    "category": "{self.category}",
    "items": ["recommended item 1", "recommended item 2"],
    "colors": ["color 1", "color 2"],
    "styles": ["style 1", "style 2"],
    "reasons": ["reason 1", "reason 2"],
    "price_range": "price range"
}}

Only return JSON.
"""
        return prompt

    def _parse_response(self, response: str) -> OutfitRecommendation:
        """Parse response"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return OutfitRecommendation(
                    category=data.get("category", self.category),
                    items=data.get("items", []),
                    colors=data.get("colors", []),
                    styles=data.get("styles", []),
                    reasons=data.get("reasons", []),
                    price_range=data.get("price_range", ""),
                )
        except Exception as e:
            logger.warning(f"Failed to parse outfit recommendation, using fallback: {e}")

        return OutfitRecommendation(
            category=self.category,
            items=["Pending"],
            colors=["TBD"],
            reasons=["Waiting"],
        )


class OutfitAgentFactory:
    """Outfit Agent Factory (using AHP Protocol)"""

    @staticmethod
    def create_agents(llm: LocalLLM) -> Dict[str, OutfitSubAgent]:
        """Create all outfit agents"""
        return {
            "agent_head": OutfitSubAgent("agent_head", "head", llm),
            "agent_top": OutfitSubAgent("agent_top", "top", llm),
            "agent_bottom": OutfitSubAgent("agent_bottom", "bottom", llm),
            "agent_shoes": OutfitSubAgent("agent_shoes", "shoes", llm),
        }
