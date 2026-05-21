"""Tests for agent tool definitions."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from server.agent.tools import (
    _POLL_INTERVAL_SECONDS,
    create_matrix,
    get_all_tools,
    list_distributions,
    query_analytics,
    run_simulation,
)

FAKE_ANALYSIS_ID = str(uuid4())
FAKE_MATRIX_ID = uuid4()


@pytest.fixture(autouse=True)
def _mock_simulation_service():
    """Mock simulation_service functions used by tools."""
    from server.services import simulation_service as real_ss

    mock_trigger = AsyncMock(return_value={"status": "submitted", "run_id": "test"})
    mock_check = AsyncMock(return_value={"status": "completed", "results": [{"mean": 42}]})
    with patch.object(real_ss, "trigger_simulation", mock_trigger), \
         patch.object(real_ss, "check_simulation", mock_check):
        mock_module = MagicMock()
        mock_module.trigger_simulation = mock_trigger
        mock_module.check_simulation = mock_check
        yield mock_module


@pytest.fixture(autouse=True)
def _mock_custom_events():
    """Mock adispatch_custom_event — requires LangGraph runtime context."""
    with patch("server.agent.tools.adispatch_custom_event", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def _mock_ensure_config():
    """Mock ensure_config to provide analysis_id for create_matrix."""
    fake_config = {"configurable": {"analysis_id": FAKE_ANALYSIS_ID}}
    with patch("server.agent.tools.ensure_config", return_value=fake_config):
        yield


@pytest.fixture(autouse=True)
def _mock_matrix_service():
    """Mock matrix_service for create_matrix tests."""
    from server.services import matrix_service as real_ms

    mock_create = AsyncMock(return_value={"id": FAKE_MATRIX_ID})
    mock_run = AsyncMock(return_value={"total": 6, "triggered": 6})
    with patch.object(real_ms, "create_matrix", mock_create), \
         patch.object(real_ms, "run_matrix", mock_run):
        mock_module = MagicMock()
        mock_module.create_matrix = mock_create
        mock_module.run_matrix = mock_run
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
    async def test_returns_cached_immediately(self, _mock_simulation_service):
        """Cache hit — trigger returns completed, no polling needed."""
        _mock_simulation_service.trigger_simulation.return_value = {
            "status": "completed",
            "results": [{"mean": 100}],
        }
        result = await run_simulation.ainvoke({
            "simulation_type": "encounter_margin",
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
        _mock_simulation_service.check_simulation.side_effect = [
            {"status": "running", "run_id": "abc123"},
            {"status": "completed", "run_id": "abc123", "results": [{"mean": 42}]},
        ]
        with patch("server.agent.tools._POLL_INTERVAL_SECONDS", 0):
            result = await run_simulation.ainvoke({
                "simulation_type": "encounter_margin",
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
        _mock_simulation_service.check_simulation.return_value = {
            "status": "failed",
            "run_id": "abc123",
            "message": "Simulation failed.",
        }
        _mock_simulation_service.check_simulation.side_effect = None
        with patch("server.agent.tools._POLL_INTERVAL_SECONDS", 0):
            result = await run_simulation.ainvoke({
                "simulation_type": "encounter_margin",
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
            "simulation_type": "encounter_margin",
            "parameters": '{"growth_rate": 0.03}',
            "num_simulations": 5000,
            "seed": 123,
        })
        _mock_simulation_service.trigger_simulation.assert_called_once_with(
            "encounter_margin",
            {"growth_rate": 0.03},
            5000,
            123,
        )


class TestCreateMatrix:
    @pytest.mark.asyncio
    async def test_creates_and_runs_matrix(self, _mock_matrix_service):
        """Tool creates matrix in Lakebase and triggers run."""
        result = await create_matrix.ainvoke({
            "simulation_type": "encounter_margin",
            "row_parameter": "growth_rate",
            "row_values": "[0.01, 0.02, 0.03]",
            "col_parameter": "cost_inflation",
            "col_values": "[0.02, 0.035]",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "created"
        assert parsed["total_cells"] == 6
        assert parsed["id"] == str(FAKE_MATRIX_ID)
        # Verify matrix_service was called
        _mock_matrix_service.create_matrix.assert_called_once()
        _mock_matrix_service.run_matrix.assert_called_once_with(FAKE_MATRIX_ID)

    @pytest.mark.asyncio
    async def test_auto_generates_name(self, _mock_matrix_service):
        result = await create_matrix.ainvoke({
            "simulation_type": "encounter_margin",
            "row_parameter": "growth_rate",
            "row_values": "[0.02]",
            "col_parameter": "cost_inflation",
            "col_values": "[0.035]",
        })
        parsed = json.loads(result)
        assert "growth_rate" in parsed["name"]
        assert "cost_inflation" in parsed["name"]

    @pytest.mark.asyncio
    async def test_returns_error_without_analysis_id(self, _mock_matrix_service):
        """Without analysis context, tool returns an error."""
        with patch("server.agent.tools.ensure_config", return_value={"configurable": {}}):
            result = await create_matrix.ainvoke({
                "simulation_type": "encounter_margin",
                "row_parameter": "x",
                "row_values": "[1]",
                "col_parameter": "y",
                "col_values": "[2]",
            })
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        _mock_matrix_service.create_matrix.assert_not_called()


class TestQueryAnalytics:
    @pytest.mark.asyncio
    async def test_returns_route_marker(self):
        result = await query_analytics.ainvoke({
            "question": "What is the average OB/GYN cost?",
        })
        parsed = json.loads(result)
        assert parsed["route"] == "genie"
        assert parsed["question"] == "What is the average OB/GYN cost?"
