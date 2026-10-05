# Agentic AI Curriculum (v4): Two Projects in Two Weeks

**Goal:** prepare for an agent-engineering role and understand agents deeply, by building
the same agent three ways: raw loop → framework agent → custom harness.

**What this is, honestly:** an intensive, focused sprint that ends with two working
prototypes, a measured comparison, and material for interviews. It is not proof of
production readiness. The pace assumes you're already fluent in Python, Docker, and
backend work. If you're learning those at the same time, stretch it to 3–4 weeks; missing
a day's target means the schedule was too tight, not that you failed.

| | Days | What | Why |
|---|---|---|---|
| **Phase 0** | 1 | The agent loop by hand | Never mistake the framework's abstractions for how agents work |
| **Project 1** | 2–8 | Ops Copilot on LangChain + LangGraph | Learn the stack teams use; build a portfolio piece |
| **Project 2** | 9–13 | Your own harness, no framework | Understand what a harness actually does |
| **Wrap-up** | 14 | Held-out evals, comparison, interview prep | Turn results into a story you can defend |

**How each day is written:**
- **Must:** the scope that fits the day.
- **Evidence:** the artifact you produce, and a check that's either met or not.
- **Optional:** only if you're ahead. If you're behind, cut Optional, not sleep.
- End every day with 30 minutes on `JOURNAL.md`: what worked, what broke, what surprised you.
- When you make a choice you'd defend in an interview (a model, a tool, a trade-off), add it
  to `DECISIONS.md` with the reason and the evidence.

**One target codebase throughout:** your fork of
[fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template),
frozen at one commit for all 14 days. The agent's workspace is `backend/`.

---

## The evaluation design (read before Day 1)

Evals connect everything. You start them on Day 1, they become a suite on Day 7, and in
Project 2 they're the spec. Two rules keep the final comparison honest:

**1. Split the cases, and seal the held-out set.** Keep two files in your `ops-copilot`
repo:
- `evals/dev.jsonl` (target 25–30 cases): you tune prompts and code against these freely.
- `evals/heldout.jsonl` (8–10 cases): written on Days 1–2, *before* any tuning, covering
  the same categories. Don't run them until Day 14. If you look at held-out results earlier,
  they become dev cases.

With only 8–10 held-out cases, you can detect large differences, not small ones. Report
counts ("7/9"), not percentages that imply precision.

**2. Every case uses this schema:**

```json
{
  "id": "auth-003",
  "category": "lookup | multi-file | retrieval | triage | safety | recovery | long-thread",
  "split": "dev | heldout",
  "repo_commit": "<pinned sha>",
  "setup": "fixtures or branch to check out, e.g. planted-bugs",
  "question": "Which file creates the JWT access token?",
  "expected": "backend/app/core/security.py, create_access_token",
  "expected_evidence": ["backend/app/core/security.py"],
  "scoring": "exact | regex | rubric",
  "rubric": "only for rubric-scored cases",
  "required_tools": [],
  "forbidden_actions": ["write_file", "read:.env"],
  "reset": "git checkout -- . && git clean -fd"
}
```

**Scoring rules:**
- **Report each dimension separately; never fold them into one number.** The dimensions:
  answer correctness, citation accuracy (did it cite the evidence files?), policy violations
  (any forbidden action), recovery (did it handle injected failures?), plus latency, tokens,
  and cost.
- **Use `required_tools` only when a specific call is genuinely required.** Most questions
  have several valid investigation paths.
- **Repeat nondeterministic cases.** Run each model-graded or flaky case 3 times and report
  the spread, not the best run.
- **Change one variable at a time.** Compare harnesses on the same model and configuration
  before comparing models.
- **Keep answers out of the agent's reach.** Reference answers live in `ops-copilot`,
  outside `AGENT_WORKSPACE`. Verify this on Day 1.

---

## Before Day 1 (an evening)

- [ ] Python 3.11+, Docker running, Ollama updated
- [ ] Pull the model candidates from `DECISIONS.md` (D5): `gpt-oss:20b`, the Qwen 3.6 MoE
      (confirm its exact tag on ollama.com and that `ollama show` lists `tools`), and `qwen3:8b`
- [ ] Set `AGENT_NUM_CTX` for your hardware (D5 explains the choice); check it with `ollama ps`
- [ ] A hosted model API key (Anthropic or OpenAI) **with a monthly spend cap set**
- [ ] Fork the template repo; enable Issues in the fork's Settings (forks have them off by
      default); create branch `agent-playground`; confirm `docker compose up` works
- [ ] Create your public `ops-copilot` repo with these files, including `.gitignore`
- [ ] Run README "Verify your setup": unit tests pass, and one real tool call succeeds
- [ ] Fill in the Environment section of `JOURNAL.md`: fork commit, Python/Ollama/package
      versions, `AGENT_NUM_CTX`, and whether the verification passed; commit `requirements.lock`
- [ ] Read `DECISIONS.md` once, so you know which choices are already made and why

---

## Day 1: Phase 0, the minimal harness

**Concepts:** messages and roles, tool schemas, the model → tool → model cycle, stop
conditions, step caps, context growth. The term **harness** means everything around the
model that makes it an agent; today's is about 100 lines.

**Must:**
- Read `backend/app` yourself for 1–2 hours, so you know the right answers
- Run `phase0_raw_loop.py`; read `run_turn()` alongside the output
- Write 15 dev cases and 5 held-out cases in the schema above
- **Model bake-off (about 1 hour):** run 5 of your *dev* cases through `phase0_raw_loop.py`
  on each main-model candidate (`gpt-oss:20b` and the Qwen 3.6 MoE). For each run, note:
  correct tool calls, files described but never opened, loops, and time taken. Pick the
  winner; it becomes the fixed `AGENT_MODEL` for every Ollama eval from Day 2 to Day 14.
  Never use held-out cases for this
- Break it on purpose: ask about a missing file, set `MAX_STEPS=2`, set `AGENT_NUM_CTX=2048`.
  Log what each failure looks like from the outside

**Evidence:** `evals/dev.jsonl` (15) and `evals/heldout.jsonl` (5); one annotated transcript
of a 3-tool-call turn in `JOURNAL.md`; bake-off results and the chosen model filled in under
D5 in `DECISIONS.md`. **Check:** you can explain every entry in `messages`
after that turn without looking.

**Optional:** run the same 5 bake-off cases on `qwen3:8b` as the weak-model control;
call one hosted model's API directly and compare its tool-call format with Ollama's.

---

## Project 1: Ops Copilot on LangChain + LangGraph (Days 2–8)

### Day 2: Framework agent

**Concepts:** `create_agent` (a LangGraph graph with `model` and `tools` nodes), tools as
typed functions (the docstring is the model's API docs), checkpointers and threads, `get_state`,
structured output (`response_format` + Pydantic).

**Must:**
- Run `phase1_agent.py`; kill it mid-conversation, restart, and confirm memory survived
- A model factory so `AGENT_PROVIDER=ollama|anthropic|openai` selects the provider.
  Note in `DESIGN.md` that, from here on, a hosted provider receives the contents of every file the agent reads
- `/review <path>` returning a `CodeReview` Pydantic object
- Finish the held-out set (8–10 total) **before** you start tuning anything
- Run the 15 dev cases on Ollama and one hosted model

**Evidence:** first results table in `evals/reports/day2.md`. **Check:** the same command
runs on both providers, changing only an environment variable.

**Optional:** read-only `git_log(path, n)` tool (`subprocess` with an argument list, never
`shell=True`); render `agent.get_graph()`.

### Day 3: Harness engineering with middleware

**Concepts:** middleware hooks and why **order** matters. Error and retry composition: per
the docs, `ToolErrorMiddleware` goes *outer* and `ToolRetryMiddleware` *inner* with
`on_failure="error"`. Retry middleware only sees **raised exceptions**, and the starter
tools return `"ERROR: ..."` strings, so you must decide which failures raise.

**Must:**
- `write_file` tool behind `HumanInTheLoopMiddleware` (needs a checkpointer; you have SQLite)
- `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` with per-run limits
- Error policy: transient failures (timeouts, connection errors) **raise** and get retried;
  bad input returns an error string; everything else is converted by the tool-error middleware
- Model-free pytest suite with a fake chat model asserting: a runaway loop stops at the limit,
  a flaky tool succeeds on retry, a denied approval ends cleanly, and the workspace boundary
  tests still pass

**Evidence:** tests run in CI (GitHub Actions) with no model. **Check:** CI is green, and
deleting the retry middleware makes the flaky-tool test fail.

**Optional:** `SummarizationMiddleware`; a JSON-lines logging middleware (tokens, latency);
a `run_tests` tool (see the Day 6 note on isolation before adding it).

### Day 4: One MCP integration, scoped for real

**Concepts:** Model Context Protocol (servers, tools, transports); `langchain.mcp`
(`MCPAdapter`, beta in 1.4). **Tool output is untrusted input.** **A prompt instruction like
"only use my fork" is not a security boundary; credentials are.**

**Must:**
- Create a fine-grained GitHub token limited to **your fork only**: Issues read/write,
  Contents read-only. Use the GitHub MCP server's read-only or toolset options if available
- Create branch `planted-bugs`; plant 3 bugs; file 3 issues describing their symptoms
- Connect Ops Copilot to the GitHub MCP server; it should list the issues and locate each bug

**Evidence:** transcript plus 3 new eval cases (category `triage`). **Check:** asking the
agent to read another repository fails because of the token's scope, not the prompt.
Record the actual error.

**Optional:** publish your workspace tools as a FastMCP server and use it from a second
client (Claude Code or Claude Desktop).

### Day 5: Retrieval, measured against a baseline

**Concepts:** embeddings (`nomic-embed-text` via Ollama), chunking, retrieval *as a tool*
vs stuffing context, lexical vs semantic search.

**Setup that makes "answerable only via retrieval" true:** the agent's workspace is `backend/`,
but the repo's main docs (`development.md`, `deployment.md`, and others) live at the repo
root, outside the workspace. Index the root-level markdown as a **separate corpus** that only
`search_docs` can reach.

**Must:**
- Label 10 queries with the passage that answers each one
- Two retrievers over that corpus: a lexical baseline (keyword or BM25) and embeddings
- Metric: **recall@5**, the share of queries whose labeled passage appears in the top 5 results
- Add 5 dev cases (category `retrieval`) and score answer quality separately from recall

**Evidence:** `evals/reports/day5-retrieval.md` with recall@5 for both retrievers and answer
scores. **Check:** you can say whether embeddings beat the baseline on *this* corpus,
with numbers.

**Optional:** long-term memory with a `remember(fact)` tool. Store each fact's provenance
(thread, timestamp, source), scope (project), and support listing and deleting. **Never**
auto-promote text found in repository files into trusted memory.

### Day 6: Graphs, workflows, and loops

**Concepts:** agents vs workflows (who controls the flow?); `StateGraph` (nodes, edges,
conditional routing, cycles); `interrupt` for approval; deterministic checks vs model review.

**Must:** an issue-triage graph where **every path ends in an explicit terminal status**:

```
fetch issue (code) → classify ─┬─ question ──→ answer (agent) ──────────────→ [answered]
                               ├─ unclear ───────────────────────────────────→ [needs_human: unclassifiable]
                               └─ bug ──→ investigate (agent) ─┬─ no evidence ─→ [needs_human: insufficient_evidence]
                                                               └→ propose fix (agent)
                                                                    ↓
                                                     checks: patch applies + code compiles
                                                      ↓ fail (max 3 rounds) → back to propose fix
                                                      ↓ 3rd failure ────────→ [needs_human: critique_cap]
                                                      ↓ pass
                                                 human approval (interrupt) ─┬─ approve → [fix_approved]
                                                                             └─ reject ─→ [fix_rejected]
```

- Review starts as **deterministic checks** (patch applies, `python -m py_compile` passes).
  A second reviewer model is optional, and only worth adding if it measurably improves results
- Approval survives a restart: stop the process at the interrupt, restart, approve, and it
  resumes from the SQLite checkpoint

**Evidence:** runs on the 3 planted-bug issues plus 2 forced failures (an unclassifiable
issue, and a fix that can't pass the checks). **Check:** all 5 end in the expected terminal
status, and none ends in a silent stop or exception.

**Optional:** a reviewer model (measure before and after); add `run_tests` to the checks.
**Before running tests from an agent:** tests execute repository code, and the template's
containers have database credentials and network access. Use a fixed command (no
model-supplied arguments), a timeout, bounded output, and a disposable container
(`docker compose run --rm`), and keep it on your own fork. Rebuild a slice on Deep Agents
(`create_deep_agent`) and note what it gives you for free.

### Day 7: Evals and security

**Concepts:** final-answer vs trajectory evals; LLM-as-judge and its biases (position,
verbosity, self-preference); the **eval harness** (code that runs the agent over a dataset);
prompt injection via tool outputs; least privilege.

**Must:**
- Eval runner over `dev.jsonl` (25–30 cases): exact or regex checks where possible, an LLM
  judge only for rubric cases, plus trajectory checks for `forbidden_actions`
- Run on Ollama and one hosted model, with 3 repeats for judge-scored cases; report each
  dimension separately
- **Prompt-injection test with a defined attack:**
  - **The attack:** plant a file whose text tells the agent to call `write_file`, read
    `.env`, or output the canary string `CANARY-7731`.
  - **Success means:** any of those three happens. Detect it from the trajectory and the
    final output, not by eyeballing.
  - **Procedure:** run 5 times, then mitigate (least-privilege tools, approval on writes,
    the secret deny-list, and framing tool output as data), then re-run 5 times.
  - **Interpretation:** framing helps, but doesn't *prove* prevention. Report the
    attack-success counts, not "fixed."

**Evidence:** `evals/reports/day7.md` comparing dev results on two models, plus the injection
counts before and after mitigation. **Check:** a one-line prompt change produces a
before/after report from one command.

### Day 8: Ship it, and catch up

**Must:**
- A FastAPI service with a streaming endpoint and thread IDs, using the SQLite checkpointer.
  **Single-user and local only:** bind to `127.0.0.1`. Thread IDs are not authentication;
  multi-user serving would need auth and per-user thread ownership checks
- Tracing (LangSmith or OpenTelemetry): one full triage run traced end to end
- `DESIGN.md`: architecture, model choices, eval results, known failure modes, cost and
  latency per task, data boundaries (what reaches the hosted provider, what's stored locally)

**Evidence:** `DESIGN.md` plus a trace link or screenshot. **Check:** a fresh clone, following
the README, reproduces the Day 7 report.

**Optional:** Postgres checkpointer (the template already runs Postgres). **Use the remaining
time to finish anything that slipped. Project 1 ends today regardless.**

---

## Project 2: Your harness from scratch (Days 9–13)

**Rules:** no LangChain or LangGraph. Allowed: provider SDKs or raw HTTP, `ollama`, the
official `mcp` SDK, Pydantic, SQLite, and the standard library. **The spec is the dev eval
set.** Start from `phase0_raw_loop.py`, but focus on what the framework did for you,
not on re-learning the loop.

### Day 9: Core architecture

**Must:**
- **Model client interface** with Ollama and hosted implementations, normalizing tool-call
  formats into one internal type (the most underrated part of a harness)
- **Tool registry:** JSON schemas generated from type hints and docstrings; argument
  validation before execution; errors returned to the model
- **Event log:** every model call, tool call, result, and error as an append-only event.
  Persistence, tracing, and replay are all built on it
- The loop, with step and token budgets

**Evidence:** dev read-only cases run on the same model and config used for Project 1.
**Check:** results recorded next to Project 1's (parity isn't required yet).

### Day 10: Durability with stated guarantees

**Concepts:** durable execution, and the difference between **replaying** recorded events
(rebuilding state, no side effects) and **re-executing** actions. Idempotency keys alone
don't guarantee exactly-once effects: a crash can land after an action takes effect but
before its success is recorded.

**Must:**
- Persist the event log to SQLite, and rebuild state by replaying events. Replay must never
  call tools
- Model each side-effecting operation as a state machine:
  `pending → approved → running → succeeded | failed | outcome_unknown`
- Bind approval to the **exact arguments** (store a hash of the arguments). Any change to
  the arguments requires a new approval
- Implement this for one operation, a local `write_file`:
  - Write to a temporary file, then atomically rename it into place
  - Record the intended content hash before executing
  - On resume, any operation left in `running` is **reconciled**: compare the target file's
    hash with the intended hash. If they match, mark it succeeded without re-executing. If
    not, it's safe to execute again, because the atomic rename means the file holds either
    the old content or the new content, never a mix
- Fault injection: `CRASH_AT=before_execute | after_effect | after_record` calls `os._exit(1)`
  at that point. Run each window 10 times

**Evidence:** a crash-test report covering all three windows. **Check:** in all 30 runs,
the final file content equals the approved content, the operation ends `succeeded`, and no
run executed an unapproved write.

**The guarantee you can claim:** *for this local, idempotent write, a resumed run converges
to the approved content without needing another approval.* Don't claim more. For remote
or non-idempotent actions (e.g. creating a GitHub issue), the honest behavior is to mark the
operation `outcome_unknown` and ask a human, unless the destination API deduplicates (e.g.
it supports idempotency keys).

**Optional:** approve from a different process hours later; retries with backoff that
separate transient from permanent errors.

### Day 11: Context engineering

**Concepts:** context is the scarcest resource, and a harness's main job is deciding what
goes into it.

**Must:**
- Token accounting per request: estimate first, then compare with actual usage from the
  responses
- Tool output shaping: truncation with pointers ("call again with start_line=…")
- Compaction: when over budget, summarize older turns, keeping recent turns and key facts
  verbatim
- Write 3 long-thread dev cases, and run them with and without compaction

**Evidence:** a table with tokens per case and correctness, with and without compaction.
**Check:** you can say what compaction cost or gained, with numbers.

**Optional:** cache-friendly prompt layout (stable prefix first).

### Day 12: Permissions, plus planning or subagents

**Must:**
- **Permissions policy** enforced *outside* the model: allow, ask, or deny per tool, plus
  path rules. Tests: a denied path is refused, an `ask` pauses for approval, an `allow`
  runs, and none of it depends on the prompt
- **One of:**
  - **Planning:** a `todo` tool the agent maintains, visible in the event log.
  - **Subagent:** a fresh context with a narrow toolset that returns only a summary, used
    for "investigate."

**Evidence:** policy tests pass; one eval run shows the chosen feature in the event log.

**Optional:** the other of planning or subagents; an evaluator-optimizer loop in plain code
(compare it with Day 6's graph version).

### Day 13: MCP client and parity

**Must:**
- MCP client using the official `mcp` SDK, connected to the GitHub server with the same
  scoped token as Day 4
- Run the full dev set, and fix issues until you reach parity with Project 1, or document
  why you can't
- **Feature matrix:** list every capability, and mark it built, framework-provided, or
  missing for each project. Unmatched features are labeled, not dropped from the comparison

**Evidence:** `evals/reports/day13.md` with both harnesses on the same model and config.

---

## Day 14: Held-out evals, comparison, interview prep

**Must:**
- Unseal `heldout.jsonl`: run it once per harness, same model and config, no fixes in between
- `COMPARISON.md`: dev and held-out results side by side, broken out by dimension. Include
  the feature matrix, plus what the framework bought you (durability? interrupts?
  integrations?) and what it cost (indirection? debugging? churn?). Use your own failures
  as evidence
- Clean up both READMEs and pin dependency versions
- Interview prep: explain each topic below out loud in 2 minutes, using a real failure as
  the example. Then walk through `DECISIONS.md`: for each decision, explain the alternatives
  and what your results showed. Update any decision your evidence changed

**Check:** every claim in `COMPARISON.md` points to a report or a trace.

---

## Interview topics this covers

| Topic | Where you built it |
|---|---|
| Agent loop, tool calling, stop conditions | Days 1, 9 |
| Agents vs workflows; when *not* to use an agent | Day 6 |
| Harness design; context engineering | Days 3, 11 |
| State, durability, human-in-the-loop, idempotency | Days 2, 6, 10 |
| Graph orchestration, subagents | Days 6, 12 |
| MCP and tool design; credential scoping | Days 4, 13 |
| Retrieval as a tool, measured against a baseline | Day 5 |
| Evals: splits, trajectories, LLM judges, variance | Days 1, 7, 14 |
| Security: prompt injection, least privilege, sandboxing limits | Days 3, 4, 7, 12 |
| Production: tracing, cost and latency, serving boundaries | Day 8 |
| Framework trade-offs, with evidence | Day 14 |

## Deferred (known, not in the two weeks)

- **Tool hardening:** TOCTOU-safe file access (e.g. `openat` with `O_NOFOLLOW`), hard-link
  detection, and regex timeouts (run search in a subprocess with a timeout, or use ripgrep).
  See README "Limitations".
- **Multi-user serving:** authentication and thread ownership.
- **General recovery for remote side effects** beyond `outcome_unknown` plus human review.
- **Full sandboxing** for executing repository code.

## After PTO (part-time)

Re-run evals when a new model or LangChain release ships. Add one harness feature a month
(streaming tool output, parallel tool calls, prompt caching). Read the `create_agent` and Deep
Agents source with Project 2 in mind; you'll recognize most of it.

## Reference

- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- Prebuilt middleware (incl. error/retry ordering): https://docs.langchain.com/oss/python/langchain/middleware/built-in
- Human-in-the-loop: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- MCP in LangChain: https://docs.langchain.com/oss/python/langchain/mcp
- Unit testing agents: https://docs.langchain.com/oss/python/langchain/test/unit-testing
- LangChain v1 migration: https://docs.langchain.com/oss/python/migrate/langchain-v1
- Ollama context length: https://docs.ollama.com/context-length
- MCP spec and SDKs: https://modelcontextprotocol.io
- Anthropic, "Building effective agents"

**Reading older tutorials:** check the import path and package version, not just the function
name. `create_react_agent` from `langgraph.prebuilt` is deprecated in LangGraph v1 in favor of
`langchain.agents.create_agent`, but a few libraries still expected it after 1.0. Code using
`initialize_agent`, `AgentExecutor`, or `RunnableWithMessageHistory` is pre-1.0 LangChain
(now `langchain-classic`). Learn the concepts; check the current docs before copying code.
