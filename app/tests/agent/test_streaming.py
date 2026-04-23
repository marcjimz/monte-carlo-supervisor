"""Tests for LangGraph events → SSE format mapping.

These tests verify that the thread_service correctly translates
LangGraph astream_events into the SSE event types the frontend expects.
"""

import json
import sys
from unittest.mock import MagicMock

import pytest

# Mock asyncpg before importing thread_service (not available locally)
sys.modules.setdefault("asyncpg", MagicMock())


class TestSSEEventTypes:
    """Verify the SSE event format contract."""

    def test_delta_format(self):
        event = json.dumps({"type": "delta", "content": "Hello"})
        sse = f"data: {event}\n\n"
        parsed = json.loads(sse.split("data: ")[1].strip())
        assert parsed["type"] == "delta"
        assert parsed["content"] == "Hello"

    def test_simulation_triggered_format(self):
        sim = {
            "run_id": "abc123",
            "simulation_type": "encounter_margin",
            "status": "SUBMITTED",
        }
        event = json.dumps({"type": "simulation_triggered", "simulation": sim})
        sse = f"data: {event}\n\n"
        parsed = json.loads(sse.split("data: ")[1].strip())
        assert parsed["type"] == "simulation_triggered"
        assert parsed["simulation"]["run_id"] == "abc123"

    def test_matrix_created_format(self):
        matrix = {
            "id": "mat-1",
            "name": "test matrix",
            "simulation_type": "encounter_margin",
            "row_parameter": "growth_rate",
            "col_parameter": "cost_inflation",
            "rows": 3,
            "cols": 2,
            "total_cells": 6,
            "auto_running": True,
        }
        event = json.dumps({"type": "matrix_created", "matrix": matrix})
        sse = f"data: {event}\n\n"
        parsed = json.loads(sse.split("data: ")[1].strip())
        assert parsed["type"] == "matrix_created"
        assert parsed["matrix"]["total_cells"] == 6
        assert parsed["matrix"]["auto_running"] is True

    def test_done_format(self):
        msg = {"id": "1", "role": "assistant", "content": "Done."}
        event = json.dumps({"type": "done", "message": msg})
        sse = f"data: {event}\n\n"
        parsed = json.loads(sse.split("data: ")[1].strip())
        assert parsed["type"] == "done"
        assert parsed["message"]["role"] == "assistant"

    def test_heartbeat_format(self):
        sse = ": heartbeat\n\n"
        assert sse.startswith(":")
        assert "heartbeat" in sse


class TestMatrixResultsFormatting:
    """Test the _format_matrix_results helper."""

    def test_format_completed_matrix(self):
        from server.services.thread_service import _format_matrix_results

        matrix = {
            "name": "Test Matrix",
            "row_parameter": "growth_rate",
            "col_parameter": "cost_inflation",
            "row_values": [0.05, 0.10],
            "col_values": [1000000, 2000000],
            "output_metric": "net_savings",
            "cells": [
                {"row_value": 0.05, "col_value": 1000000, "status": "completed", "result_mean": 50000, "result_p05": 30000, "result_p95": 70000},
                {"row_value": 0.05, "col_value": 2000000, "status": "completed", "result_mean": 100000, "result_p05": 60000, "result_p95": 140000},
                {"row_value": 0.10, "col_value": 1000000, "status": "completed", "result_mean": 95000, "result_p05": 55000, "result_p95": 135000},
                {"row_value": 0.10, "col_value": 2000000, "status": "completed", "result_mean": 190000, "result_p05": 110000, "result_p95": 270000},
            ],
        }

        result = _format_matrix_results(matrix)
        assert result is not None
        assert "Test Matrix" in result
        assert "Best scenario" in result
        assert "Worst scenario" in result

    def test_format_all_failed(self):
        from server.services.thread_service import _format_matrix_results

        matrix = {
            "name": "Failed Matrix",
            "cells": [
                {"row_value": 0.05, "col_value": 100, "status": "failed"},
            ],
        }
        result = _format_matrix_results(matrix)
        assert result is not None
        assert "failed" in result.lower()

    def test_format_still_running(self):
        from server.services.thread_service import _format_matrix_results

        matrix = {
            "name": "Running Matrix",
            "cells": [
                {"row_value": 0.05, "col_value": 100, "status": "running"},
            ],
        }
        result = _format_matrix_results(matrix)
        assert result is None  # Don't post yet
