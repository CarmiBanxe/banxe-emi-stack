"""
Banking Engine (Banksy) — Sprint B-1 LangGraph Sandbox Scaffold.

SANDBOX ONLY: no banking tools wired, all external banking calls are mocked.
DO NOT use in production. No live PSD2 / Adorsys / MCP / ledger connections.

Execution host: evo1 (100.68.102.48).
Legion = thin-client only — does NOT execute this file (ADR-103 DLP boundary).
"""
from __future__ import annotations

import asyncio
import operator
import os
import sqlite3
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

# ---------------------------------------------------------------------------
# Configuration — environment variables only; never hardcoded (security-policy.md)
# ---------------------------------------------------------------------------

LITELLM_BASE_URL: str = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
LITELLM_MODEL: str = os.environ.get("LITELLM_MODEL", "banxe-general")

# Required; fails fast with KeyError if not set. Run:
#   export LITELLM_API_KEY="sk-banxe-llm-gateway-2026"
LITELLM_API_KEY: str = os.environ["LITELLM_API_KEY"]

# SANDBOX checkpointer: in-memory by default (state lost on restart).
# For durable sandbox: export BANKSY_CHECKPOINT_URI=banksy_sandbox.db
CHECKPOINT_URI: str = os.environ.get("BANKSY_CHECKPOINT_URI", ":memory:")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class BankingState(TypedDict):
    """Graph state. messages accumulates via operator.add (append-only per turn)."""

    messages: Annotated[list[BaseMessage], operator.add]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def banking_node(state: BankingState) -> dict[str, list[BaseMessage]]:
    """
    Single-node sandbox: forwards the message thread to banxe-general via LiteLLM :4000.

    SANDBOX — no banking tools injected. In Sprint B-2+ tools will be bound here
    via llm.bind_tools([payment_tool, ledger_tool, ...]).

    Autonomy: L2 (proposes reply; human approval required for L3+ actions).
    I-27: this node PROPOSES only — never auto-applies financial decisions.
    EU AI Act Art.14: human oversight at all L3+ decision points.
    """
    llm = ChatOpenAI(
        base_url=LITELLM_BASE_URL,
        api_key=LITELLM_API_KEY,
        model=LITELLM_MODEL,
        max_tokens=1024,
        temperature=0.6,
    )
    # SANDBOX: no tool binding. Extend in Sprint B-2 with llm.bind_tools([...]).
    response: AIMessage = await llm.ainvoke(state["messages"])
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def _build_checkpointer(uri: str) -> InMemorySaver | SqliteSaver:
    # SqliteSaver.from_conn_string() is a context manager, not a saver instance.
    # Construct saver directly to avoid passing a _GeneratorContextManager to compile().
    if uri == ":memory:":
        return InMemorySaver()
    conn = sqlite3.connect(uri, check_same_thread=False)
    return SqliteSaver(conn)


def build_graph(checkpoint_uri: str = CHECKPOINT_URI) -> StateGraph:
    """Build and compile the B-1 sandbox StateGraph with the appropriate checkpointer."""
    builder: StateGraph[BankingState] = StateGraph(BankingState)
    builder.add_node("banking_node", banking_node)
    builder.add_edge(START, "banking_node")
    builder.add_edge("banking_node", END)
    return builder.compile(checkpointer=_build_checkpointer(checkpoint_uri))


# ---------------------------------------------------------------------------
# Smoke-test entrypoint
# ---------------------------------------------------------------------------


async def _smoke_test() -> None:
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
    mode = "in-memory (state lost on restart)" if CHECKPOINT_URI == ":memory:" else f"sqlite-backed ({CHECKPOINT_URI})"
    print(f"Checkpoint: {mode} (thread_id=sandbox-test-1)")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
