"""
Configuration Management - Load from .env
"""
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Config:
    """Configuration class"""
    
    # PostgreSQL
    PG_HOST = os.getenv("PG_HOST", "localhost")
    PG_PORT = int(os.getenv("PG_PORT", "5432"))
    PG_DATABASE = os.getenv("PG_DATABASE", "iflow")
    PG_USER = os.getenv("PG_USER", "postgres")
    PG_PASSWORD = os.getenv("PG_PASSWORD", "")
    
    # LLM
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss-20b")


config = Config()