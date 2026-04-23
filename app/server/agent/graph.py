"""StateGraph assembly — builds the LangGraph agent graph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from server.agent.config import AgentConfig
from server.agent.genie import GenieClient
from server.agent.nodes import (
    genie_node,
    route_after_genie,
    route_after_supervisor,
    route_after_tools,
    supervisor_node,
    tool_executor_node,
)
from server.agent.state import AgentState


def build_graph(
    agent_config: AgentConfig | None = None,
    supervisor_model=None,
    genie_client: GenieClient | None = None,
) -> StateGraph:
    """Build and compile the LangGraph agent.

    Parameters
    ----------
    agent_config : AgentConfig
        Agent configuration (models, genie, prompts).
    supervisor_model : ChatOpenAI
        The supervisor LLM (injected for testability).
    genie_client : GenieClient, optional
        Genie client for analytics queries.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph graph ready to invoke/stream.
    """
    cfg = agent_config or AgentConfig()

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("genie", genie_node)

    # Entry point
    graph.set_entry_point("supervisor")

    # Edges
    graph.add_conditional_edges("supervisor", route_after_supervisor)
    graph.add_conditional_edges("tool_executor", route_after_tools)
    graph.add_conditional_edges("genie", route_after_genie)

    # Compile with config
    compiled = graph.compile()
    return compiled
