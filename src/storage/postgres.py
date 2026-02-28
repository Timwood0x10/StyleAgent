"""
PostgreSQL + pgvector 存储层
"""
import os
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from ..utils.config import config


class Database:
    """数据库操作"""
    
    def __init__(self):
        self._conn = None
    
    @property
    def conn(self):
        if self._conn is None:
            self._conn = psycopg2.connect(
                host=config.PG_HOST,
                port=config.PG_PORT,
                database=config.PG_DATABASE,
                user=config.PG_USER,
                password=config.PG_PASSWORD
            )
        return self._conn
    
    def execute(self, sql: str, params: tuple = None):
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        self.conn.commit()
        return cursor
    
    def fetch_one(self, sql: str, params: tuple = None):
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()
    
    def fetch_all(self, sql: str, params: tuple = None):
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


class StorageLayer:
    """存储层 - PostgreSQL + pgvector"""
    
    def __init__(self):
        self.db = Database()
        self._init_tables()
    
    def _init_tables(self):
        """初始化表"""
        sql = """
        -- 用户画像表
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
        
        -- 穿搭推荐结果表
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
        
        -- 语义向量表
        CREATE TABLE IF NOT EXISTS semantic_vectors (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            content TEXT,
            embedding vector(1536),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        -- 索引
        CREATE INDEX IF NOT EXISTS idx_vectors_session ON semantic_vectors(session_id);
        CREATE INDEX IF NOT EXISTS idx_vectors_embedding ON semantic_vectors USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX IF NOT EXISTS idx_profiles_session ON user_profiles(session_id);
        CREATE INDEX IF NOT EXISTS idx_outfit_session ON outfit_recommendations(session_id);
        """
        self.db.execute(sql)
    
    # ========== User Profile ==========
    def save_user_profile(self, session_id: str, profile: Dict[str, Any]) -> int:
        """保存用户画像"""
        sql = """
            INSERT INTO user_profiles 
            (session_id, name, gender, age, occupation, hobbies, mood, style_preference, budget, season, occasion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        cursor = self.db.execute(sql, (
            session_id, profile.get("name"), profile.get("gender"), profile.get("age"),
            profile.get("occupation"), profile.get("hobbies"), profile.get("mood"),
            profile.get("style_preference"), profile.get("budget"), 
            profile.get("season"), profile.get("occasion")
        ))
        return cursor.fetchone()[0]
    
    def get_user_profile(self, session_id: str) -> Optional[Dict]:
        """获取用户画像"""
        sql = "SELECT * FROM user_profiles WHERE session_id = %s ORDER BY created_at DESC LIMIT 1"
        row = self.db.fetch_one(sql, (session_id,))
        if row:
            return {
                "id": row[0], "session_id": row[1], "name": row[2],
                "gender": row[3], "age": row[4], "occupation": row[5],
                "hobbies": row[6], "mood": row[7], "style_preference": row[8],
                "budget": row[9], "season": row[10], "occasion": row[11],
                "created_at": row[12]
            }
        return None
    
    # ========== Outfit Recommendations ==========
    def save_outfit_recommendation(self, session_id: str, category: str, 
                                   items: List[str], colors: List[str],
                                   styles: List[str], reasons: List[str],
                                   price_range: str = "") -> int:
        """保存穿搭推荐"""
        sql = """
            INSERT INTO outfit_recommendations 
            (session_id, category, items, colors, styles, reasons, price_range)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        cursor = self.db.execute(sql, (
            session_id, category, items, colors, styles, reasons, price_range
        ))
        return cursor.fetchone()[0]
    
    def get_outfit_recommendations(self, session_id: str) -> List[Dict]:
        """获取穿搭推荐列表"""
        sql = "SELECT * FROM outfit_recommendations WHERE session_id = %s ORDER BY category"
        rows = self.db.fetch_all(sql, (session_id,))
        results = []
        for row in rows:
            results.append({
                "id": row[0], "session_id": row[1], "category": row[2],
                "items": row[3], "colors": row[4], "styles": row[5],
                "reasons": row[6], "price_range": row[7], "created_at": row[8]
            })
        return results
    
    # ========== Semantic Vectors ==========
    def save_vector(self, session_id: str, content: str, 
                   embedding: List[float], metadata: Dict = None) -> int:
        """保存语义向量"""
        sql = """
            INSERT INTO semantic_vectors (session_id, content, embedding, metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        # pgvector 需要数组格式
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        cursor = self.db.execute(sql, (session_id, content, vec_str, json.dumps(metadata or {})))
        return cursor.fetchone()[0]
    
    def search_similar(self, embedding: List[float], session_id: str = None, 
                      limit: int = 5) -> List[Dict]:
        """向量相似度搜索"""
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
            results.append({
                "id": row[0], "session_id": row[1], "content": row[2],
                "embedding": row[3], "metadata": row[4], "created_at": row[5]
            })
        return results
    
    def close(self):
        self.db.close()


# 全局存储实例
_storage: Optional[StorageLayer] = None

def get_storage() -> StorageLayer:
    """获取存储实例"""
    global _storage
    if _storage is None:
        _storage = StorageLayer()
    return _storage
