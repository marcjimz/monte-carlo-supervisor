"""GenieClient — async REST API client for Databricks Genie Spaces.

Uses the Genie Conversation API to send natural language questions
and poll for results. Replaces the MAS genie agent type.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from server.agent.config import GenieConfig

logger = logging.getLogger(__name__)


class GenieClient:
    """Async client for Databricks Genie Space conversations."""

    def __init__(
        self,
        space_id: str,
        databricks_host: str,
        auth_headers: dict[str, str],
        config: GenieConfig | None = None,
    ):
        self.space_id = space_id
        self.host = databricks_host.rstrip("/")
        self.auth_headers = auth_headers
        self.config = config or GenieConfig(space_id=space_id)

    def _url(self, path: str) -> str:
        return f"{self.host}/api/2.0/genie/spaces/{self.space_id}/{path}"

    async def start_conversation(self, question: str) -> dict[str, Any]:
        """Start a new Genie conversation and return the initial response."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._url("start-conversation"),
                json={"content": question},
                headers={**self.auth_headers, "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def poll_message(
        self, conversation_id: str, message_id: str,
    ) -> dict[str, Any]:
        """Poll a Genie message until it reaches a terminal state."""
        elapsed = 0.0
        while elapsed < self.config.poll_max_seconds:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._url(f"conversations/{conversation_id}/messages/{message_id}"),
                    headers=self.auth_headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

            status = data.get("status", "")
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                return data

            await asyncio.sleep(self.config.poll_interval_seconds)
            elapsed += self.config.poll_interval_seconds

        return {"status": "TIMEOUT", "error": "Genie query timed out"}

    async def get_query_result(
        self, conversation_id: str, message_id: str,
    ) -> dict[str, Any]:
        """Get the SQL query result for a completed Genie message."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self._url(
                    f"conversations/{conversation_id}/messages/{message_id}/query-result"
                ),
                headers=self.auth_headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def ask(self, question: str) -> dict[str, Any]:
        """Full workflow: start conversation → poll → get results.

        Returns a dict with keys: status, answer, columns, data, sql.
        """
        for attempt in range(self.config.max_retries):
            try:
                # Start conversation
                start_resp = await self.start_conversation(question)
                conversation_id = start_resp.get("conversation_id", "")
                message_id = start_resp.get("message_id", "")

                if not conversation_id or not message_id:
                    return {
                        "status": "error",
                        "answer": "Genie did not return a conversation ID.",
                    }

                # Poll until done
                poll_resp = await self.poll_message(conversation_id, message_id)
                status = poll_resp.get("status", "")

                if status == "COMPLETED":
                    # Extract text reply and query from attachments
                    # Genie API uses key-based attachments (text, query, suggested_questions)
                    attachments = poll_resp.get("attachments", [])
                    text_parts = []
                    query_attachment = None

                    for att in attachments:
                        if "text" in att:
                            text_parts.append(att["text"].get("content", ""))
                        if "query" in att:
                            query_attachment = att

                    answer = "\n".join(text_parts) if text_parts else ""

                    # Try to get query results
                    result_data = {}
                    if query_attachment:
                        query = query_attachment.get("query", {})
                        sql = query.get("query", "")
                        try:
                            qr = await self.get_query_result(
                                conversation_id, message_id,
                            )
                            columns = [
                                col.get("name", "")
                                for col in qr.get("statement_response", {})
                                .get("manifest", {})
                                .get("schema", {})
                                .get("columns", [])
                            ]
                            rows = []
                            for chunk in (
                                qr.get("statement_response", {})
                                .get("result", {})
                                .get("data_array", [])
                            ):
                                rows.append(chunk)
                            result_data = {
                                "columns": columns,
                                "data": rows,
                                "sql": sql,
                            }
                        except Exception:
                            logger.warning(
                                "Failed to fetch query result", exc_info=True,
                            )
                            result_data = {"sql": sql}

                    return {
                        "status": "completed",
                        "answer": answer,
                        **result_data,
                    }

                elif status == "TIMEOUT":
                    return {
                        "status": "timeout",
                        "answer": "The query took too long. Try a simpler question.",
                    }
                else:
                    error_msg = poll_resp.get("error", f"Genie returned status: {status}")
                    if attempt < self.config.max_retries - 1:
                        logger.warning(
                            "Genie attempt %d failed: %s — retrying",
                            attempt + 1, error_msg,
                        )
                        continue
                    return {"status": "error", "answer": error_msg}

            except httpx.HTTPStatusError as e:
                logger.warning("Genie HTTP error: %s", e)
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {"status": "error", "answer": f"Genie API error: {e}"}
            except Exception as e:
                logger.exception("Genie unexpected error")
                return {"status": "error", "answer": f"Unexpected error: {e}"}

        return {"status": "error", "answer": "Max retries exceeded"}
