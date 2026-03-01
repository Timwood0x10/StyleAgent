"""
Sub Agent - Outfit Recommendation Execution (using AHP Protocol)
"""

import asyncio
import json
import threading
from typing import Dict, Any, Optional, List
from ..core.models import (
    UserProfile,
    OutfitRecommendation,
    OutfitTask,
    TaskStatus,
    Gender,
)
from ..utils.llm import LocalLLM
from ..utils import get_logger
from ..protocol import get_message_queue, AHPReceiver, AHPSender, AHPError, AHPErrorCode
from ..storage.postgres import StorageLayer

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
        self.sender = AHPSender(self.mq, self.agent_id)
        self._running = False

        # Initialize database for RAG
        self._db: Optional[StorageLayer] = None

    def _get_db(self) -> StorageLayer:
        """Lazy init database connection"""
        if self._db is None:
            self._db = StorageLayer()
        return self._db

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
                logger.info(
                    f"[{self.agent_id}] received task: {msg.payload.get('category')}"
                )
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
            # Convert gender string to Gender enum
            gender_str = user_info.get("gender", "male")
            gender = (
                Gender.MALE
                if str(gender_str).lower() in ("male", "男")
                else Gender.FEMALE
            )
            profile = UserProfile(
                name=user_info.get("name", "User"),
                gender=gender,
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
            # Get compact_instruction from payload (token control)
            compact_instruction = payload.get("compact_instruction", "")
            result = self._recommend(profile, compact_instruction)

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
            # Move to DLQ for failed tasks
            self.mq.to_dlq(self.agent_id, msg, str(e))
            logger.error(f"[{self.agent_id}] task failed: {e}")

    def _get_rag_context(self, user_profile: UserProfile, limit: int = 3) -> str:
        """
        Get RAG context from historical recommendations
        
        Args:
            user_profile: User profile for generating query
            limit: Maximum number of similar recommendations to retrieve
            
        Returns:
            Formatted historical recommendations context
        """
        try:
            # Generate query text from user profile
            query_text = self._build_rag_query(user_profile)
            
            # Generate embedding
            embedding = self.llm.embed(query_text)
            
            # Search similar recommendations in vector DB
            db = self._get_db()
            similar_results = db.search_similar(
                embedding=embedding,
                session_id=None,  # Search across all sessions
                limit=limit
            )
            
            if not similar_results:
                return ""
            
            # Format historical recommendations as context
            context_parts = []
            for i, result in enumerate(similar_results, 1):
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                if content:
                    context_parts.append(
                        f"- Similar recommendation {i}: {content} "
                        f"(mood: {metadata.get('mood', 'N/A')}, "
                        f"season: {metadata.get('season', 'N/A')})"
                    )
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.warning(f"RAG context retrieval failed: {e}")
            return ""

    def _build_rag_query(self, user_profile: UserProfile) -> str:
        """Build query text for RAG embedding"""
        return (
            f"Recommend {self.category} for user who is {user_profile.gender.value}, "
            f"age {user_profile.age}, occupation {user_profile.occupation}, "
            f"mood {user_profile.mood}, season {user_profile.season}, "
            f"occasion {user_profile.occasion}, budget {user_profile.budget}"
        )

    def _recommend(self, user_profile: UserProfile, compact_instruction: str = "") -> OutfitRecommendation:
        """Execute recommendation with tools and RAG"""

        # Use tools to get additional context
        from .resources import AgentResourceFactory

        resources = AgentResourceFactory.create_for_category(
            self.category, llm=self.llm
        )

        # Get fashion suggestions based on mood/occupation/season
        fashion_info = resources.use_tool(
            "fashion_search",
            mood=user_profile.mood,
            occupation=user_profile.occupation,
            season=user_profile.season,
            age=user_profile.age,
        )

        # Get weather info
        weather_info = resources.use_tool(
            "weather_check",
            location="Beijing",
            season=user_profile.season,
            mood=user_profile.mood,
        )

        # Get style recommendations
        style_info = resources.use_tool(
            "style_recommend",
            style="casual",
            age=user_profile.age,
            occupation=user_profile.occupation,
            mood=user_profile.mood,
            budget=user_profile.budget,
        )

        # RAG: Search similar historical recommendations
        rag_context = self._get_rag_context(user_profile)

        # Build enhanced prompt with tool results, compact_instruction and RAG context
        prompt = self._build_prompt(
            user_profile, fashion_info, weather_info, style_info, compact_instruction, rag_context
        )
        response = self.llm.invoke(prompt, self.system_prompt)

        return self._parse_response(response)

    def _build_prompt(
        self,
        user_profile: UserProfile,
        fashion_info: dict = None,
        weather_info: dict = None,
        style_info: dict = None,
        compact_instruction: str = "",
        rag_context: str = "",
    ) -> str:
        """Build prompt with tool results and RAG context"""

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

        # Build tool context
        tool_context = ""
        if fashion_info:
            colors = fashion_info.get("colors", [])
            style_tips = fashion_info.get("style_tips", [])
            season_colors = fashion_info.get("season_colors", [])
            tool_context += "\nFashion Database Suggestions:\n"
            if colors:
                tool_context += f"- Colors for mood: {', '.join(colors)}\n"
            if style_tips:
                tool_context += f"- Style tips: {', '.join(style_tips)}\n"
            if season_colors:
                tool_context += f"- Season colors: {', '.join(season_colors)}\n"

        if weather_info:
            temp = weather_info.get("temperature", "")
            weather = weather_info.get("weather", "")
            suggestion = weather_info.get("suggestion", "")
            tool_context += f"\nWeather Info ({weather_info.get('location', 'N/A')}):\n"
            tool_context += f"- Temperature: {temp}, Weather: {weather}\n"
            tool_context += f"- Suggestion: {suggestion}\n"

        if style_info:
            items = style_info.get("items", [])
            tips = style_info.get("tips", [])
            tool_context += (
                f"\nStyle Recommendations ({style_info.get('style', 'casual')}):\n"
            )
            if items:
                tool_context += f"- Recommended items: {', '.join(items[:4])}\n"
            if tips:
                tool_context += f"- Tips: {', '.join(tips)}\n"

        # Include compact instruction if provided
        compact_section = ""
        if compact_instruction:
            compact_section = f"\n[Compact Instruction - follow this if available]:\n{compact_instruction}\n"

        # Include RAG context from historical recommendations
        rag_section = ""
        if rag_context:
            rag_section = f"\n[Historical Similar Recommendations - for reference]:\n{rag_context}\n"

        prompt = f"""{compact_section}{rag_section}
User Info:
{user_profile.to_prompt_context()}
{tool_context}

Please recommend {category_names.get(self.category, self.category)} for the user.

{mood_adjustments.get(user_profile.mood, "")}

Requirements:
1. Choose appropriate styles based on user's age ({user_profile.age}) and occupation ({user_profile.occupation})
2. Consider season ({user_profile.season}) and occasion ({user_profile.occasion})
3. Budget: {user_profile.budget}
4. If user has hobbies: {", ".join(user_profile.hobbies)}, consider how these hobbies affect outfit choices

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
            logger.warning(
                f"Failed to parse outfit recommendation, using fallback: {e}"
            )

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


# ========== Async Version ==========


class AsyncOutfitSubAgent:
    """Async Outfit Sub Agent"""

    def __init__(self, agent_id: str, category: str, llm: LocalLLM):
        self.agent_id = agent_id
        self.category = category
        self.llm = llm
        self.system_prompt = CATEGORY_PROMPTS.get(
            category, "You are a fashion consultant"
        )
        self.mq = None
        self.receiver = None
        self.sender = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start async agent"""
        from ..protocol import get_async_message_queue, AsyncAHPReceiver, AsyncAHPSender

        self.mq = await get_async_message_queue()
        self.receiver = AsyncAHPReceiver(self.agent_id, self.mq)
        self.sender = AsyncAHPSender(self.mq, self.agent_id)
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Async {self.agent_id} started")

    async def stop(self):
        """Stop async agent"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Async {self.agent_id} stopped")

    async def _run_loop(self):
        """Main async loop"""
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.receiver.wait_for_task(timeout=5), timeout=5.0
                )
                if msg:
                    logger.info(
                        f"[Async {self.agent_id}] received task: {msg.payload.get('category')}"
                    )
                    await self._handle_task(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in async loop: {e}")

    async def _handle_task(self, msg):
        """Handle task (async)"""
        task_id = msg.task_id
        session_id = msg.session_id
        payload = msg.payload

        try:
            # 1. Send progress
            await self.sender.send_progress(
                "leader", task_id, session_id, 0.1, "Starting"
            )

            # 2. Execute recommendation
            user_info = payload.get("user_info", {})
            # Convert gender string to Gender enum
            gender_str = user_info.get("gender", "male")
            gender = (
                Gender.MALE
                if str(gender_str).lower() in ("male", "男")
                else Gender.FEMALE
            )
            profile = UserProfile(
                name=user_info.get("name", "User"),
                gender=gender,
                age=user_info.get("age", 25),
                occupation=user_info.get("occupation", ""),
                hobbies=user_info.get("hobbies", []),
                mood=user_info.get("mood", "normal"),
                season=user_info.get("season", "spring"),
                occasion=user_info.get("occasion", "daily"),
            )

            await self.sender.send_progress(
                "leader", task_id, session_id, 0.5, "Recommending..."
            )
            # Get compact_instruction from payload (token control)
            compact_instruction = payload.get("compact_instruction", "")
            result = await self._recommend(profile, compact_instruction)

            await self.sender.send_progress(
                "leader", task_id, session_id, 0.9, "Completed"
            )

            # 3. Return result
            await self.sender.send_result(
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

            logger.info(f"[Async {self.agent_id}] task completed")

        except Exception as e:
            await self.sender.send_result(
                "leader", task_id, session_id, {"error": str(e)}, status="failed"
            )
            logger.error(f"[Async {self.agent_id}] task failed: {e}")

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
            logger.warning(
                f"Failed to parse outfit recommendation, using fallback: {e}"
            )

        return OutfitRecommendation(
            category=self.category,
            items=["Pending"],
            colors=["TBD"],
            reasons=["Waiting"],
        )

    async def _recommend(self, user_profile: UserProfile, compact_instruction: str = "") -> OutfitRecommendation:
        """Execute recommendation (async) with tools"""
        from .resources import AgentResourceFactory

        resources = AgentResourceFactory.create_for_category(
            self.category, llm=self.llm
        )

        # Get fashion suggestions
        fashion_info = resources.use_tool(
            "fashion_search",
            mood=user_profile.mood,
            occupation=user_profile.occupation,
            season=user_profile.season,
            age=user_profile.age,
        )

        # Get weather info
        weather_info = resources.use_tool(
            "weather_check",
            location="Beijing",
            season=user_profile.season,
            mood=user_profile.mood,
        )

        # Get style recommendations
        style_info = resources.use_tool(
            "style_recommend",
            style="casual",
            age=user_profile.age,
            occupation=user_profile.occupation,
            mood=user_profile.mood,
            budget=user_profile.budget,
        )

        # Build enhanced prompt with compact_instruction
        prompt = self._build_prompt(
            user_profile, fashion_info, weather_info, style_info, compact_instruction
        )
        response = await self.llm.ainvoke(prompt, self.system_prompt)
        return self._parse_response(response)

    def _build_prompt(
        self,
        user_profile: UserProfile,
        fashion_info: dict = None,
        weather_info: dict = None,
        style_info: dict = None,
        compact_instruction: str = "",
    ) -> str:
        """Build prompt with tool results"""
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

        # Build tool context
        tool_context = ""
        if fashion_info:
            colors = fashion_info.get("colors", [])
            style_tips = fashion_info.get("style_tips", [])
            season_colors = fashion_info.get("season_colors", [])
            tool_context += "\nFashion Database Suggestions:\n"
            if colors:
                tool_context += f"- Colors for mood: {', '.join(colors)}\n"
            if style_tips:
                tool_context += f"- Style tips: {', '.join(style_tips)}\n"
            if season_colors:
                tool_context += f"- Season colors: {', '.join(season_colors)}\n"

        if weather_info:
            temp = weather_info.get("temperature", "")
            weather = weather_info.get("weather", "")
            suggestion = weather_info.get("suggestion", "")
            tool_context += f"\nWeather Info ({weather_info.get('location', 'N/A')}):\n"
            tool_context += f"- Temperature: {temp}, Weather: {weather}\n"
            tool_context += f"- Suggestion: {suggestion}\n"

        if style_info:
            items = style_info.get("items", [])
            tips = style_info.get("tips", [])
            tool_context += (
                f"\nStyle Recommendations ({style_info.get('style', 'casual')}):\n"
            )
            if items:
                tool_context += f"- Recommended items: {', '.join(items[:4])}\n"
            if tips:
                tool_context += f"- Tips: {', '.join(tips)}\n"

        # Add compact instruction context if provided (token control)
        compact_ctx = f"\nCompact Instruction: {compact_instruction}\n" if compact_instruction else ""

        prompt = f"""{compact_ctx}User Info:
{user_profile.to_prompt_context()}
{tool_context}

Please recommend {category_names.get(self.category, self.category)} for the user.

{mood_adjustments.get(user_profile.mood, "")}

Requirements:
1. Choose appropriate styles based on user's age ({user_profile.age}) and occupation ({user_profile.occupation})
2. Consider season ({user_profile.season}) and occasion ({user_profile.occasion})
3. Budget: {user_profile.budget}
4. If user has hobbies: {", ".join(user_profile.hobbies)}, consider how these hobbies affect outfit choices

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


class AsyncOutfitAgentFactory:
    """Async Outfit Agent Factory"""

    @staticmethod
    async def create_agents(llm: LocalLLM) -> Dict[str, AsyncOutfitSubAgent]:
        """Create all async outfit agents"""
        agents = {
            "agent_head": AsyncOutfitSubAgent("agent_head", "head", llm),
            "agent_top": AsyncOutfitSubAgent("agent_top", "top", llm),
            "agent_bottom": AsyncOutfitSubAgent("agent_bottom", "bottom", llm),
            "agent_shoes": AsyncOutfitSubAgent("agent_shoes", "shoes", llm),
        }
        # Start all agents
        for agent in agents.values():
            await agent.start()
        return agents

    @staticmethod
    async def stop_agents(agents: Dict[str, AsyncOutfitSubAgent]):
        """Stop all async agents"""
        for agent in agents.values():
            await agent.stop()
