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

        Handles long-running task continuation: when the MAS emits a
        ``task_continue_request``, the client automatically sends a resume
        request so the agent can keep polling sub-agents until completion.

        Yields dicts with a ``type`` field:
        - ``{"type": "text_delta", "content": ".."}`` — text chunk for display
        - ``{"type": "tool_call", "agent_name": "..", "arguments": {..}}`` — sub-agent invocation
        - ``{"type": "tool_result", "agent_name": "..", "output": ".."}`` — tool return value
        """
        MAX_CONTINUATIONS = 20  # safety limit
        current_input = list(messages)
        last_step = None
        pending_calls: dict[str, dict] = {}

        for continuation in range(MAX_CONTINUATIONS + 1):
            payload = {
                "input": current_input,
                "databricks_options": {"long_task": True},
                "stream": True,
            }
            if custom_inputs:
                payload["custom_inputs"] = custom_inputs

            client = self._get_client()
            host = client.config.host.rstrip("/")
            endpoint_name = self._settings.mas_endpoint_name
            url = f"{host}/serving-endpoints/{endpoint_name}/invocations"
            headers = client.config.authenticate()
            headers["Content-Type"] = "application/json"

            if continuation == 0:
                logger.info("Invoking MAS endpoint (stream)")
            else:
                logger.info("Resuming MAS long-running task (continuation %d)", continuation)

            continue_request = None

            async with httpx.AsyncClient() as http:
                async with http.stream(
                    "POST", url, json=payload, headers=headers, timeout=600,
                ) as resp:
                    resp.raise_for_status()
                    line_count = 0
                    event_count = 0
                    async for line in resp.aiter_lines():
                        line_count += 1
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            logger.info(
                                "MAS stream [DONE] after %d lines, %d events",
                                line_count, event_count,
                            )
                            break
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.warning("MAS stream: bad JSON on line %d: %s", line_count, data_str[:200])
                            continue

                        event_count += 1
                        event_type = event.get("type", "")
                        if event_count <= 3 or event_count % 20 == 0:
                            logger.info("MAS event #%d: type=%s", event_count, event_type)

                        # --- Text delta ---
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

                        # --- Output item done ---
                        elif event_type == "response.output_item.done":
                            item = event.get("item", {})
                            item_type = item.get("type", "")
                            call_id = item.get("call_id", "")

                            # Long-running task continuation checkpoint
                            if item_type == "task_continue_request":
                                continue_request = item
                                logger.info(
                                    "MAS requested task continuation (id=%s, step=%s)",
                                    item.get("id"), item.get("step"),
                                )
                                break  # exit line loop to resume

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

            logger.info(
                "MAS stream ended (continuation=%d, lines=%d, events=%d, continue_requested=%s)",
                continuation, line_count, event_count, continue_request is not None,
            )

            # If no continuation requested, we're done
            if not continue_request:
                break

            # Build resume input: original messages + continue_request + continue_response
            continue_id = continue_request.get("id", "")
            current_input = list(messages) + [
                continue_request,
                {
                    "type": "task_continue_response",
                    "continue_request_id": continue_id,
                },
            ]

        if continue_request:
            logger.warning("MAS hit max continuations (%d) — task may be incomplete", MAX_CONTINUATIONS)


_mas_client: MASClient | None = None


def get_mas_client() -> MASClient:
    global _mas_client
    if _mas_client is None:
        _mas_client = MASClient()
    return _mas_client
