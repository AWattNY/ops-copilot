"""
Phase 1: The same agent, rebuilt on LangChain 1.x.

Compare this with phase0_raw_loop.py. create_agent replaces the hand-written loop:
it builds a LangGraph graph with a "model" node and a "tools" node and cycles between
them until the model stops requesting tools.

New concepts in this phase:
- create_agent: the standard agent factory (LangChain 1.x)
- Checkpointer: persists the full agent state per thread_id (here: SQLite on disk),
  so conversations survive restarts. This replaces the old RunnableWithMessageHistory.
- Threads: one thread_id = one conversation. Think "session id".
- stream_mode="updates": watch each graph step (model call, tool execution) live.
- get_state(): inspect exactly what the agent has in memory. Your main debugging tool.

Run:  python phase1_agent.py
Env:  AGENT_MODEL (Ollama model name, default qwen3:8b), AGENT_WORKSPACE (default: current dir),
      AGENT_NUM_CTX (default 16384), AGENT_DB (default ./agent_memory.db)
"""

import os
import sqlite3
import uuid

from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver

from workspace_tools import TOOLS, WORKSPACE

MODEL = os.environ.get("AGENT_MODEL", "qwen3:8b")  # Ollama model name; hosted providers are a Day 2 exercise
NUM_CTX = int(os.environ.get("AGENT_NUM_CTX", "16384"))  # see phase0_raw_loop.py for why
# Relative paths resolve against the directory you run from, so print the absolute path.
DB_PATH = os.path.abspath(os.environ.get("AGENT_DB", "agent_memory.db"))
# Threads are keyed by name only. Default to the workspace folder name so switching
# workspaces doesn't silently continue a conversation about a different repo.
DEFAULT_THREAD = f"{WORKSPACE.name}-default"

# Graph steps, not model calls: each model->tools round is ~2 steps.
# This is a crude cap; Phase 2 replaces it with call-limit middleware.
RECURSION_LIMIT = 25

SYSTEM_PROMPT = f"""You are Ops Copilot, a code-exploration agent working inside a repository at {WORKSPACE}.
Use the tools to inspect real files before answering. Never guess file contents.
Prefer search_code to locate things, then read_file to confirm.
When you have enough information, answer concisely and cite file paths with line numbers."""


def build_agent(checkpointer):
    model = ChatOllama(model=MODEL, temperature=0, num_ctx=NUM_CTX)
    return create_agent(
        model=model,
        tools=TOOLS,  # same plain functions as Phase 0
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


def run_turn(agent, question: str, thread_id: str) -> str | None:
    """Stream one turn, printing each graph step as it happens."""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    final_answer = None

    for update in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
        stream_mode="updates",
    ):
        for node, payload in update.items():
            if not isinstance(payload, dict):
                continue  # some nodes (e.g. middleware) emit no state change
            for msg in payload.get("messages", []):
                if node == "model":
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            print(f"  -> {tc['name']}({tc['args']})")
                    else:
                        final_answer = msg.text
                elif node == "tools":
                    print(f"     <- {msg.name}: {len(str(msg.content))} chars")
    return final_answer


def show_history(agent, thread_id: str):
    """Dump what's actually stored for this thread. Do this often while learning."""
    state = agent.get_state({"configurable": {"thread_id": thread_id}})
    messages = state.values.get("messages", [])
    print(f"\n--- thread {thread_id}: {len(messages)} messages ---")
    for m in messages:
        kind = m.type  # human / ai / tool
        if kind == "ai" and m.tool_calls:
            summary = "tool calls: " + ", ".join(tc["name"] for tc in m.tool_calls)
        else:
            summary = str(m.content).replace("\n", " ")[:100]
        print(f"  [{kind:>5}] {summary}")
    print()


def main():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    agent = build_agent(SqliteSaver(conn))
    thread_id = DEFAULT_THREAD

    print(f"Phase 1 agent | model={MODEL} | workspace={WORKSPACE} | memory={DB_PATH}")
    print("Commands: /new  /thread <id>  /history  /quit\n")

    while True:
        try:
            question = input(f"[{thread_id}] you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question == "/quit":
            break
        if question == "/new":
            thread_id = uuid.uuid4().hex[:8]
            print(f"(new thread {thread_id})\n")
            continue
        if question.startswith("/thread "):
            thread_id = question.split(maxsplit=1)[1]
            print(f"(switched to thread {thread_id})\n")
            continue
        if question == "/history":
            show_history(agent, thread_id)
            continue

        try:
            answer = run_turn(agent, question, thread_id)
        except Exception as e:  # Phase 2 replaces this with real error handling
            print(f"Error: {type(e).__name__}: {e}\n")
            continue
        print(f"\nagent> {answer or '(no final answer; check /history)'}\n")

    conn.close()


if __name__ == "__main__":
    main()
