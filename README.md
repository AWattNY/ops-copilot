# Ops Copilot: learning agentic AI by building

Starting code for a 14-day curriculum (see `CURRICULUM.md`) that builds the same agent
three ways: a raw loop (Day 1), a LangChain/LangGraph agent (Project 1), and a harness
written from scratch (Project 2). This repo currently contains the **Day 1** and **Day 2**
starting points, plus the read-only tools both share.

**Status:** the tools and the Phase 0 loop logic are covered by model-free tests
(`python -m unittest`). The two agent scripts have not yet been run end to end against a
live Ollama model with the pinned versions; your setup verification below is the first
real run. Record the result.

## What's here

| File | Purpose |
|---|---|
| `workspace_tools.py` | Read-only tools (`list_dir`, `read_file`, `search_code`) with path checks, a secret-file deny-list, and bounded output. Shared by both scripts. |
| `phase0_raw_loop.py` | Day 1: the agent loop by hand on the Ollama client. In-memory history only. |
| `phase1_agent.py` | Day 2: the same agent on LangChain's `create_agent`, with SQLite-backed conversation memory. |
| `tests/` | Standard-library tests: tool boundaries, secret handling, and the Phase 0 loop with a scripted fake model. No model or extra packages needed. |
| `.gitignore` | Keeps virtualenvs, local databases, secrets, raw eval runs, and traces out of a public repo. |
| `CURRICULUM.md` | The 14-day plan, with a deliverable and acceptance check for each day. |
| `DECISIONS.md` | Why the project is built this way: framework, target repo, models, evals, safety. Each entry records the alternatives and what would make you revisit it. |
| `JOURNAL.md` | Your environment record and daily log. Starts as a template. |

## What the tools do and don't protect against

The tools are **read-only workspace tools with path checks and bounded output. They are
not an OS-level sandbox.** Specifically:

- **Containment.** Every path is resolved with symlinks followed and must stay inside
  `AGENT_WORKSPACE`. This applies to model-supplied paths and to every file `search_code`
  opens and every entry `list_dir` reports. Links pointing outside are skipped or refused;
  `list_dir` shows only a count of hidden entries, not their names or sizes.
- **Secret deny-list.** `.git/` internals and common secret files (`.env`, `.env.*`,
  `*.pem`, `*.key`, SSH keys, `.netrc`, `.pgpass`, `.npmrc`, `.pypirc`) are refused by
  name, including through links. `.env.example`-style files are allowed. This is a
  convenience: **secrets written into ordinary source files are still readable.**
- **Bounded work.** Results are truncated at 12,000 characters, files over 2 MB are
  skipped by search and refused by `read_file`, and FIFOs and devices are never opened.

**Known limitations** (not fixed; see "Deferred" in `CURRICULUM.md`):
- **Race conditions (TOCTOU).** A file swapped for a symlink between the check and the
  `open()` could still be read. Path checks alone can't close this if someone else can
  modify the workspace while the agent runs.
- **Hard links.** A hard link inside the workspace to an outside file looks like an
  ordinary inside file.
- **Slow regexes.** Python's `re` has no timeout, so a pathological pattern from the model
  (e.g. `(a+)+$`) can make `search_code` run for a very long time.
- **Hosted models see file contents.** With Ollama, everything stays on your machine.
  Once you add a hosted model (Day 2), every file the agent reads is sent to that
  provider. Point the agent only at code you're allowed to share. The curriculum's
  target, a public open-source repo, is fine.

## Setup

Prerequisites: Python 3.10+ (3.11+ recommended), Ollama, Git. Docker is needed from Day 3.

```bash
# Ollama: update if installed a while ago; older versions handle tool calls worse
brew upgrade ollama            # or reinstall from https://ollama.com/download
ollama pull qwen3:8b           # the scripts' default; runs on a 16 GB machine
ollama pull gpt-oss:20b        # stronger at agent tasks; needs roughly 16 GB+ of free memory
# Which model to use as your main one is decided by a short bake-off on Day 1.
# See DECISIONS.md (D5) for the candidates, the selection criteria, and the reasoning.

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Target repository

The curriculum uses a fork of
[fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template).
Pin it so your eval answers stay valid:

```bash
git clone https://github.com/<you>/full-stack-fastapi-template.git ~/code/fastapi-app
cd ~/code/fastapi-app && git checkout -b agent-playground
git rev-parse HEAD      # record this commit in JOURNAL.md; don't pull upstream for two weeks
export AGENT_WORKSPACE=~/code/fastapi-app/backend
```

### Configuration

| Variable | Default | Notes |
|---|---|---|
| `AGENT_WORKSPACE` | current directory | The only directory the tools can read. |
| `AGENT_MODEL` | `qwen3:8b` | An **Ollama** model name; any model whose `ollama show` output lists `tools` works. Both scripts always use Ollama; adding a hosted provider is a Day 2 exercise. |
| `AGENT_NUM_CTX` | `16384` | Context window requested from Ollama. See below. |
| `AGENT_DB` | `./agent_memory.db` | Phase 1 only. Relative to the directory you run from; the script prints the absolute path at startup. |

**About context length.** Ollama's default context depends on available VRAM: per
[its docs](https://docs.ollama.com/context-length), it's 4k below 24 GiB, 32k from 24 to 48 GiB,
and 256k at 48 GiB or more. Prompts larger than the context are truncated without an error,
and tool outputs fill context quickly. The scripts request 16k as a memory-conscious default.
Ollama's docs recommend at least 64k for agent workloads, so raise `AGENT_NUM_CTX` if your
machine has headroom; larger contexts cost memory. While the agent is running, `ollama ps`
shows the context actually allocated, and whether the model spilled onto CPU.

### Verify your setup (do this before Day 1)

```bash
python -m unittest                 # 17 tests, no model needed; all should pass
ollama run qwen3:8b "Say hi"       # model loads and answers
python phase0_raw_loop.py          # then ask: "List the files in the workspace root."
```

Success means you see a `-> list_dir(...)` line, then an answer that matches the real
directory. Then record your environment in `JOURNAL.md`, and lock dependencies:

```bash
python --version; ollama --version; git -C ~/code/fastapi-app rev-parse HEAD
pip freeze > requirements.lock
```

## Running

**Day 1: raw loop.** `python phase0_raw_loop.py`. Commands: `/stats` (message count and a
rough token estimate), `/reset`, `/quit`. History lives in memory and is lost on exit.
Each `->` line is a tool call the model requested; each `<-` line is the result fed back.

**Day 2: LangChain agent.** `python phase1_agent.py`. Commands: `/history` (everything
stored for the current thread), `/new`, `/thread <id>`, `/quit`.

Conversations persist in SQLite, keyed only by thread name. The default thread is named
after the workspace folder (e.g. `backend-default`), so pointing the agent at a different
repo starts a fresh thread instead of continuing an old one. Threads are not access
control: anyone who can open the database file can read every conversation, including
file contents the agent read.

## Troubleshooting

These are diagnostic starting points, not definitive causes. Check the evidence each one names.

| Symptom | Possible causes | What to check |
|---|---|---|
| Agent ignores tool results or loses the question mid-turn | Context truncation; weak model behavior; confusing tool output | `ollama ps` (allocated context); `/stats` or `/history` (how big is the conversation?); does it work right after `/reset`? |
| Reply contains JSON that looks like a tool call, but no tool runs | Model doesn't support tool calling well; Ollama version handles tools poorly; template issue | Try `qwen3:8b` or `gpt-oss:20b`; update Ollama; check that the `->` lines are missing |
| Agent describes files it never opened | Hallucination (common with small models) | Compare its answer with the `->` lines; add the question to your eval set |
| `ImportError` from `langchain.agents` | LangChain older than 1.0 installed | `pip show langchain`; `pip install -U -r requirements.txt` |
| `GraphRecursionError` (Phase 1) | The agent looped until the step cap stopped it | `/history` to see the loop; Day 3 adds proper call limits |
| `Ollama error: ... not found` | Model not pulled, or the name is misspelled | `ollama list` |
| Connection refused | Ollama not running | `curl http://localhost:11434/api/tags` should list your models |
