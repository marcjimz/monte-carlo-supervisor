"""Tests for agent configuration classes."""

import pytest

from server.agent.config import AgentConfig, GenieConfig, ModelConfig, PromptConfig


class TestModelConfig:
    def test_defaults(self):
        cfg = ModelConfig()
        assert cfg.supervisor_endpoint == "databricks-claude-opus-4-7"
        assert cfg.executor_endpoint == "databricks-claude-sonnet-4"
        assert cfg.supervisor_max_tokens == 4096
        assert cfg.executor_max_tokens == 2048
        assert cfg.supervisor_temperature == 0.3
        assert cfg.executor_temperature == 0.1

    def test_override(self):
        cfg = ModelConfig(
            supervisor_endpoint="custom-opus",
            supervisor_temperature=0.5,
        )
        assert cfg.supervisor_endpoint == "custom-opus"
        assert cfg.supervisor_temperature == 0.5
        # Other defaults unchanged
        assert cfg.executor_endpoint == "databricks-claude-sonnet-4"


class TestGenieConfig:
    def test_defaults(self):
        cfg = GenieConfig()
        assert cfg.space_id == ""
        assert cfg.poll_interval_seconds == 2.0
        assert cfg.poll_max_seconds == 120.0
        assert cfg.max_retries == 3

    def test_with_space_id(self):
        cfg = GenieConfig(space_id="abc123")
        assert cfg.space_id == "abc123"


class TestPromptConfig:
    def test_defaults(self):
        cfg = PromptConfig()
        assert "Women's Health" in cfg.persona
        assert cfg.max_poll_attempts == 10
        assert cfg.auto_trigger_on_not_found is True


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert isinstance(cfg.model, ModelConfig)
        assert isinstance(cfg.genie, GenieConfig)
        assert isinstance(cfg.prompt, PromptConfig)
        assert cfg.catalog == ""
        assert cfg.schema_name == ""

    def test_nested_override(self):
        cfg = AgentConfig(
            model=ModelConfig(supervisor_endpoint="test-model"),
            catalog="my_catalog",
            schema_name="my_schema",
        )
        assert cfg.model.supervisor_endpoint == "test-model"
        assert cfg.catalog == "my_catalog"
        assert cfg.schema_name == "my_schema"
        # Nested defaults still work
        assert cfg.model.executor_endpoint == "databricks-claude-sonnet-4"

    def test_from_dict(self):
        cfg = AgentConfig.model_validate({
            "model": {"supervisor_endpoint": "from-dict"},
            "genie": {"space_id": "space-123"},
            "catalog": "test_catalog",
        })
        assert cfg.model.supervisor_endpoint == "from-dict"
        assert cfg.genie.space_id == "space-123"
        assert cfg.catalog == "test_catalog"
