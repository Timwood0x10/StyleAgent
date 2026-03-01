"""
Task Registry - Task Registration and Status Management

Implements task registration, claim, status update, and duplicate prevention
"""

import uuid
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..storage import get_storage


class TaskStatus(str, Enum):
    """Task status"""

    PENDING = "pending"  # Waiting to be claimed
    IN_PROGRESS = "in_progress"  # Currently executing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Failed
    CANCELLED = "cancelled"  # Cancelled


@dataclass
class TaskRecord:
    """Task record"""

    task_id: str
    session_id: str
    parent_task_id: Optional[str] = None
    title: str = ""
    description: str = ""
    category: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assignee_agent_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class TaskRegistry:
    """
    Task Registry - Core component

    Features:
    - Task registration (register)
    - Task claiming (claim) - ensures unique execution
    - Status update (update_status)
    - Status query (get_status)
    - Progress reporting (report_progress)
    """

    def __init__(self, storage=None):
        self._storage = storage
        self._memory_cache: Dict[str, Any] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # Lock to protect _locks dictionary

    @property
    def storage(self):
        """Get storage instance"""
        if self._storage is None:
            self._storage = get_storage()
        return self._storage

    def _get_lock(self, task_id: str) -> threading.Lock:
        """Get task lock - thread-safe"""
        with self._locks_lock:
            if task_id not in self._locks:
                self._locks[task_id] = threading.Lock()
            return self._locks[task_id]

    def register_task(
        self,
        session_id: str,
        title: str,
        description: str = "",
        category: str = "",
        parent_task_id: str = None,
        max_retries: int = 3,
    ) -> str:
        """
        Register new task

        Returns:
            task_id: Unique task identifier
        """
        task_id = str(uuid.uuid4())

        task = TaskRecord(
            task_id=task_id,
            session_id=session_id,
            title=title,
            description=description,
            category=category,
            parent_task_id=parent_task_id,
            max_retries=max_retries,
            status=TaskStatus.PENDING,
        )

        # Memory cache
        self._memory_cache[task_id] = task

        # Persistent storage
        try:
            self.storage.save_task(task)
        except Exception as e:
            print(f"WARNING: Task save failed: {e}")

        return task_id

    def claim_task(self, agent_id: str, task_id: str) -> bool:
        """
        Claim task - ensures unique execution

        Args:
            agent_id: Agent ID claiming the task
            task_id: Task ID

        Returns:
            True: Claim success
            False: Task already claimed or not exists
        """
        lock = self._get_lock(task_id)

        with lock:
            task = self._memory_cache.get(task_id)

            if not task:
                # Load from storage
                task = self.storage.get_task(task_id)
                if not task:
                    return False
                self._memory_cache[task_id] = task

            # Check status - task is a Dict, use bracket notation
            if task.get("status") != TaskStatus.PENDING:
                return False

            # Claim task - update Dict fields
            task["status"] = TaskStatus.IN_PROGRESS
            task["assignee_agent_id"] = agent_id
            task["updated_at"] = datetime.now()

            # Update storage
            try:
                self.storage.update_task_status(
                    task_id, TaskStatus.IN_PROGRESS, agent_id
                )
            except Exception as e:
                print(f"WARNING: Status update failed: {e}")

            return True

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Dict[str, Any] = None,
        error_message: str = None,
    ) -> bool:
        """
        Update task status

        Args:
            task_id: Task ID
            status: New status
            result: Task result (optional)
            error_message: Error message (optional)
        """
        lock = self._get_lock(task_id)

        with lock:
            task = self._memory_cache.get(task_id)

            if not task:
                task = self.storage.get_task(task_id)
                if not task:
                    return False
                self._memory_cache[task_id] = task

            old_status = task.status
            task.status = status
            task.updated_at = datetime.now()

            if result:
                task.result = result

            if error_message:
                task.error_message = error_message

            if status == TaskStatus.COMPLETED or status == TaskStatus.FAILED:
                task.completed_at = datetime.now()

            # Persist to storage
            try:
                self.storage.update_task(
                    task_id,
                    status=status.value,
                    result=result,
                    error_message=error_message,
                    completed_at=task.completed_at,
                )
            except Exception as e:
                print(f"WARNING: Task update failed: {e}")

            return True

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get task status"""
        task = self._memory_cache.get(task_id)
        if not task:
            task = self.storage.get_task(task_id)
        if task:
            return task.status
        return None

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Get task details"""
        task = self._memory_cache.get(task_id)
        if not task:
            task = self.storage.get_task(task_id)
        return task

    def get_session_tasks(self, session_id: str) -> List[TaskRecord]:
        """Get all tasks for a session"""
        return self.storage.get_tasks_by_session(session_id)

    def report_progress(self, task_id: str, progress: float, message: str = "") -> bool:
        """
        Report progress

        Args:
            task_id: Task ID
            progress: Progress 0.0-1.0
            message: Progress message
        """
        task = self._memory_cache.get(task_id)
        if task:
            task.updated_at = datetime.now()
            # Could extend: store progress history
            return True
        return False

    def retry_failed_task(self, task_id: str) -> bool:
        """
        Retry failed task

        Returns:
            True: Retry success, task reset to PENDING
            False: Does not meet retry conditions
        """
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status != TaskStatus.FAILED:
            return False

        if task.retry_count >= task.max_retries:
            return False

        # Reset task
        task.status = TaskStatus.PENDING
        task.assignee_agent_id = None
        task.error_message = None
        task.retry_count += 1
        task.updated_at = datetime.now()

        # Update storage
        self.storage.update_task(
            task_id, status=TaskStatus.PENDING.value, retry_count=task.retry_count
        )

        return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel task"""
        return self.update_status(task_id, TaskStatus.CANCELLED)

    def get_pending_tasks(self, category: str = None) -> List[TaskRecord]:
        """Get pending tasks"""
        all_tasks = list(self._memory_cache.values())
        pending = [t for t in all_tasks if t.status == TaskStatus.PENDING]

        if category:
            pending = [t for t in pending if t.category == category]

        return pending


# Global instance
_registry: Optional[TaskRegistry] = None


def get_task_registry() -> TaskRegistry:
    """Get task registry instance"""
    global _registry
    if _registry is None:
        _registry = TaskRegistry()
    return _registry


# Alias for convenience
get_registry = get_task_registry
