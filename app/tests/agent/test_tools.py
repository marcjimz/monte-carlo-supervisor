"""Tests for agent tool definitions."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.agent.tools import (
    _POLL_INTERVAL_SECONDS,
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
    mock_module.check_simulation = AsyncMock(return_value={"status": "completed", "results": [{"mean": 42}]})
    with patch.dict(sys.modules, {"server.services.simulation_service": mock_module}):
        # Also patch the import path used by tools.py
        with patch.dict(sys.modules, {"server.services": MagicMock(simulation_service=mock_module)}):
            yield mock_module


@pytest.fixture(autouse=True)
def _mock_custom_events():
    """Mock adispatch_custom_event — requires LangGraph runtime context."""
    with patch("server.agent.tools.adispatch_custom_event", new_callable=AsyncMock):
        yield


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
    async def test_returns_cached_immediately(self, _mock_simulation_service):
        """Cache hit — trigger returns completed, no polling needed."""
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
        # Should NOT have called check_simulation (no polling needed)
        _mock_simulation_service.check_simulation.assert_not_called()

    @pytest.mark.asyncio
    async def test_polls_until_completed(self, _mock_simulation_service):
        """Submitted → polls check_simulation → gets completed."""
        _mock_simulation_service.trigger_simulation.return_value = {
            "status": "submitted",
            "run_id": "abc123",
        }
        # First poll: still running, second poll: completed
        _mock_simulation_service.check_simulation = AsyncMock(side_effect=[
            {"status": "running", "run_id": "abc123"},
            {"status": "completed", "run_id": "abc123", "results": [{"mean": 42}]},
        ])
        with patch("server.agent.tools._POLL_INTERVAL_SECONDS", 0):
            result = await run_simulation.ainvoke({
                "simulation_type": "cost_comparison",
            })
        parsed = json.loads(result)
        assert parsed["status"] == "completed"
        assert _mock_simulation_service.check_simulation.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_failed_without_polling(self, _mock_simulation_service):
        """If check returns failed during polling, stop immediately."""
        _mock_simulation_service.trigger_simulation.return_value = {
            "status": "submitted",
            "run_id": "abc123",
        }
        _mock_simulation_service.check_simulation = AsyncMock(return_value={
            "status": "failed",
            "run_id": "abc123",
            "message": "Simulation failed.",
        })
        with patch("server.agent.tools._POLL_INTERVAL_SECONDS", 0):
            result = await run_simulation.ainvoke({
                "simulation_type": "cost_comparison",
            })
        parsed = json.loads(result)
        assert parsed["status"] == "failed"

    @pytest.mark.asyncio
    async def test_parses_parameters(self, _mock_simulation_service):
        _mock_simulation_service.trigger_simulation.return_value = {
            "status": "completed",
            "results": [],
        }
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
