"""Agent state definition for the LangGraph graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """State passed through the LangGraph graph.

    Extends MessagesState with additional fields for routing and context.
    """

    # Genie query result (populated by genie node)
    genie_result: dict[str, Any] | None = None

    # Simulation polling counter — prevents infinite check_simulation loops
    simulation_poll_count: int = 0
