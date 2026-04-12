"""Thread service — CRUD + MAS integration for agent chat."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from server import db
from server.services.mas_client import get_mas_client

logger = logging.getLogger(__name__)


async def create_thread(analysis_id: UUID, owner_email: str, title: str, icon: str) -> dict:
    return await db.fetch_one(
        """INSERT INTO agent_threads (analysis_id, owner_email, title, icon)
           VALUES ($1, $2, $3, $4)
           RETURNING *""",
        analysis_id, owner_email, title, icon,
    )


async def list_threads(analysis_id: UUID) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM agent_threads WHERE analysis_id = $1 ORDER BY updated_at DESC",
        analysis_id,
    )


async def get_thread(thread_id: UUID) -> dict | None:
    thread = await db.fetch_one(
        "SELECT * FROM agent_threads WHERE id = $1",
        thread_id,
    )
    if not thread:
        return None

    messages = await db.fetch_all(
        "SELECT * FROM thread_messages WHERE thread_id = $1 ORDER BY created_at ASC",
        thread_id,
    )
    result = dict(thread)
    result["messages"] = [dict(m) for m in messages]
    return result


async def update_thread(thread_id: UUID, title: str | None, icon: str | None) -> dict | None:
    fields = []
    args = []
    idx = 1

    if title is not None:
        fields.append(f"title = ${idx}")
        args.append(title)
        idx += 1
    if icon is not None:
        fields.append(f"icon = ${idx}")
        args.append(icon)
        idx += 1

    if not fields:
        return await get_thread(thread_id)

    fields.append("updated_at = NOW()")
    args.append(thread_id)

    return await db.fetch_one(
        f"UPDATE agent_threads SET {', '.join(fields)} WHERE id = ${idx} RETURNING *",
        *args,
    )


async def delete_thread(thread_id: UUID) -> bool:
    result = await db.execute(
        "DELETE FROM agent_threads WHERE id = $1",
        thread_id,
    )
    return result != "DELETE 0"


async def send_message(thread_id: UUID, content: str) -> dict:
    """Send a user message, invoke MAS, and return both messages."""
    # 1. Save user message
    user_msg = await db.fetch_one(
        """INSERT INTO thread_messages (thread_id, role, content)
           VALUES ($1, 'user', $2)
           RETURNING *""",
        thread_id, content,
    )

    # 2. Fetch full thread history
    messages = await db.fetch_all(
        "SELECT role, content FROM thread_messages WHERE thread_id = $1 ORDER BY created_at ASC",
        thread_id,
    )

    # 3. Build messages array for MAS
    mas_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    # 4. Call MAS
    try:
        mas_client = get_mas_client()
        response = mas_client.invoke(mas_messages)
        assistant_content = response.get("content", "I encountered an error processing your request.")
    except Exception as e:
        logger.exception("MAS invocation failed")
        assistant_content = f"I encountered an error: {str(e)}"

    # 5. Save assistant response
    assistant_msg = await db.fetch_one(
        """INSERT INTO thread_messages (thread_id, role, content)
           VALUES ($1, 'assistant', $2)
           RETURNING *""",
        thread_id, assistant_content,
    )

    # 6. Update thread timestamp
    await db.execute(
        "UPDATE agent_threads SET updated_at = NOW() WHERE id = $1",
        thread_id,
    )

    return {
        "user_message": dict(user_msg),
        "assistant_message": dict(assistant_msg),
    }
