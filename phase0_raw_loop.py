"""
Phase 0: The agent loop, by hand. No framework.

An "agent" is a model calling tools in a loop until the task is done. That's it.
This file is the whole idea in ~100 lines so the framework never feels like magic:

    messages = [system, user]
    loop:
        response = model(messages, tools)
        if response has no tool calls: return response.text      # done
        for each tool call: run it, append result as a "tool" message
        (go around again; the model now sees the results)

Run:  python phase0_raw_loop.py
Env:  AGENT_MODEL (an Ollama model name, default qwen3:8b), AGENT_WORKSPACE (default: current dir),
      AGENT_NUM_CTX (default 16384)
"""

import os

import ollama

from workspace_tools import TOOLS, WORKSPACE

MODEL = os.environ.get("AGENT_MODEL", "qwen3:8b")
MAX_STEPS = 10  # hard cap: models can loop forever. Always bound your loops.

# Ollama's default context depends on available VRAM (4k below 24 GiB, per its docs),
# and prompts that exceed it are truncated without an error. Tool outputs fill context
# fast, so request a size explicitly. 16k is a memory-conscious teaching default;
# raise it if you have headroom. Check what was actually allocated with `ollama ps`.
NUM_CTX = int(os.environ.get("AGENT_NUM_CTX", "16384"))
MODEL_OPTIONS = {"temperature": 0, "num_ctx": NUM_CTX}

SYSTEM_PROMPT = f"""You are a code-exploration agent working inside a repository at {WORKSPACE}.
Use the tools to inspect real files before answering. Never guess file contents.
Prefer search_code to locate things, then read_file to confirm.
When you have enough information, answer concisely and cite file paths with line numbers."""

TOOL_REGISTRY = {fn.__name__: fn for fn in TOOLS}


def run_turn(messages: list, question: str) -> str:
    """One user turn = possibly many model calls + tool calls."""
    messages.append({"role": "user", "content": question})

    for step in range(1, MAX_STEPS + 1):
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            tools=TOOLS,  # the client converts these functions to JSON schemas
            options=MODEL_OPTIONS,
        )
        msg = response.message
        messages.append(msg)  # the model's turn, including any tool-call requests

        if not msg.tool_calls:
            return msg.content  # no tools requested -> this is the final answer

        for call in msg.tool_calls:
            name = call.function.name
            args = call.function.arguments or {}
            print(f"  [step {step}] -> {name}({args})")

            fn = TOOL_REGISTRY.get(name)
            if fn is None:
                result = f"ERROR: unknown tool '{name}'. Available: {list(TOOL_REGISTRY)}"
            else:
                try:
                    result = str(fn(**args))
                except TypeError as e:  # model sent wrong/missing arguments
                    result = f"ERROR: bad arguments for {name}: {e}"
                except Exception as e:  # a tool bug must not crash the whole loop
                    result = f"ERROR: {name} failed with {type(e).__name__}"

            print(f"             <- {len(result)} chars")
            # Feed the result back. The model will see it on the next iteration.
            messages.append({"role": "tool", "content": result, "tool_name": name})

    return f"Stopped after {MAX_STEPS} steps without a final answer."


def approx_tokens(messages: list) -> int:
    total = 0
    for m in messages:
        content = m["content"] if isinstance(m, dict) else (m.content or "")
        total += len(content)
    return total // 4  # rough heuristic, good enough to watch growth


def main():
    print(f"Phase 0 agent | model={MODEL} | num_ctx={NUM_CTX} | workspace={WORKSPACE}")
    print("Commands: /reset  /stats  /quit\n")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question == "/quit":
            break
        if question == "/reset":
            messages = messages[:1]
            print("(history cleared)\n")
            continue
        if question == "/stats":
            print(f"(messages={len(messages)}, ~tokens={approx_tokens(messages)})\n")
            continue

        try:
            answer = run_turn(messages, question)
        except ollama.ResponseError as e:
            print(f"Ollama error: {e}. Is the model pulled? Try: ollama pull {MODEL}\n")
            continue
        print(f"\nagent> {answer}\n")


if __name__ == "__main__":
    main()
