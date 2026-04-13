"""Thread service — CRUD + MAS integration for agent chat."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
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


async def send_message_stream(thread_id: UUID, content: str) -> AsyncGenerator[str, None]:
    """Send a user message, stream MAS response as SSE events, save when done."""
    from server.services.simulation_service import insert_submitted_placeholder

    # 1. Save user message
    user_msg = await db.fetch_one(
        """INSERT INTO thread_messages (thread_id, role, content)
           VALUES ($1, 'user', $2)
           RETURNING *""",
        thread_id, content,
    )
    yield f"data: {json.dumps({'type': 'user_message', 'message': _msg_dict(user_msg)}, default=str)}\n\n"

    # 2. Fetch full thread history for MAS context
    messages = await db.fetch_all(
        "SELECT role, content FROM thread_messages WHERE thread_id = $1 ORDER BY created_at ASC",
        thread_id,
    )
    mas_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    # 3. Stream from MAS — handle structured events
    full_content = ""
    triggered_hashes: set[str] = set()  # dedup simulation triggers

    try:
        mas_client = get_mas_client()
        async for event in mas_client.invoke_stream(mas_messages):
            if event["type"] == "text_delta":
                full_content += event["content"]
                yield f"data: {json.dumps({'type': 'delta', 'content': event['content']})}\n\n"

            elif event["type"] == "tool_call" and event.get("agent_name") == "simulation_trigger":
                # MAS is calling the simulation_trigger sub-agent
                args = event.get("arguments", {})
                sim_type = args.get("p_simulation_type", "")
                params_str = args.get("p_parameters", "{}")
                try:
                    params = json.loads(params_str) if isinstance(params_str, str) else (params_str or {})
                except json.JSONDecodeError:
                    params = {}
                num_sims = int(args.get("p_num_simulations", 10000))
                seed = int(args.get("p_seed", 42))

                dedup_key = f"{sim_type}|{json.dumps(params, sort_keys=True)}|{seed}|{num_sims}"
                if dedup_key not in triggered_hashes:
                    triggered_hashes.add(dedup_key)
                    try:
                        placeholder = await insert_submitted_placeholder(
                            sim_type, params, num_sims, seed,
                        )
                        yield f"data: {json.dumps({'type': 'simulation_triggered', 'simulation': placeholder})}\n\n"
                    except Exception:
                        logger.warning("Failed to insert placeholder from stream", exc_info=True)

    except Exception as e:
        logger.exception("MAS streaming invocation failed")
        full_content = f"I encountered an error: {e}"
        yield f"data: {json.dumps({'type': 'delta', 'content': full_content})}\n\n"

    # Text fallback: scan accumulated content for trigger results
    for sse_event in await _extract_triggers_from_text(full_content, triggered_hashes):
        yield sse_event

    if not full_content.strip():
        full_content = "No response from agent."
        yield f"data: {json.dumps({'type': 'delta', 'content': full_content})}\n\n"

    # 4. Save final assistant message
    assistant_msg = await db.fetch_one(
        """INSERT INTO thread_messages (thread_id, role, content)
           VALUES ($1, 'assistant', $2)
           RETURNING *""",
        thread_id, full_content,
    )
    await db.execute(
        "UPDATE agent_threads SET updated_at = NOW() WHERE id = $1",
        thread_id,
    )

    yield f"data: {json.dumps({'type': 'done', 'message': _msg_dict(assistant_msg)}, default=str)}\n\n"


async def _extract_triggers_from_text(
    text: str, already_triggered: set[str],
) -> list[str]:
    """Text-based fallback: scan MAS response for trigger_simulation results.

    The MAS agent often includes the UC function result JSON inline, e.g.:
    {"status":"triggered","simulation_type":"cost_comparison",...}
    """
    from server.services.simulation_service import insert_submitted_placeholder

    sse_events: list[str] = []
    for match in re.finditer(r'\{[^{}]*"status"\s*:\s*"triggered"[^{}]*\}', text):
        try:
            blob = json.loads(match.group())
        except json.JSONDecodeError:
            continue

        sim_type = blob.get("simulation_type", "")
        if not sim_type:
            continue
        params_str = blob.get("parameters", "{}")
        try:
            params = json.loads(params_str) if isinstance(params_str, str) else (params_str or {})
        except json.JSONDecodeError:
            params = {}
        num_sims = int(blob.get("num_simulations", 10000))
        seed = int(blob.get("seed", 42))

        dedup_key = f"{sim_type}|{json.dumps(params, sort_keys=True)}|{seed}|{num_sims}"
        if dedup_key in already_triggered:
            continue
        already_triggered.add(dedup_key)

        try:
            job_resp = blob.get("job_response", {})
            if isinstance(job_resp, str):
                try:
                    job_resp = json.loads(job_resp)
                except (json.JSONDecodeError, TypeError):
                    job_resp = {}
            job_run_id = str(job_resp.get("run_id", "")) if isinstance(job_resp, dict) else ""

            placeholder = await insert_submitted_placeholder(
                sim_type, params, num_sims, seed, job_run_id=job_run_id,
            )
            sse_events.append(
                f"data: {json.dumps({'type': 'simulation_triggered', 'simulation': placeholder})}\n\n"
            )
        except Exception:
            logger.warning("Failed to insert placeholder from text fallback", exc_info=True)

    return sse_events


def _msg_dict(row) -> dict:
    """Convert a DB row to a JSON-safe dict."""
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif isinstance(v, UUID):
            d[k] = str(v)
    return d
