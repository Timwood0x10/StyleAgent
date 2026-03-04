"""
Memory Distillation Module

Distills conversation history into structured memories, persists to pgvector for cross-session retrieval.

Features:
- Structured JSON output (user_profile, decisions, pending_tasks, important_facts)
- Distill level tracking to prevent recursive degradation
- Importance filtering before distillation
- Memory type separation (user_memory vs task_memory)
"""

import json
from typing import Any, Dict, List, Optional

from .logger import get_logger

logger = get_logger(__name__)


# Simple estimation: 1 token ≈ 4 characters
CHARS_PER_TOKEN = 4


class Message:
    """Conversation message."""

    def __init__(self, role: str, content: str, timestamp: str = ""):
        self.role = role  # system, user, assistant
        self.content = content
        self.timestamp = timestamp


class StructuredMemory:
    """Structured memory format from distillation."""

    def __init__(
        self,
        user_profile: Optional[Dict] = None,
        decisions_made: Optional[List[Dict]] = None,
        pending_tasks: Optional[List[Dict]] = None,
        important_facts: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ):
        self.user_profile = user_profile or {}
        self.decisions_made = decisions_made or []
        self.pending_tasks = pending_tasks or []
        self.important_facts = important_facts or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "user_profile": self.user_profile,
            "decisions_made": self.decisions_made,
            "pending_tasks": self.pending_tasks,
            "important_facts": self.important_facts,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict) -> "StructuredMemory":
        """Create from dictionary."""
        return cls(
            user_profile=data.get("user_profile"),
            decisions_made=data.get("decisions_made"),
            pending_tasks=data.get("pending_tasks"),
            important_facts=data.get("important_facts"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "StructuredMemory":
        """Create from JSON string."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {json_str[:100]}")
            return cls()

    def merge(self, other: "StructuredMemory") -> "StructuredMemory":
        """Merge another memory into this one, handling conflicts."""
        # Merge user_profile (new values override old)
        merged_profile = {**self.user_profile, **other.user_profile}

        # Merge decisions (append new, avoid duplicates)
        existing_decisions = {d.get("key", ""): d for d in self.decisions_made}
        for d in other.decisions_made:
            key = d.get("key", "")
            if key and key not in existing_decisions:
                self.decisions_made.append(d)

        # Merge pending_tasks
        existing_tasks = {t.get("task_id", ""): t for t in self.pending_tasks}
        for t in other.pending_tasks:
            task_id = t.get("task_id", "")
            if task_id and task_id not in existing_tasks:
                self.pending_tasks.append(t)

        # Merge important_facts (avoid duplicates)
        self.important_facts = list(set(self.important_facts + other.important_facts))

        return StructuredMemory(
            user_profile=merged_profile,
            decisions_made=self.decisions_made,
            pending_tasks=self.pending_tasks,
            important_facts=self.important_facts,
            metadata={**self.metadata, **other.metadata},
        )

    def __repr__(self) -> str:
        return f"StructuredMemory(profile_keys={list(self.user_profile.keys())}, decisions={len(self.decisions_made)}, tasks={len(self.pending_tasks)})"


class MemoryDistiller:
    """
    Memory Distiller.

    Features:
    - Tracks conversation history
    - Estimates token usage
    - Structured JSON output
    - Distill level tracking to prevent recursive degradation
    - Importance filtering before distillation
    - Memory type separation (user_memory vs task_memory)
    """

    def __init__(
        self,
        llm=None,
        storage=None,  # StorageLayer instance
        agent_id: str = "default",
        max_tokens: int = 4000,
        distill_threshold: float = 0.8,
        keep_recent: int = 4,
        enable_importance_filter: bool = True,
    ):
        """
        Initialize MemoryDistiller.

        Args:
            llm: LLM instance (must have invoke, ainvoke, embed methods).
            storage: StorageLayer instance for persistence.
            agent_id: Agent ID.
            max_tokens: Maximum token count before distillation.
            distill_threshold: Threshold (0.0-1.0) to trigger distillation.
            keep_recent: Number of recent turns to keep intact.
            enable_importance_filter: Whether to filter by importance before distillation.
        """
        self.llm = llm
        self.storage = storage
        self.agent_id = agent_id
        self.max_tokens = max_tokens
        self.distill_threshold = distill_threshold
        self.keep_recent = keep_recent
        self.enable_importance_filter = enable_importance_filter

        self._history: List[Message] = []
        self._distilled_memory: Optional[StructuredMemory] = None
        self._session_id: Optional[str] = None
        self._distill_level: int = (
            1  # Track distill level to prevent recursive degradation
        )
        self._memory_type: str = "user_memory"  # 'user_memory' or 'task_memory'

    def set_session(self, session_id: str):
        """Set session ID."""
        self._session_id = session_id

    def set_memory_type(self, memory_type: str):
        """Set memory type: 'user_memory' or 'task_memory'."""
        if memory_type in ("user_memory", "task_memory"):
            self._memory_type = memory_type

    def add_message(self, role: str, content: str, timestamp: str = ""):
        """Add a conversation message."""
        self._history.append(Message(role=role, content=content, timestamp=timestamp))

    def add_user(self, content: str):
        """Add a user message."""
        self.add_message("user", content)

    def add_assistant(self, content: str):
        """Add an assistant message."""
        self.add_message("assistant", content)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return len(text) // CHARS_PER_TOKEN

    def get_current_tokens(self) -> int:
        """Get current context token count."""
        parts = []
        if self._distilled_memory:
            parts.append(self._distilled_memory.to_json())
        parts.extend([f"{m.role}: {m.content}" for m in self._history])
        return self.estimate_tokens("\n".join(parts))

    def should_distill(self) -> bool:
        """Check if distillation is needed."""
        # Don't distill if already at high level (prevent recursive degradation)
        if self._distill_level >= 3:
            logger.debug("Already at high distill level, skipping")
            return False
        return self.get_current_tokens() > self.max_tokens * self.distill_threshold

    def get_context(self) -> str:
        """
        Get distilled context as formatted string.

        Format:
        [Structured Memory - User Profile]
        [Decisions Made]
        [Pending Tasks]
        [Important Facts]
        ---
        [Recent N turns]
        """
        parts = []

        if self._distilled_memory:
            mem = self._distilled_memory
            parts.append("[User Profile]")
            for k, v in mem.user_profile.items():
                parts.append(f"  {k}: {v}")
            if mem.decisions_made:
                parts.append("\n[Decisions Made]")
                for d in mem.decisions_made:
                    parts.append(f"  - {d.get('description', str(d))}")
            if mem.pending_tasks:
                parts.append("\n[Pending Tasks]")
                for t in mem.pending_tasks:
                    parts.append(f"  - {t.get('description', str(t))}")
            if mem.important_facts:
                parts.append("\n[Important Facts]")
                for f in mem.important_facts:
                    parts.append(f"  - {f}")
            parts.append("---\n[Recent Conversation]")

        # Keep recent N turns
        recent = self._history[-self.keep_recent :] if self._history else []
        for m in recent:
            parts.append(f"{m.role}: {m.content}")

        return "\n".join(parts)

    def get_structured_memory(self) -> Optional[StructuredMemory]:
        """Get structured memory object."""
        return self._distilled_memory

    def get_full_history(self) -> List[Message]:
        """Get full conversation history."""
        return self._history.copy()

    def clear(self):
        """Clear history and distilled memory."""
        self._history.clear()
        self._distilled_memory = None
        self._distill_level = 1

    def _check_importance(self, conversation: str) -> bool:
        """
        Check if conversation contains important long-term information.

        Returns True if the conversation should be distilled.
        """
        if not self.llm:
            return True  # No LLM, assume important

        prompt = f"""判断以下对话是否包含长期有效信息。

长期有效信息包括：
- 用户偏好（风格、价格、品牌）
- 用户身份信息（年龄、职业、性别）
- 关键决策（购买决定、拒绝理由）
- 重要事实（联系方式、特殊需求）

仅返回 true 或 false，不要其他内容。

对话内容：
{conversation[:1000]}
"""
        try:
            result = (
                self.llm.invoke(
                    prompt,
                    system_prompt="你是一个信息重要性判断助手。",
                )
                .strip()
                .lower()
            )
            is_important = "true" in result
            logger.debug(
                f"Importance check result: {is_important} (response: {result})"
            )
            return is_important
        except Exception as e:
            logger.warning(f"Importance check failed: {e}, assuming important")
            return True

    def distill(self) -> bool:
        """
        Manually trigger distillation (sync version).

        Returns:
            True if distilled, False if not needed or failed.
        """
        if not self.llm:
            logger.warning("No LLM provided, cannot distill")
            return False

        if not self.should_distill() and self._distilled_memory is not None:
            logger.debug("No distillation needed")
            return False

        try:
            # Messages to distill: all except recent N turns
            messages_to_distill = (
                self._history[: -self.keep_recent]
                if len(self._history) > self.keep_recent
                else self._history
            )

            if not messages_to_distill:
                return False

            conversation = "\n".join(
                [f"{m.role}: {m.content}" for m in messages_to_distill]
            )
            original_tokens = self.estimate_tokens(conversation)

            # Importance filtering
            if self.enable_importance_filter:
                if not self._check_importance(conversation):
                    logger.debug(
                        "Conversation not important enough, skipping distillation"
                    )
                    return False

            # Structured distillation prompt
            prompt = f"""将以下对话提炼为结构化JSON，格式如下：
{{
    "user_profile": {{"key": "value"}},  // 用户偏好和属性
    "decisions_made": [{{"key": "唯一标识", "description": "描述"}}],  // 已做出的决定
    "pending_tasks": [{{"task_id": "唯一标识", "description": "描述"}}],  // 待完成任务
    "important_facts": ["事实1", "事实2"]  // 其他重要事实
}}

要求：
1. user_profile 中只包含长期有效的用户属性
2. decisions_made 需要有唯一key避免重复
3. pending_tasks 只包含未完成的重要任务
4. important_facts 包含不适合上面类别的其他重要信息
5. 只返回JSON，不要其他内容

对话内容：
{conversation}

请用中文提炼："""

            # Invoke LLM for distillation
            result = self.llm.invoke(
                prompt,
                system_prompt="你是一个记忆蒸馏助手，负责将对话提取为结构化JSON。",
            )

            # Parse JSON response
            try:
                # Try to extract JSON from response
                json_str = result.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                elif "{" in json_str and "}" in json_str:
                    start = json_str.find("{")
                    end = json_str.rfind("}") + 1
                    json_str = json_str[start:end]

                memory_data = json.loads(json_str)
                self._distilled_memory = StructuredMemory.from_dict(memory_data)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(
                    f"Failed to parse JSON response: {e}, using text fallback"
                )
                # Fallback: create basic structure with text
                self._distilled_memory = StructuredMemory(
                    important_facts=[result[:500]]
                )

            # Keep recent conversation
            if len(self._history) > self.keep_recent:
                self._history = self._history[-self.keep_recent :]

            # Increment distill level
            self._distill_level += 1

            distilled_tokens = self.estimate_tokens(self._distilled_memory.to_json())
            logger.info(
                f"Memory distilled: {original_tokens} -> {distilled_tokens} tokens, "
                f"level={self._distill_level}, type={self._memory_type}"
            )

            # Persist to database
            if self.storage and self._session_id:
                self._save_to_storage(original_tokens, distilled_tokens)

            return True

        except Exception as e:
            logger.error(f"Distillation failed: {e}")
            return False

    def _save_to_storage(self, original_tokens: int, distilled_tokens: int):
        """Save distilled memory to database."""
        try:
            if not hasattr(self.storage, "save_distilled_memory"):
                logger.warning("Storage does not support save_distilled_memory")
                return

            if not self._distilled_memory:
                logger.warning("No distilled memory to save")
                return

            # Generate embedding from structured memory
            embedding = None
            if self.llm and hasattr(self.llm, "embed"):
                # Embed the JSON as text
                embedding = self.llm.embed(self._distilled_memory.to_json())

            self.storage.save_distilled_memory(
                session_id=self._session_id,
                agent_id=self.agent_id,
                summary=self._distilled_memory.to_json(),
                original_token_count=original_tokens,
                compressed_token_count=distilled_tokens,
                memory_type=self._memory_type,
                distill_level=self._distill_level,
                embedding=embedding,
                metadata={"type": "structured_memory_distillation"},
            )
            logger.info(f"Distilled memory saved for session {self._session_id}")
        except Exception as e:
            logger.error(f"Failed to save distilled memory: {e}")

    def load_from_storage(
        self, session_id: str = None, memory_type: str = None, limit: int = 5
    ) -> List[StructuredMemory]:
        """Load historical distilled memories from database."""
        if not self.storage or not hasattr(self.storage, "get_distilled_memories"):
            return []

        try:
            sid = session_id or self._session_id
            if not sid:
                return []

            memories = self.storage.get_distilled_memories(
                session_id=sid,
                agent_id=self.agent_id,
                memory_type=memory_type,
                limit=limit,
            )

            results = []
            for m in memories:
                summary = m.get("summary")
                if summary:
                    if isinstance(summary, str):
                        try:
                            summary = json.loads(summary)
                        except json.JSONDecodeError:
                            continue
                    results.append(StructuredMemory.from_dict(summary))

            logger.info(f"Loaded {len(results)} distilled memories from storage")
            return results
        except Exception as e:
            logger.error(f"Failed to load distilled memories: {e}")
            return []

    async def adistill(self) -> bool:
        """
        Manually trigger distillation (async version).

        Returns:
            True if distilled, False if not needed or failed.
        """
        if not self.llm:
            logger.warning("No LLM provided, cannot distill")
            return False

        if not self.should_distill() and self._distilled_memory is not None:
            logger.debug("No distillation needed")
            return False

        try:
            messages_to_distill = (
                self._history[: -self.keep_recent]
                if len(self._history) > self.keep_recent
                else self._history
            )

            if not messages_to_distill:
                return False

            conversation = "\n".join(
                [f"{m.role}: {m.content}" for m in messages_to_distill]
            )
            original_tokens = self.estimate_tokens(conversation)

            # Importance filtering
            if self.enable_importance_filter:
                if not self._check_importance(conversation):
                    logger.debug(
                        "Conversation not important enough, skipping distillation"
                    )
                    return False

            prompt = f"""将以下对话提炼为结构化JSON，格式如下：
{{
    "user_profile": {{"key": "value"}},
    "decisions_made": [{{"key": "唯一标识", "description": "描述"}}],
    "pending_tasks": [{{"task_id": "唯一标识", "description": "描述"}}],
    "important_facts": ["事实1", "事实2"]
}}

要求：
1. user_profile 中只包含长期有效的用户属性
2. decisions_made 需要有唯一key避免重复
3. pending_tasks 只包含未完成的重要任务
4. 只返回JSON，不要其他内容

对话内容：
{conversation}

请用中文提炼："""

            result = await self.llm.ainvoke(
                prompt,
                system_prompt="你是一个记忆蒸馏助手，负责将对话提取为结构化JSON。",
            )

            # Parse JSON response
            try:
                json_str = result.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                elif "{" in json_str and "}" in json_str:
                    start = json_str.find("{")
                    end = json_str.rfind("}") + 1
                    json_str = json_str[start:end]

                memory_data = json.loads(json_str)
                self._distilled_memory = StructuredMemory.from_dict(memory_data)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Failed to parse JSON response: {e}")
                self._distilled_memory = StructuredMemory(
                    important_facts=[result[:500]]
                )

            if len(self._history) > self.keep_recent:
                self._history = self._history[-self.keep_recent :]

            self._distill_level += 1

            distilled_tokens = self.estimate_tokens(self._distilled_memory.to_json())
            logger.info(
                f"Memory distilled: {original_tokens} -> {distilled_tokens} tokens, "
                f"level={self._distill_level}"
            )

            # Persist
            if self.storage and self._session_id:
                self._save_to_storage(original_tokens, distilled_tokens)

            return True

        except Exception as e:
            logger.error(f"Distillation failed: {e}")
            return False

    def search_similar_memories(
        self, query: str, memory_type: str = None, limit: int = 3
    ) -> List[Dict]:
        """Search for similar distilled memories."""
        if not self.storage or not hasattr(self.storage, "search_similar_memories"):
            return []

        try:
            # Generate query embedding
            embedding = None
            if self.llm and hasattr(self.llm, "embed"):
                embedding = self.llm.embed(query)

            if not embedding:
                return []

            return self.storage.search_similar_memories(
                embedding=embedding,
                agent_id=self.agent_id,
                memory_type=memory_type,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Failed to search similar memories: {e}")
            return []

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return f"MemoryDistiller(history={len(self._history)}, tokens={self.get_current_tokens()}, level={self._distill_level}, type={self._memory_type})"


class SessionMemory:
    """
    Session-level memory management.

    Suitable for Leader Agent to manage conversation memory distillation.
    Supports both user_memory and task_memory separation.
    """

    def __init__(
        self,
        session_id: str,
        llm=None,
        storage=None,
        agent_id: str = "leader",
        max_tokens: int = 4000,
        enable_importance_filter: bool = True,
    ):
        self.session_id = session_id
        self.llm = llm
        self.storage = storage
        self.agent_id = agent_id
        self.enable_importance_filter = enable_importance_filter

        # Separate distillers for user_memory and task_memory
        self._user_memory_distiller = MemoryDistiller(
            llm=llm,
            storage=storage,
            agent_id=agent_id,
            max_tokens=max_tokens,
            enable_importance_filter=enable_importance_filter,
        )
        self._user_memory_distiller.set_session(session_id)
        self._user_memory_distiller.set_memory_type("user_memory")

        self._task_memory_distiller = MemoryDistiller(
            llm=llm,
            storage=storage,
            agent_id=agent_id,
            max_tokens=max_tokens,
            enable_importance_filter=False,  # Task memory doesn't need importance filter
        )
        self._task_memory_distiller.set_session(session_id)
        self._task_memory_distiller.set_memory_type("task_memory")

        # Load historical distilled memories on init
        self._load_historical_memories()

    def _load_historical_memories(self):
        """Load historical distilled memories."""
        try:
            # Load user memories
            user_memories = self._user_memory_distiller.load_from_storage(
                self.session_id, memory_type="user_memory"
            )
            if user_memories:
                # Merge all user memories
                merged = user_memories[0]
                for mem in user_memories[1:]:
                    merged = merged.merge(mem)
                self._user_memory_distiller._distilled_memory = merged
                logger.info(f"Loaded {len(user_memories)} user memories")

            # Load task memories
            task_memories = self._task_memory_distiller.load_from_storage(
                self.session_id, memory_type="task_memory"
            )
            if task_memories:
                merged = task_memories[0]
                for mem in task_memories[1:]:
                    merged = merged.merge(mem)
                self._task_memory_distiller._distilled_memory = merged
                logger.info(f"Loaded {len(task_memories)} task memories")

        except Exception as e:
            logger.debug(f"Could not load historical memories: {e}")

    @property
    def user_memory(self) -> MemoryDistiller:
        """Get user memory distiller."""
        return self._user_memory_distiller

    @property
    def task_memory(self) -> MemoryDistiller:
        """Get task memory distiller."""
        return self._task_memory_distiller

    def add_user_turn(self, user_input: str, assistant_response: str = ""):
        """Add one conversation turn to user memory."""
        self._user_memory_distiller.add_user(user_input)
        if assistant_response:
            self._user_memory_distiller.add_assistant(assistant_response)

    def add_task_context(self, task_info: str):
        """Add task context to task memory."""
        self._task_memory_distiller.add_message("system", task_info)

    def add_system_turn(self, system_output: str):
        """Add system/assistant output to user memory."""
        self._user_memory_distiller.add_assistant(system_output)

    def get_context(self) -> str:
        """Get distilled context (both user and task memory)."""
        # Auto check if distillation is needed
        if self._user_memory_distiller.should_distill():
            self._user_memory_distiller.distill()
        if self._task_memory_distiller.should_distill():
            self._task_memory_distiller.distill()

        # Combine contexts
        parts = []
        parts.append("[User Memory]")
        parts.append(self._user_memory_distiller.get_context())

        parts.append("\n[Task Memory]")
        parts.append(self._task_memory_distiller.get_context())

        return "\n".join(parts)

    def get_user_context(self) -> str:
        """Get user memory context only."""
        if self._user_memory_distiller.should_distill():
            self._user_memory_distiller.distill()
        return self._user_memory_distiller.get_context()

    def get_task_context(self) -> str:
        """Get task memory context only."""
        if self._task_memory_distiller.should_distill():
            self._task_memory_distiller.distill()
        return self._task_memory_distiller.get_context()

    async def aget_context(self) -> str:
        """Get distilled context (async)."""
        if self._user_memory_distiller.should_distill():
            await self._user_memory_distiller.adistill()
        if self._task_memory_distiller.should_distill():
            await self._task_memory_distiller.adistill()

        parts = []
        parts.append("[User Memory]")
        parts.append(self._user_memory_distiller.get_context())
        parts.append("\n[Task Memory]")
        parts.append(self._task_memory_distiller.get_context())

        return "\n".join(parts)

    def search_memory(
        self, query: str, memory_type: str = None, limit: int = 3
    ) -> List[Dict]:
        """Search similar memories."""
        if memory_type == "user_memory":
            return self._user_memory_distiller.search_similar_memories(
                query, limit=limit
            )
        elif memory_type == "task_memory":
            return self._task_memory_distiller.search_similar_memories(
                query, limit=limit
            )
        else:
            # Search both
            results = []
            results.extend(
                self._user_memory_distiller.search_similar_memories(query, limit=limit)
            )
            results.extend(
                self._task_memory_distiller.search_similar_memories(query, limit=limit)
            )
            return results[:limit]

    def get_user_profile(self) -> Dict:
        """Get user profile from distilled memory."""
        mem = self._user_memory_distiller.get_structured_memory()
        if mem:
            return mem.user_profile
        return {}

    def get_pending_tasks(self) -> List[Dict]:
        """Get pending tasks from task memory."""
        mem = self._task_memory_distiller.get_structured_memory()
        if mem:
            return mem.pending_tasks
        return []

    def clear(self):
        """Clear all memory."""
        self._user_memory_distiller.clear()
        self._task_memory_distiller.clear()
