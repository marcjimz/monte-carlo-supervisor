"""Tests for agent tool definitions."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.agent.tools import (
    create_matrix,
    get_all_tools,
    list_distributions,
    query_analytics,
    run_simulation,
)


@pytest.fixture(autouse=True)
def _mock_simulation_service():
    """Provide a mock simulation_service module for lazy imports."""
    mock_module = MagicMock()
    mock_module.trigger_simulation = AsyncMock(return_value={"status": "submitted", "run_id": "test"})
    with patch.dict(sys.modules, {"server.services.simulation_service": mock_module}):
        # Also patch the import path used by tools.py
        with patch.dict(sys.modules, {"server.services": MagicMock(simulation_service=mock_module)}):
            yield mock_module


class TestGetAllTools:
    def test_returns_four_tools(self):
        tools = get_all_tools()
        assert len(tools) == 4

    def test_tool_names(self):
        tools = get_all_tools()
        names = {t.name for t in tools}
        assert names == {
            "run_simulation",
            "create_matrix",
            "list_distributions",
            "query_analytics",
        }

    def test_all_tools_have_descriptions(self):
        for tool in get_all_tools():
            assert tool.description, f"{tool.name} has no description"


class TestRunSimulation:
    @pytest.mark.asyncio
    async def test_returns_json(self, _mock_simulation_service):
        _mock_simulation_service.trigger_simulation.return_value = {
            "status": "completed",
            "results": [{"mean": 100}],
        }
        result = await run_simulation.ainvoke({
            "simulation_type": "cost_comparison",
            "parameters": "{}",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "completed"

    @pytest.mark.asyncio
    async def test_returns_submitted(self, _mock_simulation_service):
        _mock_simulation_service.trigger_simulation.return_value = {
            "status": "submitted",
            "run_id": "abc123",
        }
        result = await run_simulation.ainvoke({
            "simulation_type": "cost_comparison",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "submitted"
        assert parsed["run_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_parses_parameters(self, _mock_simulation_service):
        await run_simulation.ainvoke({
            "simulation_type": "cost_comparison",
            "parameters": '{"member_count": 30000}',
            "num_simulations": 5000,
            "seed": 123,
        })
        _mock_simulation_service.trigger_simulation.assert_called_once_with(
            "cost_comparison",
            {"member_count": 30000},
            5000,
            123,
        )


class TestCreateMatrix:
    @pytest.mark.asyncio
    async def test_returns_validated(self):
        result = await create_matrix.ainvoke({
            "simulation_type": "cost_comparison",
            "row_parameter": "reduction_pct",
            "row_values": "[0.05, 0.10, 0.15]",
            "col_parameter": "base_cost",
            "col_values": "[500000000, 1000000000]",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "validated"
        assert parsed["total_cells"] == 6
        assert parsed["row_values"] == [0.05, 0.10, 0.15]
        assert parsed["col_values"] == [500000000, 1000000000]

    @pytest.mark.asyncio
    async def test_auto_generates_name(self):
        result = await create_matrix.ainvoke({
            "simulation_type": "cost_comparison",
            "row_parameter": "reduction_pct",
            "row_values": "[0.05]",
            "col_parameter": "base_cost",
            "col_values": "[100]",
        })
        parsed = json.loads(result)
        assert "reduction_pct" in parsed["name"]
        assert "base_cost" in parsed["name"]


class TestQueryAnalytics:
    @pytest.mark.asyncio
    async def test_returns_route_marker(self):
        result = await query_analytics.ainvoke({
            "question": "What is the average OB/GYN cost?",
        })
        parsed = json.loads(result)
        assert parsed["route"] == "genie"
        assert parsed["question"] == "What is the average OB/GYN cost?"
