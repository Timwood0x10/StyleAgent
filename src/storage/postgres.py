"""
PostgreSQL + pgvector Storage Layer
"""

import os
import json
import uuid
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from ..utils.config import config
from ..utils import get_logger

# Logger for this module
logger = get_logger(__name__)


class Database:
    """Database operations with connection pooling"""

    _pool: Optional[Any] = None
    _pool_lock = threading.Lock()

    @classmethod
    def _get_pool(cls):
        """Get or create connection pool (singleton)"""
        if cls._pool is None:
            with cls._pool_lock:
                if cls._pool is None:
                    logger.info(
                        f"Creating connection pool: {config.PG_HOST}:{config.PG_PORT}/{config.PG_DATABASE}"
                    )
                    try:
                        # Try psycopg2.pool
                        from psycopg2 import pool as pg_pool
                        cls._pool = pg_pool.SimpleConnectionPool(
                            minconn=1,
                            maxconn=10,  # Max 10 connections in pool
                            host=config.PG_HOST,
                            port=config.PG_PORT,
                            database=config.PG_DATABASE,
                            user=config.PG_USER,
                            password=config.PG_PASSWORD,
                        )
                    except AttributeError:
                        # Fallback to simple connection
                        logger.warning("Connection pool not available, using simple connection")
                        cls._pool = None
                        return None
                    logger.info("Connection pool created")
        return cls._pool

    def __init__(self):
        """Initialize database (pool is created lazily)"""
        self._conn = None
        self._ref_count = 0  # Reference count for connection lifecycle

    def acquire(self):
        """Acquire connection (increase ref count)"""
        self._ref_count += 1
        return self.get_connection()

    def release(self):
        """Release connection (decrease ref count, close if count is 0)"""
        if self._ref_count > 0:
            self._ref_count -= 1
        if self._ref_count == 0:
            self.return_connection()

    def reset_ref_count(self):
        """Reset reference count to 0 and close connection"""
        self._ref_count = 0
        self.return_connection()

    def get_connection(self):
        """Get connection from pool"""
        if self._conn is None:
            pool = self._get_pool()
            if pool:
                self._conn = pool.getconn()
            else:
                # Fallback to simple connection
                self._conn = psycopg2.connect(
                    host=config.PG_HOST,
                    port=config.PG_PORT,
                    database=config.PG_DATABASE,
                    user=config.PG_USER,
                    password=config.PG_PASSWORD,
                )
        return self._conn

    def return_connection(self):
        """Return connection to pool"""
        if self._conn is not None:
            pool = self._get_pool()
            if pool:
                pool.putconn(self._conn)
            else:
                self._conn.close()
            self._conn = None

    @property
    def conn(self):
        """Get database connection (for backward compatibility)"""
        return self.get_connection()

    def execute(self, sql: str, params: tuple = None):
        """Execute SQL and return first row if available (cursor is auto-closed)"""
        cursor = None
        conn = None
        try:
            conn = self.acquire()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            # Fetch result before closing cursor (for RETURNING queries)
            try:
                row = cursor.fetchone()
            except Exception:
                row = None
            return row
        except Exception as e:
            logger.error(f"Database execute error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.release()

    def fetch_one(self, sql: str, params: tuple = None):
        """Fetch one row"""
        cursor = None
        conn = None
        try:
            conn = self.acquire()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Database fetch_one error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.release()

    def fetch_all(self, sql: str, params: tuple = None):
        """Fetch all rows"""
        cursor = None
        conn = None
        try:
            conn = self.acquire()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Database fetch_all error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.release()

    def close(self):
        """Close and return connection to pool"""
        self.return_connection()

    @classmethod
    def close_pool(cls):
        """Close all connections in pool (call when shutting down)"""
        if cls._pool is not None:
            try:
                cls._pool.closeall()
            except Exception as e:
                logger.warning(f"Error closing pool: {e}")
            cls._pool = None
            logger.info("Connection pool closed")


class StorageLayer:
    """Storage Layer - PostgreSQL + pgvector"""

    _tables_initialized = False  # Class-level flag to prevent re-initialization

    def __init__(self):
        self.db = Database()
        if not StorageLayer._tables_initialized:
            self._init_tables()
            StorageLayer._tables_initialized = True

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

        -- Memory distillation summaries (持久化蒸馏后的记忆)
        CREATE TABLE IF NOT EXISTS memory_summaries (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            agent_id VARCHAR(50) NOT NULL,
            summary JSONB NOT NULL,  -- 结构化JSON格式
            original_token_count INT,
            compressed_token_count INT,
            memory_type VARCHAR(20) DEFAULT 'user_memory',  -- 'user_memory' or 'task_memory'
            distill_level INT DEFAULT 1,  -- 蒸馏层级，防止递归劣化
            embedding vector(1536),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (session_id, agent_id, memory_type)
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
        CREATE INDEX IF NOT EXISTS idx_memory_session_agent ON memory_summaries(session_id, agent_id);
        CREATE INDEX IF NOT EXISTS idx_memory_embedding ON memory_summaries USING hnsw (embedding vector_cosine_ops);

        -- Add unique constraint for memory_summaries table (if not exists)
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uk_memory_session_agent_type'
            ) THEN
                ALTER TABLE memory_summaries
                ADD CONSTRAINT uk_memory_session_agent_type
                UNIQUE (session_id, agent_id, memory_type);
            END IF;
        END $$;
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
        row = self.db.execute(
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
        return row[0]

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
        row = self.db.execute(
            sql, (session_id, category, items, colors, styles, reasons, price_range)
        )
        return row[0]

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
        row = self.db.execute(
            sql, (session_id, content, vec_str, json.dumps(metadata or {}))
        )
        return row[0]

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
            RETURNING id
        """
        result = self.db.execute(sql, (session_id, agent_id, json.dumps(context_data)))
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

    # ========== Memory Distillation / 记忆蒸馏 ==========
    def save_distilled_memory(
        self,
        session_id: str,
        agent_id: str,
        summary: str,  # Now JSON string
        original_token_count: int = None,
        compressed_token_count: int = None,
        memory_type: str = "user_memory",
        distill_level: int = 1,
        embedding: List[float] = None,
        metadata: Dict = None,
    ):
        """Save distilled memory with structured JSON format."""
        sql = """
            INSERT INTO memory_summaries
            (session_id, agent_id, summary, original_token_count, compressed_token_count,
             memory_type, distill_level, embedding, metadata, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (session_id, agent_id, memory_type)
            DO UPDATE SET summary = EXCLUDED.summary,
                          original_token_count = EXCLUDED.original_token_count,
                          compressed_token_count = EXCLUDED.compressed_token_count,
                          distill_level = EXCLUDED.distill_level,
                          embedding = EXCLUDED.embedding,
                          metadata = EXCLUDED.metadata,
                          updated_at = NOW()
        """
        # Convert embedding to PostgreSQL array format
        embedding_arr = None
        if embedding:
            embedding_arr = "[" + ",".join(map(str, embedding)) + "]"

        metadata_json = json.dumps(metadata) if metadata else None

        self.db.execute(
            sql,
            (
                session_id,
                agent_id,
                summary,
                original_token_count,
                compressed_token_count,
                memory_type,
                distill_level,
                embedding_arr,
                metadata_json,
            ),
        )

    def get_distilled_memories(
        self,
        session_id: str,
        agent_id: str = None,
        memory_type: str = None,
        limit: int = 5,
    ) -> List[Dict]:
        """Get distilled memories with optional memory_type filter."""
        conditions = ["session_id = %s"]
        params = [session_id]

        if agent_id:
            conditions.append("agent_id = %s")
            params.append(agent_id)

        if memory_type:
            conditions.append("memory_type = %s")
            params.append(memory_type)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT id, session_id, agent_id, summary, original_token_count,
                   compressed_token_count, memory_type, distill_level,
                   metadata, created_at, updated_at
            FROM memory_summaries
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT %s
        """
        params.append(str(limit))

        rows = self.db.fetch_all(sql, tuple(params))

        results = []
        for row in rows:
            # Parse summary as JSON
            summary_data = row[3]
            if isinstance(summary_data, str):
                try:
                    summary_data = json.loads(summary_data)
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON

            results.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "agent_id": row[2],
                    "summary": summary_data,
                    "original_token_count": row[4],
                    "compressed_token_count": row[5],
                    "memory_type": row[6],
                    "distill_level": row[7],
                    "metadata": row[8],
                    "created_at": row[9],
                    "updated_at": row[10],
                }
            )
        return results

    def search_similar_memories(
        self,
        embedding: List[float],
        agent_id: str = None,
        memory_type: str = None,
        limit: int = 3,
        match_threshold: float = 0.7,
    ) -> List[Dict]:
        """Search similar memories (vector search)"""
        embedding_arr = "[" + ",".join(map(str, embedding)) + "]"

        # Build WHERE clause
        conditions = ["embedding <=> %s::vector < %s"]
        params = [embedding_arr, 1 - match_threshold]

        if agent_id:
            conditions.append("agent_id = %s")
            params.append(agent_id)

        if memory_type:
            conditions.append("memory_type = %s")
            params.append(memory_type)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT id, session_id, agent_id, summary, original_token_count,
                   compressed_token_count, memory_type, distill_level, metadata,
                   created_at, updated_at,
                   1 - (embedding <=> %s::vector) as similarity
            FROM memory_summaries
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        # Add embedding for similarity calculation
        params.extend([embedding_arr, limit])

        rows = self.db.fetch_all(sql, tuple(params))

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "agent_id": row[2],
                    "summary": row[3],
                    "original_token_count": row[4],
                    "compressed_token_count": row[5],
                    "metadata": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                    "similarity": row[9],
                }
            )
        return results

    def close(self):
        """Close database connection pool"""
        # Reset ref count and close connection before closing pool
        self.db.reset_ref_count()
        Database.close_pool()


# Global storage instance
_storage: Optional[StorageLayer] = None


def get_storage() -> StorageLayer:
    """Get storage instance"""
    global _storage
    if _storage is None:
        _storage = StorageLayer()
    return _storage
