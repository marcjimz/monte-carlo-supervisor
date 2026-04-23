"""Tests for graph assembly and end-to-end flows."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from server.agent.config import AgentConfig
from server.agent.graph import build_graph


class TestBuildGraph:
    def test_builds_without_error(self):
        graph = build_graph()
        assert graph is not None

    def test_has_expected_nodes(self):
        graph = build_graph()
        node_names = set(graph.get_graph().nodes.keys())
        assert "supervisor" in node_names
        assert "tool_executor" in node_names
        assert "genie" in node_names


class TestGraphEndToEnd:
    @pytest.mark.asyncio
    async def test_direct_response_flow(self):
        """Supervisor responds directly without tool calls → END."""
        mock_model = AsyncMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Hello! I can help with simulations."),
        )

        config = AgentConfig()
        graph = build_graph(agent_config=config, supervisor_model=mock_model)

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Hello")]},
            config={
                "configurable": {
                    "agent_config": config,
                    "supervisor_model": mock_model,
                },
            },
        )
        # Should have user message + assistant response
        assert len(result["messages"]) >= 2
        last_msg = result["messages"][-1]
        assert isinstance(last_msg, AIMessage)
        assert "Hello" in last_msg.content

    @pytest.mark.asyncio
    async def test_tool_call_flow(self):
        """Supervisor calls a tool → executor runs it → supervisor responds."""
        call_count = 0

        async def mock_ainvoke(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: supervisor decides to call create_matrix
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "id": "tc1",
                        "name": "create_matrix",
                        "args": {
                            "simulation_type": "cost_comparison",
                            "row_parameter": "reduction_pct",
                            "row_values": "[0.05, 0.10]",
                            "col_parameter": "base_cost",
                            "col_values": "[100]",
                        },
                    }],
                )
            else:
                # Second call: supervisor synthesizes the result
                return AIMessage(content="Matrix created with 2 cells.")

        mock_model = AsyncMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        mock_model.ainvoke = AsyncMock(side_effect=mock_ainvoke)

        config = AgentConfig()
        graph = build_graph(agent_config=config, supervisor_model=mock_model)

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Create a matrix")]},
            config={
                "configurable": {
                    "agent_config": config,
                    "supervisor_model": mock_model,
                },
            },
        )

        # Verify the flow went through tool execution
        assert call_count == 2
        last_msg = result["messages"][-1]
        assert "Matrix created" in last_msg.content
