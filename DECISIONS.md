# Decision Log

Why this project is built the way it is. Each entry records the decision, the reasoning,
the alternatives considered, and what would make me revisit it. Entries D1–D8 were made
while planning (October 3, 2026), before any code ran against a model. As results come in,
update entries with evidence instead of deleting them: "I believed X, measured Y, changed
to Z" is the most useful thing to say in an interview.

**Status key:** *Decided* (made, not yet tested) · *Pending* (needs a result) ·
*Confirmed* or *Revised* (evidence recorded).

---

## D1. Build the same agent three ways: raw loop → framework → custom harness

**Status:** Decided

**Decision:** Day 1 builds the agent loop by hand. Project 1 (Days 2–8) rebuilds it on
LangChain/LangGraph. Project 2 (Days 9–13) builds a harness from scratch, using Project 1's
eval set as its spec.

**Why:**
- **Framework first, because of the timeline.** The goal is an agent-engineering role soon.
  Teams commonly use LangGraph or something shaped like it, so fluency and a portfolio
  piece come first.
- **From scratch second, for depth.** The agent loop itself is about 100 lines. The hard
  parts of a harness are classic backend problems: persisting state, resuming after a
  crash, retries, approvals, permissions, and observability. Building them shows what a
  framework actually does for you.
- **Raw loop before everything,** so the framework's abstractions never get mistaken for
  how agents fundamentally work.
- **Same evals for both projects,** so the final comparison is measured, not anecdotal.
  "Here's what the framework bought me, with numbers" is a stronger interview story than
  two unrelated projects.

**Alternatives considered:**
- *From scratch first, framework second.* Better for pure understanding, but slower to
  produce something that matches what teams use.
- *Framework only.* Fast, but leaves the internals unexamined.
- *From scratch only.* Deep, but skips the vocabulary most teams share.

**Revisit if:** Project 1 overruns Day 8. Project 2 is the part most likely to be squeezed,
and it's the depth half of the goal.

---

## D2. LangChain 1.x + LangGraph as the framework

**Status:** Decided

**Decision:** Use `create_agent`, middleware, and LangGraph's `StateGraph` and checkpointers.

**Why:**
- LangChain 1.0 (October 2025) made `create_agent` the standard agent, built on the
  LangGraph runtime. Version 1.x promises long-term API stability.
- LangGraph's durable execution (checkpoints, interrupts for human approval, resuming
  after restarts) is genuinely useful, and is exactly what Project 2 has to rebuild.
- Middleware (call limits, retries, approvals, summarization) makes "harness engineering"
  concrete and testable.

**Risks and mitigations:**
- **Churn.** The pre-1.0 patterns from earlier in planning (`RunnableWithMessageHistory`,
  `AgentExecutor`) became legacy within a year. Mitigation: dependencies pinned with
  `requirements.lock`, and tutorials checked against the current docs before copying code.
- **Abstraction hides behavior.** Mitigation: Day 1's raw loop, plus reading framework
  source when something surprises you.

**Alternatives considered:** lighter libraries (e.g. Pydantic AI) and vendor SDKs (e.g.
Anthropic's Claude Agent SDK). Reasonable choices, but LangGraph has the widest team
adoption, which matters for the job-search goal.

---

## D3. Target codebase: a frozen fork of fastapi/full-stack-fastapi-template

**Status:** Decided

**Decision:** The agent works on `backend/` of a personal fork, frozen at one commit for
all 14 days. Planted bugs live on a separate `planted-bugs` branch.

**Why:**
- It looks like a real production service: FastAPI, SQLModel, Postgres, Docker, and tests.
- Scoping the workspace to `backend/` keeps it small enough for local models.
- A fork gives a GitHub repo you control, for issues and the MCP integration (Days 4 and 6).
- The repo's main docs live at the root, *outside* `backend/`. That makes Day 5's
  "answerable only via retrieval" literally true.
- **Freezing the commit** keeps eval answers valid. A score change then means the agent
  changed, not the code.

**Alternative considered:** `simonw/sqlite-utils` (pure Python, no infrastructure needed).
Rejected because Days 3 and 8 use the template's Docker and Postgres setup.

---

## D4. Local models for iteration, plus one hosted model as a reference

**Status:** Decided

**Decision:** Develop on Ollama. Add one hosted model (Anthropic or OpenAI, with a monthly
spend cap) on Day 2, and include it in eval runs.

**Why:**
- **Local is free and fast to iterate on,** and small models fail in instructive ways:
  looping, bad tool calls, describing files they never opened.
- **Production agent teams mostly use frontier models through an API.** Local-only results
  would make everything look worse than production, so the hosted model is the reference
  point.
- Comparing local vs. hosted on the same evals is itself a useful finding to present.

**Data boundary:** with Ollama, nothing leaves the machine. With a hosted model, every file
the agent reads is sent to the provider. That's acceptable here because the target is a
public open-source repo.

---

## D5. Main local model: chosen by a Day 1 bake-off, then fixed

**Status:** Pending (the bake-off runs on Day 1)

**Hardware:** Mac with 64 GB of unified memory. On Apple Silicon, the GPU shares that memory,
so the model, its context window, Docker, and everything else compete for the same 64 GB.

**Selection criteria, in order:**
1. **Tool calling.** A hard requirement: `ollama show <model>` must list `tools`.
2. **Memory fit, including context.** The model must stay at `100% GPU` in `ollama ps`
   with the chosen context, while Docker runs the template.
3. **Speed.** Eval sets get run many times. This is where mixture-of-experts (MoE) models
   help: a "35B-A3B" model has 35B total parameters but only about 3B active per token, so
   it needs memory like a big model but responds like a small one.
4. **Reasoning vs. non-reasoning.** Reasoning models think before acting. That's slower,
   but often produces better tool choices.
5. **Results on my own dev cases.** This criterion decides. Published rankings disagree
   with each other, and many are SEO content.

**Model roles:**

| Model | Role |
|---|---|
| Qwen 3.6 MoE (35B-A3B; confirm the exact tag on ollama.com) | Main-model candidate: built for agentic coding, recommended by OpenHands as a first local model on 64 GB Macs |
| `gpt-oss:20b` | Main-model candidate: reasoning model, different family, ~14 GB |
| **Bake-off winner** | Fixed `AGENT_MODEL` for every Ollama eval run, Days 2–14 |
| `qwen3:8b` | Weak-model control, for labeled comparison experiments that expose harness weaknesses |
| One hosted model | Reference comparison from Day 2 (see D4) |

**Considered and set aside:** Qwen3-Coder-Next. Its Q4 build is about 52 GB, which leaves
too little room on 64 GB for context, Docker, and the rest. `qwen3-coder:30b` is a
reasonable extra candidate if the first two disappoint.

**Context window:** `AGENT_NUM_CTX=65536`. Ollama's default depends on available VRAM, and
prompts beyond the context are truncated without an error. Ollama's docs recommend at least
64k for agent workloads, and 64 GB can afford it. The scripts default to 16k so they run
safely on smaller machines. Verify with `ollama ps`: `CONTEXT` should show 65536 and
`PROCESSOR` should show `100% GPU`. If it spills onto the CPU, drop to 32768.

**The rules:**
- The bake-off uses **dev cases only**, never the held-out set.
- After Day 1, the main model doesn't change. Other models appear only in clearly labeled
  comparison experiments. Change one variable at a time.

**Bake-off results** (fill in on Day 1; 5 dev cases per model):

| Model | Correct tool use | Described unopened files | Loops | Avg time per case | Notes |
|---|---|---|---|---|---|
| Qwen 3.6 MoE | /5 | | | | |
| `gpt-oss:20b` | /5 | | | | |
| `qwen3:8b` (optional control) | /5 | | | | |

**Chosen:** _____ **because:** _____

---

## D6. Evals: a sealed held-out set and separately reported dimensions

**Status:** Decided

**Decision:**
- Two files: `dev.jsonl` (25–30 cases, tuned against freely) and `heldout.jsonl`
  (8–10 cases, written before any tuning and not run until Day 14).
- Every case uses one schema (see `CURRICULUM.md`).
- These dimensions are reported separately: answer correctness, citation accuracy, policy
  violations, recovery, latency, tokens, and cost.

**Why:**
- If you tune against the cases you report, your scores overstate how well the agent
  generalizes. A sealed set is the honest check.
- A single combined score hides trade-offs. For example, a prompt change might raise
  accuracy while increasing policy violations.
- With 8–10 held-out cases, only large differences are detectable, so results are reported
  as counts ("7/9"), not percentages that imply precision.
- Nondeterministic cases run 3 times, and the spread is reported, not the best run.

**Alternative considered:** a single eval set. Simpler, but it can't distinguish real
improvement from overfitting to your own test questions.

---

## D7. Tool safety: read-only tools with path checks, and an honest description

**Status:** Confirmed by tests (17 passing, October 3)

**Decision:** The starter tools are read-only and enforce three things:
- **Containment:** every path, including each file search opens, is resolved with symlinks
  followed and must stay inside the workspace.
- **A secret-file deny-list:** `.git/` internals, `.env`, keys, and similar files are
  refused by name.
- **Bounded output.**

The README describes them as "not an OS-level sandbox."

**How this was decided:** an external review (`chat-gpt-analysis.md`) found that
`search_code` followed symlinks out of the workspace, even though `read_file` blocked them.
I reproduced the bug, fixed it, and added tests that fail against the old code. Testing
also found problems the review missed: a crash on broken symlinks, tools hanging forever on
named pipes, and a deny-list bypass through an innocently named link.

**Known limits, documented rather than fixed:**
- a file swapped for a symlink between the check and the open (TOCTOU)
- hard links to outside files
- regex patterns that run for a very long time

**Principles behind this:**
- Tools are an attack surface, so validate their inputs like a public API's.
- A prompt instruction is not a security boundary; credentials and enforcement code are.
  That's why Day 4 scopes the GitHub token to the fork instead of telling the agent to
  stay on it.
- Describe safety properties precisely; don't overclaim.

---

## D8. Durability claims are scoped to what's actually tested

**Status:** Decided (implemented on Day 10)

**Decision:** Project 2's durability guarantee is claimed for one operation only: a local,
idempotent `write_file`, proven by fault injection at three crash points with 10 runs each.
Remote or non-idempotent actions are marked `outcome_unknown` and escalated to a human.

**Why:** an earlier draft of the curriculum claimed that idempotency keys mean "a resumed
run never writes twice." That's wrong. A crash after the write takes effect but before its
success is recorded defeats any key stored only in the agent's own database. The honest
fix has four parts:
- an operation state machine
- approvals bound to a hash of the exact arguments
- atomic writes (temporary file, then rename)
- reconciliation on resume, by checking the actual file against the intended content

**The claim:** *for this local, idempotent write, a resumed run converges to the approved
content without needing another approval.* Nothing broader.

---

## Concepts clarified during planning

Short versions, to be able to explain each in under two minutes:

- **Agent vs. workflow.** A workflow is LLM calls arranged along a path your code defines;
  an agent is a loop where the model decides the next step at runtime. Most real systems
  are workflows with agents inside some steps, like the Day 6 triage graph. Rule of thumb:
  if you can draw the task as a flowchart, build a workflow.
- **Harness.** Everything around the model that makes it an agent: the loop, tools,
  context management, memory, permissions, approvals, and planning. Claude Code is an
  example of a well-built harness. LangChain's docs describe three layers: LangChain is the
  framework, LangGraph the runtime, and Deep Agents a harness.
- **Replay vs. re-execution.** Replaying recorded events rebuilds state without side
  effects; re-executing an action repeats its side effect. Durable systems need to know
  which one they're doing.
- **Eval harness.** The code that runs an agent over a dataset and scores it. Not to be
  confused with the agent harness above.
