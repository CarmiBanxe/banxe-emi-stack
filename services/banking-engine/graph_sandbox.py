"""
Banking Engine (Banksy) — Sprint B-1 LangGraph Sandbox Scaffold.

SANDBOX ONLY: no banking tools wired, all external calls are mocked.
DO NOT use in production. No live PSD2/Adorsys/MCP/ledger connections.

Execution host: evo1 (100.68.102.48).
Legion = thin-client only — does NOT execute this file (ADR-103).
"""
from __future__ import annotations

import asyncio
import operator
import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

# ---------------------------------------------------------------------------
# Configuration — environment only; never hardcoded (security-policy.md)
# ---------------------------------------------------------------------------

LITELLM_BASE_URL: str = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
LITELLM_MODEL: str = os.environ.get("LITELLM_MODEL", "banxe-general")

# LITELLM_API_KEY: required env var — no default, fail fast if missing.
# Set before running: export LITELLM_API_KEY="sk-banxe-llm-gateway-2026"
LITELLM_API_KEY: str = os.environ["LITELLM_API_KEY"]

# SANDBOX: in-memory SqliteSaver (:memory:) by default.
# For durable sandbox: export BANKSY_CHECKPOINT_URI=banksy_sandbox.db
CHECKPOINT_URI: str = os.environ.get("BANKSY_CHECKPOINT_URI", ":memory:")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class BankingState(TypedDict):
    """Graph state — message list accumulates via operator.add."""

    messages: Annotated[list[BaseMessage], operator.add]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def banking_node(state: BankingState) -> dict[str, list[BaseMessage]]:
    """
    Single-node sandbox: forwards message thread to banxe-general via LiteLLM :4000.

    SANDBOX — no banking tools injected. In Sprint B-2+ tools will be bound here.
    Autonomy level: L2 (proposes reply; HITL required for L3+ actions per EU AI Act Art.14).
    I-27: this node PROPOSES only, never auto-applies financial decisions.
    """
    llm = ChatOpenAI(
        base_url=LITELLM_BASE_URL,
        api_key=LITELLM_API_KEY,
        model=LITELLM_MODEL,
        max_tokens=1024,
        temperature=0.6,
    )
    # SANDBOX: no tool binding here. Extend in Sprint B-2 by calling llm.bind_tools([...]).
    response: AIMessage = await llm.ainvoke(state["messages"])
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(checkpoint_uri: str = CHECKPOINT_URI) -> StateGraph:
    """Build and compile the B-1 sandbox StateGraph with SqliteSaver checkpointer."""
    builder: StateGraph[BankingState] = StateGraph(BankingState)
    builder.add_node("banking_node", banking_node)
    builder.add_edge(START, "banking_node")
    builder.add_edge("banking_node", END)
    checkpointer = SqliteSaver.from_conn_string(checkpoint_uri)
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Smoke-test entrypoint
# ---------------------------------------------------------------------------


async def _smoke_test() -> None:
    """Run one round-trip through the sandbox graph and print the reply."""
    graph = build_graph()

    initial_state: BankingState = {
        "messages": [
            HumanMessage(
                content="Hello from Banking Engine sandbox B-1. What model are you?"
            )
        ]
    }
    config: dict[str, dict[str, str]] = {
        "configurable": {"thread_id": "sandbox-test-1"}
    }

    result: BankingState = await graph.ainvoke(initial_state, config=config)

    last_msg = result["messages"][-1]
    print(f"Reply: {last_msg.content}")
    print("Checkpoint: persisted (thread_id=sandbox-test-1)")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
