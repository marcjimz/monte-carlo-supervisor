"""Tests for graph nodes — supervisor routing and tool execution."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from server.agent.config import AgentConfig
from server.agent.nodes import (
    route_after_genie,
    route_after_supervisor,
    route_after_tools,
    tool_executor_node,
)
from server.agent.state import AgentState


class TestRouteAfterSupervisor:
    def test_routes_to_end_on_plain_text(self):
        state = AgentState(
            messages=[AIMessage(content="Here are your results.")],
        )
        assert route_after_supervisor(state) == "__end__"

    def test_routes_to_tools_on_tool_call(self):
        msg = AIMessage(
            content="",
            tool_calls=[{
                "id": "tc1",
                "name": "run_simulation",
                "args": {"simulation_type": "test"},
            }],
        )
        state = AgentState(messages=[msg])
        assert route_after_supervisor(state) == "tool_executor"

    def test_routes_to_tools_for_analytics(self):
        msg = AIMessage(
            content="",
            tool_calls=[{
                "id": "tc1",
                "name": "query_analytics",
                "args": {"question": "cost?"},
            }],
        )
        state = AgentState(messages=[msg])
        assert route_after_supervisor(state) == "tool_executor"

    def test_routes_to_end_on_non_ai_message(self):
        state = AgentState(
            messages=[HumanMessage(content="hello")],
        )
        assert route_after_supervisor(state) == "__end__"


class TestRouteAfterTools:
    def test_routes_to_genie_when_pending(self):
        state = AgentState(
            messages=[],
            genie_result={"question": "test?", "pending": True},
        )
        assert route_after_tools(state) == "genie"

    def test_routes_to_supervisor_normally(self):
        state = AgentState(messages=[], genie_result=None)
        assert route_after_tools(state) == "supervisor"

    def test_routes_to_supervisor_when_genie_not_pending(self):
        state = AgentState(
            messages=[],
            genie_result={"status": "completed", "answer": "done"},
        )
        assert route_after_tools(state) == "supervisor"


class TestRouteAfterGenie:
    def test_always_routes_to_supervisor(self):
        state = AgentState(
            messages=[],
            genie_result={"status": "completed"},
        )
        assert route_after_genie(state) == "supervisor"


class TestToolExecutorNode:
    @pytest.mark.asyncio
    async def test_executes_tool_call(self):
        tool_call_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": "tc1",
                "name": "create_matrix",
                "args": {
                    "simulation_type": "test",
                    "row_parameter": "p1",
                    "row_values": "[1,2]",
                    "col_parameter": "p2",
                    "col_values": "[3,4]",
                },
            }],
        )
        state = AgentState(messages=[tool_call_msg])
        config = {"configurable": {}}

        result = await tool_executor_node(state, config)
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert isinstance(msg, ToolMessage)
        parsed = json.loads(msg.content)
        assert parsed["status"] == "validated"
        assert parsed["total_cells"] == 4

    @pytest.mark.asyncio
    async def test_handles_unknown_tool(self):
        tool_call_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": "tc1",
                "name": "nonexistent_tool",
                "args": {},
            }],
        )
        state = AgentState(messages=[tool_call_msg])
        config = {"configurable": {}}

        result = await tool_executor_node(state, config)
        assert "Unknown tool" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_genie_routing(self):
        tool_call_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": "tc1",
                "name": "query_analytics",
                "args": {"question": "What is the cost?"},
            }],
        )
        state = AgentState(messages=[tool_call_msg])
        config = {"configurable": {}}

        result = await tool_executor_node(state, config)
        assert result["genie_result"]["pending"] is True
        assert result["genie_result"]["question"] == "What is the cost?"

    @pytest.mark.asyncio
    async def test_no_tool_calls(self):
        state = AgentState(
            messages=[AIMessage(content="Just text")],
        )
        config = {"configurable": {}}

        result = await tool_executor_node(state, config)
        assert result["messages"] == []
