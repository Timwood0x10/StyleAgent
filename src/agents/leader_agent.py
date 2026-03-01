"""
Leader Agent - User Profile Parsing and Task Distribution (using AHP Protocol)
"""

import asyncio
import json
import queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, List
from ..core.models import (
    UserProfile,
    Gender,
    OutfitTask,
    OutfitRecommendation,
    OutfitResult,
)
from ..core.validator import ResultValidator, ValidationLevel
from ..core.registry import TaskRegistry, get_task_registry, TaskStatus
from ..core.errors import RetryHandler, RetryConfig, ErrorType, CircuitBreaker
from ..utils.llm import LocalLLM
from ..utils import get_logger
from ..protocol import get_message_queue, AHPSender, AHPError, AHPErrorCode, AHPMethod
from ..storage.postgres import StorageLayer

# Logger for this module
logger = get_logger(__name__)


SYSTEM_PROMPT = """You are a professional fashion consultant, skilled at recommending appropriate outfits based on user information and mood.

You need to:
1. Parse user information, extract key features
2. Adjust outfit style based on user's mood (depressed/happy/normal)
3. Consider user's occupation and hobbies for recommendations
4. Provide professional and thoughtful suggestions

Please reply in JSON format.
"""


class LeaderAgent:
    """Main Agent - User profile parsing and task distribution (via AHP Protocol)"""

    def __init__(self, llm: LocalLLM):
        self.llm = llm
        self.tasks: List[OutfitTask] = []
        self.mq = get_message_queue()
        self.sender = AHPSender(self.mq)
        self.session_id = ""
        self.validator = ResultValidator(level=ValidationLevel.NORMAL)
        self.registry = get_task_registry()
        self._db = StorageLayer()  # For RAG vector storage

        # Initialize retry handler
        retry_config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
            retry_on=[
                ErrorType.LLM_FAILED,
                ErrorType.NETWORK,
                ErrorType.TIMEOUT,
            ],
        )
        self.retry_handler = RetryHandler(retry_config)

        # Initialize circuit breaker for LLM calls
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,  # Open after 5 consecutive failures
            timeout=60,  # Try again after 60 seconds
        )

    def _execute_with_timeout(
        self, func: Callable, timeout: int = 30, *args, **kwargs
    ) -> Any:
        """Execute function with timeout (cross-platform)"""
        import threading

        result = []
        exception = []

        def target():
            try:
                result.append(func(*args, **kwargs))
            except Exception as e:
                exception.append(e)

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise TimeoutError(f"Function execution timed out after {timeout}s")

        if exception:
            raise exception[0]

        return result[0] if result else None

    def _llm_call_with_circuit_breaker(
        self, func_name: str, func: Callable, *args, **kwargs
    ) -> Any:
        """
        Execute LLM call with circuit breaker and retry
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {func_name}, using fallback")
            return self._get_fallback_result(func_name)

        try:
            # Execute with retry
            result = self.retry_handler.execute_with_retry(
                func, f"leader_{func_name}", *args, **kwargs
            )
            self.circuit_breaker.record_success()
            return result
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"Circuit breaker recorded failure for {func_name}: {e}")
            return self._get_fallback_result(func_name)

    def _get_fallback_result(self, func_name: str) -> Any:
        """
        Get fallback result when circuit is open or retry exhausted
        """
        if func_name == "parse_user_profile":
            # Return default user profile
            return UserProfile(
                name="User",
                gender=Gender.MALE,
                age=25,
                occupation="",
                hobbies=[],
                mood="normal",
                budget="medium",
                season="spring",
                occasion="daily",
            )
        elif func_name == "aggregate_results":
            # Return empty result
            return None
        return None

    def _enrich_user_context(
        self, profile: UserProfile, user_input: str
    ) -> UserProfile:
        """
        Enrich user profile with context from previous sessions

        Loads user history to provide:
        - previous_recommendations: Items user liked before
        - preferred_colors: Colors user prefers
        - rejected_items: Items user rejected
        """
        try:
            # Try to get user context from storage based on name
            if profile.name and profile.name != "User":
                # Search for similar users or previous sessions
                # For now, we'll use RAG to find relevant history
                query = (
                    f"user {profile.name} {profile.gender.value} {profile.occupation}"
                )
                try:
                    embedding = self.llm.embed(query)
                    similar = self._db.db.search_similar(embedding, limit=3)

                    if similar:
                        # Extract context from similar sessions
                        for row in similar:
                            content = row.get("content", "")
                            metadata = row.get("metadata", {})

                            # Load preferred colors
                            if metadata.get("preferred_colors"):
                                profile.preferred_colors = metadata["preferred_colors"]

                            # Load rejected items
                            if metadata.get("rejected_items"):
                                profile.rejected_items = metadata.get(
                                    "rejected_items", []
                                )

                            logger.info(
                                f"Loaded context from session {row.get('session_id', 'unknown')}"
                            )
                except Exception as e:
                    logger.debug(f"Could not load user context: {e}")

        except Exception as e:
            logger.warning(f"Failed to enrich user context: {e}")

        return profile

    def _analyze_required_categories(self, user_profile: UserProfile) -> List[str]:
        """
        Analyze user profile to determine which categories to recommend

        Uses LLM to intelligently decide based on:
        - User's occasion (daily/work/date/party)
        - User's budget
        - User's season
        - Explicit mentions in original input
        """

        prompt = f"""Based on the following user profile, determine which clothing categories to recommend.

User Profile:
- Name: {user_profile.name}
- Gender: {user_profile.gender.value}
- Age: {user_profile.age}
- Occupation: {user_profile.occupation}
- Mood: {user_profile.mood}
- Budget: {user_profile.budget}
- Season: {user_profile.season}
- Occasion: {user_profile.occasion}

Available categories:
- head: head accessories (hats, glasses, necklaces, earrings)
- top: tops (T-shirts, shirts, jackets, hoodies)
- bottom: bottoms (jeans, pants, skirts)
- shoes: shoes (sneakers, dress shoes, casual shoes)

Return a JSON list of categories to recommend. Examples:
- Full outfit: ["head", "top", "bottom", "shoes"]
- Just top and bottom: ["top", "bottom"]
- Accessory focused: ["head"]
- Only shoes: ["shoes"]

Consider:
1. If occasion is "work", recommend professional outfits
2. If budget is "low", focus on essential categories
3. If user mentions specific items, prioritize those
4. For "date" or "party", include all categories for complete outfit

Return ONLY JSON array like ["head", "top"], no other text.
"""

        try:
            # Use circuit breaker protected LLM call
            response = self._llm_call_with_circuit_breaker(
                "analyze_categories",
                self.llm.invoke,
                prompt=prompt,
                system_prompt="You are a fashion expert. Analyze user needs and return appropriate categories.",
            )

            if not response:
                return []

            # Parse response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                categories = json.loads(response[start:end])
                # Validate categories
                valid_categories = {"head", "top", "bottom", "shoes"}
                categories = [c for c in categories if c in valid_categories]
                if categories:
                    logger.info(f"LLM determined categories: {categories}")
                    return categories

        except Exception as e:
            logger.warning(f"Failed to analyze categories with LLM: {e}")

        return []  # Will fallback to default

    def process(self, user_input: str) -> OutfitResult:
        """Process user input - full workflow"""
        logger.info("Leader Agent starting processing")
        logger.debug(f"User input: {user_input}")

        # 0. Generate session ID
        self.session_id = str(uuid.uuid4())

        # 1. Parse user profile
        logger.info("Parsing user profile")
        profile = self.parse_user_profile(user_input)

        # 1.5. Load user context from previous sessions (context awareness)
        logger.info("Loading user context from history")
        profile = self._enrich_user_context(profile, user_input)

        # 2. Create tasks
        logger.info("Creating outfit tasks")
        tasks = self.create_tasks(profile)

        # 3. Dispatch tasks to Sub Agents via AHP
        logger.info("Dispatching tasks via AHP protocol")
        self._dispatch_tasks_via_ahp(tasks, profile)

        # 4. Collect results
        logger.info("Waiting for Sub Agent results")
        results = self._collect_results(tasks)

        # 5. Aggregate
        logger.info("Aggregating results")
        final = self.aggregate_results(profile, results)
        return final

    def parse_user_profile(self, user_input: str) -> UserProfile:
        """Parse user input to user profile"""

        prompt = f"""Extract user profile information from the following input, return JSON format:

Input: {user_input}

Please return JSON in the following format:
{{
    "name": "name",
    "gender": "male/female/other",
    "age": age_number,
    "occupation": "occupation",
    "hobbies": ["hobby1", "hobby2"],
    "mood": "happy/normal/depressed/excited",
    "style_preference": "style preference (optional)",
    "budget": "low/medium/high",
    "season": "spring/summer/autumn/winter",
    "occasion": "daily/work/date/party"
}}

Only return JSON, no other content.
"""

        response = self._llm_call_with_circuit_breaker(
            "parse_user_profile",
            self.llm.invoke,
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
        )

        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return UserProfile(
                    name=data.get("name", "User"),
                    gender=Gender(data.get("gender", "male")),
                    age=int(data.get("age", 25)),
                    occupation=data.get("occupation", ""),
                    hobbies=data.get("hobbies", []),
                    mood=data.get("mood", "normal"),
                    style_preference=data.get("style_preference", ""),
                    budget=data.get("budget", "medium"),
                    season=data.get("season", "spring"),
                    occasion=data.get("occasion", "daily"),
                )
        except Exception as e:
            logger.warning(f"Failed to parse user profile, using fallback: {e}")

        return self._fallback_parse(user_input)

    def _fallback_parse(self, user_input: str) -> UserProfile:
        """Fallback parsing"""
        import re

        name = "User"
        gender = Gender.MALE
        age = 25
        occupation = ""
        hobbies: list[str] = []
        mood = "normal"

        # Check for Chinese gender keywords
        if "男" in user_input:
            gender = Gender.MALE
        elif "女" in user_input:
            gender = Gender.FEMALE

        # Check for mood keywords
        if "压抑" in user_input:
            mood = "depressed"
        elif "开心" in user_input or "愉悦" in user_input:
            mood = "happy"

        # Extract age
        age_match = re.search(r"(\d+)岁", user_input)
        if age_match:
            age = int(age_match.group(1))

        # Extract occupation
        occ_map = {
            "厨师": "chef",
            "医生": "doctor",
            "教师": "teacher",
            "程序员": "programmer",
            "设计师": "designer",
            "学生": "student",
        }
        for cn, en in occ_map.items():
            if cn in user_input:
                occupation = en
                break

        # Extract hobbies
        hobby_map = {
            "旅游": "travel",
            "运动": "sports",
            "音乐": "music",
            "阅读": "reading",
            "游戏": "gaming",
            "美食": "food",
        }
        for cn, en in hobby_map.items():
            if cn in user_input:
                hobbies.append(en)

        return UserProfile(
            name=name,
            gender=gender,
            age=age,
            occupation=occupation,
            hobbies=hobbies,
            mood=mood,
            season="spring",
            occasion="daily",
        )

    def create_tasks(self, user_profile: UserProfile) -> List[OutfitTask]:
        """
        Create outfit tasks with intelligent decomposition

        Uses LLM to analyze user needs and determine which categories to recommend.
        Falls back to default 4 categories if LLM fails.
        """

        # Try intelligent task decomposition with LLM
        categories = self._analyze_required_categories(user_profile)

        # If LLM fails, use default categories
        if not categories:
            categories = ["head", "top", "bottom", "shoes"]
            logger.info("Using default categories due to LLM failure")

        # Build task configs based on determined categories
        task_configs = []
        category_agent_map = {
            "head": "agent_head",
            "top": "agent_top",
            "bottom": "agent_bottom",
            "shoes": "agent_shoes",
        }
        category_desc_map = {
            "head": "head accessories recommendation",
            "top": "top clothing recommendation",
            "bottom": "bottom clothing recommendation",
            "shoes": "shoes recommendation",
        }

        for cat in categories:
            task_configs.append(
                {
                    "category": cat,
                    "agent_id": category_agent_map.get(cat, f"agent_{cat}"),
                    "desc": category_desc_map.get(cat, f"{cat} recommendation"),
                }
            )

        tasks = []
        for config in task_configs:
            task = OutfitTask(category=config["category"], user_profile=user_profile)
            task.assignee_agent_id = config["agent_id"]

            # Register task to TaskRegistry
            self.registry.register_task(
                session_id=self.session_id,
                title=f"{config['category']} recommendation",
                description=config["desc"],
                category=config["category"],
            )

            tasks.append(task)
            logger.debug(f"Created task: {config['category']} -> {config['agent_id']}")

        self.tasks = tasks
        return tasks

    def _dispatch_tasks_via_ahp(self, tasks: List[OutfitTask], profile: UserProfile):
        """Dispatch tasks via AHP protocol with error handling"""

        # Category description mapping
        category_desc = {
            "head": "head accessories",
            "top": "top clothing",
            "bottom": "bottom clothing",
            "shoes": "shoes",
        }

        for task in tasks:
            desc = category_desc.get(task.category, task.category)
            # Build compact instruction (Token control)
            payload = {
                "category": task.category,
                "description": desc,
                "user_info": {
                    "name": profile.name,
                    "gender": profile.gender.value,
                    "age": profile.age,
                    "occupation": profile.occupation,
                    "mood": profile.mood,
                    "hobbies": profile.hobbies,
                    "season": profile.season,
                    "budget": profile.budget,
                },
                "instruction": f"Please recommend {desc} for {profile.name}, considering their mood is {profile.mood}",
            }

            # Send via AHP protocol with error handling
            try:
                target_agent = task.assignee_agent_id
                if not target_agent:
                    raise ValueError(f"Task {task.task_id} has no assignee agent")
                self.sender.send_task(
                    target_agent=target_agent,
                    task_id=task.task_id,
                    session_id=self.session_id,
                    payload=payload,
                    token_limit=500,
                )
                logger.info(
                    f"Dispatched task {task.task_id} to {task.assignee_agent_id}"
                )
            except Exception as e:
                target_agent = task.assignee_agent_id or "unknown"
                error = AHPError(
                    message=f"Failed to dispatch task: {str(e)}",
                    code=AHPErrorCode.TIMEOUT,
                    agent_id=target_agent,
                    task_id=task.task_id,
                )
                logger.error(f"AHP Error: {error.message}")

    def _collect_results(
        self, tasks: List[OutfitTask], timeout: int = 60
    ) -> Dict[str, OutfitRecommendation]:
        """Collect results from all agents with ACK handling"""
        results: Dict[str, OutfitRecommendation] = {}
        start = time.time()
        received: set[str] = set()
        pending_tasks = {t.assignee_agent_id: t for t in tasks}
        agent_progress: Dict[str, float] = {}  # Track progress per agent
        progress_queue: queue.Queue = queue.Queue()  # Queue for progress messages

        # Start a background thread to handle PROGRESS messages
        def progress_handler():
            while time.time() - start < timeout:
                try:
                    msg = self.mq.receive("leader", timeout=1)
                    if msg is None:
                        continue
                    if msg.method == AHPMethod.PROGRESS:
                        progress_queue.put(msg)
                    else:
                        # Put non-PROGRESS messages back to main handling
                        # For now, just log other message types
                        logger.debug(f"Ignoring non-PROGRESS in handler: {msg.method}")
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.warning(f"Progress handler error: {e}")
                    break

        progress_thread = threading.Thread(target=progress_handler, daemon=True)
        progress_thread.start()

        while len(received) < len(tasks) and (time.time() - start) < timeout:
            # Process any queued PROGRESS messages
            while not progress_queue.empty():
                try:
                    msg = progress_queue.get_nowait()
                    sender_id = msg.agent_id
                    progress = msg.payload.get("progress", 0)
                    progress_msg = msg.payload.get("message", "")
                    agent_progress[sender_id] = progress
                    logger.info(
                        f"Progress from {sender_id}: {progress*100:.0f}% - {progress_msg}"
                    )
                except queue.Empty:
                    break

            # Receive any message, not specific to any agent
            msg = self.mq.receive("leader", timeout=2)

            if msg is None:
                continue

            # Use actual sender from message, not iteration variable
            sender_id = msg.agent_id

            # Handle ACK messages
            if msg.method == AHPMethod.ACK:
                ack_status = msg.payload.get("ack_status", "")
                logger.debug(f"Received ACK from {sender_id}: {ack_status}")
                continue

            # Skip PROGRESS messages - they are handled by background thread
            if msg.method == AHPMethod.PROGRESS:
                continue
                result_data = msg.payload.get("result", {})
                status = msg.payload.get("status", "success")

                if status == "failed":
                    error_msg = result_data.get("error", "Unknown error")
                    logger.error(f"Task failed from {sender_id}: {error_msg}")
                    # Move to DLQ for investigation
                    self.mq.to_dlq(sender_id, msg, error_msg)
                    received.add(sender_id)
                    continue

                category = result_data.get("category", "unknown")
                results[category] = OutfitRecommendation(
                    category=category,
                    items=result_data.get("items", []),
                    colors=result_data.get("colors", []),
                    styles=result_data.get("styles", []),
                    reasons=result_data.get("reasons", []),
                    price_range=result_data.get("price_range", ""),
                )
                received.add(sender_id)

                # Update task status in registry
                task_id = msg.task_id
                if task_id:
                    self.registry.update_status(
                        task_id, TaskStatus.COMPLETED, result=result_data
                    )

                logger.info(f"Received result from {category} (agent: {sender_id})")

            # Handle PROGRESS messages - skip them, do NOT consume from queue
            # This prevents progress messages from blocking result collection
            # Sub Agent should send progress to a separate queue or we should use peek
            elif msg.method == AHPMethod.PROGRESS:
                # Skip PROGRESS messages - don't consume them
                # They should be handled by a separate progress listener
                # For now, just log and continue without consuming
                progress = msg.payload.get("progress", 0)
                progress_msg = msg.payload.get("message", "")
                agent_progress[sender_id] = progress
                logger.info(
                    f"Progress from {sender_id}: {progress*100:.0f}% - {progress_msg}"
                )
                # Don't break or return - continue the loop to get next message
                # But we need to avoid infinite loop on PROGRESS messages
                # Since we can't "un-receive", we'll just continue
                continue

        # Check for missing results and log warnings
        missing = set(pending_tasks.keys()) - received
        if missing:
            logger.warning(f"Missing results from agents: {missing}")
            # Check DLQ for failed messages
            dlq = self.mq.get_dlq()
            if dlq and isinstance(dlq, dict):
                logger.error(
                    f"DLQ contains {sum(len(v) for v in dlq.values())} failed messages"
                )

        return results

    def _save_for_rag(
        self, user_profile: UserProfile, results: Dict[str, OutfitRecommendation]
    ):
        """
        Save recommendations to vector DB for RAG

        Args:
            user_profile: User profile
            results: Dictionary of category -> OutfitRecommendation
        """
        try:
            for category, rec in results.items():
                # Build content string for embedding
                content = (
                    f"Category: {category}, "
                    f"Items: {', '.join(rec.items)}, "
                    f"Colors: {', '.join(rec.colors)}, "
                    f"Styles: {', '.join(rec.styles)}, "
                    f"Reasons: {', '.join(rec.reasons)}"
                )

                # Generate embedding
                embedding = self.llm.embed(content)

                # Save to vector DB
                metadata = {
                    "mood": user_profile.mood,
                    "season": user_profile.season,
                    "occupation": user_profile.occupation,
                    "age": user_profile.age,
                    "gender": user_profile.gender.value,
                    "occasion": user_profile.occasion,
                }

                self._db.save_vector(
                    session_id=self.session_id,
                    content=content,
                    embedding=embedding,
                    metadata=metadata,
                )
                logger.debug(
                    f"Saved vector for {category} in session {self.session_id}"
                )

        except Exception as e:
            logger.warning(f"Failed to save vectors for RAG: {e}")

    def aggregate_results(
        self, user_profile: UserProfile, results: Dict[str, OutfitRecommendation]
    ) -> OutfitResult:
        """Aggregate results with validation"""

        # Validate each result before aggregation
        validated_results = {}
        for category, recommendation in results.items():
            result_dict = {
                "category": recommendation.category,
                "items": recommendation.items,
                "colors": recommendation.colors,
                "styles": recommendation.styles,
                "reasons": recommendation.reasons,
                "price_range": recommendation.price_range,
            }
            validation = self.validator.validate(result_dict, "outfit", category)
            if not validation.is_valid:
                logger.warning(
                    f"Validation failed for {category}: "
                    f"{[e.message for e in validation.errors]}"
                )
                # Use auto-fixed result if available
                if validation.corrected:
                    recommendation.items = validation.corrected.get(
                        "items", recommendation.items
                    )
                    recommendation.colors = validation.corrected.get(
                        "colors", recommendation.colors
                    )
                    recommendation.styles = validation.corrected.get(
                        "styles", recommendation.styles
                    )
            validated_results[category] = recommendation

        style_prompt = f"""Based on the following user profile and outfit recommendations, provide overall style suggestions:

User Profile:
{user_profile.to_prompt_context()}

Recommendations:
{json.dumps({k: {"items": v.items, "colors": v.colors, "styles": v.styles} for k, v in validated_results.items()}, ensure_ascii=False)}

Please provide:
1. Overall style description
2. One sentence summary

Return JSON format:
{{
    "overall_style": "style description",
    "summary": "summary"
}}
"""

        response = self._llm_call_with_circuit_breaker(
            "aggregate_results",
            self.llm.invoke,
            prompt=style_prompt,
            system_prompt=SYSTEM_PROMPT,
        )

        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                result = OutfitResult(
                    session_id=self.session_id,
                    user_profile=user_profile,
                    head=validated_results.get("head"),
                    top=validated_results.get("top"),
                    bottom=validated_results.get("bottom"),
                    shoes=validated_results.get("shoes"),
                    overall_style=data.get("overall_style", ""),
                    summary=data.get("summary", ""),
                )
                # Save recommendations to vector DB for RAG
                self._save_for_rag(user_profile, validated_results)
                return result
        except (ValueError, json.JSONDecodeError):
            pass

        result = OutfitResult(
            session_id=self.session_id,
            user_profile=user_profile,
            head=validated_results.get("head"),
            top=validated_results.get("top"),
            bottom=validated_results.get("bottom"),
            shoes=validated_results.get("shoes"),
        )
        # Save recommendations to vector DB for RAG
        self._save_for_rag(user_profile, validated_results)
        return result


# ========== Async Version ==========


class AsyncLeaderAgent:
    """Async Leader Agent"""

    def __init__(self, llm: LocalLLM):
        self.llm = llm
        self.tasks: List[OutfitTask] = []
        self.mq = None
        self.sender = None
        self.session_id = ""
        self._db = StorageLayer()  # For RAG vector storage

        # Initialize retry handler
        retry_config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
            retry_on=[
                ErrorType.LLM_FAILED,
                ErrorType.NETWORK,
                ErrorType.TIMEOUT,
            ],
        )
        self.retry_handler = RetryHandler(retry_config)

        # Initialize circuit breaker for LLM calls
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)

    async def _init_mq(self):
        """Initialize async message queue"""
        from ..protocol import get_async_message_queue, AsyncAHPSender

        if self.mq is None:
            self.mq = await get_async_message_queue()
            self.sender = AsyncAHPSender(self.mq)

    async def _llm_call_with_circuit_breaker(
        self, func_name: str, func, *args, **kwargs
    ) -> Any:
        """Execute LLM call with circuit breaker and retry (async version)"""
        from typing import Callable

        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {func_name}, using fallback")
            return self._get_fallback_result(func_name)

        try:
            # Execute with retry (sync version for simplicity)
            result = self.retry_handler.execute_with_retry(
                func, f"async_leader_{func_name}", *args, **kwargs
            )
            self.circuit_breaker.record_success()
            return result
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"Circuit breaker recorded failure for {func_name}: {e}")
            return self._get_fallback_result(func_name)

    def _get_fallback_result(self, func_name: str) -> Any:
        """Get fallback result when circuit is open or retry exhausted"""
        if func_name == "parse_user_profile":
            return UserProfile(
                name="User",
                gender=Gender.MALE,
                age=25,
                occupation="",
                hobbies=[],
                mood="normal",
                budget="medium",
                season="spring",
                occasion="daily",
            )
        elif func_name == "aggregate_results":
            return None
        return None

    def _save_for_rag(
        self, user_profile: UserProfile, results: Dict[str, OutfitRecommendation]
    ):
        """
        Save recommendations to vector DB for RAG (sync version for async agent)

        Args:
            user_profile: User profile
            results: Dictionary of category -> OutfitRecommendation
        """
        try:
            for category, rec in results.items():
                # Build content string for embedding
                content = (
                    f"Category: {category}, "
                    f"Items: {', '.join(rec.items)}, "
                    f"Colors: {', '.join(rec.colors)}, "
                    f"Styles: {', '.join(rec.styles)}, "
                    f"Reasons: {', '.join(rec.reasons)}"
                )

                # Generate embedding
                embedding = self.llm.embed(content)

                # Save to vector DB
                metadata = {
                    "mood": user_profile.mood,
                    "season": user_profile.season,
                    "occupation": user_profile.occupation,
                    "age": user_profile.age,
                    "gender": user_profile.gender.value,
                    "occasion": user_profile.occasion,
                }

                self._db.save_vector(
                    session_id=self.session_id,
                    content=content,
                    embedding=embedding,
                    metadata=metadata,
                )
                logger.debug(
                    f"Saved vector for {category} in session {self.session_id}"
                )

        except Exception as e:
            logger.warning(f"Failed to save vectors for RAG: {e}")

    async def process(self, user_input: str) -> OutfitResult:
        """Process user input (async)"""
        await self._init_mq()

        logger.info("Async Leader Agent starting processing")
        logger.debug(f"User input: {user_input}")

        # 1. Parse user profile
        logger.info("Parsing user profile (async)")
        profile = await self._parse_user_profile(user_input)
        self.session_id = str(uuid.uuid4())

        # 2. Create tasks
        logger.info("Creating outfit tasks")
        tasks = await self.create_tasks(profile)

        # 3. Dispatch tasks via AHP
        logger.info("Dispatching tasks via async AHP protocol")
        await self._dispatch_tasks_via_ahp(tasks, profile)

        # 4. Collect results
        logger.info("Waiting for Sub Agent results (async)")
        results = await self._collect_results(tasks)

        # 5. Aggregate
        logger.info("Aggregating results (async)")
        final = await self.aggregate_results(profile, results)
        return final

    async def _parse_user_profile(self, user_input: str) -> UserProfile:
        """Parse user input (async)"""
        prompt = f"""Extract user profile information from the following input, return JSON format:

Input: {user_input}

Please return JSON in the following format:
{{
    "name": "Name",
    "gender": "male/female",
    "age": 25,
    "occupation": "Occupation",
    "hobbies": ["hobby1", "hobby2"],
    "mood": "happy/normal/depressed",
    "season": "spring/summer/autumn/winter",
    "occasion": "daily/formal/casual",
    "budget": "low/medium/high"
}}"""

        try:
            response = await self.llm.ainvoke(prompt, SYSTEM_PROMPT)
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return UserProfile(
                    name=data.get("name", "User"),
                    gender=Gender(data.get("gender", "male")),
                    age=data.get("age", 25),
                    occupation=data.get("occupation", ""),
                    hobbies=data.get("hobbies", []),
                    mood=data.get("mood", "normal"),
                    season=data.get("season", "spring"),
                    occasion=data.get("occasion", "daily"),
                )
        except Exception as e:
            logger.warning(f"Failed to parse user profile, using fallback: {e}")

        return self._fallback_parse(user_input)

    def _fallback_parse(self, user_input: str) -> UserProfile:
        """Fallback parsing"""
        import re

        name = "User"
        gender = "male"
        age = 25
        occupation = ""
        hobbies: list[str] = []
        mood = "normal"
        season = "spring"
        occasion = "daily"

        # Simple regex extraction
        name_match = re.search(r"(\w+),?\s+(male|female)", user_input, re.IGNORECASE)
        if name_match:
            name = name_match.group(1)
            gender = name_match.group(2).lower()

        age_match = re.search(r"(\d+)\s*(years? old|yo)", user_input, re.IGNORECASE)
        if age_match:
            age = int(age_match.group(1))

        occ_match = re.search(r"(\w+)(?:\s|,|$)", user_input)
        if occ_match:
            occupation = occ_match.group(1)

        if "depressed" in user_input.lower():
            mood = "depressed"
        elif "happy" in user_input.lower():
            mood = "happy"

        return UserProfile(
            name=name,
            gender=Gender(gender),
            age=age,
            occupation=occupation,
            hobbies=hobbies,
            mood=mood,
            season=season,
            occasion=occasion,
        )

    async def _analyze_required_categories(
        self, user_profile: UserProfile
    ) -> List[str]:
        """Analyze user profile to determine which categories to recommend (async)"""

        prompt = f"""Based on the following user profile, determine which clothing categories to recommend.

User Profile:
- Name: {user_profile.name}
- Gender: {user_profile.gender.value}
- Age: {user_profile.age}
- Occupation: {user_profile.occupation}
- Mood: {user_profile.mood}
- Budget: {user_profile.budget}
- Season: {user_profile.season}
- Occasion: {user_profile.occasion}

Available categories: head, top, bottom, shoes

Return ONLY JSON array like ["head", "top"], no other text.
"""

        try:
            response = await self.llm.ainvoke(prompt, SYSTEM_PROMPT)
            if not response:
                return []

            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                categories = json.loads(response[start:end])
                valid_categories = {"head", "top", "bottom", "shoes"}
                categories = [c for c in categories if c in valid_categories]
                if categories:
                    logger.info(f"LLM determined categories: {categories}")
                    return categories
        except Exception as e:
            logger.warning(f"Failed to analyze categories with LLM: {e}")

        return []

    async def create_tasks(self, user_profile: UserProfile) -> List[OutfitTask]:
        """Create outfit tasks with intelligent decomposition"""

        # Try intelligent task decomposition with LLM
        categories = await self._analyze_required_categories(user_profile)

        # If LLM fails, use default categories
        if not categories:
            categories = ["head", "top", "bottom", "shoes"]
            logger.info("Using default categories due to LLM failure")

        category_agent_map = {
            "head": "agent_head",
            "top": "agent_top",
            "bottom": "agent_bottom",
            "shoes": "agent_shoes",
        }
        category_desc_map = {
            "head": "head accessories recommendation",
            "top": "top clothing recommendation",
            "bottom": "bottom clothing recommendation",
            "shoes": "shoes recommendation",
        }

        task_configs = [
            {
                "category": cat,
                "agent_id": category_agent_map.get(cat, f"agent_{cat}"),
                "desc": category_desc_map.get(cat, f"{cat} recommendation"),
            }
            for cat in categories
        ]

        tasks = []
        for config in task_configs:
            task = OutfitTask(category=config["category"], user_profile=user_profile)
            task.assignee_agent_id = config["agent_id"]
            tasks.append(task)
            logger.debug(f"Created task: {config['category']} -> {config['agent_id']}")

        self.tasks = tasks
        return tasks

    async def _dispatch_tasks_via_ahp(
        self, tasks: List[OutfitTask], profile: UserProfile
    ):
        """Dispatch tasks via AHP protocol (async)"""
        category_desc = {
            "head": "head accessories",
            "top": "top clothing",
            "bottom": "bottom clothing",
            "shoes": "shoes",
        }

        # Dispatch all tasks concurrently
        async def send_task(task):
            desc = category_desc.get(task.category, task.category)
            payload = {
                "category": task.category,
                "description": desc,
                "user_info": {
                    "name": profile.name,
                    "gender": profile.gender.value,
                    "age": profile.age,
                    "occupation": profile.occupation,
                    "mood": profile.mood,
                    "hobbies": profile.hobbies,
                    "season": profile.season,
                    "budget": profile.budget,
                },
                "instruction": f"Please recommend {desc} for {profile.name}, considering their mood is {profile.mood}",
            }
            await self.sender.send_task(
                target_agent=task.assignee_agent_id,
                task_id=task.task_id,
                session_id=self.session_id,
                payload=payload,
                token_limit=500,
            )
            logger.info(f"Dispatched task {task.task_id} to {task.assignee_agent_id}")

        await asyncio.gather(*[send_task(task) for task in tasks])

    async def _collect_results(
        self, tasks: List[OutfitTask], timeout: int = 60
    ) -> Dict[str, OutfitRecommendation]:
        """Collect results from all agents (async)"""
        results: Dict[str, OutfitRecommendation] = {}
        start = time.time()
        received: set[str] = set()
        pending_tasks = {t.assignee_agent_id: t for t in tasks}
        agent_progress: Dict[str, float] = {}  # Track progress per agent

        while len(received) < len(tasks) and (time.time() - start) < timeout:
            # Receive any message, not specific to any agent
            mq = self.mq
            if mq is None:
                break
            msg = await mq.receive("leader", timeout=2)

            if msg is None:
                continue

            # Use actual sender from message
            sender_id = msg.agent_id

            if msg.method == AHPMethod.RESULT:
                result_data = msg.payload.get("result", {})
                category = result_data.get("category", "unknown")
                results[category] = OutfitRecommendation(
                    category=category,
                    items=result_data.get("items", []),
                    colors=result_data.get("colors", []),
                    styles=result_data.get("styles", []),
                    reasons=result_data.get("reasons", []),
                    price_range=result_data.get("price_range", ""),
                )
                received.add(sender_id)
                logger.info(f"Received result from {category} (agent: {sender_id})")
            elif msg.method == AHPMethod.ACK:
                logger.debug(f"Received ACK from {sender_id}")
            elif msg.method == AHPMethod.PROGRESS:
                progress = msg.payload.get("progress", 0)
                progress_msg = msg.payload.get("message", "")
                agent_progress[sender_id] = progress
                logger.info(
                    f"Progress from {sender_id}: {progress*100:.0f}% - {progress_msg}"
                )

        # Check for missing results
        missing = set(pending_tasks.keys()) - received
        if missing:
            logger.warning(f"Missing results from agents: {missing}")

        return results

    async def aggregate_results(
        self, user_profile: UserProfile, results: Dict[str, OutfitRecommendation]
    ) -> OutfitResult:
        """Aggregate results (async)"""
        style_prompt = f"""Based on the following user profile and outfit recommendations, provide overall style suggestions:

User Profile:
{user_profile.to_prompt_context()}

Recommendations:
{json.dumps({k: {"items": v.items, "colors": v.colors, "styles": v.styles} for k, v in results.items()}, ensure_ascii=False)}

Please provide:
{{
    "overall_style": "Style description",
    "summary": "Summary"
}}"""

        try:
            response = await self.llm.ainvoke(style_prompt, SYSTEM_PROMPT)
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                result = OutfitResult(
                    session_id=self.session_id,
                    user_profile=user_profile,
                    head=results.get("head"),
                    top=results.get("top"),
                    bottom=results.get("bottom"),
                    shoes=results.get("shoes"),
                    overall_style=data.get("overall_style", ""),
                    summary=data.get("summary", ""),
                )
                # Save recommendations to vector DB for RAG
                self._save_for_rag(user_profile, results)
                return result
        except Exception as e:
            logger.warning(f"Failed to aggregate results: {e}")

        result = OutfitResult(
            session_id=self.session_id,
            user_profile=user_profile,
            head=results.get("head"),
            top=results.get("top"),
            bottom=results.get("bottom"),
            shoes=results.get("shoes"),
        )
        # Save recommendations to vector DB for RAG
        self._save_for_rag(user_profile, results)
        return result
