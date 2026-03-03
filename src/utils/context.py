"""
Memory Distillation Module

Distills conversation history into key memories, persists to pgvector for cross-session retrieval.
"""

from typing import Dict, List, Optional

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


class MemoryDistiller:
    """
    Memory Distiller.

    Features:
    - Tracks conversation history
    - Estimates token usage
    - Triggers LLM distillation when threshold exceeded
    - Persists distilled memories to pgvector
    - Retrieves historical memories from vector database
    """

    def __init__(
        self,
        llm=None,
        storage=None,  # StorageLayer instance
        agent_id: str = "default",
        max_tokens: int = 4000,
        distill_threshold: float = 0.8,
        keep_recent: int = 4,
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
        """
        self.llm = llm
        self.storage = storage
        self.agent_id = agent_id
        self.max_tokens = max_tokens
        self.distill_threshold = distill_threshold
        self.keep_recent = keep_recent

        self._history: List[Message] = []
        self._distilled_memory: Optional[str] = None
        self._session_id: Optional[str] = None

    def set_session(self, session_id: str):
        """Set session ID."""
        self._session_id = session_id

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
            parts.append(self._distilled_memory)
        parts.extend([f"{m.role}: {m.content}" for m in self._history])
        return self.estimate_tokens("\n".join(parts))

    def should_distill(self) -> bool:
        """Check if distillation is needed."""
        return self.get_current_tokens() > self.max_tokens * self.distill_threshold

    def get_context(self) -> str:
        """
        Get distilled context.

        Format:
        [Distilled Memory]
        ---
        [Recent N turns]
        """
        parts = []

        if self._distilled_memory:
            parts.append(f"[Distilled Memory]\n{self._distilled_memory}")
            parts.append("---")

        # Keep recent N turns
        recent = self._history[-self.keep_recent :] if self._history else []
        if recent:
            parts.append("[Recent Conversation]")
            for m in recent:
                parts.append(f"{m.role}: {m.content}")

        return "\n\n".join(parts)

    def get_full_history(self) -> List[Message]:
        """Get full conversation history."""
        return self._history.copy()

    def clear(self):
        """Clear history and distilled memory."""
        self._history.clear()
        self._distilled_memory = None

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

            # Distillation prompt
            prompt = f"""Summarize the following conversation into key points, preserving:
1. User preferences and characteristics
2. Important decisions and results
3. Unfinished tasks
4. Key context

Conversation:
{conversation}

Please summarize in English:"""

            # Invoke LLM for distillation
            distilled = self.llm.invoke(
                prompt,
                system_prompt="You are a memory distillation assistant that extracts key information from conversations.",
            )

            self._distilled_memory = distilled

            # Keep recent conversation
            if len(self._history) > self.keep_recent:
                self._history = self._history[-self.keep_recent :]

            distilled_tokens = self.estimate_tokens(distilled)
            logger.info(
                f"Memory distilled: {original_tokens} -> {distilled_tokens} tokens"
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

            # Generate embedding
            embedding = None
            if self.llm and hasattr(self.llm, "embed"):
                embedding = self.llm.embed(self._distilled_memory)

            self.storage.save_distilled_memory(
                session_id=self._session_id,
                agent_id=self.agent_id,
                summary=self._distilled_memory,
                original_token_count=original_tokens,
                compressed_token_count=distilled_tokens,
                embedding=embedding,
                metadata={"type": "memory_distillation"},
            )
            logger.info(f"Distilled memory saved for session {self._session_id}")
        except Exception as e:
            logger.error(f"Failed to save distilled memory: {e}")

    def load_from_storage(self, session_id: str = None, limit: int = 5) -> List[str]:
        """Load historical distilled memories from database."""
        if not self.storage or not hasattr(self.storage, "get_distilled_memories"):
            return []

        try:
            sid = session_id or self._session_id
            if not sid:
                return []

            memories = self.storage.get_distilled_memories(
                session_id=sid, agent_id=self.agent_id, limit=limit
            )

            results = []
            for m in memories:
                if m.get("summary"):
                    results.append(m["summary"])

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

            prompt = f"""Summarize the following conversation into key points, preserving:
1. User preferences and characteristics
2. Important decisions and results
3. Unfinished tasks
4. Key context

Conversation:
{conversation}

Please summarize in English:"""

            distilled = await self.llm.ainvoke(
                prompt,
                system_prompt="You are a memory distillation assistant that extracts key information from conversations.",
            )

            self._distilled_memory = distilled

            if len(self._history) > self.keep_recent:
                self._history = self._history[-self.keep_recent :]

            distilled_tokens = self.estimate_tokens(distilled)
            logger.info(
                f"Memory distilled: {original_tokens} -> {distilled_tokens} tokens"
            )

            # Persist
            if self.storage and self._session_id:
                self._save_to_storage(original_tokens, distilled_tokens)

            return True

        except Exception as e:
            logger.error(f"Distillation failed: {e}")
            return False

    def search_similar_memories(self, query: str, limit: int = 3) -> List[Dict]:
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
                embedding=embedding, agent_id=self.agent_id, limit=limit
            )
        except Exception as e:
            logger.error(f"Failed to search similar memories: {e}")
            return []

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return f"MemoryDistiller(history={len(self._history)}, tokens={self.get_current_tokens()}, memory={'Yes' if self._distilled_memory else 'No'})"


class SessionMemory:
    """
    Session-level memory management.

    Suitable for Leader Agent to manage conversation memory distillation.
    """

    def __init__(
        self,
        session_id: str,
        llm=None,
        storage=None,
        agent_id: str = "leader",
        max_tokens: int = 4000,
    ):
        self.session_id = session_id
        self.distiller = MemoryDistiller(
            llm=llm, storage=storage, agent_id=agent_id, max_tokens=max_tokens
        )
        self.distiller.set_session(session_id)

        # Load historical distilled memories on init
        self._load_historical_memories()

    def _load_historical_memories(self):
        """Load historical distilled memories."""
        try:
            memories = self.distiller.load_from_storage(self.session_id)
            if memories:
                # Use historical memories as initial context
                self.distiller._distilled_memory = "\n\n".join(memories)
                logger.info(f"Loaded {len(memories)} historical distilled memories")
        except Exception as e:
            logger.debug(f"Could not load historical memories: {e}")

    def add_user_turn(self, user_input: str, assistant_response: str = ""):
        """Add one conversation turn (user input + optional assistant response)."""
        self.distiller.add_user(user_input)
        if assistant_response:
            self.distiller.add_assistant(assistant_response)

    def add_system_turn(self, system_output: str):
        """Add system/assistant output."""
        self.distiller.add_assistant(system_output)

    def get_context(self) -> str:
        """Get distilled context."""
        # Auto check if distillation is needed
        if self.distiller.should_distill():
            self.distiller.distill()
        return self.distiller.get_context()

    async def aget_context(self) -> str:
        """Get distilled context (async)."""
        if self.distiller.should_distill():
            await self.distiller.adistill()
        return self.distiller.get_context()

    def search_memory(self, query: str, limit: int = 3) -> List[Dict]:
        """Search similar memories."""
        return self.distiller.search_similar_memories(query, limit)

    def clear(self):
        """Clear memory."""
        self.distiller.clear()
