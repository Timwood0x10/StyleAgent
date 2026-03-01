"""
Tests for config module
"""

import os
import pytest
from src.utils.config import Config


class TestConfig:
    """Test configuration module"""

    def test_config_shared_state(self):
        """Test that config instances share state"""
        config1 = Config()
        config2 = Config()
        # Both instances should share the same yaml config
        assert config1._yaml_config == config2._yaml_config

    def test_config_loads_from_yaml(self):
        """Test that config loads from yaml"""
        config = Config()
        # Check that basic config is loaded
        assert config.ENVIRONMENT is not None

    def test_pg_host_default(self):
        """Test default PG_HOST"""
        config = Config()
        # Should have a default value
        assert config.PG_HOST is not None
        assert isinstance(config.PG_HOST, str)

    def test_llm_config(self):
        """Test LLM configuration"""
        config = Config()
        assert config.LLM_PROVIDER is not None
        assert config.LLM_BASE_URL is not None
        assert config.LLM_MODEL is not None

    def test_log_level_default(self):
        """Test default log level"""
        config = Config()
        assert config.LOG_LEVEL is not None
