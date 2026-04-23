"""Graph nodes — supervisor reasoning and tool execution."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from server.agent.config import AgentConfig
from server.agent.state import AgentState

logger = logging.getLogger(__name__)


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict:
    """Supervisor node — reasons about the query and decides next action.

    Uses the high-reasoning model (Opus) to analyze the user's request
    and either respond directly, call a tool, or route to Genie.
    """
    from server.agent.prompts import get_system_prompt
    from server.agent.tools import get_all_tools

    agent_config: AgentConfig = config["configurable"]["agent_config"]
    model = config["configurable"]["supervisor_model"]

    system_prompt = get_system_prompt(agent_config)
    tools = get_all_tools()

    # Bind tools to the model
    model_with_tools = model.bind_tools(tools)

    # Build messages: system + conversation history
    messages = [SystemMessage(content=system_prompt)] + list(state["messages"])

    # If we have a genie result, inject it
    if state.get("genie_result"):
        genie_data = state["genie_result"]
        genie_msg = f"Genie query result:\n{json.dumps(genie_data, indent=2, default=str)}"
        messages.append(HumanMessage(content=genie_msg))

    response = await model_with_tools.ainvoke(messages)
    return {"messages": [response], "genie_result": None}


_MAX_SIMULATION_POLLS = 5


async def tool_executor_node(state: AgentState, config: RunnableConfig) -> dict:
    """Execute tool calls from the supervisor's response."""
    from server.agent.tools import get_all_tools

    tools = get_all_tools()
    tool_map = {t.name: t for t in tools}

    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    tool_messages = []
    genie_result = None
    poll_count = state.get("simulation_poll_count", 0)

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if tool_name not in tool_map:
            tool_messages.append(
                ToolMessage(
                    content=f"Error: Unknown tool '{tool_name}'",
                    tool_call_id=tool_call["id"],
                )
            )
            continue

        # Enforce polling limit for check_simulation
        if tool_name == "check_simulation" and poll_count >= _MAX_SIMULATION_POLLS:
            tool_messages.append(
                ToolMessage(
                    content=json.dumps({
                        "status": "poll_limit_reached",
                        "message": (
                            "Polling limit reached. The simulation pipeline is still "
                            "processing. Tell the user the simulation is running and "
                            "they can ask again in a few minutes to check progress. "
                            "Do NOT call check_simulation again."
                        ),
                    }),
                    tool_call_id=tool_call["id"],
                )
            )
            continue

        try:
            result = await tool_map[tool_name].ainvoke(tool_args)

            # Track check_simulation polls for non-completed statuses
            if tool_name == "check_simulation":
                try:
                    parsed_check = json.loads(result)
                    if parsed_check.get("status") in ("submitted", "running", "not_found"):
                        poll_count += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check if this is a genie routing marker
            try:
                parsed = json.loads(result)
                if parsed.get("route") == "genie":
                    # Route to genie node — store the question
                    genie_result = {"question": parsed["question"], "pending": True}
                    result = json.dumps({
                        "status": "routing_to_genie",
                        "question": parsed["question"],
                    })
            except (json.JSONDecodeError, TypeError):
                pass

            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"],
                )
            )
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            tool_messages.append(
                ToolMessage(
                    content=f"Error executing {tool_name}: {e}",
                    tool_call_id=tool_call["id"],
                )
            )

    return {
        "messages": tool_messages,
        "genie_result": genie_result,
        "simulation_poll_count": poll_count,
    }


async def genie_node(state: AgentState, config: RunnableConfig) -> dict:
    """Query Genie Space for analytics data."""
    genie_result = state.get("genie_result")
    if not genie_result or not genie_result.get("pending"):
        return {"genie_result": None}

    question = genie_result["question"]
    genie_client = config["configurable"].get("genie_client")

    if not genie_client:
        return {
            "genie_result": {
                "status": "error",
                "answer": "Genie Space not configured.",
            },
        }

    result = await genie_client.ask(question)
    return {"genie_result": result}


def route_after_supervisor(state: AgentState) -> Literal["tool_executor", "genie", "__end__"]:
    """Route based on supervisor's response."""
    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage):
        return "__end__"

    if last_message.tool_calls:
        # Check if any tool call is a genie route
        for tc in last_message.tool_calls:
            if tc["name"] == "query_analytics":
                return "tool_executor"  # Execute tool first, which sets genie_result
        return "tool_executor"

    return "__end__"


def route_after_tools(state: AgentState) -> Literal["supervisor", "genie"]:
    """Route after tool execution — back to supervisor or to genie."""
    if state.get("genie_result") and state["genie_result"].get("pending"):
        return "genie"
    return "supervisor"


def route_after_genie(state: AgentState) -> Literal["supervisor"]:
    """After genie, always go back to supervisor to synthesize."""
    return "supervisor"
