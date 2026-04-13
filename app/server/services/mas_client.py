"""MAS (Multi-Agent Supervisor) HTTP client.

Calls the Databricks serving endpoint for the MAS agent.
Uses the Agent API format (input/output) rather than chat completions (messages/choices).
Supports both synchronous (invoke) and async streaming (invoke_stream) modes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx
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

    def _build_request(self, messages: list[dict], custom_inputs: dict | None = None, stream: bool = False):
        """Build the URL, headers, and payload for the MAS endpoint."""
        client = self._get_client()
        endpoint_name = self._settings.mas_endpoint_name

        payload: dict = {
            "input": messages,
            "databricks_options": {"long_task": True},
        }
        if stream:
            payload["stream"] = True
        if custom_inputs:
            payload["custom_inputs"] = custom_inputs

        host = client.config.host.rstrip("/")
        url = f"{host}/serving-endpoints/{endpoint_name}/invocations"
        headers = client.config.authenticate()
        headers["Content-Type"] = "application/json"

        return url, headers, payload

    def invoke(self, messages: list[dict], custom_inputs: dict | None = None) -> dict:
        """Send messages to the MAS and return the full response (blocking)."""
        url, headers, payload = self._build_request(messages, custom_inputs)

        logger.info("Invoking MAS endpoint (sync)")
        resp = httpx.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output", [])
        content = ""
        for item in reversed(output):
            if item.get("type") == "message" and item.get("role") == "assistant":
                parts = item.get("content", [])
                if isinstance(parts, list):
                    content = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict))
                elif isinstance(parts, str):
                    content = parts
                break

        return {"content": content or "No response from agent."}

    async def invoke_stream(
        self, messages: list[dict], custom_inputs: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream structured events from the MAS endpoint.

        Yields dicts with a ``type`` field:
        - ``{"type": "text_delta", "content": ".."}`` — text chunk for display
        - ``{"type": "tool_call", "agent_name": "..", "arguments": {..}}`` — sub-agent invocation
        - ``{"type": "tool_result", "agent_name": "..", "output": ".."}`` — tool return value
        """
        url, headers, payload = self._build_request(messages, custom_inputs, stream=True)

        logger.info("Invoking MAS endpoint (stream)")
        last_step = None
        pending_calls: dict[str, dict] = {}  # call_id -> {agent_name}

        async with httpx.AsyncClient() as http:
            async with http.stream("POST", url, json=payload, headers=headers, timeout=180) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    # --- Text delta (existing behavior) ---
                    if event_type == "response.output_text.delta":
                        step = event.get("step")
                        if last_step is not None and step != last_step:
                            yield {"type": "text_delta", "content": "\n\n"}
                        last_step = step
                        yield {"type": "text_delta", "content": event.get("delta", "")}

                    # --- Function call arguments complete ---
                    elif event_type == "response.function_call_arguments.done":
                        call_id = event.get("call_id", "")
                        agent_name = event.get("name", "")
                        try:
                            arguments = json.loads(event.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}
                        pending_calls[call_id] = {"agent_name": agent_name}
                        yield {
                            "type": "tool_call",
                            "agent_name": agent_name,
                            "arguments": arguments,
                            "call_id": call_id,
                        }

                    # --- Output item done (function_call or function_call_output) ---
                    elif event_type == "response.output_item.done":
                        item = event.get("item", {})
                        item_type = item.get("type", "")
                        call_id = item.get("call_id", "")

                        if item_type == "function_call" and call_id not in pending_calls:
                            agent_name = item.get("name", "")
                            try:
                                arguments = json.loads(item.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                arguments = {}
                            pending_calls[call_id] = {"agent_name": agent_name}
                            yield {
                                "type": "tool_call",
                                "agent_name": agent_name,
                                "arguments": arguments,
                                "call_id": call_id,
                            }

                        elif item_type == "function_call_output":
                            info = pending_calls.get(call_id, {})
                            yield {
                                "type": "tool_result",
                                "agent_name": info.get("agent_name", ""),
                                "output": item.get("output", ""),
                                "call_id": call_id,
                            }


_mas_client: MASClient | None = None


def get_mas_client() -> MASClient:
    global _mas_client
    if _mas_client is None:
        _mas_client = MASClient()
    return _mas_client
