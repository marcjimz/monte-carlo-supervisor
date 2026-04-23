"""Tests for prompt generation."""

from server.agent.config import AgentConfig
from server.agent.prompts import ROUTING_INSTRUCTIONS, TOOL_GUIDE, get_system_prompt


class TestRoutingInstructions:
    def test_contains_routing_rules(self):
        assert "query_analytics" in ROUTING_INSTRUCTIONS
        assert "check_simulation" in ROUTING_INSTRUCTIONS
        assert "trigger_simulation" in ROUTING_INSTRUCTIONS
        assert "create_matrix" in ROUTING_INSTRUCTIONS
        assert "list_distributions" in ROUTING_INSTRUCTIONS

    def test_simulation_workflow(self):
        assert "SIMULATION WORKFLOW" in ROUTING_INSTRUCTIONS
        assert "check → trigger → poll" in ROUTING_INSTRUCTIONS
        assert "not_found" in ROUTING_INSTRUCTIONS

    def test_matrix_workflow(self):
        assert "MATRIX WORKFLOW" in ROUTING_INSTRUCTIONS
        assert "parameter sweep" in ROUTING_INSTRUCTIONS


class TestToolGuide:
    def test_lists_all_tools(self):
        assert "check_simulation" in TOOL_GUIDE
        assert "trigger_simulation" in TOOL_GUIDE
        assert "create_matrix" in TOOL_GUIDE
        assert "list_distributions" in TOOL_GUIDE
        assert "query_analytics" in TOOL_GUIDE


class TestGetSystemPrompt:
    def test_includes_persona(self):
        config = AgentConfig()
        prompt = get_system_prompt(config)
        assert "Women's Health" in prompt

    def test_includes_routing(self):
        config = AgentConfig()
        prompt = get_system_prompt(config)
        assert "SIMULATION WORKFLOW" in prompt
        assert "MATRIX WORKFLOW" in prompt

    def test_includes_tool_guide(self):
        config = AgentConfig()
        prompt = get_system_prompt(config)
        assert "Available tools:" in prompt

    def test_custom_persona(self):
        config = AgentConfig(prompt={"persona": "You are a test agent."})
        prompt = get_system_prompt(config)
        assert prompt.startswith("You are a test agent.")
        # Still includes routing
        assert "SIMULATION WORKFLOW" in prompt
