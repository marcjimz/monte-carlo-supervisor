"""Tests for GenieClient."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from server.agent.config import GenieConfig
from server.agent.genie import GenieClient


def _make_response(status_code: int, json_data: dict) -> httpx.Response:
    """Create an httpx.Response with a request set (needed for raise_for_status)."""
    resp = httpx.Response(
        status_code,
        json=json_data,
        request=httpx.Request("GET", "https://test.databricks.com/api"),
    )
    return resp


@pytest.fixture
def genie_client():
    return GenieClient(
        space_id="test-space-123",
        databricks_host="https://test.databricks.com",
        auth_headers={"Authorization": "Bearer test-token"},
        config=GenieConfig(
            space_id="test-space-123",
            poll_interval_seconds=0.01,  # fast for tests
            poll_max_seconds=0.1,
            max_retries=2,
        ),
    )


class TestGenieClientInit:
    def test_url_construction(self, genie_client):
        url = genie_client._url("start-conversation")
        assert url == "https://test.databricks.com/api/2.0/genie/spaces/test-space-123/start-conversation"

    def test_strips_trailing_slash(self):
        client = GenieClient(
            space_id="s1",
            databricks_host="https://host.com/",
            auth_headers={},
        )
        assert client.host == "https://host.com"


class TestStartConversation:
    @pytest.mark.asyncio
    async def test_sends_question(self, genie_client):
        mock_response = _make_response(200, {"conversation_id": "conv-1", "message_id": "msg-1"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await genie_client.start_conversation("What is the cost?")
            assert result["conversation_id"] == "conv-1"
            assert result["message_id"] == "msg-1"


class TestPollMessage:
    @pytest.mark.asyncio
    async def test_returns_completed(self, genie_client):
        mock_response = _make_response(200, {"status": "COMPLETED", "attachments": []})
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await genie_client.poll_message("conv-1", "msg-1")
            assert result["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_timeout(self, genie_client):
        mock_response = _make_response(200, {"status": "EXECUTING_QUERY"})
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await genie_client.poll_message("conv-1", "msg-1")
            assert result["status"] == "TIMEOUT"


class TestAsk:
    @pytest.mark.asyncio
    async def test_full_workflow_completed(self, genie_client):
        start_resp = _make_response(200, {"conversation_id": "conv-1", "message_id": "msg-1"})
        poll_resp = _make_response(200, {
            "status": "COMPLETED",
            "attachments": [
                {"type": "TEXT", "text": {"content": "The average cost is $500."}},
            ],
        })
        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=start_resp),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=poll_resp),
        ):
            result = await genie_client.ask("What is the average cost?")
            assert result["status"] == "completed"
            assert "500" in result["answer"]

    @pytest.mark.asyncio
    async def test_no_conversation_id(self, genie_client):
        start_resp = _make_response(200, {})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=start_resp):
            result = await genie_client.ask("test")
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_completed_with_query_result(self, genie_client):
        start_resp = _make_response(200, {"conversation_id": "conv-1", "message_id": "msg-1"})
        poll_resp = _make_response(200, {
            "status": "COMPLETED",
            "attachments": [
                {"type": "TEXT", "text": {"content": "Here are the results."}},
                {"type": "QUERY", "query": {"query": "SELECT * FROM costs"}},
            ],
        })
        qr_resp = _make_response(200, {
            "statement_response": {
                "manifest": {
                    "schema": {
                        "columns": [{"name": "dept"}, {"name": "cost"}],
                    },
                },
                "result": {
                    "data_array": [["OB/GYN", "500"], ["Cardio", "700"]],
                },
            },
        })

        async def mock_get(url, **kwargs):
            if "query-result" in str(url):
                return qr_resp
            return poll_resp

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=start_resp),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get),
        ):
            result = await genie_client.ask("Show me costs by department")
            assert result["status"] == "completed"
            assert result["columns"] == ["dept", "cost"]
            assert len(result["data"]) == 2
            assert result["sql"] == "SELECT * FROM costs"
