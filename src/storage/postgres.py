"""
PostgreSQL + pgvector Storage Layer
"""

import os
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from ..utils.config import config
from ..utils import get_logger

# Logger for this module
logger = get_logger(__name__)


class Database:
    """Database operations"""

    def __init__(self):
        self._conn = None

    @property
    def conn(self):
        """Get database connection"""
        if self._conn is None:
            logger.info(
                f"Connecting to database: {config.PG_HOST}:{config.PG_PORT}/{config.PG_DATABASE}"
            )
            self._conn = psycopg2.connect(
                host=config.PG_HOST,
                port=config.PG_PORT,
                database=config.PG_DATABASE,
                user=config.PG_USER,
                password=config.PG_PASSWORD,
            )
            logger.info("Database connection established")
        return self._conn

    def execute(self, sql: str, params: tuple = None):
        """Execute SQL"""
        cursor = None
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            self.conn.commit()
            return cursor
        except Exception as e:
            logger.error(f"Database execute error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()

    def fetch_one(self, sql: str, params: tuple = None):
        """Fetch one row"""
        cursor = None
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Database fetch_one error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()

    def fetch_all(self, sql: str, params: tuple = None):
        """Fetch all rows"""
        cursor = None
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Database fetch_all error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()

    def close(self):
        """Close connection"""
        if self._conn:
            self._conn.close()
            self._conn = None


class StorageLayer:
    """Storage Layer - PostgreSQL + pgvector"""

    def __init__(self):
        self.db = Database()
        self._init_tables()

    def _init_tables(self):
        """Initialize all tables"""
        # Enable pgvector extension
        self.db.execute("CREATE EXTENSION IF NOT EXISTS vector")

        sql = """
        -- User profiles table
        CREATE TABLE IF NOT EXISTS user_profiles (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            name VARCHAR(100),
            gender VARCHAR(20),
            age INT,
            occupation VARCHAR(100),
            hobbies TEXT[],
            mood VARCHAR(50),
            style_preference VARCHAR(100),
            budget VARCHAR(20),
            season VARCHAR(20),
            occasion VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        -- Outfit recommendations table
        CREATE TABLE IF NOT EXISTS outfit_recommendations (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            category VARCHAR(50),
            items TEXT[],
            colors TEXT[],
            styles TEXT[],
            reasons TEXT[],
            price_range VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        -- Semantic vectors table
        CREATE TABLE IF NOT EXISTS semantic_vectors (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            agent_id VARCHAR(50),
            content TEXT,
            embedding vector(1536),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        -- Task status table (Task Registry)
        CREATE TABLE IF NOT EXISTS tasks (
            task_id UUID PRIMARY KEY,
            session_id UUID NOT NULL,
            parent_task_id UUID,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            category VARCHAR(50),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            assignee_agent_id VARCHAR(50),
            result JSONB,
            error_message TEXT,
            retry_count INT DEFAULT 0,
            max_retries INT DEFAULT 3,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP
        );
        
        -- Session/dialogue history table
        CREATE TABLE IF NOT EXISTS sessions (
            session_id UUID PRIMARY KEY,
            user_input TEXT NOT NULL,
            final_output TEXT,
            summary TEXT,
            status VARCHAR(20) DEFAULT 'running',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP
        );
        
        -- Agent context table (private context)
        CREATE TABLE IF NOT EXISTS agent_contexts (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            agent_id VARCHAR(50) NOT NULL,
            context_data JSONB,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(session_id, agent_id)
        );
        
        -- Task progress history table
        CREATE TABLE IF NOT EXISTS task_progress (
            id SERIAL PRIMARY KEY,
            task_id UUID NOT NULL,
            agent_id VARCHAR(50) NOT NULL,
            progress FLOAT,
            message TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_vectors_session ON semantic_vectors(session_id);
        CREATE INDEX IF NOT EXISTS idx_vectors_embedding ON semantic_vectors USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX IF NOT EXISTS idx_profiles_session ON user_profiles(session_id);
        CREATE INDEX IF NOT EXISTS idx_outfit_session ON outfit_recommendations(session_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_contexts_session_agent ON agent_contexts(session_id, agent_id);
        CREATE INDEX IF NOT EXISTS idx_progress_task ON task_progress(task_id);
        """
        self.db.execute(sql)

    # ========== User Profile ==========
    def save_user_profile(self, session_id: str, profile: Dict[str, Any]) -> int:
        """Save user profile"""
        sql = """
            INSERT INTO user_profiles 
            (session_id, name, gender, age, occupation, hobbies, mood, style_preference, budget, season, occasion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        cursor = self.db.execute(
            sql,
            (
                session_id,
                profile.get("name"),
                profile.get("gender"),
                profile.get("age"),
                profile.get("occupation"),
                profile.get("hobbies"),
                profile.get("mood"),
                profile.get("style_preference"),
                profile.get("budget"),
                profile.get("season"),
                profile.get("occasion"),
            ),
        )
        return cursor.fetchone()[0]

    def get_user_profile(self, session_id: str) -> Optional[Dict]:
        """Get user profile"""
        sql = "SELECT * FROM user_profiles WHERE session_id = %s ORDER BY created_at DESC LIMIT 1"
        row = self.db.fetch_one(sql, (session_id,))
        if row:
            return {
                "id": row[0],
                "session_id": row[1],
                "name": row[2],
                "gender": row[3],
                "age": row[4],
                "occupation": row[5],
                "hobbies": row[6],
                "mood": row[7],
                "style_preference": row[8],
                "budget": row[9],
                "season": row[10],
                "occasion": row[11],
                "created_at": row[12],
            }
        return None

    # ========== Outfit Recommendations ==========
    def save_outfit_recommendation(
        self,
        session_id: str,
        category: str,
        items: List[str],
        colors: List[str],
        styles: List[str],
        reasons: List[str],
        price_range: str = "",
    ) -> int:
        """Save outfit recommendation"""
        sql = """
            INSERT INTO outfit_recommendations 
            (session_id, category, items, colors, styles, reasons, price_range)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        cursor = self.db.execute(
            sql, (session_id, category, items, colors, styles, reasons, price_range)
        )
        return cursor.fetchone()[0]

    def get_outfit_recommendations(self, session_id: str) -> List[Dict]:
        """Get outfit recommendations list"""
        sql = "SELECT * FROM outfit_recommendations WHERE session_id = %s ORDER BY category"
        rows = self.db.fetch_all(sql, (session_id,))
        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "category": row[2],
                    "items": row[3],
                    "colors": row[4],
                    "styles": row[5],
                    "reasons": row[6],
                    "price_range": row[7],
                    "created_at": row[8],
                }
            )
        return results

    # ========== Semantic Vectors ==========
    def save_vector(
        self,
        session_id: str,
        content: str,
        embedding: List[float],
        metadata: Dict = None,
    ) -> int:
        """Save semantic vector"""
        sql = """
            INSERT INTO semantic_vectors (session_id, content, embedding, metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        # pgvector requires array format
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        cursor = self.db.execute(
            sql, (session_id, content, vec_str, json.dumps(metadata or {}))
        )
        return cursor.fetchone()[0]

    def search_similar(
        self, embedding: List[float], session_id: str = None, limit: int = 5
    ) -> List[Dict]:
        """Vector similarity search"""
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

        if session_id:
            sql = """
                SELECT * FROM semantic_vectors 
                WHERE session_id = %s
                ORDER BY embedding <=> %s::vector LIMIT %s
            """
            rows = self.db.fetch_all(sql, (session_id, vec_str, limit))
        else:
            sql = """
                SELECT * FROM semantic_vectors 
                ORDER BY embedding <=> %s::vector LIMIT %s
            """
            rows = self.db.fetch_all(sql, (vec_str, limit))

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "agent_id": row[2],
                    "content": row[3],
                    "embedding": row[4],
                    "metadata": row[5],
                    "created_at": row[6],
                }
            )
        return results

    # ========== Tasks (Task Registry) ==========
    def save_task(self, task) -> str:
        """Save task"""
        sql = """
            INSERT INTO tasks 
            (task_id, session_id, parent_task_id, title, description, category, status, 
             assignee_agent_id, retry_count, max_retries)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (task_id) DO UPDATE SET
                status = EXCLUDED.status,
                assignee_agent_id = EXCLUDED.assignee_agent_id,
                updated_at = NOW()
        """
        self.db.execute(
            sql,
            (
                task.task_id,
                task.session_id,
                task.parent_task_id,
                task.title,
                task.description,
                task.category,
                task.status.value,
                task.assignee_agent_id,
                task.retry_count,
                task.max_retries,
            ),
        )
        return task.task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task"""
        sql = "SELECT * FROM tasks WHERE task_id = %s"
        row = self.db.fetch_one(sql, (task_id,))
        if row:
            return self._row_to_task(row)
        return None

    def update_task_status(self, task_id: str, status: str, agent_id: str = None):
        """Update task status"""
        sql = """
            UPDATE tasks 
            SET status = %s, assignee_agent_id = COALESCE(%s, assignee_agent_id), 
                updated_at = NOW()
            WHERE task_id = %s
        """
        self.db.execute(sql, (status, agent_id, task_id))

    def update_task(
        self,
        task_id: str,
        status: str = None,
        result: Dict = None,
        error_message: str = None,
        completed_at: datetime = None,
        retry_count: int = None,
    ):
        """Update task"""
        sql = "UPDATE tasks SET "
        params: List[Any] = []

        if status:
            sql += "status = %s, "
            params.append(status)
        if result:
            sql += "result = %s, "
            params.append(json.dumps(result))
        if error_message:
            sql += "error_message = %s, "
            params.append(error_message)
        if completed_at:
            sql += "completed_at = %s, "
            params.append(completed_at)
        if retry_count is not None:
            sql += "retry_count = %s, "
            params.append(retry_count)

        sql += "updated_at = NOW() WHERE task_id = %s"
        params.append(task_id)

        self.db.execute(sql, tuple(params))

    def get_tasks_by_session(self, session_id: str) -> List[Dict]:
        """Get all tasks for session"""
        sql = "SELECT * FROM tasks WHERE session_id = %s ORDER BY created_at"
        rows = self.db.fetch_all(sql, (session_id,))
        return [self._row_to_task(row) for row in rows]

    def get_pending_tasks(self) -> List[Dict]:
        """Get pending tasks"""
        sql = "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at"
        rows = self.db.fetch_all(sql)
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row) -> Dict:
        """Convert row to task dict"""
        return {
            "task_id": row[0],
            "session_id": row[1],
            "parent_task_id": row[2],
            "title": row[3],
            "description": row[4],
            "category": row[5],
            "status": row[6],
            "assignee_agent_id": row[7],
            "result": row[8],
            "error_message": row[9],
            "retry_count": row[10],
            "max_retries": row[11],
            "created_at": row[12],
            "updated_at": row[13],
            "completed_at": row[14],
        }

    # ========== Sessions ==========
    def save_session(self, session_id: str, user_input: str) -> str:
        """Save session"""
        sql = """
            INSERT INTO sessions (session_id, user_input, status)
            VALUES (%s, %s, 'running')
            ON CONFLICT (session_id) DO UPDATE SET
                user_input = EXCLUDED.user_input,
                updated_at = NOW()
        """
        self.db.execute(sql, (session_id, user_input))
        return session_id

    def update_session(
        self,
        session_id: str,
        final_output: str = None,
        summary: str = None,
        status: str = None,
    ):
        """Update session"""
        sql = "UPDATE sessions SET "
        params = []

        if final_output:
            sql += "final_output = %s, "
            params.append(final_output)
        if summary:
            sql += "summary = %s, "
            params.append(summary)
        if status:
            sql += "status = %s, "
            params.append(status)
            if status in ("completed", "failed"):
                sql += "completed_at = NOW(), "

        sql += "updated_at = NOW() WHERE session_id = %s"
        params.append(session_id)

        self.db.execute(sql, tuple(params))

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session"""
        sql = "SELECT * FROM sessions WHERE session_id = %s"
        row = self.db.fetch_one(sql, (session_id,))
        if row:
            return {
                "session_id": row[0],
                "user_input": row[1],
                "final_output": row[2],
                "summary": row[3],
                "status": row[4],
                "created_at": row[5],
                "completed_at": row[6],
            }
        return None

    # ========== Agent Contexts ==========
    def save_agent_context(
        self, session_id: str, agent_id: str, context_data: Dict
    ) -> int:
        """Save agent context"""
        sql = """
            INSERT INTO agent_contexts (session_id, agent_id, context_data)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id, agent_id) DO UPDATE SET
                context_data = EXCLUDED.context_data,
                updated_at = NOW()
        """
        cursor = self.db.execute(sql, (session_id, agent_id, json.dumps(context_data)))
        result = cursor.fetchone()
        return result[0] if result else 0

    def get_agent_context(self, session_id: str, agent_id: str) -> Optional[Dict]:
        """Get agent context"""
        sql = "SELECT * FROM agent_contexts WHERE session_id = %s AND agent_id = %s"
        row = self.db.fetch_one(sql, (session_id, agent_id))
        if row:
            return {
                "id": row[0],
                "session_id": row[1],
                "agent_id": row[2],
                "context_data": row[3],
                "updated_at": row[4],
            }
        return None

    def get_all_agent_contexts(self, session_id: str) -> List[Dict]:
        """Get all agent contexts for session"""
        sql = "SELECT * FROM agent_contexts WHERE session_id = %s"
        rows = self.db.fetch_all(sql, (session_id,))
        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "agent_id": row[2],
                    "context_data": row[3],
                    "updated_at": row[4],
                }
            )
        return results

    # ========== Task Progress ==========
    def save_task_progress(
        self, task_id: str, agent_id: str, progress: float, message: str = ""
    ):
        """Save task progress"""
        sql = """
            INSERT INTO task_progress (task_id, agent_id, progress, message)
            VALUES (%s, %s, %s, %s)
        """
        self.db.execute(sql, (task_id, agent_id, progress, message))

    def get_task_progress_history(self, task_id: str) -> List[Dict]:
        """Get task progress history"""
        sql = "SELECT * FROM task_progress WHERE task_id = %s ORDER BY created_at"
        rows = self.db.fetch_all(sql, (task_id,))
        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "task_id": row[1],
                    "agent_id": row[2],
                    "progress": row[3],
                    "message": row[4],
                    "created_at": row[5],
                }
            )
        return results

    def close(self):
        """Close database connection"""
        self.db.close()


# Global storage instance
_storage: Optional[StorageLayer] = None


def get_storage() -> StorageLayer:
    """Get storage instance"""
    global _storage
    if _storage is None:
        _storage = StorageLayer()
    return _storage
