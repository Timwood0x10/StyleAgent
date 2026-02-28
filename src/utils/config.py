"""
Configuration Management - Load from config.yaml and .env
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# Load .env file for sensitive data
load_dotenv()


class Config:
    """Configuration class - loads from yaml with .env overrides"""

    _yaml_config: Dict[str, Any] = {}
    _loaded: bool = False

    def __init__(self):
        self._load_yaml()

    def _load_yaml(self):
        """Load configuration from yaml file"""
        if Config._loaded:
            return

        # Find config.yaml in project root
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config.yaml"

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                Config._yaml_config = yaml.safe_load(f) or {}
        Config._loaded = True

    def _get(self, key: str, default: Any = None, env_key: str = None) -> Any:
        """Get config value - yaml first, then .env, then default"""
        # Try .env first for sensitive data
        if env_key:
            env_val = os.getenv(env_key)
            if env_val is not None:
                return env_val

        # Try yaml
        keys = key.split(".")
        value = Config._yaml_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                break
        if value is not None:
            return value

        return default

    # ==================== Database ====================
    @property
    def PG_HOST(self) -> str:
        return self._get("database.host", "localhost", "PG_HOST")

    @property
    def PG_PORT(self) -> int:
        return int(self._get("database.port", 5432))

    @property
    def PG_DATABASE(self) -> str:
        return self._get("database.name", "user", "PG_DATABASE")

    @property
    def PG_USER(self) -> str:
        return self._get("database.user", "postgres", "PG_USER")

    @property
    def PG_PASSWORD(self) -> str:
        return os.getenv("PG_PASSWORD", "")

    @property
    def PG_POOL_SIZE(self) -> int:
        return int(self._get("database.pool_size", 10))

    @property
    def PG_TIMEOUT(self) -> int:
        return int(self._get("database.timeout", 30))

    # ==================== LLM ====================
    @property
    def LLM_PROVIDER(self) -> str:
        return self._get("llm.provider", "local")

    @property
    def LLM_BASE_URL(self) -> str:
        return self._get("llm.base_url", "http://localhost:11434/v1", "LLM_BASE_URL")

    @property
    def LLM_API_KEY(self) -> str:
        return self._get("llm.api_key", "not-needed", "LLM_API_KEY")

    @property
    def LLM_MODEL(self) -> str:
        return self._get("llm.model", "gpt-oss:20b", "LLM_MODEL")

    @property
    def LLM_TEMPERATURE(self) -> float:
        return float(self._get("llm.temperature", 0.7))

    @property
    def LLM_MAX_TOKENS(self) -> int:
        return int(self._get("llm.max_tokens", 2048))

    @property
    def LLM_TIMEOUT(self) -> int:
        return int(self._get("llm.timeout", 60))

    # ==================== AHP ====================
    @property
    def AHP_TOKEN_LIMIT(self) -> int:
        return int(self._get("ahp.token_limit", 500))

    @property
    def AHP_TASK_TIMEOUT(self) -> int:
        return int(self._get("ahp.task_timeout", 60))

    @property
    def AHP_HEARTBEAT_INTERVAL(self) -> int:
        return int(self._get("ahp.heartbeat_interval", 30))

    @property
    def AHP_MAX_RETRIES(self) -> int:
        return int(self._get("ahp.max_retries", 3))

    # ==================== Retry ====================
    @property
    def RETRY_MAX_RETRIES(self) -> int:
        return int(self._get("retry.max_retries", 3))

    @property
    def RETRY_INITIAL_DELAY(self) -> float:
        return float(self._get("retry.initial_delay", 1.0))

    @property
    def RETRY_MAX_DELAY(self) -> float:
        return float(self._get("retry.max_delay", 60.0))

    @property
    def RETRY_BACKOFF_FACTOR(self) -> float:
        return float(self._get("retry.backoff_factor", 2.0))

    # ==================== Logging ====================
    @property
    def LOG_LEVEL(self) -> str:
        return self._get("logging.level", "INFO")

    @property
    def LOG_FORMAT(self) -> str:
        return self._get(
            "logging.format",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    @property
    def LOG_FILE(self) -> str:
        return self._get("logging.file", "logs/styleagent.log")

    @property
    def LOG_MAX_BYTES(self) -> int:
        return int(self._get("logging.max_bytes", 10485760))

    @property
    def LOG_BACKUP_COUNT(self) -> int:
        return int(self._get("logging.backup_count", 5))

    # ==================== App ====================
    @property
    def APP_NAME(self) -> str:
        return self._get("app.name", "Style Multi-Agent")

    @property
    def APP_VERSION(self) -> str:
        return self._get("app.version", "1.0.0")

    @property
    def APP_DEBUG(self) -> bool:
        return bool(self._get("app.debug", False))

    @property
    def ENVIRONMENT(self) -> str:
        return self._get("environment", "development")

    # ==================== Agents ====================
    def get_agent_config(self, category: str) -> Dict[str, Any]:
        """Get agent configuration by category"""
        agents = self._yaml_config.get("agents", {})
        return agents.get(category, {})


# Global config instance
config = Config()