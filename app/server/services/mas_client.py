"""MAS (Multi-Agent Supervisor) HTTP client.

Calls the Databricks serving endpoint for the MAS agent.
"""

from __future__ import annotations

import json
import logging

from databricks.sdk import WorkspaceClient

from server.config import Settings, get_settings

logger = logging.getLogger(__name__)


class MASClient:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client: WorkspaceClient | None = None

    def _get_client(self) -> WorkspaceClient:
        if self._client is None:
            if self._settings.is_databricks_app:
                self._client = WorkspaceClient()
            else:
                self._client = WorkspaceClient(profile=self._settings.databricks_profile)
        return self._client

    def invoke(self, messages: list[dict], custom_inputs: dict | None = None) -> dict:
        """Send messages to the MAS serving endpoint.

        Parameters
        ----------
        messages : list[dict]
            Chat messages in {"role": "...", "content": "..."} format.
        custom_inputs : dict, optional
            Additional inputs for the agent.

        Returns
        -------
        dict
            Parsed response with 'content' key containing assistant message.
        """
        client = self._get_client()
        endpoint_name = self._settings.mas_endpoint_name

        payload = {
            "messages": messages,
            "databricks_options": {"long_task": True},
        }
        if custom_inputs:
            payload["custom_inputs"] = custom_inputs

        logger.info(f"Invoking MAS endpoint: {endpoint_name}")

        # Use the serving endpoints API
        response = client.serving_endpoints.query(
            name=endpoint_name,
            messages=messages,
            extra_params={"databricks_options": {"long_task": True}},
        )

        # Extract assistant content from response
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            content = choice.message.content if choice.message else ""
            return {"content": content}

        return {"content": "No response from agent."}


_mas_client: MASClient | None = None


def get_mas_client() -> MASClient:
    global _mas_client
    if _mas_client is None:
        _mas_client = MASClient()
    return _mas_client
