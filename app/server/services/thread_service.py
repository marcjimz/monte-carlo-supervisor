"""Thread service — CRUD + MAS integration for agent chat."""

from __future__ import annotations

import asyncio
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
    """Send a user message, stream MAS response as SSE events, save when done.

    The MAS client handles long-running task continuations internally via the
    Agent API's task_continue_request/task_continue_response protocol.  This
    function simply streams the events to the frontend and keeps the proxy
    connection alive with heartbeats.
    """
    from server.services.simulation_service import insert_submitted_placeholder
    from server.services import analysis_service

    # 0. Resolve analysis_id from thread (needed for linking simulations)
    thread_row = await db.fetch_one(
        "SELECT analysis_id FROM agent_threads WHERE id = $1", thread_id,
    )
    analysis_id = thread_row["analysis_id"] if thread_row else None

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
    created_matrix_ids: set[str] = set()  # dedup matrix creations

    try:
        mas_client = get_mas_client()
        stream = mas_client.invoke_stream(mas_messages)

        # Use heartbeat to keep the SSE connection alive through the
        # Databricks Apps reverse proxy during long MAS continuations.
        while True:
            try:
                event = await asyncio.wait_for(stream.__anext__(), timeout=15)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue

            # Track whether we yield something to the client for this event.
            yielded = False

            if event["type"] == "text_delta":
                full_content += event["content"]
                yield f"data: {json.dumps({'type': 'delta', 'content': event['content']})}\n\n"
                yielded = True

            elif event["type"] == "tool_call" and "trigger_simulation" in event.get("agent_name", ""):
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
                        if analysis_id and placeholder.get("run_id"):
                            try:
                                await analysis_service.link_simulation(
                                    analysis_id, placeholder["run_id"], "agent",
                                )
                            except Exception:
                                logger.warning("Failed to link sim to analysis", exc_info=True)
                        yield f"data: {json.dumps({'type': 'simulation_triggered', 'simulation': placeholder})}\n\n"
                        yielded = True
                    except Exception:
                        logger.warning("Failed to insert placeholder from stream", exc_info=True)

            elif event["type"] == "tool_call" and "create_matrix" in event.get("agent_name", ""):
                sse_event = await _handle_matrix_builder(
                    thread_id, event.get("arguments", {}), created_matrix_ids,
                )
                if sse_event:
                    yield sse_event
                    yielded = True

            # Keep proxy alive during MAS internal polling (e.g. repeated
            # check_simulation calls that we don't forward to the client).
            if not yielded:
                yield ": heartbeat\n\n"

    except Exception as e:
        logger.exception("MAS streaming invocation failed")
        full_content = f"I encountered an error: {e}"
        yield f"data: {json.dumps({'type': 'delta', 'content': full_content})}\n\n"

    # Text fallback: scan accumulated content for trigger results
    for sse_event in await _extract_triggers_from_text(full_content, triggered_hashes, analysis_id):
        yield sse_event

    # Text fallback: scan for validated matrix results
    for sse_event in await _extract_matrices_from_text(
        full_content, thread_id, created_matrix_ids,
    ):
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
    text: str, already_triggered: set[str], analysis_id=None,
) -> list[str]:
    """Text-based fallback: scan MAS response for trigger_simulation results.

    The MAS agent often includes the UC function result JSON inline, e.g.:
    {"status":"triggered","simulation_type":"cost_comparison",...}
    """
    from server.services.simulation_service import insert_submitted_placeholder
    from server.services import analysis_service

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
            # Link to the current analysis
            if analysis_id and placeholder.get("run_id"):
                try:
                    await analysis_service.link_simulation(
                        analysis_id, placeholder["run_id"], "agent",
                    )
                except Exception:
                    logger.warning("Failed to link sim to analysis (text fallback)", exc_info=True)
            sse_events.append(
                f"data: {json.dumps({'type': 'simulation_triggered', 'simulation': placeholder})}\n\n"
            )
        except Exception:
            logger.warning("Failed to insert placeholder from text fallback", exc_info=True)

    return sse_events


async def _handle_matrix_builder(
    thread_id: UUID, args: dict, created_matrix_ids: set[str],
) -> str | None:
    """Intercept a matrix_builder tool_call and create the matrix via Lakebase.

    Returns an SSE event string or None.
    """
    from server.services import matrix_service

    sim_type = args.get("p_simulation_type", "")
    if not sim_type:
        return None

    # Parse row/col values
    try:
        row_values = json.loads(args.get("p_row_values", "[]"))
    except (json.JSONDecodeError, TypeError):
        row_values = []
    try:
        col_values = json.loads(args.get("p_col_values", "[]"))
    except (json.JSONDecodeError, TypeError):
        col_values = []

    if not row_values or not col_values:
        return None

    row_param = args.get("p_row_parameter", "")
    col_param = args.get("p_col_parameter", "")
    if not row_param or not col_param:
        return None

    # Dedup key
    dedup_key = f"{sim_type}|{row_param}|{col_param}|{json.dumps(row_values, sort_keys=True)}|{json.dumps(col_values, sort_keys=True)}"
    if dedup_key in created_matrix_ids:
        return None
    created_matrix_ids.add(dedup_key)

    # Resolve output_metric and group columns from the app's own config.yaml
    output_metric = args.get("p_output_metric") or ""
    output_group_key = None
    output_group_value = None
    try:
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent / "config.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        sim_cfg = cfg.get("simulation_types", {}).get(sim_type, {})
        agg = sim_cfg.get("aggregation", {})
        if not output_metric:
            output_metric = agg.get("value_column", "mean_value")
        output_group_key = agg.get("group_column")
    except Exception:
        logger.debug("Could not resolve agg config for %s", sim_type)
        if not output_metric:
            output_metric = "mean_value"

    # Parse base_parameters
    try:
        base_params = json.loads(args.get("p_base_parameters") or "{}")
    except (json.JSONDecodeError, TypeError):
        base_params = {}

    num_sims = int(args.get("p_num_simulations") or 10000)
    seed = int(args.get("p_seed") or 42)

    # Auto-generate name if not provided
    name = args.get("p_name") or ""
    if not name:
        name = f"{sim_type} — {row_param} vs {col_param}"

    # Look up analysis_id from thread
    thread = await db.fetch_one(
        "SELECT analysis_id FROM agent_threads WHERE id = $1",
        thread_id,
    )
    if not thread:
        logger.warning("Thread %s not found — cannot create matrix", thread_id)
        return None

    analysis_id = thread["analysis_id"]

    logger.info(
        "Creating matrix: sim_type=%s, output_metric=%s, group_key=%s, group_value=%s, "
        "rows=%d, cols=%d, base_params=%s",
        sim_type, output_metric, output_group_key, output_group_value,
        len(row_values), len(col_values), json.dumps(base_params)[:200],
    )

    try:
        matrix = await matrix_service.create_matrix(
            analysis_id=analysis_id,
            name=name,
            simulation_type=sim_type,
            row_parameter=row_param,
            row_values=row_values,
            col_parameter=col_param,
            col_values=col_values,
            base_parameters=base_params,
            output_metric=output_metric,
            output_group_key=output_group_key,
            output_group_value=output_group_value,
            num_simulations=num_sims,
            seed=seed,
        )

        # Kick off all cell simulations in background (with thread_id for auto-results)
        asyncio.create_task(_run_matrix_background(matrix["id"], thread_id))

        # Build SSE payload
        matrix_payload = {
            "id": str(matrix["id"]),
            "name": name,
            "simulation_type": sim_type,
            "row_parameter": row_param,
            "col_parameter": col_param,
            "rows": len(row_values),
            "cols": len(col_values),
            "total_cells": len(row_values) * len(col_values),
        }
        return f"data: {json.dumps({'type': 'matrix_created', 'matrix': matrix_payload})}\n\n"

    except Exception:
        logger.warning("Failed to create matrix from stream", exc_info=True)
        return None


async def _run_matrix_background(matrix_id, thread_id=None):
    """Run all matrix cell simulations, poll until done, and save results to thread."""
    from server.services import matrix_service

    try:
        result = await matrix_service.run_matrix(matrix_id)
        logger.info("Background matrix run completed for %s: %s", matrix_id, result)
    except Exception:
        logger.warning("Background matrix run failed for %s", matrix_id, exc_info=True)
        return

    if not thread_id:
        return

    # Poll until all cells complete (check every 30s, up to 10 minutes)
    max_polls = 20
    for attempt in range(max_polls):
        await asyncio.sleep(30)
        try:
            matrix = await matrix_service.get_matrix(matrix_id)
            if not matrix:
                return

            incomplete = [
                c for c in matrix["cells"]
                if c["status"] in ("running", "queued", "pending")
            ]
            if not incomplete:
                break

            # Re-check incomplete cells
            await matrix_service.poll_status(matrix_id)

            logger.info(
                "Matrix %s poll %d/%d: %d incomplete cells remaining",
                matrix_id, attempt + 1, max_polls, len(incomplete),
            )
        except Exception:
            logger.warning("Matrix poll failed for %s", matrix_id, exc_info=True)

    # Fetch final state and save summary to thread
    try:
        matrix = await matrix_service.get_matrix(matrix_id)
        if not matrix:
            return

        summary = _format_matrix_results(matrix)
        if summary:
            await db.execute(
                """INSERT INTO thread_messages (thread_id, role, content)
                   VALUES ($1, 'assistant', $2)""",
                thread_id, summary,
            )
            await db.execute(
                "UPDATE agent_threads SET updated_at = NOW() WHERE id = $1",
                thread_id,
            )
            logger.info("Saved matrix results summary to thread %s", thread_id)
    except Exception:
        logger.warning("Failed to save matrix results to thread", exc_info=True)


def _format_matrix_results(matrix: dict) -> str | None:
    """Format a completed matrix as a markdown summary for chat."""
    cells = matrix.get("cells", [])
    completed = [c for c in cells if c["status"] == "completed" and c.get("result_mean") is not None]
    if not completed:
        failed = [c for c in cells if c["status"] == "failed"]
        running = [c for c in cells if c["status"] in ("running", "queued", "pending")]
        if failed:
            return f"**Matrix results update:** {len(failed)} of {len(cells)} cells failed. You may want to retry."
        if running:
            return None  # Still running, don't post yet
        return None

    row_vals = matrix["row_values"]
    col_vals = matrix["col_values"]
    row_param = matrix["row_parameter"]
    col_param = matrix["col_parameter"]
    metric = matrix["output_metric"]

    # Build cell lookup
    cell_map = {}
    for c in cells:
        cell_map[(c["row_value"], c["col_value"])] = c

    # Detect formatting
    def _fmt_param(param, val):
        if any(k in param for k in ("pct", "percent", "rate", "ratio", "fraction", "penetration")) and 0 < val <= 1:
            return f"{val * 100:.0f}%"
        if any(k in param for k in ("cost", "savings", "revenue", "charge")):
            if val >= 1e9:
                return f"${val / 1e9:.1f}B"
            if val >= 1e6:
                return f"${val / 1e6:.0f}M"
            if val >= 1e3:
                return f"${val / 1e3:.0f}K"
            return f"${val:,.0f}"
        if val >= 1e6:
            return f"{val / 1e6:.1f}M"
        if val >= 1e3:
            return f"{val / 1e3:.0f}K"
        return f"{val:g}"

    def _fmt_result(val):
        if val is None:
            return "---"
        is_ratio = any(k in metric for k in ("roi", "rate", "ratio", "pct"))
        if is_ratio:
            return f"{'+' if val >= 0 else ''}{val * 100:.1f}%"
        if abs(val) >= 1e9:
            return f"${val / 1e9:.2f}B"
        if abs(val) >= 1e6:
            return f"${val / 1e6:.1f}M"
        if abs(val) >= 1e3:
            return f"${val / 1e3:.0f}K"
        return f"{val:,.2f}"

    # Build markdown table
    header_label = row_param.replace("_", " ").title()
    lines = [f"**Matrix Results: {matrix['name']}**", ""]
    lines.append(f"Metric: **{metric.replace('_', ' ').title()}** | {len(completed)} of {len(cells)} cells completed")
    lines.append("")

    # Table header
    col_headers = [_fmt_param(col_param, cv) for cv in col_vals]
    lines.append(f"| {header_label} | " + " | ".join(col_headers) + " |")
    lines.append("|" + "---|" * (len(col_vals) + 1))

    # Table rows
    for rv in row_vals:
        row_label = _fmt_param(row_param, rv)
        cells_in_row = []
        for cv in col_vals:
            cell = cell_map.get((rv, cv))
            if cell and cell["status"] == "completed" and cell.get("result_mean") is not None:
                mean_str = _fmt_result(cell["result_mean"])
                p05 = cell.get("result_p05")
                p95 = cell.get("result_p95")
                if p05 is not None and p95 is not None:
                    cells_in_row.append(f"{mean_str} ({_fmt_result(p05)} to {_fmt_result(p95)})")
                else:
                    cells_in_row.append(mean_str)
            elif cell and cell["status"] == "failed":
                cells_in_row.append("FAILED")
            elif cell and cell["status"] in ("running", "queued", "pending"):
                cells_in_row.append("running...")
            else:
                cells_in_row.append("---")
        lines.append(f"| {row_label} | " + " | ".join(cells_in_row) + " |")

    # Key findings
    if completed:
        means = [(c["result_mean"], c["row_value"], c["col_value"]) for c in completed if c.get("result_mean") is not None]
        if means:
            best = max(means, key=lambda x: x[0])
            worst = min(means, key=lambda x: x[0])
            lines.append("")
            lines.append(f"**Best scenario:** {row_param}={_fmt_param(row_param, best[1])}, "
                         f"{col_param}={_fmt_param(col_param, best[2])} → {_fmt_result(best[0])}")
            lines.append(f"**Worst scenario:** {row_param}={_fmt_param(row_param, worst[1])}, "
                         f"{col_param}={_fmt_param(col_param, worst[2])} → {_fmt_result(worst[0])}")

    return "\n".join(lines)


async def _extract_matrices_from_text(
    text: str, thread_id: UUID, already_created: set[str],
) -> list[str]:
    """Text-based fallback: scan MAS response for validated matrix results."""
    sse_events: list[str] = []
    for match in re.finditer(r'\{[^{}]*"status"\s*:\s*"validated"[^{}]*\}', text):
        try:
            blob = json.loads(match.group())
        except json.JSONDecodeError:
            continue

        sim_type = blob.get("simulation_type", "")
        row_param = blob.get("row_parameter", "")
        col_param = blob.get("col_parameter", "")
        if not sim_type or not row_param or not col_param:
            continue

        row_values = blob.get("row_values", [])
        col_values = blob.get("col_values", [])
        if not row_values or not col_values:
            continue

        # Build args dict matching the tool_call format
        args = {
            "p_simulation_type": sim_type,
            "p_row_parameter": row_param,
            "p_row_values": json.dumps(row_values),
            "p_col_parameter": col_param,
            "p_col_values": json.dumps(col_values),
            "p_output_metric": blob.get("output_metric", ""),
            "p_base_parameters": json.dumps(blob.get("base_parameters", {})),
            "p_name": blob.get("name", ""),
            "p_num_simulations": blob.get("num_simulations", 10000),
            "p_seed": blob.get("seed", 42),
        }

        sse_event = await _handle_matrix_builder(thread_id, args, already_created)
        if sse_event:
            sse_events.append(sse_event)

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
