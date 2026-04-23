"""Thread service — CRUD + LangGraph agent integration for chat."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from uuid import UUID

from server import db

logger = logging.getLogger(__name__)


def _get_graph_and_config():
    """Lazy-initialize the LangGraph agent and its config."""
    import os

    from server.agent.config import AgentConfig, GenieConfig, ModelConfig
    from server.agent.genie import GenieClient
    from server.agent.graph import build_graph
    from server.agent.models import get_supervisor_model
    from server.config import get_settings

    settings = get_settings()

    model_config = ModelConfig(
        supervisor_endpoint=os.environ.get(
            "SUPERVISOR_ENDPOINT", "databricks-claude-opus-4-7"
        ),
        executor_endpoint=os.environ.get(
            "EXECUTOR_ENDPOINT", "databricks-claude-sonnet-4"
        ),
    )

    genie_config = GenieConfig(space_id=settings.genie_space_id)

    agent_config = AgentConfig(
        model=model_config,
        genie=genie_config,
        catalog=settings.uc_catalog,
        schema_name=settings.uc_schema,
    )

    supervisor_model = get_supervisor_model(model_config)

    # Build Genie client if configured
    genie_client = None
    if settings.genie_space_id:
        from databricks.sdk import WorkspaceClient

        if settings.is_databricks_app:
            w = WorkspaceClient()
        else:
            w = WorkspaceClient(profile=settings.databricks_profile)

        host = w.config.host or ""
        if host and not host.startswith("http"):
            host = f"https://{host}"
        genie_client = GenieClient(
            space_id=settings.genie_space_id,
            databricks_host=host,
            auth_headers=w.config.authenticate(),
            config=genie_config,
        )

    graph = build_graph(
        agent_config=agent_config,
        supervisor_model=supervisor_model,
        genie_client=genie_client,
    )

    configurable = {
        "agent_config": agent_config,
        "supervisor_model": supervisor_model,
        "genie_client": genie_client,
    }

    return graph, configurable


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
    """Send a user message, invoke LangGraph agent, return both messages."""
    from langchain_core.messages import HumanMessage

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

    # 3. Build LangGraph messages
    lc_messages = []
    for m in messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            from langchain_core.messages import AIMessage
            lc_messages.append(AIMessage(content=m["content"]))

    # 4. Invoke LangGraph
    try:
        graph, configurable = _get_graph_and_config()
        result = await graph.ainvoke(
            {"messages": lc_messages},
            config={"configurable": configurable, "recursion_limit": 25},
        )
        last_msg = result["messages"][-1]
        assistant_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    except Exception as e:
        logger.exception("LangGraph invocation failed")
        assistant_content = f"I encountered an error: {e}"

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
    """Send a user message, stream LangGraph response as SSE events.

    Translates LangGraph astream_events into the same SSE event types
    the frontend expects: delta, simulation_triggered, matrix_created, done.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from server.services.simulation_service import insert_submitted_placeholder
    from server.services import analysis_service

    # 0. Resolve analysis_id from thread
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

    # 2. Fetch full thread history
    messages = await db.fetch_all(
        "SELECT role, content FROM thread_messages WHERE thread_id = $1 ORDER BY created_at ASC",
        thread_id,
    )
    lc_messages = []
    for m in messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            lc_messages.append(AIMessage(content=m["content"]))

    # 3. Stream from LangGraph
    full_content = ""
    triggered_hashes: set[str] = set()
    created_matrix_ids: set[str] = set()
    current_model_run_id: str | None = None

    try:
        graph, configurable = _get_graph_and_config()

        _SENTINEL = object()
        queue: asyncio.Queue = asyncio.Queue()

        async def _consume_stream():
            try:
                async for event in graph.astream_events(
                    {"messages": lc_messages},
                    config={
                        "configurable": {
                            **configurable,
                            "analysis_id": str(analysis_id) if analysis_id else None,
                        },
                        "recursion_limit": 25,
                    },
                    version="v2",
                ):
                    await queue.put(event)
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(_SENTINEL)

        consumer_task = asyncio.create_task(_consume_stream())

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if item is _SENTINEL:
                    break
                if isinstance(item, Exception):
                    raise item

                event = item
                event_kind = event.get("event", "")

                # Stream text deltas from the supervisor model
                if event_kind == "on_chat_model_stream":
                    run_id = event.get("run_id", "")
                    # Insert newline separator between different model invocations
                    # so markdown headings from the second call render correctly
                    if run_id and run_id != current_model_run_id:
                        if current_model_run_id is not None and full_content:
                            separator = "\n\n"
                            full_content += separator
                            sep_payload = json.dumps({"type": "delta", "content": separator})
                            yield f"data: {sep_payload}\n\n"
                        current_model_run_id = run_id

                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        text = chunk.content
                        full_content += text
                        yield f"data: {json.dumps({'type': 'delta', 'content': text})}\n\n"

                # Stream progress events from long-running tools
                elif event_kind == "on_custom_event":
                    event_name = event.get("name", "")
                    if event_name == "simulation_progress":
                        msg = event.get("data", {}).get("message", "")
                        if msg:
                            full_content += msg
                            yield f"data: {json.dumps({'type': 'delta', 'content': msg})}\n\n"

                # Detect tool calls completing
                elif event_kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    output = event.get("data", {}).get("output", "")

                    if tool_name == "run_simulation":
                        try:
                            result = json.loads(output) if isinstance(output, str) else output
                            sim_type = result.get("simulation_type", "")
                            params = result.get("parameters", {})
                            if isinstance(params, str):
                                params = json.loads(params)
                            num_sims = int(result.get("num_simulations", 10000))
                            seed = int(result.get("seed", 42))

                            dedup_key = f"{sim_type}|{json.dumps(params, sort_keys=True)}|{seed}|{num_sims}"
                            if dedup_key not in triggered_hashes:
                                triggered_hashes.add(dedup_key)
                                placeholder = await insert_submitted_placeholder(
                                    sim_type, params, num_sims, seed,
                                )
                                if analysis_id and placeholder.get("run_id"):
                                    try:
                                        await analysis_service.link_simulation(
                                            analysis_id, placeholder["run_id"], "agent",
                                        )
                                    except Exception:
                                        logger.warning("Failed to link sim", exc_info=True)
                                yield f"data: {json.dumps({'type': 'simulation_triggered', 'simulation': placeholder})}\n\n"
                        except Exception:
                            logger.warning("Failed to process trigger result", exc_info=True)

                    elif tool_name == "create_matrix":
                        sse_event = await _handle_matrix_builder(
                            thread_id, output, created_matrix_ids,
                        )
                        if sse_event:
                            yield sse_event

        finally:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.exception("LangGraph streaming failed")
        full_content = f"I encountered an error: {e}"
        yield f"data: {json.dumps({'type': 'delta', 'content': full_content})}\n\n"

    if not full_content.strip():
        full_content = "No response from agent."
        yield f"data: {json.dumps({'type': 'delta', 'content': full_content})}\n\n"

    # 3b. Chart inference disabled — re-enable when chart rendering is stable
    # try:
    #     chart_payload = _infer_chart_from_markdown(full_content)
    #     if chart_payload:
    #         yield f"data: {json.dumps({'type': 'chart_data', 'chart': chart_payload}, default=str)}\n\n"
    # except Exception:
    #     logger.debug("Chart inference from markdown failed", exc_info=True)

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


async def _handle_matrix_builder(
    thread_id: UUID, output: str, created_matrix_ids: set[str],
) -> str | None:
    """Emit SSE event for a matrix created by the create_matrix tool.

    The tool now does the actual creation + run via matrix_service.
    This handler just emits the SSE event and starts background polling.
    """
    try:
        result = json.loads(output) if isinstance(output, str) else output
    except (json.JSONDecodeError, TypeError):
        return None

    if result.get("status") != "created":
        return None

    matrix_id = result.get("id")
    if not matrix_id or matrix_id in created_matrix_ids:
        return None
    created_matrix_ids.add(matrix_id)

    # Start background polling (matrix already created + running from the tool)
    asyncio.create_task(_poll_matrix_background(UUID(matrix_id), thread_id))

    matrix_payload = {
        "id": matrix_id,
        "name": result.get("name", ""),
        "simulation_type": result.get("simulation_type", ""),
        "row_parameter": result.get("row_parameter", ""),
        "col_parameter": result.get("col_parameter", ""),
        "rows": result.get("rows", 0),
        "cols": result.get("cols", 0),
        "total_cells": result.get("total_cells", 0),
        "auto_running": True,
    }
    return f"data: {json.dumps({'type': 'matrix_created', 'matrix': matrix_payload})}\n\n"


async def _poll_matrix_background(matrix_id, thread_id=None):
    """Poll matrix cell statuses until done, then save results to thread.

    The matrix has already been created and run_matrix() already called
    by the create_matrix tool. This function only polls for completion.
    """
    from server.services import matrix_service

    if not thread_id:
        return

    await asyncio.sleep(10)

    max_polls = 30
    retried = False
    for attempt in range(max_polls):
        await asyncio.sleep(30)
        try:
            matrix = await matrix_service.get_matrix(matrix_id)
            if not matrix:
                return

            cells = matrix["cells"]
            incomplete = [
                c for c in cells
                if c["status"] in ("running", "queued", "pending")
            ]
            failed = [c for c in cells if c["status"] == "failed"]

            if failed and not retried:
                retried = True
                logger.info(
                    "Matrix %s: %d failed cells — retrying",
                    matrix_id, len(failed),
                )
                try:
                    await matrix_service.run_matrix(matrix_id)
                except Exception:
                    logger.warning("Matrix retry failed for %s", matrix_id, exc_info=True)
                continue

            if not incomplete:
                break

            await matrix_service.poll_status(matrix_id)

            logger.info(
                "Matrix %s poll %d/%d: %d incomplete",
                matrix_id, attempt + 1, max_polls, len(incomplete),
            )
        except Exception:
            logger.warning("Matrix poll failed for %s", matrix_id, exc_info=True)

    # Save summary to thread
    try:
        matrix = await matrix_service.get_matrix(matrix_id)
        if not matrix:
            return

        summary = _format_matrix_results(matrix)
        if summary:
            await db.execute(
                """INSERT INTO thread_messages (thread_id, role, content, metadata)
                   VALUES ($1, 'assistant', $2, $3)""",
                thread_id, summary,
                json.dumps({"type": "matrix_results", "matrix_id": str(matrix_id)}),
            )
            await db.execute(
                "UPDATE agent_threads SET updated_at = NOW() WHERE id = $1",
                thread_id,
            )
    except Exception:
        logger.warning("Failed to save matrix results", exc_info=True)


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
            return None
        return None

    row_vals = matrix["row_values"]
    col_vals = matrix["col_values"]
    row_param = matrix["row_parameter"]
    col_param = matrix["col_parameter"]
    metric = matrix["output_metric"]

    cell_map = {}
    for c in cells:
        cell_map[(c["row_value"], c["col_value"])] = c

    def _fmt_param(param, val):
        if any(k in param for k in ("pct", "percent", "rate", "ratio", "fraction", "penetration")) and 0 < val <= 1:
            return f"{val * 100:.0f}%"
        if any(k in param for k in ("cost", "savings", "revenue", "charge", "margin")):
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

    header_label = row_param.replace("_", " ").title()
    lines = [f"**Matrix Results: {matrix['name']}**", ""]
    lines.append(f"Metric: **{metric.replace('_', ' ').title()}** | {len(completed)} of {len(cells)} cells completed")
    lines.append("")

    col_headers = [_fmt_param(col_param, cv) for cv in col_vals]
    lines.append(f"| {header_label} | " + " | ".join(col_headers) + " |")
    lines.append("|" + "---|" * (len(col_vals) + 1))

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


def _infer_chart_from_markdown(text: str) -> dict | None:
    """Parse a markdown table from the response and infer a chart."""
    lines = text.split("\n")
    table_lines: list[str] = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                in_table = True
                continue
            table_lines.append(stripped)
            in_table = True
        elif in_table:
            break

    if len(table_lines) < 3:
        return None

    header_cells = [c.strip() for c in table_lines[0].split("|")[1:-1]]

    rows: list[dict] = []
    for line in table_lines[1:]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) != len(header_cells):
            continue
        rows.append(dict(zip(header_cells, cells)))

    if len(rows) < 2:
        return None

    def _parse_number(s: str) -> float | None:
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s).strip()
        s = re.sub(r"^[$\u20ac\u00a3]", "", s)
        s = s.replace(",", "")
        if not s or s in ("\u2014", "---", "~", "N/A", "n/a") or "next" in s.lower():
            return None
        try:
            return float(s)
        except ValueError:
            return None

    label_col = None
    value_cols: list[str] = []

    for col in header_cells:
        if col.lower() in ("rank", "#", "no", "no.", "trend"):
            continue
        nums = [_parse_number(r.get(col, "")) for r in rows]
        valid_nums = [n for n in nums if n is not None]
        if len(valid_nums) >= len(rows) * 0.5:
            value_cols.append(col)
        elif label_col is None:
            label_col = col

    if not label_col or not value_cols:
        return None

    chart_rows: list[dict] = []
    for row in rows:
        label = row.get(label_col, "")
        label = re.sub(r"\*\*(.+?)\*\*", r"\1", label)
        label = re.sub(
            r"[\U0001f300-\U0001f9ff\u2b07\ufe0f\u2b06\ufe0f\U0001fa00-\U0001faff]+\s*",
            "", label,
        ).strip()
        if not label:
            continue
        d: dict = {label_col: label}
        has_value = False
        for vc in value_cols:
            num = _parse_number(row.get(vc, ""))
            if num is not None:
                d[vc] = num
                has_value = True
            else:
                d[vc] = 0
        if has_value:
            chart_rows.append(d)

    if len(chart_rows) < 2:
        return None

    time_keywords = ("month", "date", "year", "quarter", "week", "period", "time")
    is_time = any(kw in label_col.lower() for kw in time_keywords)
    chart_type = "line" if is_time else "bar"

    return {
        "chart_type": chart_type,
        "x_key": label_col,
        "y_keys": value_cols[:3],
        "data": chart_rows,
    }


def _msg_dict(row) -> dict:
    """Convert a DB row to a JSON-safe dict."""
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif isinstance(v, UUID):
            d[k] = str(v)
    return d
